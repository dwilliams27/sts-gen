"""Full integration tests -- load vanilla content, run combats, verify telemetry.

These tests serve as the Phase 1 exit gate: if they pass, the simulation
pipeline is working end-to-end.
"""

import pytest

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.play_agents.random_agent import RandomAgent
from sts_gen.sim.runner import BatchRunner, CombatSimulator
from sts_gen.sim.telemetry import BattleTelemetry, RunTelemetry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    """Load vanilla content once for the entire test module."""
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    return reg


def _build_battle(
    registry: ContentRegistry,
    seed: int,
    enemy_ids: list[str] | None = None,
) -> BattleState:
    """Build a ready-to-run BattleState with Ironclad starter deck."""
    rng = GameRNG(seed)
    combat_rng = rng.fork("combat")

    player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)

    deck_ids = registry.get_starter_deck("ironclad")
    deck = [CardInstance(card_id=cid) for cid in deck_ids]

    enemy_id_list = enemy_ids or ["jaw_worm"]
    enemies: list[Enemy] = []
    for eid in enemy_id_list:
        edata = registry.get_enemy_data(eid)
        if edata is not None:
            hp = combat_rng.random_int(edata["hp_min"], edata["hp_max"])
            enemies.append(Enemy(
                name=edata["name"],
                enemy_id=eid,
                max_hp=hp,
                current_hp=hp,
            ))
        else:
            enemies.append(Enemy(
                name=eid, enemy_id=eid, max_hp=50, current_hp=50,
            ))

    return BattleState(
        player=player,
        enemies=enemies,
        card_piles=CardPiles(draw=deck),
        rng=combat_rng,
    )


# ---------------------------------------------------------------------------
# Test 1: Load vanilla content, run 10 combats, all complete without error
# ---------------------------------------------------------------------------

class TestVanillaContentRuns:
    def test_run_10_combats_complete(self, registry):
        """Run 10 combats with the Ironclad starter deck vs Jaw Worm.
        All must complete without exceptions."""
        for seed in range(10):
            battle = _build_battle(registry, seed=seed, enemy_ids=["jaw_worm"])
            agent_rng = GameRNG(seed).fork("agent")
            agent = RandomAgent(rng=agent_rng)
            interpreter = ActionInterpreter(card_registry=registry.cards)
            sim = CombatSimulator(registry, interpreter, agent)

            telemetry = sim.run_combat(battle)

            assert telemetry.result in ("win", "loss")
            assert telemetry.turns > 0
            assert battle.is_over


# ---------------------------------------------------------------------------
# Test 2: Run 100 combats vs jaw_worm, check win rate > 80%
# ---------------------------------------------------------------------------

class TestWinRate:
    def test_jaw_worm_win_rate_above_80_percent(self, registry):
        """With the Ironclad starter deck vs a single Jaw Worm, the random
        agent should win the majority of the time (> 80%).

        Jaw Worm is an Act 1 enemy and the starter deck should handle it."""
        runner = BatchRunner(registry)
        encounter_config = {"enemy_ids": ["jaw_worm"]}

        results = runner.run_batch(
            n_runs=100,
            encounter_config=encounter_config,
            base_seed=1000,
            parallel=False,
        )

        assert len(results) == 100
        wins = sum(1 for r in results if r.final_result == "win")
        win_rate = wins / len(results)

        # The random agent should win > 80% against jaw_worm
        assert win_rate > 0.80, (
            f"Win rate {win_rate:.1%} is below 80%. "
            f"Wins: {wins}/100"
        )


# ---------------------------------------------------------------------------
# Test 3: Telemetry fields are non-zero
# ---------------------------------------------------------------------------

class TestTelemetryFields:
    def test_telemetry_fields_populated(self, registry):
        """Run a batch and verify that telemetry fields have sensible values."""
        runner = BatchRunner(registry)
        encounter_config = {"enemy_ids": ["jaw_worm"]}

        results = runner.run_batch(
            n_runs=20,
            encounter_config=encounter_config,
            base_seed=5000,
            parallel=False,
        )

        assert len(results) == 20

        total_damage = 0
        total_cards = 0
        total_turns = 0
        total_block = 0

        for run in results:
            assert run.seed >= 5000
            assert len(run.battles) == 1
            assert run.final_result in ("win", "loss")
            assert run.floors_reached == 1
            assert len(run.cards_in_deck) == 10  # starter deck size

            bt = run.battles[0]
            assert bt.turns > 0
            assert bt.player_hp_start == 80
            assert bt.player_hp_end >= 0
            assert bt.hp_lost >= 0
            assert bt.damage_dealt >= 0
            assert bt.cards_played >= 0

            total_damage += bt.damage_dealt
            total_cards += bt.cards_played
            total_turns += bt.turns
            total_block += bt.block_gained

        # Over 20 runs, aggregates should be significantly non-zero
        assert total_damage > 0, "No damage dealt across 20 runs"
        assert total_cards > 0, "No cards played across 20 runs"
        assert total_turns > 0, "No turns taken across 20 runs"
        assert total_block > 0, "No block gained across 20 runs"

    def test_cards_played_by_id_is_populated(self, registry):
        """The cards_played_by_id dict should contain at least strike/defend/bash."""
        battle = _build_battle(registry, seed=42, enemy_ids=["jaw_worm"])
        agent_rng = GameRNG(42).fork("agent")
        agent = RandomAgent(rng=agent_rng)
        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter, agent)

        telemetry = sim.run_combat(battle)

        # At least some cards should have been played
        assert len(telemetry.cards_played_by_id) > 0
        # The total from the dict should match cards_played
        assert sum(telemetry.cards_played_by_id.values()) == telemetry.cards_played

    def test_enemy_ids_recorded(self, registry):
        """BattleTelemetry should record the enemy IDs."""
        battle = _build_battle(registry, seed=99, enemy_ids=["jaw_worm"])
        agent_rng = GameRNG(99).fork("agent")
        agent = RandomAgent(rng=agent_rng)
        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter, agent)

        telemetry = sim.run_combat(battle)

        assert telemetry.enemy_ids == ["jaw_worm"]
