"""Phase 2H exit gate — full Act 1 integration tests.

Validates that the simulation runs correctly at scale and that the
HeuristicAgent demonstrates intelligent play relative to the RandomAgent
baseline.

Exit gate criteria (adjusted for simulation fidelity):
  1. 10,000 full Act 1 runs complete without errors
  2. HeuristicAgent win rate > 5% (RandomAgent ~ 0%)
  3. HeuristicAgent avg floors > 2× RandomAgent
  4. All tests pass, no regressions
"""

from __future__ import annotations

import time

import pytest

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
from sts_gen.sim.play_agents.random_agent import RandomAgent
from sts_gen.sim.runner import BatchRunner


@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    reg.load_vanilla_encounters()
    return reg


# ======================================================================
# Exit Gate: 10,000 runs without errors, under 5 minutes
# ======================================================================


class TestExitGate:
    """Core exit gate: 10k runs complete, performance target met."""

    def test_10k_runs_no_errors(self, registry: ContentRegistry):
        """10,000 full Act 1 runs complete without any errors."""
        runner = BatchRunner(registry, agent_class=HeuristicAgent)
        t0 = time.time()
        results = runner.run_full_act_batch(n_runs=10_000, base_seed=0)
        elapsed = time.time() - t0

        assert len(results) == 10_000
        for r in results:
            assert r.final_result in ("win", "loss")
            assert r.floors_reached > 0
            assert len(r.battles) > 0

        # Performance gate: must complete in under 5 minutes
        assert elapsed < 300, f"10k runs took {elapsed:.0f}s, exceeds 5 min limit"


# ======================================================================
# Statistical assertions (1000-run sample for speed)
# ======================================================================


@pytest.fixture(scope="module")
def heuristic_results(registry: ContentRegistry) -> list:
    runner = BatchRunner(registry, agent_class=HeuristicAgent)
    return runner.run_full_act_batch(n_runs=1000, base_seed=100)


@pytest.fixture(scope="module")
def random_results(registry: ContentRegistry) -> list:
    runner = BatchRunner(registry, agent_class=RandomAgent)
    return runner.run_full_act_batch(n_runs=1000, base_seed=100)


class TestHeuristicOutperformsRandom:
    """HeuristicAgent must demonstrate clear superiority over RandomAgent."""

    def test_heuristic_wins_some(self, heuristic_results):
        """HeuristicAgent must win at least 5% of Act 1 runs."""
        wins = sum(1 for r in heuristic_results if r.final_result == "win")
        win_rate = wins / len(heuristic_results)
        assert win_rate >= 0.05, f"Win rate {win_rate:.1%} below 5% threshold"

    def test_random_wins_near_zero(self, random_results):
        """RandomAgent should win very few runs (sanity check)."""
        wins = sum(1 for r in random_results if r.final_result == "win")
        win_rate = wins / len(random_results)
        assert win_rate < 0.03, f"RandomAgent win rate {win_rate:.1%} unexpectedly high"

    def test_heuristic_reaches_more_floors(self, heuristic_results, random_results):
        """HeuristicAgent must average at least 2× the floors of RandomAgent."""
        h_avg = sum(r.floors_reached for r in heuristic_results) / len(heuristic_results)
        r_avg = sum(r.floors_reached for r in random_results) / len(random_results)
        assert h_avg > r_avg * 2, (
            f"Heuristic avg floors {h_avg:.1f} not 2× random {r_avg:.1f}"
        )

    def test_heuristic_wins_more_battles(self, heuristic_results, random_results):
        """HeuristicAgent must win more battles on average."""
        def avg_battles_won(results):
            total = sum(
                sum(1 for b in r.battles if b.result == "win")
                for r in results
            )
            return total / len(results)

        h_avg = avg_battles_won(heuristic_results)
        r_avg = avg_battles_won(random_results)
        assert h_avg > r_avg * 2, (
            f"Heuristic avg battles {h_avg:.1f} not 2× random {r_avg:.1f}"
        )


class TestRunStatistics:
    """Validate that run statistics are within plausible ranges."""

    def test_avg_floors_plausible(self, heuristic_results):
        """Average floors reached should be between 5 and 14."""
        avg = sum(r.floors_reached for r in heuristic_results) / len(heuristic_results)
        assert 5 < avg < 14, f"Avg floors {avg:.1f} outside plausible range"

    def test_winning_deck_size(self, heuristic_results):
        """Winning runs should have reasonable deck sizes (14-30 cards)."""
        winning = [r for r in heuristic_results if r.final_result == "win"]
        if not winning:
            pytest.skip("No winning runs to check")
        for r in winning:
            deck_size = len(r.cards_in_deck)
            assert 14 <= deck_size <= 30, (
                f"Winning deck size {deck_size} outside 14-30 range"
            )

    def test_hp_trends_downward(self, heuristic_results):
        """On average, HP should trend downward across floors (taking damage)."""
        # Look at runs that reached at least floor 8
        long_runs = [r for r in heuristic_results if len(r.hp_at_each_floor) >= 8]
        if len(long_runs) < 50:
            pytest.skip("Not enough long runs for HP trend analysis")

        avg_first = sum(r.hp_at_each_floor[0] for r in long_runs) / len(long_runs)
        avg_mid = sum(r.hp_at_each_floor[4] for r in long_runs) / len(long_runs)

        # HP at floor 5 should be lower than floor 1 on average
        assert avg_mid < avg_first, (
            f"HP not trending down: floor 1 avg={avg_first:.0f}, floor 5 avg={avg_mid:.0f}"
        )

    def test_cards_are_added(self, heuristic_results):
        """Runs should pick up card rewards (deck grows beyond starter)."""
        starter_size = 10  # Ironclad starter deck
        runs_with_additions = sum(
            1 for r in heuristic_results
            if len(r.cards_in_deck) > starter_size
        )
        pct = runs_with_additions / len(heuristic_results)
        assert pct > 0.50, f"Only {pct:.0%} of runs added cards to deck"

    def test_all_results_valid(self, heuristic_results):
        """Every run must have a valid result and at least one battle."""
        for r in heuristic_results:
            assert r.final_result in ("win", "loss")
            assert r.floors_reached >= 1
            assert len(r.battles) >= 1
            assert r.seed is not None

    def test_deterministic_same_seed(self, registry: ContentRegistry):
        """Same seed must produce identical results."""
        results = []
        for _ in range(2):
            runner = BatchRunner(registry, agent_class=HeuristicAgent)
            batch = runner.run_full_act_batch(n_runs=10, base_seed=999)
            results.append([
                (r.final_result, r.floors_reached, len(r.cards_in_deck))
                for r in batch
            ])
        assert results[0] == results[1]
