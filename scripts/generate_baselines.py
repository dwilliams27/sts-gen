"""Generate vanilla baselines from Act 1 runs.

Usage:
    uv run python scripts/generate_baselines.py [--runs 50000] [--output data/baselines/]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from sts_gen.balance.baselines import generate_baseline, save_baseline
from sts_gen.balance.report import generate_text_report
from sts_gen.sim.content.registry import ContentRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate vanilla baselines")
    parser.add_argument("--runs", type=int, default=50_000, help="Number of Act 1 runs")
    parser.add_argument("--output", type=str, default="data/baselines/", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    args = parser.parse_args()

    print("Loading registry...")
    registry = ContentRegistry()
    registry.load_vanilla_cards()
    registry.load_vanilla_enemies()
    registry.load_vanilla_status_effects()
    registry.load_vanilla_relics()
    registry.load_vanilla_potions()
    registry.load_vanilla_encounters()

    print(f"Running {args.runs:,} Act 1 simulations...")
    t0 = time.perf_counter()
    baseline = generate_baseline(
        registry, num_runs=args.runs, base_seed=args.seed,
    )
    elapsed = time.perf_counter() - t0
    print(f"Done in {elapsed:.1f}s")

    # Save JSON
    out_dir = Path(args.output)
    filename = f"ironclad_heuristic_{args.runs // 1000}k.json"
    json_path = out_dir / filename
    save_baseline(baseline, json_path)
    print(f"Saved baseline to {json_path}")

    # Print text report
    print()
    print(generate_text_report(baseline))


if __name__ == "__main__":
    main()
