"""Entity models for a headless Slay the Spire combat simulator.

All data classes use Pydantic v2 BaseModel for validation and
serialization.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Entity base
# ---------------------------------------------------------------------------

class Entity(BaseModel):
    """Common base for anything with HP, block, and status effects."""

    name: str
    max_hp: int
    current_hp: int
    block: int = 0
    status_effects: dict[str, int] = Field(default_factory=dict)
    """Maps a status-effect identifier (e.g. ``"vulnerable"``) to its
    current stack count.  Stacks <= 0 are automatically removed."""

    # -- HP queries ----------------------------------------------------------

    @property
    def is_dead(self) -> bool:
        return self.current_hp <= 0

    # -- block ---------------------------------------------------------------

    def apply_block(self, amount: int) -> None:
        """Add *amount* block (must be >= 0)."""
        if amount < 0:
            raise ValueError(f"apply_block amount must be >= 0, got {amount}")
        self.block += amount

    def lose_block(self, amount: int) -> None:
        """Remove up to *amount* block.  Block cannot go below 0."""
        self.block = max(0, self.block - amount)

    def clear_block(self) -> None:
        """Set block to 0."""
        self.block = 0

    # -- status effects ------------------------------------------------------

    def apply_status(self, status_id: str, stacks: int) -> None:
        """Add *stacks* of a status effect.  If the total falls to 0 or
        below, the status is removed entirely."""
        current = self.status_effects.get(status_id, 0)
        new_total = current + stacks
        if new_total <= 0:
            self.status_effects.pop(status_id, None)
        else:
            self.status_effects[status_id] = new_total

    def get_status(self, status_id: str) -> int:
        """Return the stack count for *status_id*, or ``0`` if absent."""
        return self.status_effects.get(status_id, 0)

    def remove_status(self, status_id: str) -> None:
        """Completely remove a status effect."""
        self.status_effects.pop(status_id, None)

    # -- damage / heal -------------------------------------------------------

    def take_damage(self, amount: int) -> int:
        """Apply *amount* damage: absorbed by block first, remainder to HP.

        Returns the actual HP lost (i.e. damage that got through block).
        """
        if amount <= 0:
            return 0

        blocked = min(self.block, amount)
        self.block -= blocked
        remaining = amount - blocked

        hp_lost = min(self.current_hp, remaining)
        self.current_hp -= hp_lost
        return hp_lost

    def heal(self, amount: int) -> None:
        """Heal *amount* HP, capped at ``max_hp``."""
        if amount <= 0:
            return
        self.current_hp = min(self.max_hp, self.current_hp + amount)


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class Player(Entity):
    """The player character."""

    energy: int = 0
    max_energy: int = 3
    gold: int = 0
    strength: int = 0
    dexterity: int = 0


# ---------------------------------------------------------------------------
# Enemy
# ---------------------------------------------------------------------------

class Enemy(Entity):
    """A single enemy in combat."""

    enemy_id: str
    """Identifier that ties this instance back to an IR enemy definition."""

    strength: int = 0
    intent: str | None = None
    """Human-readable intent label (e.g. ``"Bash"``).  Set each turn by the
    enemy AI."""

    intent_damage: int | None = None
    """Base damage the enemy intends to deal (before modifiers)."""

    intent_hits: int | None = None
    """Number of hits the enemy intends to deal (multi-attack)."""


# ---------------------------------------------------------------------------
# EnemyIntent (value object)
# ---------------------------------------------------------------------------

class EnemyIntent(BaseModel):
    """Resolved intent information shown to the player above an enemy."""

    intent_type: str = "unknown"
    """One of ``"attack"``, ``"defend"``, ``"buff"``, ``"debuff"``,
    ``"attack_defend"``, ``"unknown"``."""

    damage: int | None = None
    """Per-hit damage, or ``None`` if the intent is not an attack."""

    hits: int = 1
    """Number of hits (for multi-attacks)."""

    block: int | None = None
    """Block the enemy will gain, or ``None``."""
