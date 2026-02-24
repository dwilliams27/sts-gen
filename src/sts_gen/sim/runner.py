"""Battle simulation runner -- ties the combat loop, enemy AI, and telemetry together.

Provides three key classes:

- **EnemyAI**: Determines and executes enemy intents each turn.
- **CombatSimulator**: Runs a single combat encounter to completion.
- **BatchRunner**: Orchestrates many simulation runs (optionally in parallel).
"""

from __future__ import annotations

import logging
import multiprocessing
from typing import Any, TYPE_CHECKING

from sts_gen.ir.actions import ActionNode
from sts_gen.ir.cards import CardTarget, CardType
from sts_gen.ir.status_effects import StatusTrigger
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.block import gain_block
from sts_gen.sim.mechanics.damage import deal_damage
from sts_gen.sim.mechanics.card_piles import draw_cards
from sts_gen.sim.mechanics.status_effects import apply_status, decay_statuses, has_status
from sts_gen.sim.triggers import TriggerDispatcher

from sts_gen.sim.play_agents.base import PlayAgent
from sts_gen.sim.play_agents.random_agent import RandomAgent
from sts_gen.sim.telemetry import BattleTelemetry, RunTelemetry

if TYPE_CHECKING:
    from sts_gen.ir.cards import CardDefinition
    from sts_gen.sim.content.registry import ContentRegistry

logger = logging.getLogger(__name__)

_MAX_TURNS = 200


# =====================================================================
# EnemyAI
# =====================================================================

class EnemyAI:
    """Determines enemy behaviour based on their definition in the content registry.

    Supports pattern types:
    - fixed_sequence: cycle through moves in order (with loop_from and start_offset_by_index)
    - weighted_random: pick moves by weight, with per-move max_consecutive limits
    - sequential: simple cycle through moves list
    - looter: branching sequence for the Looter enemy
    - red_slaver: phase-based pattern for Red Slaver
    - shield_gremlin: conditional on living allies
    - lagavulin: sleep/wake cycle
    - guardian_mode_shift: offensive/defensive mode switching
    """

    def __init__(self, interpreter: ActionInterpreter) -> None:
        self._interpreter = interpreter
        self._move_counters: dict[str, int] = {}
        self._last_moves: dict[str, list[str]] = {}
        # Per-enemy complex state (sleep, phase tracking, split status, etc.)
        self._enemy_state: dict[str, dict[str, Any]] = {}

    def init_enemy_state(
        self,
        enemy: Enemy,
        enemy_data: dict[str, Any],
        battle: BattleState,
        rng: GameRNG,
        enemy_idx: int,
    ) -> None:
        """Initialize per-enemy state at combat start (powers, passive abilities)."""
        key = self._enemy_key(enemy)
        state = self._enemy_state.setdefault(key, {})

        for power in enemy_data.get("powers", []):
            pid = power["id"]
            if pid == "curl_up":
                block_val = rng.random_int(power["block_min"], power["block_max"])
                state["curl_up"] = block_val
            elif pid == "angry":
                apply_status(enemy, "Angry", power.get("value", 1))
            elif pid == "thievery":
                apply_status(enemy, "Thievery", power.get("value", 15))
                state["stolen_gold"] = 0
            elif pid == "artifact":
                apply_status(enemy, "Artifact", power.get("value", 1))

        # Lagavulin sleep initialization
        pattern = enemy_data.get("pattern", {})
        if pattern.get("type") == "lagavulin":
            sleep_turns = pattern.get("sleep_turns", 3)
            state["sleep_turns"] = sleep_turns
            state["woken"] = False
            state["stunned"] = False
            metallicize = pattern.get("metallicize", 8)
            apply_status(enemy, "Metallicize", metallicize)

        # Guardian mode shift initialization
        if pattern.get("type") == "guardian_mode_shift":
            state["mode"] = "offensive"
            state["seq_counter"] = 0
            state["def_seq_counter"] = 0
            state["damage_since_shift"] = 0
            state["current_threshold"] = pattern.get("initial_threshold", 30)

    def determine_intent(
        self,
        enemy: Enemy,
        enemy_data: dict[str, Any],
        battle: BattleState,
        rng: GameRNG,
        enemy_idx: int = 0,
    ) -> None:
        """Set the enemy's intent for this turn."""
        moves = enemy_data.get("moves", [])
        if not moves:
            return

        key = self._enemy_key(enemy)
        pattern = enemy_data.get("pattern", {})
        pattern_type = pattern.get("type", "sequential")
        counter = self._move_counters.get(key, 0)
        last_moves = self._last_moves.get(key, [])
        state = self._enemy_state.setdefault(key, {})

        move = None

        if pattern_type == "fixed_sequence":
            move = self._determine_fixed_sequence(
                moves, pattern, counter, enemy_idx,
            )

        elif pattern_type == "weighted_random":
            move = self._determine_weighted_random(
                moves, pattern, counter, last_moves, rng,
            )

        elif pattern_type == "looter":
            move = self._determine_looter(moves, counter, state, rng)

        elif pattern_type == "red_slaver":
            move = self._determine_red_slaver(
                moves, pattern, counter, state, last_moves, rng,
            )

        elif pattern_type == "shield_gremlin":
            move = self._determine_shield_gremlin(
                moves, pattern, enemy, battle,
            )

        elif pattern_type == "lagavulin":
            move = self._determine_lagavulin(moves, pattern, state)

        elif pattern_type == "guardian_mode_shift":
            move = self._determine_guardian(moves, pattern, state)

        else:
            # Simple sequential fallback
            move = moves[counter % len(moves)]

        if move is None:
            move = moves[0]

        # Update tracking
        self._move_counters[key] = counter + 1
        last_moves.append(move["id"])
        if len(last_moves) > 5:
            last_moves = last_moves[-5:]
        self._last_moves[key] = last_moves

        # Set intent on enemy
        self._set_intent_from_move(enemy, move, battle, rng)
        enemy._current_move = move  # type: ignore[attr-defined]
        enemy._current_move_type = move.get("type", "attack")  # type: ignore[attr-defined]

    def execute_intent(
        self,
        enemy: Enemy,
        enemy_idx: int,
        battle: BattleState,
    ) -> int:
        """Execute the enemy's current intent. Returns HP damage dealt to player."""
        if enemy.is_dead:
            return 0

        move = getattr(enemy, "_current_move", None)
        move_type = getattr(enemy, "_current_move_type", "attack")
        damage_dealt = 0

        # 1. Deal damage (attack types)
        if move_type in ("attack", "attack_defend"):
            base_damage = enemy.intent_damage or 0
            hits = enemy.intent_hits or 1
            damage_dealt = deal_damage(
                battle, source_idx=enemy_idx, target_idx="player",
                base_damage=base_damage, hits=hits,
            )
            # Thievery: steal gold on attack
            thievery = enemy.status_effects.get("Thievery", 0)
            if thievery > 0:
                key = self._enemy_key(enemy)
                state = self._enemy_state.setdefault(key, {})
                stolen = min(thievery, battle.player.gold)
                battle.player.gold -= stolen
                state["stolen_gold"] = state.get("stolen_gold", 0) + stolen

        # 2. Gain block (defend types)
        if move_type in ("defend", "attack_defend") and move:
            block_amount = move.get("block", 0)
            if block_amount > 0:
                # Direct block for enemy (skip dex/frail modifiers)
                enemy.block += block_amount

        # 3. Protect ally (Shield Gremlin)
        if move_type == "protect_ally" and move:
            block_amount = move.get("block", 0)
            if block_amount > 0:
                allies = [
                    i for i, e in enumerate(battle.enemies)
                    if not e.is_dead and i != enemy_idx
                ]
                if allies:
                    target_idx = battle.rng.random_choice(allies)
                    battle.enemies[target_idx].block += block_amount
                else:
                    # No allies, protect self
                    enemy.block += block_amount

        # 4. Apply debuffs to player (from move's debuffs field)
        if move:
            for debuff in move.get("debuffs", []):
                apply_status(battle.player, debuff["status"], debuff.get("stacks", 1))

        # 5. Add status cards to player's discard
        if move:
            for sc in move.get("status_cards", []):
                card_id = sc["card_id"]
                count = sc.get("count", 1)
                for _ in range(count):
                    battle.card_piles.discard.append(CardInstance(card_id=card_id))

        # 6. Execute complex buff/debuff actions through interpreter (existing behavior)
        if move and move_type in ("buff", "debuff"):
            raw_actions = move.get("actions", [])
            if raw_actions:
                action_nodes = []
                for a in raw_actions:
                    if isinstance(a, ActionNode):
                        action_nodes.append(a)
                    elif isinstance(a, dict):
                        action_nodes.append(ActionNode(**a))
                if action_nodes:
                    self._interpreter.execute_actions(
                        action_nodes, battle, source=str(enemy_idx),
                    )

        # 7. Escape (Looter)
        if move_type == "escape":
            enemy.current_hp = 0

        # 8. Nothing (charging, preparing, sleeping)
        # type == "none" → no action

        battle._check_battle_over()
        return damage_dealt

    # ------------------------------------------------------------------
    # Pattern helpers
    # ------------------------------------------------------------------

    def _determine_fixed_sequence(
        self,
        moves: list[dict],
        pattern: dict,
        counter: int,
        enemy_idx: int,
    ) -> dict | None:
        sequence = pattern.get("sequence", [m["id"] for m in moves])
        loop_from = pattern.get("loop_from", 0)

        # Start offset by enemy index (used for Sentries)
        effective_counter = counter
        if counter == 0 and pattern.get("start_offset_by_index"):
            effective_counter = enemy_idx % len(sequence)
            # Override the counter for this enemy
        elif pattern.get("start_offset_by_index"):
            effective_counter = counter + (enemy_idx % len(sequence))

        if effective_counter < len(sequence):
            move_id = sequence[effective_counter]
        else:
            loop_len = len(sequence) - loop_from
            if loop_len <= 0:
                loop_len = 1
            loop_idx = loop_from + ((effective_counter - len(sequence)) % loop_len)
            move_id = sequence[loop_idx]

        return self._find_move(moves, move_id)

    def _determine_weighted_random(
        self,
        moves: list[dict],
        pattern: dict,
        counter: int,
        last_moves: list[str],
        rng: GameRNG,
    ) -> dict | None:
        opening_move = pattern.get("opening_move")
        global_max_consecutive = pattern.get("max_consecutive", 3)
        per_move_consecutive = pattern.get("per_move_consecutive", {})
        weights = pattern.get("weights", {})

        if counter == 0 and opening_move:
            return self._find_move(moves, opening_move)

        # Filter out moves that have been used too many times in a row
        available = []
        available_weights = []
        for m in moves:
            mid = m["id"]
            w = weights.get(mid, 1)
            if w <= 0:
                continue
            max_consec = per_move_consecutive.get(mid, global_max_consecutive)
            if (
                len(last_moves) >= max_consec
                and all(lm == mid for lm in last_moves[-max_consec:])
            ):
                continue
            available.append(m)
            available_weights.append(w)

        if not available:
            # Fallback: allow all moves with positive weight
            available = [m for m in moves if weights.get(m["id"], 1) > 0]
            available_weights = [weights.get(m["id"], 1) for m in available]
            if not available:
                available = moves
                available_weights = [1] * len(moves)

        # Weighted random selection
        total = sum(available_weights)
        roll = rng.random_float() * total
        cumulative = 0
        selected = available[0]
        for m, w in zip(available, available_weights):
            cumulative += w
            if roll <= cumulative:
                selected = m
                break

        return selected

    def _determine_looter(
        self,
        moves: list[dict],
        counter: int,
        state: dict,
        rng: GameRNG,
    ) -> dict | None:
        """Looter pattern: Mug, Mug, 50/50 Lunge|SmokeBomb, SmokeBomb after Lunge, Escape."""
        if counter <= 1:
            return self._find_move(moves, "mug")
        elif counter == 2:
            if rng.random_float() < 0.5:
                state["looter_path"] = "long"
                return self._find_move(moves, "lunge")
            else:
                state["looter_path"] = "short"
                return self._find_move(moves, "smoke_bomb")
        elif counter == 3:
            if state.get("looter_path") == "long":
                return self._find_move(moves, "smoke_bomb")
            else:
                return self._find_move(moves, "escape")
        else:
            return self._find_move(moves, "escape")

    def _determine_red_slaver(
        self,
        moves: list[dict],
        pattern: dict,
        counter: int,
        state: dict,
        last_moves: list[str],
        rng: GameRNG,
    ) -> dict | None:
        """Red Slaver: open with Stab, phase 1 (25% Entangle + scrape/scrape/stab pattern),
        phase 2 (55/45 weighted random after Entangle used)."""
        if counter == 0:
            return self._find_move(moves, pattern.get("opening_move", "stab"))

        if not state.get("entangle_used"):
            # Phase 1: chance of Entangle each turn
            chance = pattern.get("entangle_chance", 25)
            if rng.random_float() * 100 < chance:
                state["entangle_used"] = True
                return self._find_move(moves, "entangle")
            # Follow pre-entangle sequence
            seq = pattern.get("pre_entangle_sequence", ["scrape", "scrape", "stab"])
            seq_counter = state.get("pre_seq_counter", 0)
            move_id = seq[seq_counter % len(seq)]
            state["pre_seq_counter"] = seq_counter + 1
            return self._find_move(moves, move_id)
        else:
            # Phase 2: weighted random
            post_weights = pattern.get("post_entangle_weights", {"stab": 55, "scrape": 45})
            max_consec = pattern.get("post_entangle_max_consecutive", 2)
            available = []
            available_weights = []
            for mid, w in post_weights.items():
                if w <= 0:
                    continue
                if (
                    len(last_moves) >= max_consec
                    and all(lm == mid for lm in last_moves[-max_consec:])
                ):
                    continue
                available.append(mid)
                available_weights.append(w)
            if not available:
                available = list(post_weights.keys())
                available_weights = list(post_weights.values())

            total = sum(available_weights)
            roll = rng.random_float() * total
            cumulative = 0
            selected_id = available[0]
            for mid, w in zip(available, available_weights):
                cumulative += w
                if roll <= cumulative:
                    selected_id = mid
                    break
            return self._find_move(moves, selected_id)

    def _determine_shield_gremlin(
        self,
        moves: list[dict],
        pattern: dict,
        enemy: Enemy,
        battle: BattleState,
    ) -> dict | None:
        """Shield Gremlin: Protect if allies alive, Shield Bash if alone."""
        allies_alive = any(
            not e.is_dead and e is not enemy
            for e in battle.enemies
        )
        if allies_alive:
            return self._find_move(moves, pattern.get("protect_move", "protect"))
        else:
            return self._find_move(moves, pattern.get("solo_move", "shield_bash"))

    def _determine_lagavulin(
        self,
        moves: list[dict],
        pattern: dict,
        state: dict,
    ) -> dict | None:
        """Lagavulin: sleep → wake → attack/attack/siphon_soul loop."""
        if not state.get("woken"):
            sleep_remaining = state.get("sleep_turns", 0)
            if sleep_remaining > 0:
                state["sleep_turns"] = sleep_remaining - 1
                if sleep_remaining - 1 <= 0:
                    # Natural wake at end of sleep
                    state["woken"] = True
                return self._find_move(moves, "sleep")
            else:
                state["woken"] = True

        if state.get("stunned"):
            state["stunned"] = False
            return self._find_move(moves, "sleep")

        # Awake cycle
        seq = pattern.get("awake_sequence", ["attack", "attack", "siphon_soul"])
        loop_from = pattern.get("awake_loop_from", 0)
        awake_counter = state.get("awake_counter", 0)
        if awake_counter < len(seq):
            move_id = seq[awake_counter]
        else:
            loop_len = len(seq) - loop_from
            if loop_len <= 0:
                loop_len = 1
            idx = loop_from + ((awake_counter - len(seq)) % loop_len)
            move_id = seq[idx]
        state["awake_counter"] = awake_counter + 1
        return self._find_move(moves, move_id)

    def _determine_guardian(
        self,
        moves: list[dict],
        pattern: dict,
        state: dict,
    ) -> dict | None:
        """Guardian mode shift: offensive cycle ↔ defensive cycle."""
        mode = state.get("mode", "offensive")

        if mode == "offensive":
            seq = pattern.get("offensive_sequence",
                              ["charging_up", "fierce_bash", "vent_steam", "whirlwind"])
            idx = state.get("seq_counter", 0) % len(seq)
            state["seq_counter"] = state.get("seq_counter", 0) + 1
            return self._find_move(moves, seq[idx])
        else:
            # Defensive mode
            seq = pattern.get("defensive_sequence",
                              ["defensive_mode", "roll_attack", "twin_slam"])
            idx = state.get("def_seq_counter", 0)
            state["def_seq_counter"] = idx + 1

            if idx + 1 >= len(seq):
                # After Twin Slam → back to offensive
                state["mode"] = "offensive"
                # Resume offensive cycle from whirlwind (index 3)
                state["seq_counter"] = 3
                state["def_seq_counter"] = 0
                # Increase threshold for next mode shift
                increase = pattern.get("threshold_increase", 10)
                state["current_threshold"] = state.get("current_threshold", 30) + increase
                state["damage_since_shift"] = 0

            return self._find_move(moves, seq[idx])

    # ------------------------------------------------------------------
    # Intent helpers
    # ------------------------------------------------------------------

    def _set_intent_from_move(
        self,
        enemy: Enemy,
        move: dict,
        battle: BattleState,
        rng: GameRNG,
    ) -> None:
        """Set intent fields on the enemy from a move dict."""
        enemy.intent = move.get("name", "Unknown")
        move_type = move.get("type", "attack")

        if move_type in ("attack", "attack_defend"):
            # Handle special damage calculations
            if move.get("special_damage") == "divider":
                # Hexaghost Divider: floor(player_hp / 12) + 1 per hit
                damage = (battle.player.current_hp // 12) + 1
            elif "damage_min" in move:
                damage = rng.random_int(move["damage_min"], move["damage_max"])
            else:
                damage = move.get("damage", 0)
            enemy.intent_damage = damage
            enemy.intent_hits = move.get("hits", 1)
        else:
            enemy.intent_damage = None
            enemy.intent_hits = None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _enemy_key(enemy: Enemy) -> str:
        return f"{enemy.enemy_id}_{id(enemy)}"

    @staticmethod
    def _find_move(moves: list[dict], move_id: str) -> dict | None:
        for m in moves:
            if m["id"] == move_id:
                return m
        return None


# =====================================================================
# CombatSimulator
# =====================================================================

class CombatSimulator:
    """Runs a single combat encounter to completion."""

    def __init__(
        self,
        registry: ContentRegistry,
        interpreter: ActionInterpreter,
        agent: PlayAgent,
    ) -> None:
        self.registry = registry
        self.interpreter = interpreter
        self.agent = agent
        self.enemy_ai = EnemyAI(interpreter)
        self.trigger_dispatcher = TriggerDispatcher(interpreter, registry.status_defs)

    def run_combat(self, battle: BattleState) -> BattleTelemetry:
        """Run a combat to completion, returning telemetry."""
        player_hp_start = battle.player.current_hp
        total_damage_dealt = 0
        total_block_gained = 0
        total_cards_played = 0
        cards_played_by_id: dict[str, int] = {}
        enemy_ids = [e.enemy_id for e in battle.enemies]

        # Setup: shuffle draw pile, then move innate cards to top
        battle.rng.shuffle(battle.card_piles.draw)
        self._move_innate_to_top(battle)

        # Load enemy data
        enemy_datas: list[dict[str, Any]] = []
        for enemy in battle.enemies:
            edata = self.registry.get_enemy_data(enemy.enemy_id)
            enemy_datas.append(edata if edata is not None else {})

        # Initialize enemy powers and complex state
        for i, enemy in enumerate(battle.enemies):
            self.enemy_ai.init_enemy_state(
                enemy, enemy_datas[i], battle, battle.rng, i,
            )

        enemy_moves_per_turn: list[list[str]] = []

        td = self.trigger_dispatcher
        has_corruption = lambda: has_status(battle.player, "Corruption")

        # Main combat loop
        while not battle.is_over and battle.turn < _MAX_TURNS:
            # Check Barricade: skip block clear if player has it
            skip_block_clear = has_status(battle.player, "Barricade")
            battle.start_turn(clear_block=not skip_block_clear)

            # Fire ON_TURN_START triggers on player (Demon Form, Brutality, Berserk)
            td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")

            if battle.is_over:
                break

            # Determine enemy intents
            turn_moves: list[str] = []
            for i, enemy in enumerate(battle.enemies):
                if not enemy.is_dead:
                    self.enemy_ai.determine_intent(
                        enemy, enemy_datas[i], battle, battle.rng,
                        enemy_idx=i,
                    )
                    turn_moves.append(enemy.intent or "Unknown")
            enemy_moves_per_turn.append(turn_moves)

            # Draw cards
            drawn_cards = draw_cards(battle, 5)

            # Fire ON_STATUS_DRAWN for each STATUS/CURSE drawn (Evolve, Fire Breathing)
            self._fire_on_status_drawn(battle, drawn_cards)

            if battle.is_over:
                break

            # Player action loop
            while not battle.is_over:
                playable = self._get_playable_cards(battle)
                choice = self.agent.choose_card_to_play(battle, playable)

                if choice is None:
                    break

                card_instance, card_def, chosen_target = choice

                block_before = battle.player.block
                player_hp_before = battle.player.current_hp
                exhaust_ids_before = {id(c) for c in battle.card_piles.exhaust}
                enemy_hp_before = {
                    id(e): e.current_hp for e in battle.enemies
                }

                # Corruption: skills cost 0 and exhaust
                force_exhaust = False
                if has_corruption() and card_def.type == CardType.SKILL:
                    force_exhaust = True
                    card_instance.cost_override = 0

                self.interpreter.play_card(
                    card_def, battle, card_instance, chosen_target=chosen_target,
                    force_exhaust=force_exhaust,
                )

                total_cards_played += 1
                cards_played_by_id[card_def.id] = (
                    cards_played_by_id.get(card_def.id, 0) + 1
                )

                block_delta = max(0, battle.player.block - block_before)
                total_block_gained += block_delta

                total_damage_dealt += max(
                    0,
                    sum(enemy_hp_before.values()) - sum(
                        e.current_hp for e in battle.enemies
                    ),
                )

                # --- Trigger-based post-card-play hooks ---

                # ON_ATTACK_PLAYED (Rage)
                if card_def.type == CardType.ATTACK:
                    td.fire(battle.player, StatusTrigger.ON_ATTACK_PLAYED, battle, "player")

                # ON_CARD_EXHAUSTED (Dark Embrace, Feel No Pain) + per-card on_exhaust (Sentinel)
                newly_exhausted = [
                    c for c in battle.card_piles.exhaust
                    if id(c) not in exhaust_ids_before
                ]
                for exhausted_card in newly_exhausted:
                    if battle.is_over:
                        break
                    # Per-card on_exhaust actions (Sentinel: gain energy)
                    exhausted_def = self.registry.cards.get(exhausted_card.card_id)
                    if exhausted_def:
                        on_exhaust_actions = exhausted_def.on_exhaust
                        if (
                            exhausted_card.upgraded
                            and exhausted_def.upgrade is not None
                            and exhausted_def.upgrade.on_exhaust is not None
                        ):
                            on_exhaust_actions = exhausted_def.upgrade.on_exhaust
                        if on_exhaust_actions:
                            self.interpreter.execute_actions(
                                on_exhaust_actions, battle, source="player",
                            )
                    # Global ON_CARD_EXHAUSTED trigger (Dark Embrace, Feel No Pain)
                    td.fire(battle.player, StatusTrigger.ON_CARD_EXHAUSTED, battle, "player")

                # ON_BLOCK_GAINED (Juggernaut)
                if block_delta > 0:
                    td.fire(battle.player, StatusTrigger.ON_BLOCK_GAINED, battle, "player")

                # ON_HP_LOSS from a card (Rupture)
                hp_delta = player_hp_before - battle.player.current_hp
                if hp_delta > 0:
                    td.fire(battle.player, StatusTrigger.ON_HP_LOSS, battle, "player")

                # Enemy reactive hooks (Enrage, Sharp Hide, Curl Up, etc.)
                self._post_card_play_hooks(
                    battle, enemy_datas, card_def, enemy_hp_before,
                )

                battle._check_battle_over()

            if battle.is_over:
                break

            # End turn — handle ethereal/retain before discarding
            self._end_turn_card_handling(battle)

            # Decay player statuses (vuln, weak, frail, entangled, temporary statuses)
            decay_statuses(battle.player, self.registry.status_defs)

            # Fire ON_TURN_END on player (Metallicize, Combust)
            td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

            # ON_HP_LOSS from Combust (triggers Rupture)
            # Check if Combust caused HP loss
            # (Combust fires lose_hp which is direct HP loss from a power,
            #  but in real STS, Combust does trigger Rupture)
            # This is handled by the turn-end trigger itself.

            if battle.is_over:
                break

            # Enemy turn
            for i, enemy in enumerate(battle.enemies):
                if enemy.is_dead or battle.is_over:
                    continue

                # Track HP before Lagavulin sleep check
                hp_before_enemy_turn = enemy.current_hp

                # Fire ON_TURN_START on enemy (currently no enemy ON_TURN_START triggers)
                td.fire(enemy, StatusTrigger.ON_TURN_START, battle, str(i))

                damage_dealt_to_player = self.enemy_ai.execute_intent(enemy, i, battle)

                # Fire ON_ATTACKED on player when enemy deals attack damage
                if damage_dealt_to_player > 0:
                    move_type = getattr(enemy, "_current_move_type", "")
                    if move_type in ("attack", "attack_defend"):
                        hits = enemy.intent_hits or 1
                        for _ in range(hits):
                            if battle.is_over:
                                break
                            td.fire(
                                battle.player, StatusTrigger.ON_ATTACKED,
                                battle, "player", attacker_idx=i,
                            )

                # Fire ON_TURN_END on enemy (Ritual, Metallicize)
                td.fire(enemy, StatusTrigger.ON_TURN_END, battle, str(i))

                decay_statuses(enemy, self.registry.status_defs)

            battle._check_battle_over()

        if not battle.is_over:
            battle.is_over = True
            battle.battle_result = "loss"

        return BattleTelemetry(
            enemy_ids=enemy_ids,
            result=battle.battle_result or "loss",
            turns=battle.turn,
            player_hp_start=player_hp_start,
            player_hp_end=max(0, battle.player.current_hp),
            hp_lost=max(0, player_hp_start - battle.player.current_hp),
            damage_dealt=total_damage_dealt,
            block_gained=total_block_gained,
            cards_played=total_cards_played,
            cards_played_by_id=cards_played_by_id,
            enemy_moves_per_turn=enemy_moves_per_turn,
        )

    # ------------------------------------------------------------------
    # Status trigger helpers
    # ------------------------------------------------------------------

    def _fire_on_status_drawn(
        self,
        battle: BattleState,
        drawn_cards: list[CardInstance],
    ) -> None:
        """Fire ON_STATUS_DRAWN triggers for STATUS/CURSE cards drawn.

        Evolve triggers on STATUS cards only.
        Fire Breathing triggers on both STATUS and CURSE cards.
        We fire a single ON_STATUS_DRAWN event per qualifying card; the
        TriggerDispatcher iterates all statuses with that trigger.
        """
        for card_inst in drawn_cards:
            if battle.is_over:
                break
            card_def = self.registry.get_card(card_inst.card_id)
            if card_def is None:
                continue

            is_status = card_def.type == CardType.STATUS
            is_curse = card_def.type == CardType.CURSE

            if is_status or is_curse:
                # Fire Breathing triggers on both; Evolve only on STATUS.
                # The dispatcher fires ALL statuses with ON_STATUS_DRAWN trigger.
                # We need to differentiate: Evolve should only fire on STATUS.
                # We handle this by checking inside _fire_selective_status_drawn.
                self._fire_selective_status_drawn(battle, is_status, is_curse)

    def _fire_selective_status_drawn(
        self,
        battle: BattleState,
        is_status: bool,
        is_curse: bool,
    ) -> None:
        """Fire ON_STATUS_DRAWN selectively based on card type.

        Evolve triggers only on STATUS cards.
        Fire Breathing triggers on both STATUS and CURSE cards.
        """
        td = self.trigger_dispatcher
        player = battle.player

        for status_id in list(player.status_effects.keys()):
            stacks = player.status_effects.get(status_id, 0)
            if stacks <= 0:
                continue

            defn = td.status_defs.get(status_id)
            if defn is None:
                continue

            actions = defn.triggers.get(StatusTrigger.ON_STATUS_DRAWN)
            if not actions:
                continue

            # Evolve only triggers on STATUS, not CURSE
            if status_id == "Evolve" and not is_status:
                continue

            # Fire Breathing triggers on both STATUS and CURSE
            # (and any other ON_STATUS_DRAWN status triggers on both by default)

            scaled = td._scale_actions(actions, stacks)
            self.interpreter.execute_actions(scaled, battle, source="player")

    # ------------------------------------------------------------------
    # Post-card-play hooks
    # ------------------------------------------------------------------

    def _post_card_play_hooks(
        self,
        battle: BattleState,
        enemy_datas: list[dict[str, Any]],
        card_def: CardDefinition,
        enemy_hp_before: dict[int, int],
    ) -> None:
        """Process reactive hooks after the player plays a card."""
        card_type = card_def.type

        for i, enemy in enumerate(battle.enemies):
            if enemy.is_dead:
                # Check on-death hooks for newly dead enemies
                self._check_on_death(enemy, enemy_datas[i], battle)
                # Check split mechanics for newly dead enemies
                self._check_split(enemy, i, enemy_datas, battle)
                continue

            key = self.enemy_ai._enemy_key(enemy)
            state = self.enemy_ai._enemy_state.setdefault(key, {})
            prev_hp = enemy_hp_before.get(id(enemy), enemy.current_hp)
            damage_taken = prev_hp - enemy.current_hp

            # Enrage: enemy gains strength when player plays a Skill
            if card_type == CardType.SKILL:
                enrage = enemy.status_effects.get("Enrage", 0)
                if enrage > 0:
                    apply_status(enemy, "strength", enrage)

            # Sharp Hide: player takes damage when playing Attack card
            if card_type == CardType.ATTACK:
                sharp_hide = enemy.status_effects.get("Sharp Hide", 0)
                if sharp_hide > 0:
                    battle.player.current_hp = max(
                        0, battle.player.current_hp - sharp_hide,
                    )

            if damage_taken > 0:
                # Curl Up: gain block on first attack damage
                curl_up_val = state.get("curl_up")
                if curl_up_val is not None:
                    enemy.block += curl_up_val
                    del state["curl_up"]

                # Angry: gain strength when taking attack damage
                angry = enemy.status_effects.get("Angry", 0)
                if angry > 0:
                    apply_status(enemy, "strength", angry)

                # Guardian mode shift: track damage
                edata = enemy_datas[i]
                if edata.get("pattern", {}).get("type") == "guardian_mode_shift":
                    if state.get("mode", "offensive") == "offensive":
                        state["damage_since_shift"] = (
                            state.get("damage_since_shift", 0) + damage_taken
                        )
                        threshold = state.get("current_threshold", 30)
                        if state["damage_since_shift"] >= threshold:
                            self._trigger_guardian_mode_shift(
                                enemy, i, edata, state, battle,
                            )

                # Lagavulin wake check: if sleeping and took HP damage
                edata = enemy_datas[i]
                if edata.get("pattern", {}).get("type") == "lagavulin":
                    if not state.get("woken"):
                        state["woken"] = True
                        state["stunned"] = True
                        enemy.status_effects.pop("Metallicize", None)

                # Check split conditions
                self._check_split(enemy, i, enemy_datas, battle)

    def _check_on_death(
        self,
        enemy: Enemy,
        enemy_data: dict[str, Any],
        battle: BattleState,
    ) -> None:
        """Execute on-death hooks when an enemy dies."""
        key = self.enemy_ai._enemy_key(enemy)
        state = self.enemy_ai._enemy_state.setdefault(key, {})
        if state.get("death_processed"):
            return
        state["death_processed"] = True

        on_death = enemy_data.get("on_death", [])
        for action in on_death:
            action_type = action.get("action_type", "")
            target = action.get("target", "player")
            if action_type == "apply_status" and target == "player":
                apply_status(
                    battle.player,
                    action["status_name"],
                    action.get("value", 1),
                )

    def _check_split(
        self,
        enemy: Enemy,
        enemy_idx: int,
        enemy_datas: list[dict[str, Any]],
        battle: BattleState,
    ) -> None:
        """Check and execute split mechanics for an enemy."""
        if enemy.is_dead:
            return

        key = self.enemy_ai._enemy_key(enemy)
        state = self.enemy_ai._enemy_state.setdefault(key, {})
        if state.get("has_split"):
            return

        edata = enemy_datas[enemy_idx]
        split = edata.get("special", {}).get("split")
        if split is None:
            return

        threshold_pct = split["hp_threshold_pct"]
        if enemy.current_hp > (enemy.max_hp * threshold_pct / 100):
            return

        # Execute split!
        state["has_split"] = True
        split_hp = enemy.current_hp

        # Kill the splitting enemy
        enemy.current_hp = 0

        # Spawn new enemies
        spawn_ids = split.get("spawn", [])
        for spawn_id in spawn_ids:
            spawn_data = self.registry.get_enemy_data(spawn_id)
            if spawn_data is None:
                continue

            if split.get("inherit_hp"):
                hp = split_hp
            else:
                hp = battle.rng.random_int(
                    spawn_data.get("hp_min", 20),
                    spawn_data.get("hp_max", 20),
                )

            new_enemy = Enemy(
                name=spawn_data.get("name", spawn_id),
                enemy_id=spawn_id,
                max_hp=hp,
                current_hp=hp,
            )
            battle.enemies.append(new_enemy)
            enemy_datas.append(spawn_data)

            # Initialize the new enemy's state
            new_idx = len(battle.enemies) - 1
            self.enemy_ai.init_enemy_state(
                new_enemy, spawn_data, battle, battle.rng, new_idx,
            )

    def _trigger_guardian_mode_shift(
        self,
        enemy: Enemy,
        enemy_idx: int,
        edata: dict[str, Any],
        state: dict,
        battle: BattleState,
    ) -> None:
        """Trigger Guardian's mode shift from offensive to defensive."""
        pattern = edata.get("pattern", {})
        block_on_shift = pattern.get("block_on_shift", 20)

        state["mode"] = "defensive"
        state["def_seq_counter"] = 0
        state["damage_since_shift"] = 0
        enemy.block += block_on_shift

    # ------------------------------------------------------------------
    # Card play helpers
    # ------------------------------------------------------------------

    def _get_playable_cards(
        self,
        battle: BattleState,
    ) -> list[tuple[CardInstance, CardDefinition]]:
        """Return cards in hand that the player can afford to play."""
        is_entangled = has_status(battle.player, "entangled")
        is_corrupted = has_status(battle.player, "Corruption")

        playable: list[tuple[CardInstance, CardDefinition]] = []
        for card_inst in battle.card_piles.hand:
            card_def = self.registry.get_card(card_inst.card_id)
            if card_def is None:
                continue

            if card_inst.cost_override is not None:
                cost = card_inst.cost_override
            elif (
                card_inst.upgraded
                and card_def.upgrade is not None
                and card_def.upgrade.cost is not None
            ):
                cost = card_def.upgrade.cost
            else:
                cost = card_def.cost

            # Corruption: skills cost 0
            if is_corrupted and card_def.type == CardType.SKILL:
                cost = 0

            if cost == -2:
                continue

            # Entangled: can't play Attack cards
            if is_entangled and card_def.type == CardType.ATTACK:
                continue

            # Check play restriction (e.g. Clash: only_attacks_in_hand)
            if card_def.play_restriction:
                if not self.interpreter._evaluate_condition(
                    card_def.play_restriction, battle, "player", None,
                ):
                    continue

            if cost == -1:
                playable.append((card_inst, card_def))
                continue
            if cost <= battle.player.energy:
                playable.append((card_inst, card_def))

        return playable

    def _move_innate_to_top(self, battle: BattleState) -> None:
        """Move cards with innate=True to the top of the draw pile.

        Respects upgrade overrides: if upgrade.innate is set and the card
        is upgraded, uses the upgrade value.
        """
        innate_cards: list[CardInstance] = []
        remaining: list[CardInstance] = []
        for card_inst in battle.card_piles.draw:
            card_def = self.registry.get_card(card_inst.card_id)
            if card_def is None:
                remaining.append(card_inst)
                continue

            is_innate = card_def.innate
            if (
                card_inst.upgraded
                and card_def.upgrade is not None
                and card_def.upgrade.innate is not None
            ):
                is_innate = card_def.upgrade.innate

            if is_innate:
                innate_cards.append(card_inst)
            else:
                remaining.append(card_inst)
        if innate_cards:
            battle.card_piles.draw = innate_cards + remaining

    def _end_turn_card_handling(self, battle: BattleState) -> None:
        """Handle ethereal/retain at end of turn, then discard remaining hand.

        Order matches real STS:
        1. Exhaust ethereal cards still in hand.
        2. Retain cards with retain=True (keep them in hand).
        3. Discard everything else.
        4. Clear enemy block and check battle over.
        """
        from sts_gen.sim.mechanics.card_piles import exhaust_card

        # Snapshot hand to iterate safely
        hand_snapshot = list(battle.card_piles.hand)

        # 1. Exhaust ethereal cards
        for card_inst in hand_snapshot:
            card_def = self.registry.get_card(card_inst.card_id)
            if card_def is not None and card_def.ethereal:
                if card_inst in battle.card_piles.hand:
                    exhaust_card(battle, card_inst)

        # 2+3. Separate retained cards from cards to discard
        retained: list[CardInstance] = []
        to_discard: list[CardInstance] = []
        for card_inst in list(battle.card_piles.hand):
            card_def = self.registry.get_card(card_inst.card_id)
            if card_def is not None and card_def.retain:
                retained.append(card_inst)
            else:
                to_discard.append(card_inst)

        # Discard non-retained cards
        battle.card_piles.discard.extend(to_discard)
        battle.card_piles.hand = retained

        # Clear enemy block and check
        for enemy in battle.living_enemies:
            enemy.clear_block()
        battle._check_battle_over()


# =====================================================================
# BatchRunner
# =====================================================================

def _run_single_encounter(
    registry: ContentRegistry,
    agent: PlayAgent,
    seed: int,
    encounter_config: dict[str, Any],
) -> RunTelemetry:
    """Run a single encounter with the given seed and configuration."""
    master_rng = GameRNG(seed)
    combat_rng = master_rng.fork("combat")

    # Build player
    player = Player(
        name="Ironclad", max_hp=80, current_hp=80, max_energy=3,
    )

    # Build deck
    custom_deck = encounter_config.get("custom_deck")
    if custom_deck is not None:
        deck_ids = custom_deck
    else:
        deck_ids = registry.get_starter_deck("ironclad")

    deck = [CardInstance(card_id=cid) for cid in deck_ids]

    # Build enemies
    enemy_ids = encounter_config.get("enemy_ids", ["cultist"])
    enemies: list[Enemy] = []
    for eid in enemy_ids:
        edata = registry.get_enemy_data(eid)
        if edata is not None:
            hp_min = edata.get("hp_min", 50)
            hp_max = edata.get("hp_max", hp_min)
            hp = combat_rng.random_int(hp_min, hp_max)
            enemies.append(Enemy(
                name=edata.get("name", eid),
                enemy_id=eid,
                max_hp=hp,
                current_hp=hp,
            ))
        else:
            enemies.append(Enemy(
                name=eid, enemy_id=eid, max_hp=50, current_hp=50,
            ))

    # Assemble battle
    battle = BattleState(
        player=player,
        enemies=enemies,
        card_piles=CardPiles(draw=deck),
        rng=combat_rng,
    )

    # Run
    interpreter = ActionInterpreter(card_registry=registry.cards)
    simulator = CombatSimulator(registry, interpreter, agent)
    battle_telemetry = simulator.run_combat(battle)

    return RunTelemetry(
        seed=seed,
        battles=[battle_telemetry],
        final_result=battle_telemetry.result,
        floors_reached=1,
        cards_in_deck=deck_ids,
    )


def _worker_run_single(args: tuple) -> RunTelemetry:
    """Top-level worker function for multiprocessing (must be picklable)."""
    cards_json_path, enemies_json_path, seed, encounter_config = args

    from sts_gen.sim.content.registry import ContentRegistry

    registry = ContentRegistry()
    registry.load_vanilla_cards(cards_json_path)
    registry.load_vanilla_enemies(enemies_json_path)
    registry.load_vanilla_status_effects()

    agent_rng = GameRNG(seed).fork("agent")
    agent = RandomAgent(rng=agent_rng)

    return _run_single_encounter(registry, agent, seed, encounter_config)


class BatchRunner:
    """Runs multiple simulation batches, optionally in parallel."""

    def __init__(
        self,
        registry: ContentRegistry,
        agent_class: type[PlayAgent] = RandomAgent,
    ) -> None:
        self.registry = registry
        self.agent_class = agent_class

    def run_batch(
        self,
        n_runs: int,
        encounter_config: dict[str, Any],
        base_seed: int = 42,
        parallel: bool = False,
    ) -> list[RunTelemetry]:
        """Run n_runs simulation batches."""
        seeds = [base_seed + i for i in range(n_runs)]

        if parallel and n_runs > 1:
            return self._run_parallel(seeds, encounter_config)
        return self._run_sequential(seeds, encounter_config)

    def _run_sequential(
        self,
        seeds: list[int],
        encounter_config: dict[str, Any],
    ) -> list[RunTelemetry]:
        results: list[RunTelemetry] = []
        for seed in seeds:
            agent_rng = GameRNG(seed).fork("agent")
            if self.agent_class is RandomAgent:
                agent = RandomAgent(rng=agent_rng)
            else:
                try:
                    agent = self.agent_class(rng=agent_rng)  # type: ignore[call-arg]
                except TypeError:
                    agent = self.agent_class()  # type: ignore[call-arg]

            result = _run_single_encounter(
                self.registry, agent, seed, encounter_config,
            )
            results.append(result)
        return results

    def _run_parallel(
        self,
        seeds: list[int],
        encounter_config: dict[str, Any],
    ) -> list[RunTelemetry]:
        """Run simulations in parallel using multiprocessing.

        Rather than pickling the registry, we pass file paths and reload
        in each worker process.
        """
        from sts_gen.sim.content.registry import _DEFAULT_CARDS_PATH, _DEFAULT_ENEMIES_PATH

        cards_path = str(_DEFAULT_CARDS_PATH)
        enemies_path = str(_DEFAULT_ENEMIES_PATH)

        work_items = [
            (cards_path, enemies_path, seed, encounter_config)
            for seed in seeds
        ]

        n_workers = min(len(seeds), multiprocessing.cpu_count() or 1)

        with multiprocessing.Pool(processes=n_workers) as pool:
            results = pool.map(_worker_run_single, work_items)

        return results
