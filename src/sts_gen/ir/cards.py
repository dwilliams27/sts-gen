"""Card definitions -- the most common content type in a Slay the Spire mod."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from .actions import ActionNode


class CardType(str, Enum):
    """The five card types recognised by the base game."""

    ATTACK = "ATTACK"
    SKILL = "SKILL"
    POWER = "POWER"
    STATUS = "STATUS"
    CURSE = "CURSE"


class CardRarity(str, Enum):
    """Controls how frequently a card appears in rewards and shops."""

    BASIC = "BASIC"
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    SPECIAL = "SPECIAL"


class CardTarget(str, Enum):
    """Targeting mode shown in the UI and enforced by the game engine."""

    ENEMY = "ENEMY"
    ALL_ENEMIES = "ALL_ENEMIES"
    SELF = "SELF"
    NONE = "NONE"


class UpgradeDefinition(BaseModel):
    """Describes *only the deltas* that change when a card is upgraded.

    Any field left as ``None`` means "keep the base value".
    """

    cost: int | None = None
    """New energy cost after upgrade, or None to keep the base cost."""

    actions: list[ActionNode] | None = None
    """Replacement action list after upgrade, or None to keep the base actions."""

    description: str | None = None
    """Replacement description text after upgrade, or None to keep the base."""

    exhaust: bool | None = None
    """If set, overrides the base card's exhaust flag on upgrade."""

    innate: bool | None = None
    """If set, overrides the base card's innate flag on upgrade."""

    on_exhaust: list[ActionNode] | None = None
    """If set, overrides the base card's on_exhaust actions on upgrade."""


class CardDefinition(BaseModel):
    """Complete definition of a single card in the IR."""

    id: str
    """Unique identifier used for cross-references (e.g. 'my_mod:FireSlash')."""

    name: str
    """Display name shown on the card."""

    type: CardType
    """Attack, Skill, Power, Status, or Curse."""

    rarity: CardRarity
    """Controls drop frequency and shop pricing."""

    cost: int
    """Energy cost to play.  -1 = X-cost, -2 = unplayable."""

    target: CardTarget
    """Targeting mode."""

    description: str
    """Card body text (may contain dynamic placeholders like !D! for damage)."""

    actions: list[ActionNode]
    """The action tree executed when this card is played."""

    upgrade: UpgradeDefinition | None = None
    """How the card changes when upgraded.  None means the card cannot upgrade."""

    keywords: list[str] = []
    """Keyword ids attached to this card (e.g. ['exhaust', 'ethereal'])."""

    exhaust: bool = False
    """If True the card is exhausted (removed for the rest of combat) after play."""

    ethereal: bool = False
    """If True the card is exhausted at end of turn if still in hand."""

    innate: bool = False
    """If True the card is always drawn in the opening hand."""

    retain: bool = False
    """If True the card is not discarded at end of turn."""

    on_exhaust: list[ActionNode] = []
    """Actions to execute when this card is exhausted (e.g. Sentinel's energy gain)."""

    play_restriction: str | None = None
    """Condition string that must evaluate to True for this card to be playable.
    Uses the same condition syntax as CONDITIONAL nodes (e.g. 'only_attacks_in_hand').
    None means no restriction."""
