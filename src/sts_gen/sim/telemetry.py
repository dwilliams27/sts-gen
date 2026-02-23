"""Telemetry data models for per-battle and per-run statistics.

These lightweight dataclasses capture everything needed to evaluate
card-set quality without storing the entire game-state history:

- **BattleTelemetry**: outcome, damage dealt/taken, cards played, turn count.
- **RunTelemetry**: seed, ordered list of battle results, final outcome.

Both classes are plain ``dataclass`` instances (not Pydantic models) to
keep telemetry collection as cheap as possible during batch runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BattleTelemetry:
    """Stats from a single combat encounter.

    Attributes
    ----------
    enemy_ids:
        Identifiers of the enemies in this encounter (in position order).
    result:
        ``"win"`` if the player killed all enemies, ``"loss"`` otherwise.
    turns:
        Number of player turns taken.
    player_hp_start:
        Player HP at the start of the battle.
    player_hp_end:
        Player HP at the end of the battle (0 on loss).
    hp_lost:
        Total player HP lost (``player_hp_start - player_hp_end``).
    damage_dealt:
        Total HP damage dealt to enemies across all turns.
    block_gained:
        Total block gained by the player across all turns.
    cards_played:
        Total number of cards played by the player.
    cards_played_by_id:
        Breakdown of cards played: ``card_id -> play count``.
    """

    enemy_ids: list[str]
    result: str  # "win" or "loss"
    turns: int
    player_hp_start: int
    player_hp_end: int
    hp_lost: int
    damage_dealt: int
    block_gained: int
    cards_played: int
    cards_played_by_id: dict[str, int] = field(default_factory=dict)
    enemy_moves_per_turn: list[list[str]] = field(default_factory=list)


@dataclass
class RunTelemetry:
    """Stats from a full run (or a single battle for Phase 1).

    Attributes
    ----------
    seed:
        The master RNG seed used for this run.
    battles:
        Ordered list of battle telemetry, one per encounter.
    final_result:
        ``"win"`` if the player survived all encounters, ``"loss"`` otherwise.
    floors_reached:
        Number of floors/encounters completed (including the final one).
    cards_in_deck:
        Snapshot of the player's deck (as card IDs) at end of run.
    """

    seed: int
    battles: list[BattleTelemetry] = field(default_factory=list)
    final_result: str = "loss"  # "win" or "loss"
    floors_reached: int = 0
    cards_in_deck: list[str] = field(default_factory=list)
