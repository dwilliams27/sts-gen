"""Status effect definitions -- buffs and debuffs applied to players and enemies."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from .actions import ActionNode


class StackBehavior(str, Enum):
    """How multiple applications of the same status interact."""

    INTENSITY = "INTENSITY"
    """Stacks add power -- the numeric value grows (e.g. Strength, Vulnerable)."""

    DURATION = "DURATION"
    """Stacks add turns -- the status lasts longer (e.g. custom timed buffs)."""

    NONE = "NONE"
    """Doesn't stack -- reapplying just refreshes the effect."""


class StatusTrigger(str, Enum):
    """Game events that can cause a status effect to fire its actions."""

    ON_TURN_START = "ON_TURN_START"
    ON_TURN_END = "ON_TURN_END"
    ON_ATTACK = "ON_ATTACK"
    ON_ATTACKED = "ON_ATTACKED"
    ON_CARD_PLAYED = "ON_CARD_PLAYED"
    ON_CARD_DRAWN = "ON_CARD_DRAWN"
    ON_CARD_EXHAUSTED = "ON_CARD_EXHAUSTED"
    ON_STATUS_DRAWN = "ON_STATUS_DRAWN"
    ON_ATTACK_PLAYED = "ON_ATTACK_PLAYED"
    ON_BLOCK_GAINED = "ON_BLOCK_GAINED"
    ON_HP_LOSS = "ON_HP_LOSS"
    ON_DEATH = "ON_DEATH"
    PASSIVE = "PASSIVE"


class StatusEffectDefinition(BaseModel):
    """Complete definition of a custom status effect (buff or debuff)."""

    id: str
    """Unique identifier (e.g. 'my_mod:Burning')."""

    name: str
    """Display name shown on the buff/debuff icon tooltip."""

    description: str
    """Tooltip text explaining the effect."""

    is_debuff: bool
    """True if this is a debuff (red icon, removed by artifact, etc.)."""

    stack_behavior: StackBehavior
    """How repeated applications of this status combine."""

    triggers: dict[StatusTrigger, list[ActionNode]]
    """Maps game events to the action trees that fire when the event occurs.

    A status can respond to multiple events.  For example a 'Burning' debuff
    might trigger ``ON_TURN_END`` to deal damage and also ``ON_DEATH`` to
    spread to another enemy.
    """

    decay_per_turn: int = 0
    """How many stacks are lost automatically at end of turn.

    Set to 1 for standard duration-based debuffs (Vulnerable, Weak, etc.).
    Set to 0 for permanent effects that must be explicitly removed.
    """

    min_stacks: int = 0
    """The status is removed entirely when stacks reach this value.

    Typically 0 -- the effect disappears when all stacks are gone.
    """
