"""Tests for RunManager -- full Act 1 runs."""

import pytest

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.dungeon.run_manager import RunManager
from sts_gen.sim.play_agents.random_agent import RandomAgent
from sts_gen.sim.runner import BatchRunner
from sts_gen.sim.telemetry import RunTelemetry


@pytest.fixture
def registry():
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_encounters()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    return reg


def _make_run_manager(registry, seed=42):
    rng = GameRNG(seed=seed)
    agent = RandomAgent(rng=rng.fork("agent"))
    return RunManager(registry, agent, rng)


class TestRunManagerBasic:
    def test_run_completes_without_error(self, registry):
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        assert isinstance(telemetry, RunTelemetry)

    def test_final_result_is_win_or_loss(self, registry):
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        assert telemetry.final_result in ("win", "loss")

    def test_floors_reached_at_least_1(self, registry):
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        assert telemetry.floors_reached >= 1

    def test_battles_list_populated(self, registry):
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        assert len(telemetry.battles) >= 1

    def test_seed_stored_in_telemetry(self, registry):
        rm = _make_run_manager(registry, seed=99)
        telemetry = rm.run_act_1()
        assert telemetry.seed == 99


class TestRunManagerPersistence:
    def test_deck_grows_from_card_rewards(self, registry):
        """Over multiple runs, most should gain at least 1 card."""
        gained_cards = 0
        for seed in range(20):
            rm = _make_run_manager(registry, seed=seed)
            telemetry = rm.run_act_1()
            if len(telemetry.cards_added) > 0:
                gained_cards += 1
        # Most runs should gain at least one card
        assert gained_cards > 5

    def test_gold_accumulated(self, registry):
        """Gold should be earned from combat victories."""
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        assert telemetry.gold_earned > 0

    def test_hp_tracked_per_floor(self, registry):
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        assert len(telemetry.hp_at_each_floor) >= 1
        # First floor HP should be starting HP
        assert telemetry.hp_at_each_floor[0] == 80

    def test_cards_in_deck_at_end(self, registry):
        rm = _make_run_manager(registry, seed=42)
        telemetry = rm.run_act_1()
        # Should have at least the starter deck
        assert len(telemetry.cards_in_deck) >= 10


class TestRunManagerRelicsAndPotions:
    def test_starter_relic_is_burning_blood(self, registry):
        """RunManager should start with Burning Blood."""
        rm = _make_run_manager(registry, seed=42)
        game_state = rm._init_game_state()
        assert "burning_blood" in game_state.relics

    def test_relics_accumulate(self, registry):
        """Over many runs, some should gain relics from elites/treasure."""
        total_relics = 0
        for seed in range(20):
            rm = _make_run_manager(registry, seed=seed)
            telemetry = rm.run_act_1()
            total_relics += len(telemetry.relics_collected)
        # At least some runs should gain relics
        assert total_relics > 0


class TestRunManagerDeterminism:
    def test_same_seed_same_result(self, registry):
        rm1 = _make_run_manager(registry, seed=42)
        t1 = rm1.run_act_1()
        rm2 = _make_run_manager(registry, seed=42)
        t2 = rm2.run_act_1()
        assert t1.final_result == t2.final_result
        assert t1.floors_reached == t2.floors_reached
        assert len(t1.battles) == len(t2.battles)

    def test_different_seeds_different_outcomes(self, registry):
        """Different seeds should produce some variation."""
        results = set()
        for seed in range(20):
            rm = _make_run_manager(registry, seed=seed)
            telemetry = rm.run_act_1()
            results.add((telemetry.final_result, telemetry.floors_reached))
        assert len(results) > 1


class TestBatchRunnerIntegration:
    def test_run_full_act_batch(self, registry):
        br = BatchRunner(registry, RandomAgent)
        results = br.run_full_act_batch(n_runs=5, base_seed=42)
        assert len(results) == 5
        for r in results:
            assert isinstance(r, RunTelemetry)
            assert r.final_result in ("win", "loss")

    def test_batch_deterministic(self, registry):
        br = BatchRunner(registry, RandomAgent)
        r1 = br.run_full_act_batch(n_runs=3, base_seed=42)
        r2 = br.run_full_act_batch(n_runs=3, base_seed=42)
        for a, b in zip(r1, r2):
            assert a.final_result == b.final_result
            assert a.floors_reached == b.floors_reached
