#!/usr/bin/env python3
"""Stress-test: generate fresh IR via DesignerAgent, then simulate it.

Usage:
    uv run python scripts/stress_test_pipeline.py [--brief "..."] [--runs N] [--from-json PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def load_registry():
    """Load a full vanilla registry."""
    from sts_gen.sim.content.registry import ContentRegistry

    registry = ContentRegistry()
    registry.load_vanilla_cards()
    registry.load_vanilla_enemies()
    registry.load_vanilla_encounters()
    registry.load_vanilla_status_effects()
    registry.load_vanilla_relics()
    registry.load_vanilla_potions()
    return registry


def generate_content(brief: str, registry) -> tuple:
    """Run the DesignerAgent pipeline and return (content_set, run_dir)."""
    from sts_gen.agents.designer import DesignerAgent

    baseline_path = PROJECT_ROOT / "data" / "baselines" / "ironclad_heuristic_50k.json"

    agent = DesignerAgent(
        registry=registry,
        baseline_path=baseline_path,
        model="claude-sonnet-4-20250514",
        max_retries=3,
    )

    print(f"[GENERATE] Starting DesignerAgent with brief: {brief!r}")
    content_set = agent.generate(brief)
    print(f"[GENERATE] Done! {len(content_set.cards)} cards, "
          f"{len(content_set.relics)} relics, {len(content_set.potions)} potions, "
          f"{len(content_set.status_effects)} status effects")
    print(f"[GENERATE] Tokens: {agent.usage.input_tokens} in / {agent.usage.output_tokens} out")
    print(f"[GENERATE] Artifacts: {agent.run_dir}")

    return content_set, agent.run_dir


def load_content_from_json(path: Path):
    """Load a previously-generated ContentSet from JSON."""
    from sts_gen.ir.content_set import ContentSet

    print(f"[LOAD] Loading content from {path}")
    data = json.loads(path.read_text())
    content_set = ContentSet.model_validate(data)
    print(f"[LOAD] Loaded {len(content_set.cards)} cards, "
          f"{len(content_set.relics)} relics, {len(content_set.potions)} potions, "
          f"{len(content_set.status_effects)} status effects")
    return content_set


def simulate(content_set, num_runs: int):
    """Load custom content into registry and run Act 1 simulations."""
    from sts_gen.balance.metrics import compute_card_metrics, compute_global_metrics
    from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
    from sts_gen.sim.runner import BatchRunner

    registry = load_registry()
    registry.load_content_set(content_set)

    print(f"\n[SIM] Registry: {len(registry.cards)} cards total "
          f"({len(content_set.cards)} custom)")
    print(f"[SIM] Running {num_runs} Act 1 simulations...")

    runner = BatchRunner(registry, agent_class=HeuristicAgent)

    # Run in batches to identify where failures happen
    completed = []
    errors = []
    batch_size = min(10, num_runs)

    for batch_start in range(0, num_runs, batch_size):
        batch_end = min(batch_start + batch_size, num_runs)
        actual_batch = batch_end - batch_start
        try:
            results = runner.run_full_act_batch(
                n_runs=actual_batch,
                base_seed=42 + batch_start,
            )
            completed.extend(results)
            print(f"  Batch {batch_start}-{batch_end}: OK "
                  f"({sum(1 for r in results if r.final_result == 'win')}/{actual_batch} wins)")
        except Exception as exc:
            tb = traceback.format_exc()
            errors.append({
                "batch": f"{batch_start}-{batch_end}",
                "error": str(exc),
                "traceback": tb,
            })
            print(f"  Batch {batch_start}-{batch_end}: FAILED - {exc}")
            # Try individual runs to isolate
            for i in range(actual_batch):
                try:
                    single = runner.run_full_act_batch(
                        n_runs=1,
                        base_seed=42 + batch_start + i,
                    )
                    completed.extend(single)
                except Exception as inner_exc:
                    inner_tb = traceback.format_exc()
                    errors.append({
                        "seed": 42 + batch_start + i,
                        "error": str(inner_exc),
                        "traceback": inner_tb,
                    })

    # Report results
    print(f"\n[RESULTS] Completed: {len(completed)}/{num_runs} runs")
    print(f"[RESULTS] Errors: {len(errors)}")

    if completed:
        wins = sum(1 for r in completed if r.final_result == "win")
        avg_floors = sum(r.floors_reached for r in completed) / len(completed)
        print(f"[RESULTS] Win rate: {wins}/{len(completed)} ({100*wins/len(completed):.1f}%)")
        print(f"[RESULTS] Avg floors: {avg_floors:.1f}")

        # Compute metrics for custom cards
        global_metrics = compute_global_metrics(completed)
        all_card_metrics = compute_card_metrics(completed, global_metrics.win_rate)
        custom_ids = {c.id for c in content_set.cards}
        custom_metrics = [m for m in all_card_metrics if m.card_id in custom_ids]

        if custom_metrics:
            print(f"\n[METRICS] Custom card metrics ({len(custom_metrics)} cards seen):")
            # Sort by times offered descending
            custom_metrics.sort(key=lambda m: m.times_offered, reverse=True)
            for m in custom_metrics[:20]:
                print(f"  {m.card_id}: offered={m.times_offered}, "
                      f"picked={m.times_picked}, "
                      f"pick_rate={m.pick_rate:.2f}")

    if errors:
        print(f"\n[ERRORS] Unique error types:")
        seen = set()
        for e in errors:
            key = e["error"]
            if key not in seen:
                seen.add(key)
                print(f"\n  --- {key} ---")
                # Print last few lines of traceback
                tb_lines = e["traceback"].strip().split("\n")
                for line in tb_lines[-8:]:
                    print(f"  {line}")

    return completed, errors


def main():
    parser = argparse.ArgumentParser(description="Stress-test IR generation → simulation")
    parser.add_argument("--brief", default="A pyromancer character who manipulates Heat, "
                        "building up burning stacks on enemies and using self-damage "
                        "for powerful effects. Archetypes: sustained burn damage, "
                        "explosive burst combos, and self-immolation risk/reward.",
                        help="Design brief for the DesignerAgent")
    parser.add_argument("--runs", type=int, default=100,
                        help="Number of Act 1 simulation runs")
    parser.add_argument("--from-json", type=str, default=None,
                        help="Skip generation; load ContentSet from this JSON file")
    args = parser.parse_args()

    if args.from_json:
        content_set = load_content_from_json(Path(args.from_json))
    else:
        registry = load_registry()
        content_set, run_dir = generate_content(args.brief, registry)

    if args.runs <= 0:
        print("[SKIP] No simulation runs requested (--runs 0)")
        sys.exit(0)

    completed, errors = simulate(content_set, args.runs)

    if errors:
        print(f"\n{'='*60}")
        print(f"STRESS TEST FAILED: {len(errors)} simulation errors")
        print(f"{'='*60}")
        sys.exit(1)
    else:
        print(f"\n{'='*60}")
        print(f"STRESS TEST PASSED: {len(completed)} runs clean")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
