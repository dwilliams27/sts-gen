"""Pydantic v2 models for vanilla baseline data.

These models define the structured output of balance analysis:
per-card metrics, per-relic metrics, synergy detection, and
global run statistics. All are serializable to/from JSON.
"""

from __future__ import annotations

from pydantic import BaseModel


class CardMetrics(BaseModel):
    """Per-card balance metrics computed from batch run telemetry."""

    card_id: str
    # Presence metrics
    times_in_deck: int
    """Runs where this card was in the final deck."""
    wins_with: int
    """Wins among runs where this card was in deck."""
    losses_with: int
    """Losses among runs where this card was in deck."""
    win_rate_with: float
    """wins_with / times_in_deck."""
    win_rate_delta: float
    """win_rate_with - global_win_rate."""
    # Pick metrics
    times_offered: int
    """Reward screens where this card appeared."""
    times_picked: int
    """Times chosen from rewards."""
    pick_rate: float
    """times_picked / times_offered."""
    # Play metrics
    times_played: int
    """Total plays across all battles in runs where card was in deck."""
    play_rate: float
    """times_played / total_battle_turns_with_card."""
    # Efficiency (None until per-card tracking is added to telemetry)
    avg_damage_per_play: float | None = None
    avg_block_per_play: float | None = None


class RelicMetrics(BaseModel):
    """Per-relic balance metrics."""

    relic_id: str
    times_held: int
    """Runs where this relic was collected."""
    wins_with: int
    win_rate_with: float
    win_rate_delta: float


class SynergyPair(BaseModel):
    """Detected synergy (or anti-synergy) between two cards."""

    card_a: str
    card_b: str
    co_occurrence_count: int
    """Number of decks containing both cards."""
    co_win_rate: float
    """Win rate among decks containing both cards."""
    independent_expected_wr: float
    """P(win|A) * P(win|B) / global_wr — independence baseline."""
    synergy_score: float
    """co_win_rate - independent_expected_wr."""


class GlobalMetrics(BaseModel):
    """Aggregate run statistics."""

    total_runs: int
    wins: int
    losses: int
    win_rate: float
    avg_floors_reached: float
    avg_battles_won: float
    avg_deck_size: float
    avg_gold_earned: float


class VanillaBaseline(BaseModel):
    """Top-level baseline data structure."""

    agent: str
    """Agent type used for generation (e.g. 'heuristic')."""
    num_runs: int
    generated_at: str
    """ISO 8601 timestamp."""
    global_metrics: GlobalMetrics
    card_metrics: list[CardMetrics]
    relic_metrics: list[RelicMetrics]
    synergies: list[SynergyPair]
    """Top N positive synergies."""
    anti_synergies: list[SynergyPair]
    """Top N negative synergies."""
