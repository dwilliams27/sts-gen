"""Integration tests for baseline generation, save, and load."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sts_gen.balance.baselines import generate_baseline, load_baseline, save_baseline
from sts_gen.balance.models import VanillaBaseline
from sts_gen.sim.content.registry import ContentRegistry


@pytest.fixture()
def registry() -> ContentRegistry:
    """Fully loaded vanilla registry."""
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    reg.load_vanilla_encounters()
    return reg


class TestGenerateBaseline:
    def test_small_batch(self, registry: ContentRegistry) -> None:
        """100 runs should produce a valid baseline with reasonable data."""
        baseline = generate_baseline(registry, num_runs=100, min_co_occurrence=5)
        assert baseline.agent == "heuristic"
        assert baseline.num_runs == 100
        assert baseline.global_metrics.total_runs == 100
        assert baseline.global_metrics.wins >= 0
        assert baseline.global_metrics.win_rate >= 0.0
        assert len(baseline.card_metrics) > 0

        # Starter cards should be present
        card_ids = {m.card_id for m in baseline.card_metrics}
        assert "strike" in card_ids
        assert "defend" in card_ids
        assert "bash" in card_ids

    def test_card_offers_recorded(self, registry: ContentRegistry) -> None:
        """Verify that card_offers/picks telemetry is populated."""
        from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
        from sts_gen.sim.runner import BatchRunner

        runner = BatchRunner(registry, agent_class=HeuristicAgent)
        results = runner.run_full_act_batch(n_runs=20, base_seed=42)

        # At least some runs should have card offers (from combat wins)
        runs_with_offers = [r for r in results if len(r.card_offers) > 0]
        assert len(runs_with_offers) > 0

        # Offers and picks should have same length
        for r in results:
            assert len(r.card_offers) == len(r.card_picks)


class TestSaveLoadBaseline:
    def test_roundtrip(self, registry: ContentRegistry, tmp_path: Path) -> None:
        """Generate → save → load should produce identical data."""
        baseline = generate_baseline(registry, num_runs=50, min_co_occurrence=3)
        path = tmp_path / "test_baseline.json"
        save_baseline(baseline, path)

        assert path.exists()
        loaded = load_baseline(path)
        assert loaded.agent == baseline.agent
        assert loaded.num_runs == baseline.num_runs
        assert loaded.global_metrics == baseline.global_metrics
        assert len(loaded.card_metrics) == len(baseline.card_metrics)

    def test_save_creates_dirs(self, tmp_path: Path) -> None:
        """save_baseline should create parent directories."""
        from sts_gen.balance.models import GlobalMetrics

        baseline = VanillaBaseline(
            agent="test",
            num_runs=0,
            generated_at="2026-01-01T00:00:00+00:00",
            global_metrics=GlobalMetrics(
                total_runs=0, wins=0, losses=0, win_rate=0.0,
                avg_floors_reached=0.0, avg_battles_won=0.0,
                avg_deck_size=0.0, avg_gold_earned=0.0,
            ),
            card_metrics=[],
            relic_metrics=[],
            synergies=[],
            anti_synergies=[],
        )
        path = tmp_path / "sub" / "dir" / "baseline.json"
        save_baseline(baseline, path)
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["agent"] == "test"

    def test_load_validates(self, tmp_path: Path) -> None:
        """Loading invalid JSON should raise a validation error."""
        path = tmp_path / "bad.json"
        path.write_text('{"agent": "test"}')
        with pytest.raises(Exception):
            load_baseline(path)
