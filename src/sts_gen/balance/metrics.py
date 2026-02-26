"""Pure metric computation functions for balance analysis.

All functions take a list of RunTelemetry and return structured metrics.
No side effects, no I/O.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import TYPE_CHECKING

from sts_gen.balance.models import (
    CardMetrics,
    GlobalMetrics,
    RelicMetrics,
    SynergyPair,
)

if TYPE_CHECKING:
    from sts_gen.sim.telemetry import RunTelemetry

# Starter cards — excluded from synergy analysis
_STARTER_CARDS = frozenset({"strike", "defend", "bash", "ascenders_bane"})


def compute_global_metrics(runs: list[RunTelemetry]) -> GlobalMetrics:
    """Compute aggregate run statistics."""
    total = len(runs)
    if total == 0:
        return GlobalMetrics(
            total_runs=0, wins=0, losses=0, win_rate=0.0,
            avg_floors_reached=0.0, avg_battles_won=0.0,
            avg_deck_size=0.0, avg_gold_earned=0.0,
        )

    wins = sum(1 for r in runs if r.final_result == "win")
    losses = total - wins

    avg_floors = sum(r.floors_reached for r in runs) / total
    avg_battles = sum(
        sum(1 for b in r.battles if b.result == "win")
        for r in runs
    ) / total
    avg_deck = sum(len(r.cards_in_deck) for r in runs) / total
    avg_gold = sum(r.gold_earned for r in runs) / total

    return GlobalMetrics(
        total_runs=total,
        wins=wins,
        losses=losses,
        win_rate=wins / total,
        avg_floors_reached=avg_floors,
        avg_battles_won=avg_battles,
        avg_deck_size=avg_deck,
        avg_gold_earned=avg_gold,
    )


def compute_card_metrics(
    runs: list[RunTelemetry],
    global_wr: float,
) -> list[CardMetrics]:
    """Compute per-card balance metrics from run telemetry."""
    if not runs:
        return []

    # Collect all card IDs seen across all decks
    all_card_ids: set[str] = set()
    for r in runs:
        all_card_ids.update(r.cards_in_deck)

    # Build per-card stats
    results: list[CardMetrics] = []
    for card_id in sorted(all_card_ids):
        # Presence
        runs_with = [r for r in runs if card_id in r.cards_in_deck]
        times_in_deck = len(runs_with)
        if times_in_deck == 0:
            continue

        wins_with = sum(1 for r in runs_with if r.final_result == "win")
        losses_with = times_in_deck - wins_with
        wr_with = wins_with / times_in_deck
        wr_delta = wr_with - global_wr

        # Pick metrics (from card_offers / card_picks)
        times_offered = 0
        times_picked = 0
        for r in runs:
            for offer in r.card_offers:
                if card_id in offer:
                    times_offered += 1
            for pick in r.card_picks:
                if pick == card_id:
                    times_picked += 1

        pick_rate = times_picked / times_offered if times_offered > 0 else 0.0

        # Play metrics — sum across all battles in runs where card was in deck
        times_played = 0
        total_turns = 0
        for r in runs_with:
            for b in r.battles:
                times_played += b.cards_played_by_id.get(card_id, 0)
                total_turns += b.turns

        play_rate = times_played / total_turns if total_turns > 0 else 0.0

        results.append(CardMetrics(
            card_id=card_id,
            times_in_deck=times_in_deck,
            wins_with=wins_with,
            losses_with=losses_with,
            win_rate_with=wr_with,
            win_rate_delta=wr_delta,
            times_offered=times_offered,
            times_picked=times_picked,
            pick_rate=pick_rate,
            times_played=times_played,
            play_rate=play_rate,
        ))

    return results


def compute_relic_metrics(
    runs: list[RunTelemetry],
    global_wr: float,
) -> list[RelicMetrics]:
    """Compute per-relic balance metrics from run telemetry."""
    if not runs:
        return []

    # Collect all relic IDs
    all_relic_ids: set[str] = set()
    for r in runs:
        all_relic_ids.update(r.relics_collected)

    results: list[RelicMetrics] = []
    for relic_id in sorted(all_relic_ids):
        runs_with = [r for r in runs if relic_id in r.relics_collected]
        times_held = len(runs_with)
        if times_held == 0:
            continue

        wins_with = sum(1 for r in runs_with if r.final_result == "win")
        wr_with = wins_with / times_held
        wr_delta = wr_with - global_wr

        results.append(RelicMetrics(
            relic_id=relic_id,
            times_held=times_held,
            wins_with=wins_with,
            win_rate_with=wr_with,
            win_rate_delta=wr_delta,
        ))

    return results


def compute_synergies(
    runs: list[RunTelemetry],
    global_wr: float,
    min_co_occurrence: int = 50,
    top_n: int = 20,
) -> tuple[list[SynergyPair], list[SynergyPair]]:
    """Detect card synergies and anti-synergies from co-occurrence win rates.

    Returns (synergies, anti_synergies) — each sorted by abs(synergy_score).
    """
    if not runs or global_wr == 0.0:
        return [], []

    # Pre-compute per-card win rates (excluding starters)
    card_wins: Counter[str] = Counter()
    card_counts: Counter[str] = Counter()
    for r in runs:
        non_starter = set(r.cards_in_deck) - _STARTER_CARDS
        is_win = r.final_result == "win"
        for cid in non_starter:
            card_counts[cid] += 1
            if is_win:
                card_wins[cid] += 1

    card_wr: dict[str, float] = {}
    for cid, count in card_counts.items():
        card_wr[cid] = card_wins[cid] / count

    # Count co-occurrences and co-wins
    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_wins: Counter[tuple[str, str]] = Counter()

    for r in runs:
        non_starter = sorted(set(r.cards_in_deck) - _STARTER_CARDS)
        is_win = r.final_result == "win"
        for a, b in combinations(non_starter, 2):
            pair_counts[(a, b)] += 1
            if is_win:
                pair_wins[(a, b)] += 1

    # Compute synergy scores
    all_pairs: list[SynergyPair] = []
    for (a, b), count in pair_counts.items():
        if count < min_co_occurrence:
            continue

        co_wr = pair_wins[(a, b)] / count
        # Independence assumption: P(win|A&B) ≈ P(win|A) * P(win|B) / P(win)
        wr_a = card_wr.get(a, 0.0)
        wr_b = card_wr.get(b, 0.0)
        expected = (wr_a * wr_b) / global_wr
        score = co_wr - expected

        all_pairs.append(SynergyPair(
            card_a=a,
            card_b=b,
            co_occurrence_count=count,
            co_win_rate=co_wr,
            independent_expected_wr=expected,
            synergy_score=score,
        ))

    # Sort: positive synergies descending, negative (anti) ascending
    synergies = sorted(
        [p for p in all_pairs if p.synergy_score > 0],
        key=lambda p: p.synergy_score,
        reverse=True,
    )[:top_n]

    anti_synergies = sorted(
        [p for p in all_pairs if p.synergy_score < 0],
        key=lambda p: p.synergy_score,
    )[:top_n]

    return synergies, anti_synergies
