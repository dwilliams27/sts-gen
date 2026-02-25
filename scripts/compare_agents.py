"""Compare RandomAgent vs HeuristicAgent over many Act 1 runs.

Usage:
    uv run python scripts/compare_agents.py [--runs N]
"""

from __future__ import annotations

import argparse
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
from sts_gen.sim.play_agents.random_agent import RandomAgent
from sts_gen.sim.runner import BatchRunner


def run_comparison(n_runs: int = 500) -> None:
    print(f"Loading registry...")
    registry = ContentRegistry()
    registry.load_vanilla_cards()
    registry.load_vanilla_enemies()
    registry.load_vanilla_status_effects()
    registry.load_vanilla_relics()
    registry.load_vanilla_potions()
    registry.load_vanilla_encounters()

    results = {}
    for label, agent_class in [("RandomAgent", RandomAgent), ("HeuristicAgent", HeuristicAgent)]:
        print(f"\nRunning {n_runs} Act 1 runs with {label}...")
        runner = BatchRunner(registry, agent_class=agent_class)
        t0 = time.time()
        telemetry = runner.run_full_act_batch(n_runs=n_runs, base_seed=0)
        elapsed = time.time() - t0

        wins = sum(1 for r in telemetry if r.final_result == "win")
        floors = [r.floors_reached for r in telemetry]
        battles_won = []
        for r in telemetry:
            battles_won.append(sum(1 for b in r.battles if b.result == "win"))
        hp_at_end = []
        for r in telemetry:
            if r.battles:
                hp_at_end.append(r.battles[-1].player_hp_end)

        results[label] = {
            "telemetry": telemetry,
            "wins": wins,
            "win_rate": wins / n_runs * 100,
            "floors": floors,
            "battles_won": battles_won,
            "hp_at_end": hp_at_end,
            "elapsed": elapsed,
        }

        print(f"  Time: {elapsed:.1f}s ({elapsed/n_runs*1000:.0f}ms/run)")
        print(f"  Win rate: {wins}/{n_runs} ({wins/n_runs*100:.1f}%)")
        print(f"  Avg floors: {np.mean(floors):.1f} (median {np.median(floors):.0f})")
        print(f"  Max floors: {max(floors)}")
        print(f"  Avg battles won: {np.mean(battles_won):.1f}")

    generate_charts(results, n_runs)


def generate_charts(results: dict, n_runs: int) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"RandomAgent vs HeuristicAgent — {n_runs} Act 1 Runs", fontsize=16, fontweight="bold")

    colors = {"RandomAgent": "#e74c3c", "HeuristicAgent": "#2ecc71"}

    # --- Chart 1: Win Rate ---
    ax = axes[0, 0]
    labels = list(results.keys())
    win_rates = [results[l]["win_rate"] for l in labels]
    bars = ax.bar(labels, win_rates, color=[colors[l] for l in labels], edgecolor="black", linewidth=0.5)
    for bar, rate, r in zip(bars, win_rates, [results[l] for l in labels]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{rate:.1f}%\n({r["wins"]}/{n_runs})',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    ax.set_ylabel("Win Rate (%)")
    ax.set_title("Act 1 Win Rate")
    ax.set_ylim(0, max(win_rates) * 1.4 + 5)

    # --- Chart 2: Floors Reached Distribution ---
    ax = axes[0, 1]
    for label in labels:
        floors = results[label]["floors"]
        max_floor = max(max(results[l]["floors"]) for l in labels)
        bins = np.arange(0.5, max_floor + 1.5, 1)
        ax.hist(floors, bins=bins, alpha=0.6, label=f'{label} (avg={np.mean(floors):.1f})',
                color=colors[label], edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Floors Reached")
    ax.set_ylabel("Count")
    ax.set_title("Floors Reached Distribution")
    ax.legend()

    # --- Chart 3: Battles Won Distribution ---
    ax = axes[1, 0]
    for label in labels:
        bw = results[label]["battles_won"]
        max_bw = max(max(results[l]["battles_won"]) for l in labels)
        bins = np.arange(-0.5, max_bw + 1.5, 1)
        ax.hist(bw, bins=bins, alpha=0.6, label=f'{label} (avg={np.mean(bw):.1f})',
                color=colors[label], edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Battles Won Per Run")
    ax.set_ylabel("Count")
    ax.set_title("Battles Won Distribution")
    ax.legend()

    # --- Chart 4: Summary Table ---
    ax = axes[1, 1]
    ax.axis("off")
    row_labels = [
        "Win Rate",
        "Avg Floors",
        "Median Floors",
        "Max Floors",
        "Avg Battles Won",
        "Avg HP (last battle)",
        "Time (s)",
    ]
    table_data = []
    for metric in row_labels:
        row = []
        for label in labels:
            r = results[label]
            if metric == "Win Rate":
                row.append(f'{r["win_rate"]:.1f}%')
            elif metric == "Avg Floors":
                row.append(f'{np.mean(r["floors"]):.1f}')
            elif metric == "Median Floors":
                row.append(f'{np.median(r["floors"]):.0f}')
            elif metric == "Max Floors":
                row.append(f'{max(r["floors"])}')
            elif metric == "Avg Battles Won":
                row.append(f'{np.mean(r["battles_won"]):.1f}')
            elif metric == "Avg HP (last battle)":
                row.append(f'{np.mean(r["hp_at_end"]):.1f}')
            elif metric == "Time (s)":
                row.append(f'{r["elapsed"]:.1f}')
        table_data.append(row)

    table = ax.table(
        cellText=table_data,
        rowLabels=row_labels,
        colLabels=labels,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.6)

    # Color the header cells
    for j, label in enumerate(labels):
        table[0, j].set_facecolor(colors[label])
        table[0, j].set_text_props(color="white", fontweight="bold")

    plt.tight_layout()
    out_path = "agent_comparison.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=500, help="Number of runs per agent")
    args = parser.parse_args()
    run_comparison(args.runs)
