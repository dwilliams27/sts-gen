"""Potion definitions -- single-use consumable items."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from .actions import ActionNode
from .cards import CardTarget


class PotionRarity(str, Enum):
    """Controls how frequently a potion appears in rewards."""

    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"


class PotionDefinition(BaseModel):
    """Complete definition of a single potion in the IR."""

    id: str
    """Unique identifier (e.g. 'my_mod:LiquidFlame')."""

    name: str
    """Display name."""

    rarity: PotionRarity
    """Controls drop frequency."""

    description: str
    """Tooltip text describing the potion's effect."""

    target: CardTarget
    """Targeting mode when the potion is used."""

    actions: list[ActionNode]
    """The action tree executed when the potion is consumed."""
