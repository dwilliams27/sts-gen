"""Heuristic-based agent that uses game knowledge to make decisions.

The ``HeuristicAgent`` is a hand-crafted policy that plays Slay the Spire
using a priority-based decision system:

- **Card play**: Evaluates a priority waterfall each action (lethal kills,
  survival blocking, powers, vulnerable application, best-ratio attacks,
  efficient blocking, zero-cost plays).
- **Card rewards**: Hardcoded tier list scoring with deck-size modifiers.
- **Potions**: Situational usage (lethal defense, elite offense, secure kills).
- **Rest sites**: HP-threshold rest vs. smith with upgrade priority list.
"""

from __future__ import annotations

import math
from typing import Any, TYPE_CHECKING

from sts_gen.ir.actions import ActionType
from sts_gen.ir.cards import CardTarget, CardType
from sts_gen.sim.mechanics.status_effects import get_status_stacks, has_status
from sts_gen.sim.play_agents.base import PlayAgent

if TYPE_CHECKING:
    from sts_gen.ir.actions import ActionNode
    from sts_gen.ir.cards import CardDefinition
    from sts_gen.ir.potions import PotionDefinition
    from sts_gen.sim.content.registry import ContentRegistry
    from sts_gen.sim.core.entities import Enemy, Player
    from sts_gen.sim.core.game_state import BattleState, CardInstance

# Hard fights where we should use offensive potions early
_HARD_FIGHT_IDS = frozenset({
    "gremlin_nob", "lagavulin", "sentry",
    "the_guardian", "hexaghost", "slime_boss",
})

# Card reward tier scores (0-100)
_CARD_TIER_SCORES: dict[str, int] = {
    # S tier
    "offering": 100,
    "demon_form": 95,
    "battle_trance": 92,
    "feed": 90,
    "inflame": 88,
    "reaper": 85,
    # A tier
    "impervious": 84,
    "shrug_it_off": 80,
    "flame_barrier": 78,
    "pommel_strike": 77,
    "carnage": 76,
    "uppercut": 75,
    "metallicize": 74,
    "clothesline": 72,
    "bludgeon": 70,
    # B tier
    "anger": 65,
    "iron_wave": 60,
    "thunderclap": 58,
    "twin_strike": 55,
    "true_grit": 52,
    "sentinel": 51,
    "headbutt": 50,
    # C tier
    "body_slam": 45,
    "clash": 42,
    "flex": 40,
    "warcry": 38,
    "rage": 36,
    "combust": 35,
    "power_through": 34,
    "blood_for_blood": 33,
    "second_wind": 32,
    "disarm": 30,
    "entrench": 28,
    "ghostly_armor": 27,
    "hemokinesis": 26,
    "dropkick": 25,
    "limit_break": 24,
    "whirlwind": 23,
    "searing_blow": 22,
    "spot_weakness": 21,
    "heavy_blade": 20,
    # Low tier — generally skip
    "strike": 10,
    "defend": 8,
}

# Upgrade priority scores
_UPGRADE_SCORES: dict[str, int] = {
    "bash": 100,
    "demon_form": 95,
    "inflame": 90,
    "carnage": 85,
    "reaper": 84,
    "bludgeon": 83,
    "battle_trance": 82,
    "feed": 80,
    "offering": 78,
    "pommel_strike": 75,
    "shrug_it_off": 70,
    "uppercut": 65,
    "flame_barrier": 60,
    "metallicize": 55,
    "impervious": 50,
    "thunderclap": 45,
    "clothesline": 40,
    "iron_wave": 35,
    "twin_strike": 30,
    "anger": 25,
    "strike": 20,
    "defend": 15,
}

# Power card priority (higher = play first)
_POWER_PRIORITY: dict[str, int] = {
    "demon_form": 100,
    "corruption": 90,
    "barricade": 85,
    "inflame": 80,
    "metallicize": 75,
    "dark_embrace": 70,
    "feel_no_pain": 65,
    "evolve": 60,
    "fire_breathing": 55,
    "juggernaut": 50,
    "combust": 45,
    "brutality": 40,
    "berserk": 35,
    "rupture": 30,
}


class HeuristicAgent(PlayAgent):
    """Agent that uses game-knowledge heuristics to play well.

    Parameters
    ----------
    registry:
        Content registry for looking up card definitions.
    **kwargs:
        Absorbs extra kwargs (e.g. ``rng=``) from BatchRunner.
    """

    def __init__(self, registry: ContentRegistry, **kwargs: Any) -> None:
        self.registry = registry

    # ==================================================================
    # PlayAgent interface
    # ==================================================================

    def choose_card_to_play(
        self,
        battle: BattleState,
        playable_cards: list[tuple[CardInstance, CardDefinition]],
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        if not playable_cards:
            return None

        player = battle.player
        living = battle.living_enemies
        if not living:
            return None

        primary_idx = self._best_target(battle)
        primary = battle.enemies[primary_idx]
        incoming = self._incoming_damage(battle)
        nob_fight = self._is_nob_fight(battle)

        # Filter out skills in Nob fight
        if nob_fight:
            playable_cards = [
                (ci, cd) for ci, cd in playable_cards
                if cd.type != CardType.SKILL
            ]
            if not playable_cards:
                return None

        # --- Priority 1: Offering (0-cost draw 3 + 2 energy) ---
        for ci, cd in playable_cards:
            if cd.id == "offering" and player.current_hp > 10:
                return ci, cd, None

        # --- Priority 2: Battle Trance (0-cost draw 3) ---
        for ci, cd in playable_cards:
            if cd.id == "battle_trance" and not has_status(player, "No Draw"):
                return ci, cd, None

        # --- Priority 3: Lethal kill ---
        result = self._try_lethal(playable_cards, battle, primary_idx)
        if result is not None:
            return result

        # --- Priority 4: Survive lethal incoming ---
        effective_incoming = incoming - player.block
        if effective_incoming >= player.current_hp and effective_incoming > 0:
            result = self._best_block_card(playable_cards, battle)
            if result is not None:
                return result

        # --- Priority 5: Powers ---
        result = self._try_power(playable_cards, battle)
        if result is not None:
            return result

        # --- Priority 6: Apply vulnerable ---
        if not has_status(primary, "vulnerable"):
            result = self._try_vulnerable(playable_cards, battle, primary_idx)
            if result is not None:
                return result

        # --- Priority 7: Best attack (defer Body Slam) ---
        result = self._best_attack(playable_cards, battle, primary_idx)
        if result is not None:
            return result

        # --- Priority 8: Block if significant incoming ---
        if incoming - player.block > 5:
            result = self._best_block_card(playable_cards, battle)
            if result is not None:
                return result

        # --- Priority 9: Zero-cost cards ---
        for ci, cd in playable_cards:
            cost = self._effective_cost(cd, ci, battle)
            if cost == 0 and cd.id != "body_slam":
                target = self._resolve_target(cd, battle, primary_idx)
                return ci, cd, target

        # --- Priority 10: Remaining block cards ---
        result = self._best_block_card(playable_cards, battle)
        if result is not None:
            return result

        # --- Priority 10b: Body Slam (now that block is gained) ---
        for ci, cd in playable_cards:
            if cd.id == "body_slam":
                return ci, cd, primary_idx

        # --- Priority 11: End turn ---
        return None

    def choose_card_reward(
        self,
        cards: list[CardDefinition],
        deck: list[str],
    ) -> CardDefinition | None:
        if not cards:
            return None

        deck_size = len(deck)
        best_card: CardDefinition | None = None
        best_score = -1

        for card in cards:
            score = _CARD_TIER_SCORES.get(card.id, 30)

            # Penalize adding cards to a bloated deck
            if deck_size > 15 and score < 70:
                score -= (deck_size - 15) * 3

            # Penalize duplicates
            copies = sum(1 for cid in deck if cid == card.id)
            if copies >= 2:
                score -= 30

            if score > best_score:
                best_score = score
                best_card = card

        # Skip if best option is bad and deck is large
        if best_score < 25 and deck_size > 20:
            return None

        return best_card

    def choose_potion_to_use(
        self,
        battle: BattleState,
        available_potions: list[tuple[int, PotionDefinition]],
    ) -> tuple[int, PotionDefinition, int | None] | None:
        if not available_potions:
            return None

        player = battle.player
        incoming = self._incoming_damage(battle)
        primary_idx = self._best_target(battle)

        # --- Lethal defense: use defensive potion if incoming would kill ---
        effective_incoming = incoming - player.block
        if effective_incoming >= player.current_hp and effective_incoming > 0:
            for slot, pdef in available_potions:
                if pdef.id in ("block_potion", "regen_potion", "weak_potion"):
                    target = self._resolve_potion_target(pdef, battle, primary_idx)
                    return slot, pdef, target

        # --- Hard fight offense: use offensive potions turns 1-2 ---
        if self._is_fight_hard(battle) and battle.turn <= 2:
            for slot, pdef in available_potions:
                if pdef.id in ("strength_potion", "fear_potion", "dexterity_potion"):
                    target = self._resolve_potion_target(pdef, battle, primary_idx)
                    return slot, pdef, target

        # --- Secure kill: fire potion can kill a low-HP enemy ---
        for slot, pdef in available_potions:
            if pdef.id == "fire_potion":
                for i, enemy in enumerate(battle.enemies):
                    if not enemy.is_dead and (enemy.current_hp + enemy.block) <= 20:
                        return slot, pdef, i

        # --- Low HP defense: use any defensive potion when HP < 30% ---
        hp_ratio = player.current_hp / max(player.max_hp, 1)
        if hp_ratio < 0.30:
            for slot, pdef in available_potions:
                if pdef.id in (
                    "block_potion", "regen_potion", "weak_potion",
                    "dexterity_potion",
                ):
                    target = self._resolve_potion_target(pdef, battle, primary_idx)
                    return slot, pdef, target

        # Save potions
        return None

    def choose_rest_action(
        self,
        player: Player,
        deck: list[CardInstance],
    ) -> str:
        hp_ratio = player.current_hp / max(player.max_hp, 1)

        if hp_ratio <= 0.50:
            return "rest"

        if hp_ratio > 0.65:
            # Check if we have a high-priority upgrade target
            for ci in deck:
                if not ci.upgraded and _UPGRADE_SCORES.get(ci.card_id, 0) >= 80:
                    return "smith"

        return "rest"

    def choose_card_to_upgrade(
        self,
        upgradable: list[CardInstance],
    ) -> CardInstance | None:
        if not upgradable:
            return None

        best: CardInstance | None = None
        best_score = -1
        for ci in upgradable:
            score = _UPGRADE_SCORES.get(ci.card_id, 10)
            if score > best_score:
                best_score = score
                best = ci
        return best

    # ==================================================================
    # Helpers — damage/block estimation
    # ==================================================================

    def _estimate_damage(
        self,
        card_def: CardDefinition,
        card_inst: CardInstance,
        player: Player,
        target: Enemy,
    ) -> int:
        """Estimate total damage a card deals to a single target."""
        actions = self._get_actions(card_def, card_inst)
        return self._walk_damage(actions, player, target, 1)

    def _walk_damage(
        self,
        actions: list[ActionNode],
        player: Player,
        target: Enemy,
        multiplier: int,
    ) -> int:
        """Recursively walk action tree summing DEAL_DAMAGE nodes."""
        total = 0
        for action in actions:
            if action.action_type == ActionType.DEAL_DAMAGE:
                base = action.value or 0
                # Apply strength
                strength = get_status_stacks(player, "strength")
                damage = float(base + strength)
                # Vulnerable on target
                if has_status(target, "vulnerable"):
                    damage = math.floor(damage * 1.5)
                # Weak on player
                if has_status(player, "weak"):
                    damage = math.floor(damage * 0.75)
                total += max(0, int(damage)) * multiplier
            elif action.action_type == ActionType.REPEAT:
                times = action.times or 1
                if action.children:
                    total += self._walk_damage(
                        action.children, player, target, multiplier * times,
                    )
            elif action.action_type == ActionType.CONDITIONAL:
                # Optimistically include conditional damage
                if action.children:
                    total += self._walk_damage(
                        action.children, player, target, multiplier,
                    )
        return total

    def _estimate_block(
        self,
        card_def: CardDefinition,
        card_inst: CardInstance,
        player: Player,
    ) -> int:
        """Estimate total block a card provides."""
        actions = self._get_actions(card_def, card_inst)
        return self._walk_block(actions, player)

    def _walk_block(
        self,
        actions: list[ActionNode],
        player: Player,
    ) -> int:
        """Recursively walk action tree summing GAIN_BLOCK nodes."""
        total = 0
        for action in actions:
            if action.action_type == ActionType.GAIN_BLOCK:
                # Skip raw-block nodes (condition="raw")
                if action.condition == "raw":
                    continue
                base = action.value or 0
                dex = get_status_stacks(player, "dexterity")
                block = float(base + dex)
                if has_status(player, "frail"):
                    block = math.floor(block * 0.75)
                total += max(0, int(block))
            elif action.action_type == ActionType.REPEAT:
                times = action.times or 1
                if action.children:
                    total += self._walk_block(action.children, player) * times
            elif action.action_type == ActionType.CONDITIONAL:
                if action.children:
                    total += self._walk_block(action.children, player)
        return total

    def _incoming_damage(self, battle: BattleState) -> int:
        """Sum expected incoming damage from all living enemies."""
        total = 0
        for enemy in battle.living_enemies:
            if enemy.intent_damage is not None and enemy.intent_damage > 0:
                hits = enemy.intent_hits or 1
                # Account for enemy strength
                strength = get_status_stacks(enemy, "strength")
                per_hit = float(enemy.intent_damage + strength)
                # Weak on enemy reduces damage
                if has_status(enemy, "weak"):
                    per_hit = math.floor(per_hit * 0.75)
                # Vulnerable on player increases damage
                if has_status(battle.player, "vulnerable"):
                    per_hit = math.floor(per_hit * 1.5)
                total += max(0, int(per_hit)) * hits
        return total

    def _best_target(self, battle: BattleState) -> int:
        """Pick the best enemy to target. Returns enemy index."""
        best_idx = 0
        best_score = -9999
        for i, enemy in enumerate(battle.enemies):
            if enemy.is_dead:
                continue
            effective_hp = enemy.current_hp + enemy.block
            score = 0.0
            # Killable bonus
            if effective_hp <= 15:
                score += 100
            # Prioritize enemies that deal more damage
            if enemy.intent_damage is not None:
                hits = enemy.intent_hits or 1
                score += 2 * enemy.intent_damage * hits
            # Prefer lower HP targets
            score -= effective_hp
            if score > best_score:
                best_score = score
                best_idx = i
        return best_idx

    def _effective_cost(
        self,
        card_def: CardDefinition,
        card_inst: CardInstance,
        battle: BattleState,
    ) -> int:
        """Resolve the effective energy cost of a card."""
        if card_inst.cost_override is not None:
            return card_inst.cost_override
        if (
            card_inst.upgraded
            and card_def.upgrade is not None
            and card_def.upgrade.cost is not None
        ):
            return card_def.upgrade.cost
        # Corruption: skills cost 0
        if has_status(battle.player, "Corruption") and card_def.type == CardType.SKILL:
            return 0
        return card_def.cost

    def _get_actions(
        self,
        card_def: CardDefinition,
        card_inst: CardInstance,
    ) -> list[ActionNode]:
        """Return the appropriate action list (base or upgraded)."""
        if (
            card_inst.upgraded
            and card_def.upgrade is not None
            and card_def.upgrade.actions is not None
        ):
            return card_def.upgrade.actions
        return card_def.actions

    # ==================================================================
    # Helpers — card play priorities
    # ==================================================================

    def _try_lethal(
        self,
        playable: list[tuple[CardInstance, CardDefinition]],
        battle: BattleState,
        target_idx: int,
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """If any attack can kill the primary target, play it."""
        target = battle.enemies[target_idx]
        effective_hp = target.current_hp + target.block

        for ci, cd in playable:
            if cd.type != CardType.ATTACK:
                continue
            est = self._estimate_damage(cd, ci, battle.player, target)
            if est >= effective_hp:
                tgt = self._resolve_target(cd, battle, target_idx)
                return ci, cd, tgt
        return None

    def _best_block_card(
        self,
        playable: list[tuple[CardInstance, CardDefinition]],
        battle: BattleState,
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """Play the best block-per-energy card."""
        best: tuple[CardInstance, CardDefinition] | None = None
        best_ratio = -1.0
        for ci, cd in playable:
            est_block = self._estimate_block(cd, ci, battle.player)
            if est_block <= 0:
                continue
            cost = self._effective_cost(cd, ci, battle)
            ratio = est_block / max(cost, 0.5)
            if ratio > best_ratio:
                best_ratio = ratio
                best = (ci, cd)

        if best is not None:
            ci, cd = best
            target = self._resolve_target(cd, battle, self._best_target(battle))
            return ci, cd, target
        return None

    def _try_power(
        self,
        playable: list[tuple[CardInstance, CardDefinition]],
        battle: BattleState,
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """Play the highest-priority affordable power card."""
        best: tuple[CardInstance, CardDefinition] | None = None
        best_priority = -1
        for ci, cd in playable:
            if cd.type != CardType.POWER:
                continue
            priority = _POWER_PRIORITY.get(cd.id, 10)
            if priority > best_priority:
                best_priority = priority
                best = (ci, cd)
        if best is not None:
            ci, cd = best
            return ci, cd, None
        return None

    def _try_vulnerable(
        self,
        playable: list[tuple[CardInstance, CardDefinition]],
        battle: BattleState,
        target_idx: int,
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """Play a card that applies vulnerable (Bash, Uppercut, Thunderclap)."""
        vuln_cards = ("bash", "uppercut", "thunderclap")
        for ci, cd in playable:
            if cd.id in vuln_cards:
                target = self._resolve_target(cd, battle, target_idx)
                return ci, cd, target
        return None

    def _best_attack(
        self,
        playable: list[tuple[CardInstance, CardDefinition]],
        battle: BattleState,
        target_idx: int,
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """Play the highest damage/energy attack card."""
        target = battle.enemies[target_idx]
        n_living = len(battle.living_enemies)

        # Bump ethereal attacks (Carnage) — they exhaust if unplayed
        ethereal_ids = {
            ci.id for ci, cd in playable
            if cd.ethereal and cd.type == CardType.ATTACK
        }

        best: tuple[CardInstance, CardDefinition] | None = None
        best_ratio = -1.0
        for ci, cd in playable:
            if cd.type != CardType.ATTACK:
                continue
            # Defer Body Slam until after block cards
            if cd.id == "body_slam":
                continue
            est = self._estimate_damage(cd, ci, battle.player, target)
            cost = self._effective_cost(cd, ci, battle)
            # AoE bonus when multiple enemies alive
            if cd.target == CardTarget.ALL_ENEMIES and n_living >= 2:
                est = int(est * n_living * 0.8)
            ratio = est / max(cost, 0.5)
            # Ethereal bump
            if ci.id in ethereal_ids:
                ratio *= 1.5
            if ratio > best_ratio:
                best_ratio = ratio
                best = (ci, cd)

        if best is not None:
            ci, cd = best
            tgt = self._resolve_target(cd, battle, target_idx)
            return ci, cd, tgt
        return None

    # ==================================================================
    # Helpers — targeting
    # ==================================================================

    def _resolve_target(
        self,
        card_def: CardDefinition,
        battle: BattleState,
        preferred_idx: int,
    ) -> int | None:
        """Resolve targeting for a card. Returns enemy index or None."""
        if card_def.target == CardTarget.ENEMY:
            # Validate the preferred index
            if (
                preferred_idx < len(battle.enemies)
                and not battle.enemies[preferred_idx].is_dead
            ):
                return preferred_idx
            # Fallback to first living enemy
            for i, e in enumerate(battle.enemies):
                if not e.is_dead:
                    return i
            return 0
        return None

    def _resolve_potion_target(
        self,
        potion_def: PotionDefinition,
        battle: BattleState,
        preferred_idx: int,
    ) -> int | None:
        """Resolve targeting for a potion."""
        if potion_def.target == CardTarget.ENEMY:
            if (
                preferred_idx < len(battle.enemies)
                and not battle.enemies[preferred_idx].is_dead
            ):
                return preferred_idx
            for i, e in enumerate(battle.enemies):
                if not e.is_dead:
                    return i
            return 0
        return None

    def _is_nob_fight(self, battle: BattleState) -> bool:
        """Check if any living enemy is Gremlin Nob."""
        return any(
            e.enemy_id == "gremlin_nob"
            for e in battle.living_enemies
        )

    def _is_fight_hard(self, battle: BattleState) -> bool:
        """Check if this is a hard fight (elite/boss)."""
        return any(
            e.enemy_id in _HARD_FIGHT_IDS
            for e in battle.enemies
        )
