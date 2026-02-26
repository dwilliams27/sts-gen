"""Baseline generation: run sims, compute metrics, save/load JSON.

Orchestrates BatchRunner → metric computation → VanillaBaseline model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sts_gen.balance.metrics import (
    compute_card_metrics,
    compute_global_metrics,
    compute_relic_metrics,
    compute_synergies,
)
from sts_gen.balance.models import VanillaBaseline
from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
from sts_gen.sim.runner import BatchRunner

if TYPE_CHECKING:
    from sts_gen.sim.content.registry import ContentRegistry


def generate_baseline(
    registry: ContentRegistry,
    num_runs: int = 50_000,
    base_seed: int = 42,
    min_co_occurrence: int = 50,
    synergy_top_n: int = 20,
) -> VanillaBaseline:
    """Run batch simulations and compute a full vanilla baseline.

    Parameters
    ----------
    registry:
        Fully loaded ContentRegistry with all vanilla data.
    num_runs:
        Number of Act 1 runs to simulate.
    base_seed:
        Starting seed for reproducible runs.
    min_co_occurrence:
        Minimum co-occurrence count for synergy detection.
    synergy_top_n:
        Number of top synergies/anti-synergies to keep.
    """
    runner = BatchRunner(registry, agent_class=HeuristicAgent)
    results = runner.run_full_act_batch(n_runs=num_runs, base_seed=base_seed)

    global_metrics = compute_global_metrics(results)
    global_wr = global_metrics.win_rate

    card_metrics = compute_card_metrics(results, global_wr)
    relic_metrics = compute_relic_metrics(results, global_wr)
    synergies, anti_synergies = compute_synergies(
        results, global_wr,
        min_co_occurrence=min_co_occurrence,
        top_n=synergy_top_n,
    )

    return VanillaBaseline(
        agent="heuristic",
        num_runs=num_runs,
        generated_at=datetime.now(timezone.utc).isoformat(),
        global_metrics=global_metrics,
        card_metrics=card_metrics,
        relic_metrics=relic_metrics,
        synergies=synergies,
        anti_synergies=anti_synergies,
    )


def save_baseline(baseline: VanillaBaseline, path: Path) -> None:
    """Save baseline to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline.model_dump(), indent=2))


def load_baseline(path: Path) -> VanillaBaseline:
    """Load baseline from JSON file."""
    data = json.loads(path.read_text())
    return VanillaBaseline.model_validate(data)
