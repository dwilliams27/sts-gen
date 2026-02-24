"""ActionNode interpreter -- bridge between IR content definitions and simulation mechanics.

Reads ActionNode trees from the IR and dispatches to the mechanics functions
at runtime.  This is what makes custom cards "just work": they compose the
same primitives (deal_damage, gain_block, apply_status, ...) as every
built-in card.

Usage::

    from sts_gen.sim.interpreter import ActionInterpreter

    interp = ActionInterpreter(card_registry=my_card_defs)
    interp.play_card(card_def, battle, card_instance, chosen_target=0)

    # Or execute raw action nodes directly:
    interp.execute_actions(action_list, battle, source="player", chosen_target=0)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import CardDefinition, CardTarget
from sts_gen.sim.core.game_state import BattleState, CardInstance
from sts_gen.sim.core.entities import Player, Enemy
from sts_gen.sim.mechanics.damage import deal_damage
from sts_gen.sim.mechanics.block import gain_block
from sts_gen.sim.mechanics.energy import gain_energy, spend_energy
from sts_gen.sim.mechanics.card_piles import (
    draw_cards,
    discard_card,
    exhaust_card,
    add_to_draw_pile,
    shuffle_draw_pile,
)
from sts_gen.sim.mechanics.status_effects import apply_status, remove_status, has_status, get_status_stacks
from sts_gen.sim.mechanics.targeting import resolve_targets

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ActionInterpreter:
    """Walks an ActionNode tree and dispatches each node to the corresponding
    mechanics function.

    The interpreter is stateless between calls -- all mutable state lives in
    the ``BattleState`` that is threaded through every execution.

    Parameters
    ----------
    card_registry:
        Maps ``card_id`` to ``CardDefinition`` so the interpreter can look up
        card data when it needs to create new card instances
        (``ADD_CARD_TO_PILE``) or resolve card properties during play.
    """

    def __init__(self, card_registry: dict[str, CardDefinition] | None = None) -> None:
        self._card_registry: dict[str, CardDefinition] = card_registry or {}
        # X-cost context: when an X-cost card is played, this is set to the
        # amount of energy spent, so child actions can read it as their value.
        self._x_cost_value: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_actions(
        self,
        actions: list[ActionNode],
        battle: BattleState,
        source: str = "player",
        chosen_target: int | None = None,
    ) -> None:
        """Execute a list of action nodes in sequence.

        Stops early if the battle ends mid-sequence (e.g. the target dies
        to damage and there are no living enemies left).

        Parameters
        ----------
        actions:
            Ordered list of ``ActionNode`` objects to execute.
        battle:
            The current combat state (mutated in-place).
        source:
            Who is performing the actions -- ``"player"`` or an enemy index.
        chosen_target:
            The enemy index the player targeted (for single-target cards).
        """
        for node in actions:
            if battle.is_over:
                break
            self.execute_node(node, battle, source=source, chosen_target=chosen_target)

    def execute_node(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str = "player",
        chosen_target: int | None = None,
    ) -> None:
        """Execute a single action node, dispatching by ``action_type``.

        Parameters
        ----------
        node:
            The ``ActionNode`` to execute.
        battle:
            The current combat state (mutated in-place).
        source:
            ``"player"`` or an enemy index.
        chosen_target:
            The enemy index the player targeted (for single-target cards).
        """
        if battle.is_over:
            return

        handler = _DISPATCH.get(node.action_type)
        if handler is None:
            logger.warning("No handler for action type %s", node.action_type)
            return
        handler(self, node, battle, source, chosen_target)

    def play_card(
        self,
        card_def: CardDefinition,
        battle: BattleState,
        card_instance: CardInstance,
        chosen_target: int | None = None,
        force_exhaust: bool = False,
    ) -> None:
        """Play a card: spend energy, execute its actions, then dispose of it.

        Steps:
            1. Determine the effective energy cost (respecting cost overrides).
            2. Determine the correct action list (base or upgraded).
            3. Spend energy (X-cost cards spend all remaining energy).
            4. Execute the action list.
            5. Exhaust or discard the card.

        Parameters
        ----------
        card_def:
            The IR ``CardDefinition`` for the card being played.
        battle:
            The current combat state.
        card_instance:
            The physical ``CardInstance`` being played from the hand.
        chosen_target:
            Enemy index for single-target cards, or ``None``.
        """
        # 1. Determine effective cost
        if card_instance.cost_override is not None:
            cost = card_instance.cost_override
        else:
            # Use upgraded cost if the card is upgraded and an upgrade cost is defined
            if (
                card_instance.upgraded
                and card_def.upgrade is not None
                and card_def.upgrade.cost is not None
            ):
                cost = card_def.upgrade.cost
            else:
                cost = card_def.cost

        # 2. Determine action list (upgraded actions override base)
        if (
            card_instance.upgraded
            and card_def.upgrade is not None
            and card_def.upgrade.actions is not None
        ):
            actions = card_def.upgrade.actions
        else:
            actions = card_def.actions

        # 3. Spend energy
        if cost == -1:
            # X-cost card: spend all remaining energy, record for child nodes
            self._x_cost_value = battle.player.energy
            battle.player.energy = 0
        elif cost >= 0:
            if not spend_energy(battle.player, cost):
                logger.warning(
                    "Not enough energy to play %s (cost=%d, energy=%d)",
                    card_def.id,
                    cost,
                    battle.player.energy,
                )
                return
        # cost < -1 (e.g. -2 = unplayable) should never reach here, but
        # if it does we skip the energy step entirely.

        # 4. Execute actions
        self.execute_actions(actions, battle, source="player", chosen_target=chosen_target)

        # 5. Dispose of the card
        # The card may have already been moved from hand by its own actions
        # (e.g. Fiend Fire's exhaust-all). Only dispose if still in hand.
        still_in_hand = any(
            c.id == card_instance.id for c in battle.card_piles.hand
        )
        if still_in_hand:
            effective_exhaust = card_def.exhaust
            if (
                card_instance.upgraded
                and card_def.upgrade is not None
                and card_def.upgrade.exhaust is not None
            ):
                effective_exhaust = card_def.upgrade.exhaust

            if force_exhaust or effective_exhaust or "exhaust" in card_def.keywords:
                exhaust_card(battle, card_instance)
            else:
                discard_card(battle, card_instance)

        # Reset X-cost context
        self._x_cost_value = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_source_entity(self, battle: BattleState, source: str) -> Player | Enemy:
        """Return the entity performing the action."""
        if source == "player":
            return battle.player
        # source is an enemy index (as string or int)
        idx = int(source)
        return battle.enemies[idx]

    def _effective_value(self, node: ActionNode) -> int:
        """Return the effective numeric value for a node.

        If the node has an explicit value, use it.  If it is 0 or None and
        we have an X-cost context, substitute the X-cost value.
        """
        if node.value is not None and node.value != 0:
            return node.value
        if self._x_cost_value > 0:
            return self._x_cost_value
        return node.value if node.value is not None else 0

    # ------------------------------------------------------------------
    # Action handlers (one per ActionType)
    # ------------------------------------------------------------------

    def _handle_deal_damage(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        target_spec = node.target or "default"
        targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
        base_damage = self._effective_value(node)
        hits = node.times if node.times and node.times > 0 else 1

        # Handle special conditions on damage nodes
        condition = node.condition or ""

        # no_strength: deal raw damage without strength modifier (Combust, Fire Breathing, etc.)
        if condition == "no_strength":
            from sts_gen.sim.mechanics.damage import _resolve_entity
            # Handle numeric string targets (e.g. "0" for enemy index from Flame Barrier)
            if not targets and target_spec not in ("self", "none"):
                try:
                    idx = int(target_spec)
                    if 0 <= idx < len(battle.enemies) and not battle.enemies[idx].is_dead:
                        targets = [idx]
                except (ValueError, IndexError):
                    pass
            for target_idx in targets:
                if battle.is_over:
                    break
                target_entity = _resolve_entity(battle, target_idx)
                if target_entity.is_dead:
                    continue
                target_entity.take_damage(base_damage)
            return

        if condition == "use_block_as_damage":
            # Body Slam: use current block as base damage
            source_entity = self._resolve_source_entity(battle, source)
            base_damage = source_entity.block
        elif condition.startswith("strength_multiplier_"):
            # Heavy Blade: strength applies N times instead of once
            try:
                multiplier = int(condition.rsplit("_", 1)[1])
            except (ValueError, IndexError):
                multiplier = 1
            source_entity = self._resolve_source_entity(battle, source)
            strength = get_status_stacks(source_entity, "strength")
            # calculate_damage adds 1× strength; add the extra (N-1)× here
            base_damage += (multiplier - 1) * strength
        elif condition.startswith("plus_per_strike_"):
            # Perfected Strike: +N damage per Strike card in deck
            try:
                bonus_per = int(condition.rsplit("_", 1)[1])
            except (ValueError, IndexError):
                bonus_per = 0
            strike_count = self._count_strikes_in_deck(battle)
            base_damage += bonus_per * strike_count
        elif condition.startswith("plus_per_exhaust_"):
            # +N damage per card in exhaust pile
            try:
                bonus_per = int(condition.rsplit("_", 1)[1])
            except (ValueError, IndexError):
                bonus_per = 0
            exhaust_count = len(battle.card_piles.exhaust)
            base_damage += bonus_per * exhaust_count
        elif condition == "times_from_x_cost":
            # Use X-cost value as hit count (Whirlwind)
            hits = self._x_cost_value

        source_idx: int | str = source
        for target_idx in targets:
            if battle.is_over:
                break
            deal_damage(battle, source_idx, target_idx, base_damage, hits=hits)

    def _handle_gain_block(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        amount = self._effective_value(node)
        target_spec = node.target or "self"
        condition = node.condition or ""

        # raw: bypass dex/frail modifiers (Rage)
        if condition == "raw":
            if target_spec in ("self", "default"):
                source_entity = self._resolve_source_entity(battle, source)
                source_entity.block += max(0, amount)
            else:
                targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
                for idx in targets:
                    battle.enemies[idx].block += max(0, amount)
            return

        if target_spec in ("self", "default"):
            source_entity = self._resolve_source_entity(battle, source)
            gain_block(source_entity, amount)
        else:
            # Targeting enemies (unusual but possible -- e.g. giving block to an ally)
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            for idx in targets:
                gain_block(battle.enemies[idx], amount)

    def _handle_apply_status(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        status_id = node.status_name
        if status_id is None:
            logger.warning("APPLY_STATUS node missing status_name")
            return
        stacks = self._effective_value(node)
        target_spec = node.target or "default"

        if target_spec == "self":
            source_entity = self._resolve_source_entity(battle, source)
            apply_status(source_entity, status_id, stacks)
        else:
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            if targets:
                for idx in targets:
                    apply_status(battle.enemies[idx], stacks=stacks, status_id=status_id)
            else:
                # No enemy targets resolved (e.g. target_spec was "none") --
                # fall back to applying on source.
                source_entity = self._resolve_source_entity(battle, source)
                apply_status(source_entity, status_id, stacks)

    def _handle_remove_status(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        status_id = node.status_name
        if status_id is None:
            logger.warning("REMOVE_STATUS node missing status_name")
            return
        target_spec = node.target or "self"

        if target_spec == "self":
            source_entity = self._resolve_source_entity(battle, source)
            remove_status(source_entity, status_id)
        else:
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            for idx in targets:
                remove_status(battle.enemies[idx], status_id)

    def _handle_draw_cards(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        n = self._effective_value(node)
        if n > 0:
            draw_cards(battle, n)

    def _handle_discard_cards(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        # Full implementation would require card-selection UI.
        # For headless simulation: discard random cards from hand.
        n = self._effective_value(node)
        hand = battle.card_piles.hand
        for _ in range(min(n, len(hand))):
            if not hand:
                break
            # Pick the last card in hand (deterministic for reproducibility).
            card = hand[-1]
            discard_card(battle, card)

    def _handle_exhaust_cards(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        # Same limitation as discard: exhaust random cards from hand.
        n = self._effective_value(node)
        hand = battle.card_piles.hand
        condition = node.condition or ""

        if n == -1 and condition == "non_attack":
            # Sever Soul: exhaust all non-Attack cards from hand
            from sts_gen.ir.cards import CardType
            to_exhaust = [
                c for c in list(hand)
                if (cd := self._card_registry.get(c.card_id)) is not None
                and cd.type != CardType.ATTACK
            ]
            for card in to_exhaust:
                if card in hand:
                    exhaust_card(battle, card)
            return

        if n == -1:
            # Exhaust entire hand (Fiend Fire)
            n = len(hand)
        for _ in range(min(n, len(hand))):
            if not hand:
                break
            card = hand[-1]
            exhaust_card(battle, card)

    def _handle_gain_energy(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        amount = self._effective_value(node)
        gain_energy(battle.player, amount)

    def _handle_lose_energy(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        amount = self._effective_value(node)
        battle.player.energy = max(0, battle.player.energy - amount)

    def _handle_heal(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        amount = self._effective_value(node)
        target_spec = node.target or "self"

        if target_spec in ("self", "default"):
            source_entity = self._resolve_source_entity(battle, source)
            source_entity.heal(amount)
        else:
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            for idx in targets:
                battle.enemies[idx].heal(amount)

    def _handle_lose_hp(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Direct HP loss -- bypasses block."""
        amount = self._effective_value(node)
        target_spec = node.target or "self"

        if target_spec in ("self", "default"):
            source_entity = self._resolve_source_entity(battle, source)
            source_entity.current_hp = max(0, source_entity.current_hp - amount)
        else:
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            for idx in targets:
                enemy = battle.enemies[idx]
                enemy.current_hp = max(0, enemy.current_hp - amount)

    def _handle_add_card_to_pile(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        card_id = node.card_id
        if card_id is None:
            logger.warning("ADD_CARD_TO_PILE node missing card_id")
            return

        new_card = CardInstance(card_id=card_id)
        pile = (node.pile or "discard").lower()

        if pile == "draw":
            add_to_draw_pile(battle, new_card, position="random")
        elif pile == "discard":
            battle.card_piles.discard.append(new_card)
        elif pile == "hand":
            battle.card_piles.add_to_hand(new_card)
        elif pile == "exhaust":
            battle.card_piles.exhaust.append(new_card)
        else:
            logger.warning("Unknown pile %r in ADD_CARD_TO_PILE, defaulting to discard", pile)
            battle.card_piles.discard.append(new_card)

    def _handle_shuffle_into_draw(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        shuffle_draw_pile(battle)

    def _handle_gain_gold(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        amount = self._effective_value(node)
        battle.player.gold += amount

    def _handle_gain_strength(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        stacks = self._effective_value(node)
        target_spec = node.target or "self"

        if target_spec in ("self", "default"):
            source_entity = self._resolve_source_entity(battle, source)
            apply_status(source_entity, "strength", stacks)
        else:
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            for idx in targets:
                apply_status(battle.enemies[idx], "strength", stacks)

    def _handle_gain_dexterity(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        stacks = self._effective_value(node)
        target_spec = node.target or "self"

        if target_spec in ("self", "default"):
            source_entity = self._resolve_source_entity(battle, source)
            apply_status(source_entity, "dexterity", stacks)
        else:
            targets = resolve_targets(battle, source, target_spec, chosen_target=chosen_target)
            for idx in targets:
                apply_status(battle.enemies[idx], "dexterity", stacks)

    def _handle_conditional(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Evaluate a simple condition string; execute children if true.

        Supported condition formats:
            - ``"has_status:<status_id>"`` -- source entity has the status
            - ``"target_has_status:<status_id>"`` -- chosen target has the status
            - ``"hp_below:<percentage>"`` -- source entity HP is below percentage
            - ``"hp_above:<percentage>"`` -- source entity HP is above percentage
            - ``"no_block"`` -- source entity has zero block
            - ``"hand_empty"`` -- no cards in hand
            - ``"hand_size_gte:<n>"`` -- hand size >= n
        """
        if not node.condition:
            logger.warning("CONDITIONAL node missing condition string")
            return

        condition_met = self._evaluate_condition(node.condition, battle, source, chosen_target)

        if condition_met and node.children:
            self.execute_actions(node.children, battle, source=source, chosen_target=chosen_target)

    def _handle_for_each(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Execute children once per matching item.

        The ``condition`` field determines *what* to iterate over:
            - ``"enemy"`` -- once per living enemy (chosen_target is set to
              each enemy index in turn)
            - ``"card_in_hand"`` -- once per card currently in hand
            - ``"status_on_self"`` -- once per unique status on the source entity
            - ``"exhaust_count"`` -- once per card in the exhaust pile
        """
        if not node.children:
            return

        iterator = (node.condition or "").lower().strip()

        if iterator == "enemy":
            for idx, enemy in enumerate(battle.enemies):
                if battle.is_over:
                    break
                if not enemy.is_dead:
                    self.execute_actions(
                        node.children, battle, source=source, chosen_target=idx,
                    )

        elif iterator == "card_in_hand":
            # Snapshot hand size so mutations during iteration don't cause issues
            hand_count = len(battle.card_piles.hand)
            for _ in range(hand_count):
                if battle.is_over:
                    break
                self.execute_actions(
                    node.children, battle, source=source, chosen_target=chosen_target,
                )

        elif iterator == "status_on_self":
            source_entity = self._resolve_source_entity(battle, source)
            status_ids = list(source_entity.status_effects.keys())
            for _ in status_ids:
                if battle.is_over:
                    break
                self.execute_actions(
                    node.children, battle, source=source, chosen_target=chosen_target,
                )

        elif iterator == "exhaust_count":
            exhaust_count = len(battle.card_piles.exhaust)
            for _ in range(exhaust_count):
                if battle.is_over:
                    break
                self.execute_actions(
                    node.children, battle, source=source, chosen_target=chosen_target,
                )

        else:
            logger.warning("Unknown FOR_EACH iterator %r, skipping", iterator)

    def _handle_repeat(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Execute children ``node.times`` times.

        If ``times`` is 0 or None and an X-cost value is available,
        use the X-cost value as the repeat count (Whirlwind pattern).
        """
        if not node.children:
            return
        times = node.times if node.times and node.times > 0 else 0
        if times == 0 and self._x_cost_value > 0:
            times = self._x_cost_value
        for _ in range(times):
            if battle.is_over:
                break
            self.execute_actions(
                node.children, battle, source=source, chosen_target=chosen_target,
            )

    def _handle_trigger_custom(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """No-op escape hatch for future exotic effects."""
        logger.debug(
            "TRIGGER_CUSTOM hit (condition=%r, value=%r) -- no-op",
            node.condition,
            node.value,
        )

    def _handle_double_block(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Double the source entity's current block (Entrench)."""
        source_entity = self._resolve_source_entity(battle, source)
        source_entity.block *= 2

    def _handle_multiply_status(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Multiply a status's stacks by a factor (Limit Break).

        Uses ``status_name`` for which status and ``value`` as the multiplier.
        """
        status_id = node.status_name
        if status_id is None:
            logger.warning("MULTIPLY_STATUS node missing status_name")
            return
        multiplier = node.value if node.value is not None else 2
        source_entity = self._resolve_source_entity(battle, source)
        current = source_entity.status_effects.get(status_id, 0)
        if current > 0:
            new_stacks = current * multiplier
            source_entity.status_effects[status_id] = new_stacks

    def _handle_play_top_card(
        self,
        node: ActionNode,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> None:
        """Play the top card of the draw pile, optionally exhausting it (Havoc).

        ``pile`` selects which pile (default "draw").
        ``condition`` of "exhaust" means exhaust after play instead of discard.
        """
        pile_name = (node.pile or "draw").lower()
        if pile_name == "draw":
            pile = battle.card_piles.draw
        elif pile_name == "discard":
            pile = battle.card_piles.discard
        else:
            logger.warning("PLAY_TOP_CARD: unknown pile %r", pile_name)
            return

        if not pile:
            return

        card_instance = pile.pop(0)
        card_def = self._card_registry.get(card_instance.card_id)
        if card_def is None:
            logger.warning(
                "PLAY_TOP_CARD: card %r not in registry", card_instance.card_id,
            )
            return

        # Determine actions
        if (
            card_instance.upgraded
            and card_def.upgrade is not None
            and card_def.upgrade.actions is not None
        ):
            actions = card_def.upgrade.actions
        else:
            actions = card_def.actions

        # Pick a target for the card
        play_target = chosen_target
        if card_def.target == CardTarget.ENEMY and play_target is None:
            living = [i for i, e in enumerate(battle.enemies) if not e.is_dead]
            if living:
                play_target = battle.rng.random_choice(living)

        # Execute the card's actions (free — no energy cost)
        self.execute_actions(actions, battle, source=source, chosen_target=play_target)

        # Dispose: exhaust or discard
        should_exhaust = (
            (node.condition or "").lower() == "exhaust"
            or card_def.exhaust
            or "exhaust" in card_def.keywords
        )
        if should_exhaust:
            battle.card_piles.exhaust.append(card_instance)
        else:
            battle.card_piles.discard.append(card_instance)

    # ------------------------------------------------------------------
    # Deck helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_strikes_in_deck(battle: BattleState) -> int:
        """Count cards with 'strike' in their card_id across all piles."""
        count = 0
        for pile in (
            battle.card_piles.draw,
            battle.card_piles.hand,
            battle.card_piles.discard,
            battle.card_piles.exhaust,
        ):
            for card in pile:
                if "strike" in card.card_id.lower():
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Condition evaluator
    # ------------------------------------------------------------------

    def _evaluate_condition(
        self,
        condition: str,
        battle: BattleState,
        source: str,
        chosen_target: int | None,
    ) -> bool:
        """Parse and evaluate a simple condition string.

        Returns ``True`` if the condition is met, ``False`` otherwise.
        Unknown conditions default to ``False`` with a warning.
        """
        condition = condition.strip()
        source_entity = self._resolve_source_entity(battle, source)

        # has_status:<status_id>
        if condition.startswith("has_status:"):
            status_id = condition.split(":", 1)[1].strip()
            return has_status(source_entity, status_id)

        # target_has_status:<status_id>
        if condition.startswith("target_has_status:"):
            status_id = condition.split(":", 1)[1].strip()
            if chosen_target is not None and 0 <= chosen_target < len(battle.enemies):
                return has_status(battle.enemies[chosen_target], status_id)
            return False

        # hp_below:<percentage>
        if condition.startswith("hp_below:"):
            try:
                threshold = int(condition.split(":", 1)[1].strip())
            except ValueError:
                return False
            if source_entity.max_hp <= 0:
                return False
            pct = (source_entity.current_hp / source_entity.max_hp) * 100
            return pct < threshold

        # hp_above:<percentage>
        if condition.startswith("hp_above:"):
            try:
                threshold = int(condition.split(":", 1)[1].strip())
            except ValueError:
                return False
            if source_entity.max_hp <= 0:
                return False
            pct = (source_entity.current_hp / source_entity.max_hp) * 100
            return pct > threshold

        # no_block
        if condition == "no_block":
            return source_entity.block == 0

        # hand_empty
        if condition == "hand_empty":
            return len(battle.card_piles.hand) == 0

        # hand_size_gte:<n>
        if condition.startswith("hand_size_gte:"):
            try:
                n = int(condition.split(":", 1)[1].strip())
            except ValueError:
                return False
            return len(battle.card_piles.hand) >= n

        # only_attacks_in_hand — Clash: every card in hand must be Attack type
        if condition == "only_attacks_in_hand":
            hand = battle.card_piles.hand
            if not hand:
                return False
            for card_inst in hand:
                card_def = self._card_registry.get(card_inst.card_id)
                if card_def is None:
                    return False
                from sts_gen.ir.cards import CardType
                if card_def.type != CardType.ATTACK:
                    return False
            return True

        # enemy_intends_attack — Spot Weakness: chosen target intends an attack
        if condition == "enemy_intends_attack":
            if chosen_target is not None and 0 <= chosen_target < len(battle.enemies):
                enemy = battle.enemies[chosen_target]
                return enemy.intent_damage is not None and enemy.intent_damage > 0
            return False

        logger.warning("Unknown condition %r, evaluating to False", condition)
        return False


# ------------------------------------------------------------------
# Dispatch table -- maps ActionType -> handler method
# ------------------------------------------------------------------

_DISPATCH: dict[ActionType, callable] = {
    ActionType.DEAL_DAMAGE: ActionInterpreter._handle_deal_damage,
    ActionType.GAIN_BLOCK: ActionInterpreter._handle_gain_block,
    ActionType.APPLY_STATUS: ActionInterpreter._handle_apply_status,
    ActionType.REMOVE_STATUS: ActionInterpreter._handle_remove_status,
    ActionType.DRAW_CARDS: ActionInterpreter._handle_draw_cards,
    ActionType.DISCARD_CARDS: ActionInterpreter._handle_discard_cards,
    ActionType.EXHAUST_CARDS: ActionInterpreter._handle_exhaust_cards,
    ActionType.GAIN_ENERGY: ActionInterpreter._handle_gain_energy,
    ActionType.LOSE_ENERGY: ActionInterpreter._handle_lose_energy,
    ActionType.HEAL: ActionInterpreter._handle_heal,
    ActionType.LOSE_HP: ActionInterpreter._handle_lose_hp,
    ActionType.ADD_CARD_TO_PILE: ActionInterpreter._handle_add_card_to_pile,
    ActionType.SHUFFLE_INTO_DRAW: ActionInterpreter._handle_shuffle_into_draw,
    ActionType.GAIN_GOLD: ActionInterpreter._handle_gain_gold,
    ActionType.GAIN_STRENGTH: ActionInterpreter._handle_gain_strength,
    ActionType.GAIN_DEXTERITY: ActionInterpreter._handle_gain_dexterity,
    ActionType.CONDITIONAL: ActionInterpreter._handle_conditional,
    ActionType.FOR_EACH: ActionInterpreter._handle_for_each,
    ActionType.REPEAT: ActionInterpreter._handle_repeat,
    ActionType.TRIGGER_CUSTOM: ActionInterpreter._handle_trigger_custom,
    ActionType.DOUBLE_BLOCK: ActionInterpreter._handle_double_block,
    ActionType.MULTIPLY_STATUS: ActionInterpreter._handle_multiply_status,
    ActionType.PLAY_TOP_CARD: ActionInterpreter._handle_play_top_card,
}
