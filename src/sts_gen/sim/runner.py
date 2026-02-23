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
from sts_gen.ir.cards import CardTarget
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.block import gain_block
from sts_gen.sim.mechanics.damage import deal_damage
from sts_gen.sim.mechanics.card_piles import draw_cards
from sts_gen.sim.mechanics.status_effects import apply_status, decay_statuses
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

    Supports three pattern types from enemy definitions:
    - fixed_sequence: cycle through moves in order (loop from a given index)
    - weighted_random: pick moves by weight, respecting max_consecutive
    - simple sequential fallback: cycle through moves list
    """

    def __init__(self, interpreter: ActionInterpreter) -> None:
        self._interpreter = interpreter
        self._move_counters: dict[str, int] = {}
        self._last_moves: dict[str, list[str]] = {}

    def determine_intent(
        self,
        enemy: Enemy,
        enemy_data: dict[str, Any],
        battle: BattleState,
        rng: GameRNG,
    ) -> None:
        """Set the enemy's intent for this turn."""
        moves = enemy_data.get("moves", [])
        if not moves:
            enemy.intent = "Attack"
            enemy.intent_damage = 6
            enemy.intent_hits = 1
            return

        key = f"{enemy.enemy_id}_{id(enemy)}"
        pattern = enemy_data.get("pattern", {})
        pattern_type = pattern.get("type", "sequential")
        counter = self._move_counters.get(key, 0)
        last_moves = self._last_moves.get(key, [])

        move = None

        if pattern_type == "fixed_sequence":
            sequence = pattern.get("sequence", [m["id"] for m in moves])
            loop_from = pattern.get("loop_from", 0)

            if counter < len(sequence):
                move_id = sequence[counter]
            else:
                loop_idx = loop_from + ((counter - len(sequence)) % (len(sequence) - loop_from))
                move_id = sequence[loop_idx]

            move = self._find_move(moves, move_id)

        elif pattern_type == "weighted_random":
            opening_move = pattern.get("opening_move")
            max_consecutive = pattern.get("max_consecutive", 3)
            weights = pattern.get("weights", {})

            if counter == 0 and opening_move:
                move = self._find_move(moves, opening_move)
            else:
                # Filter out moves that have been used max_consecutive times in a row
                available = []
                available_weights = []
                for m in moves:
                    mid = m["id"]
                    w = weights.get(mid, 1)
                    if w <= 0:
                        continue
                    # Check consecutive usage
                    if len(last_moves) >= max_consecutive and all(
                        lm == mid for lm in last_moves[-max_consecutive:]
                    ):
                        continue
                    available.append(m)
                    available_weights.append(w)

                if not available:
                    available = moves
                    available_weights = [weights.get(m["id"], 1) for m in moves]

                # Weighted random selection
                total = sum(available_weights)
                roll = rng.random_float() * total
                cumulative = 0
                move = available[0]
                for m, w in zip(available, available_weights):
                    cumulative += w
                    if roll <= cumulative:
                        move = m
                        break

        else:
            # Simple sequential
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
        enemy.intent = move.get("name", "Unknown")
        move_type = move.get("type", "attack")

        if move_type in ("attack", "attack_defend"):
            # Handle damage range (e.g., Red Louse)
            if "damage_min" in move:
                damage = rng.random_int(move["damage_min"], move["damage_max"])
            else:
                damage = move.get("damage", 6)
            enemy.intent_damage = damage
            enemy.intent_hits = move.get("hits", 1)
        else:
            enemy.intent_damage = None
            enemy.intent_hits = None

        # Store current move for execute_intent
        enemy._current_move = move  # type: ignore[attr-defined]
        enemy._current_move_type = move_type  # type: ignore[attr-defined]

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

        if move_type in ("attack", "attack_defend"):
            base_damage = enemy.intent_damage or 6
            hits = enemy.intent_hits or 1
            damage_dealt = deal_damage(
                battle, source_idx=enemy_idx, target_idx="player",
                base_damage=base_damage, hits=hits,
            )

        if move_type in ("defend", "attack_defend"):
            block_amount = move.get("block", 0) if move else 0
            if block_amount > 0:
                gain_block(enemy, block_amount)

        if move_type in ("buff", "debuff"):
            if move is not None:
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

        battle._check_battle_over()
        return damage_dealt

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

    def run_combat(self, battle: BattleState) -> BattleTelemetry:
        """Run a combat to completion, returning telemetry."""
        player_hp_start = battle.player.current_hp
        total_damage_dealt = 0
        total_block_gained = 0
        total_cards_played = 0
        cards_played_by_id: dict[str, int] = {}
        enemy_ids = [e.enemy_id for e in battle.enemies]

        # Setup: shuffle draw pile
        battle.rng.shuffle(battle.card_piles.draw)

        # Load enemy data
        enemy_datas: list[dict[str, Any]] = []
        for enemy in battle.enemies:
            edata = self.registry.get_enemy_data(enemy.enemy_id)
            enemy_datas.append(edata if edata is not None else {})

        enemy_moves_per_turn: list[list[str]] = []

        # Main combat loop
        while not battle.is_over and battle.turn < _MAX_TURNS:
            # Start turn
            battle.start_turn()

            # Determine enemy intents
            turn_moves: list[str] = []
            for i, enemy in enumerate(battle.enemies):
                if not enemy.is_dead:
                    self.enemy_ai.determine_intent(
                        enemy, enemy_datas[i], battle, battle.rng,
                    )
                    turn_moves.append(enemy.intent or "Unknown")
            enemy_moves_per_turn.append(turn_moves)

            # Draw cards
            draw_cards(battle, 5)

            # Player action loop
            while not battle.is_over:
                playable = self._get_playable_cards(battle)
                choice = self.agent.choose_card_to_play(battle, playable)

                if choice is None:
                    break

                card_instance, card_def, chosen_target = choice

                block_before = battle.player.block
                enemy_hp_before = sum(
                    e.current_hp for e in battle.enemies if not e.is_dead
                )

                self.interpreter.play_card(
                    card_def, battle, card_instance, chosen_target=chosen_target,
                )

                total_cards_played += 1
                cards_played_by_id[card_def.id] = (
                    cards_played_by_id.get(card_def.id, 0) + 1
                )

                block_delta = max(0, battle.player.block - block_before)
                total_block_gained += block_delta

                enemy_hp_after = sum(
                    e.current_hp for e in battle.enemies if not e.is_dead
                )
                total_damage_dealt += max(0, enemy_hp_before - enemy_hp_after)

                battle._check_battle_over()

            if battle.is_over:
                break

            # End turn
            battle.end_turn()
            decay_statuses(battle.player)

            # Metallicize: gain block at end of turn (not affected by dex/frail)
            metallicize_stacks = battle.player.status_effects.get("Metallicize", 0)
            if metallicize_stacks > 0:
                battle.player.block += metallicize_stacks

            if battle.is_over:
                break

            # Enemy turn
            for i, enemy in enumerate(battle.enemies):
                if enemy.is_dead or battle.is_over:
                    continue
                # Ritual: grant strength each turn before acting
                ritual_stacks = enemy.status_effects.get("Ritual", 0)
                if ritual_stacks > 0:
                    apply_status(enemy, "strength", ritual_stacks)
                self.enemy_ai.execute_intent(enemy, i, battle)
                decay_statuses(enemy)

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

    def _get_playable_cards(
        self,
        battle: BattleState,
    ) -> list[tuple[CardInstance, CardDefinition]]:
        """Return cards in hand that the player can afford to play."""
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

            if cost == -2:
                continue
            if cost == -1:
                playable.append((card_inst, card_def))
                continue
            if cost <= battle.player.energy:
                playable.append((card_inst, card_def))

        return playable


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
