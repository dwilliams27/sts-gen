"""Diagnose where HeuristicAgent runs are dying and why.

Usage:
    uv run python scripts/diagnose_agent.py [--runs N]
"""

from __future__ import annotations

import argparse
from collections import Counter

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
from sts_gen.sim.runner import BatchRunner


def diagnose(n_runs: int = 2000) -> None:
    registry = ContentRegistry()
    registry.load_vanilla_cards()
    registry.load_vanilla_enemies()
    registry.load_vanilla_status_effects()
    registry.load_vanilla_relics()
    registry.load_vanilla_potions()
    registry.load_vanilla_encounters()

    runner = BatchRunner(registry, agent_class=HeuristicAgent)
    results = runner.run_full_act_batch(n_runs=n_runs, base_seed=0)

    # --- Death analysis ---
    killed_by: Counter[str] = Counter()
    death_floor: Counter[int] = Counter()
    wins = 0
    losses = 0
    win_deck_sizes: list[int] = []
    loss_deck_sizes: list[int] = []
    hp_before_death: list[int] = []
    battle_results_by_enemy: dict[str, dict[str, int]] = {}

    for r in results:
        if r.final_result == "win":
            wins += 1
            win_deck_sizes.append(len(r.cards_in_deck))
        else:
            losses += 1
            loss_deck_sizes.append(len(r.cards_in_deck))
            death_floor[r.floors_reached] += 1
            # Last battle is the one that killed us
            if r.battles:
                last = r.battles[-1]
                enemy_key = "+".join(sorted(last.enemy_ids))
                killed_by[enemy_key] += 1
                hp_before_death.append(last.player_hp_start)

        # Per-enemy win/loss
        for b in r.battles:
            enemy_key = "+".join(sorted(b.enemy_ids))
            if enemy_key not in battle_results_by_enemy:
                battle_results_by_enemy[enemy_key] = {"win": 0, "loss": 0}
            battle_results_by_enemy[enemy_key][b.result] += 1

    print(f"=== HeuristicAgent Diagnosis ({n_runs} runs) ===\n")
    print(f"Wins: {wins} ({wins/n_runs*100:.1f}%)")
    print(f"Losses: {losses} ({losses/n_runs*100:.1f}%)")

    print(f"\n--- Killed By (top 15) ---")
    for enemy, count in killed_by.most_common(15):
        pct = count / losses * 100
        print(f"  {enemy:40s} {count:4d} ({pct:.1f}%)")

    print(f"\n--- Death Floor Distribution ---")
    for floor in sorted(death_floor.keys()):
        count = death_floor[floor]
        bar = "#" * (count // max(1, n_runs // 200))
        print(f"  Floor {floor:2d}: {count:4d} ({count/losses*100:.1f}%) {bar}")

    print(f"\n--- Per-Enemy Win Rate (sorted by loss count) ---")
    sorted_enemies = sorted(
        battle_results_by_enemy.items(),
        key=lambda x: x[1]["loss"],
        reverse=True,
    )
    for enemy, stats in sorted_enemies[:20]:
        total = stats["win"] + stats["loss"]
        wr = stats["win"] / total * 100 if total > 0 else 0
        print(f"  {enemy:40s} {stats['win']:4d}W {stats['loss']:4d}L ({wr:.0f}% WR, {total} fights)")

    print(f"\n--- Deck Size ---")
    if win_deck_sizes:
        print(f"  Winning runs: avg={sum(win_deck_sizes)/len(win_deck_sizes):.1f}, "
              f"min={min(win_deck_sizes)}, max={max(win_deck_sizes)}")
    if loss_deck_sizes:
        print(f"  Losing runs:  avg={sum(loss_deck_sizes)/len(loss_deck_sizes):.1f}, "
              f"min={min(loss_deck_sizes)}, max={max(loss_deck_sizes)}")

    print(f"\n--- HP Entering Fatal Battle ---")
    if hp_before_death:
        buckets = Counter()
        for hp in hp_before_death:
            if hp <= 10:
                buckets["1-10"] += 1
            elif hp <= 20:
                buckets["11-20"] += 1
            elif hp <= 30:
                buckets["21-30"] += 1
            elif hp <= 40:
                buckets["31-40"] += 1
            elif hp <= 50:
                buckets["41-50"] += 1
            else:
                buckets["51+"] += 1
        for bucket in ["1-10", "11-20", "21-30", "31-40", "41-50", "51+"]:
            count = buckets.get(bucket, 0)
            print(f"  HP {bucket:5s}: {count:4d} ({count/len(hp_before_death)*100:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2000)
    args = parser.parse_args()
    diagnose(args.runs)
