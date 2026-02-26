"""Report generation for vanilla baselines.

Two output formats:
- Text report: human-readable summary for terminal/markdown.
- LLM context: compact structured block for LLM agent system prompts.
"""

from __future__ import annotations

from sts_gen.balance.models import VanillaBaseline


def generate_text_report(baseline: VanillaBaseline) -> str:
    """Generate a human-readable summary of the baseline."""
    g = baseline.global_metrics
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append(f"Vanilla Baseline Report — {baseline.agent} agent")
    lines.append(f"Runs: {baseline.num_runs:,} | Generated: {baseline.generated_at}")
    lines.append("=" * 60)

    # Global stats
    lines.append("")
    lines.append("## Global Stats")
    lines.append(f"  Win rate:        {g.win_rate:.1%} ({g.wins}/{g.total_runs})")
    lines.append(f"  Avg floors:      {g.avg_floors_reached:.1f}")
    lines.append(f"  Avg battles won: {g.avg_battles_won:.1f}")
    lines.append(f"  Avg deck size:   {g.avg_deck_size:.1f}")
    lines.append(f"  Avg gold earned: {g.avg_gold_earned:.0f}")

    # Top/bottom win rate delta cards
    cards_by_wr = sorted(baseline.card_metrics, key=lambda c: c.win_rate_delta, reverse=True)
    non_trivial = [c for c in cards_by_wr if c.times_in_deck >= 10]

    lines.append("")
    lines.append("## Top 10 Highest Win Rate Delta Cards")
    for c in non_trivial[:10]:
        lines.append(
            f"  {c.card_id:30s}  wr_delta={c.win_rate_delta:+.3f}"
            f"  pick={c.pick_rate:.2f}  played={c.times_played}"
            f"  in_deck={c.times_in_deck}"
        )

    lines.append("")
    lines.append("## Top 10 Lowest Win Rate Delta Cards")
    for c in non_trivial[-10:]:
        lines.append(
            f"  {c.card_id:30s}  wr_delta={c.win_rate_delta:+.3f}"
            f"  pick={c.pick_rate:.2f}  played={c.times_played}"
            f"  in_deck={c.times_in_deck}"
        )

    # Top/bottom pick rate
    cards_by_pick = sorted(non_trivial, key=lambda c: c.pick_rate, reverse=True)
    lines.append("")
    lines.append("## Top 10 Highest Pick Rate Cards")
    for c in cards_by_pick[:10]:
        lines.append(
            f"  {c.card_id:30s}  pick={c.pick_rate:.2f}"
            f"  wr_delta={c.win_rate_delta:+.3f}"
            f"  offered={c.times_offered}"
        )

    lines.append("")
    lines.append("## Top 10 Lowest Pick Rate Cards")
    for c in cards_by_pick[-10:]:
        lines.append(
            f"  {c.card_id:30s}  pick={c.pick_rate:.2f}"
            f"  wr_delta={c.win_rate_delta:+.3f}"
            f"  offered={c.times_offered}"
        )

    # Synergies
    if baseline.synergies:
        lines.append("")
        lines.append("## Top Synergy Pairs")
        for s in baseline.synergies[:5]:
            lines.append(
                f"  {s.card_a} + {s.card_b}"
                f"  score={s.synergy_score:+.3f}"
                f"  co_wr={s.co_win_rate:.3f}"
                f"  n={s.co_occurrence_count}"
            )

    if baseline.anti_synergies:
        lines.append("")
        lines.append("## Top Anti-Synergy Pairs")
        for s in baseline.anti_synergies[:5]:
            lines.append(
                f"  {s.card_a} + {s.card_b}"
                f"  score={s.synergy_score:+.3f}"
                f"  co_wr={s.co_win_rate:.3f}"
                f"  n={s.co_occurrence_count}"
            )

    lines.append("")
    return "\n".join(lines)


def generate_llm_context(baseline: VanillaBaseline) -> str:
    """Generate a compact context block for LLM agent system prompts."""
    g = baseline.global_metrics
    lines: list[str] = []

    lines.append("<vanilla_baseline>")
    lines.append(f"agent={baseline.agent} runs={baseline.num_runs}")
    lines.append(
        f"global: wr={g.win_rate:.3f} floors={g.avg_floors_reached:.1f}"
        f" battles={g.avg_battles_won:.1f} deck={g.avg_deck_size:.1f}"
    )

    # Per-card table
    lines.append("")
    lines.append("card_id | wr_delta | pick_rate | play_rate | in_deck")
    lines.append("--------|----------|-----------|-----------|--------")
    cards_by_wr = sorted(baseline.card_metrics, key=lambda c: c.win_rate_delta, reverse=True)
    for c in cards_by_wr:
        lines.append(
            f"{c.card_id} | {c.win_rate_delta:+.3f} | {c.pick_rate:.2f}"
            f" | {c.play_rate:.3f} | {c.times_in_deck}"
        )

    # Synergies
    if baseline.synergies:
        lines.append("")
        lines.append("synergies:")
        for s in baseline.synergies:
            lines.append(
                f"- {s.card_a} + {s.card_b}"
                f" (score={s.synergy_score:+.3f}, n={s.co_occurrence_count})"
            )

    if baseline.anti_synergies:
        lines.append("")
        lines.append("anti_synergies:")
        for s in baseline.anti_synergies:
            lines.append(
                f"- {s.card_a} + {s.card_b}"
                f" (score={s.synergy_score:+.3f}, n={s.co_occurrence_count})"
            )

    lines.append("</vanilla_baseline>")
    return "\n".join(lines)
