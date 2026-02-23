"""Shared fixtures and helpers for simulation tests."""

from __future__ import annotations

from typing import Any

import pytest

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.runner import BatchRunner
from sts_gen.sim.telemetry import RunTelemetry


@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    """Module-scoped registry with vanilla content loaded once."""
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    return reg


def run_experiment(
    registry: ContentRegistry,
    deck: list[str],
    enemy_ids: list[str],
    n_runs: int = 500,
    base_seed: int = 42,
) -> list[RunTelemetry]:
    """Run a batch of combats and return telemetry results."""
    runner = BatchRunner(registry)
    config: dict[str, Any] = {"custom_deck": deck, "enemy_ids": enemy_ids}
    return runner.run_batch(n_runs, config, base_seed=base_seed)


def mean_stat(results: list[RunTelemetry], field: str) -> float:
    """Extract the mean of a BattleTelemetry field across results."""
    values = [getattr(r.battles[0], field) for r in results]
    return sum(values) / len(values)


def win_rate(results: list[RunTelemetry]) -> float:
    """Fraction of results that are wins."""
    wins = sum(1 for r in results if r.battles[0].result == "win")
    return wins / len(results)
