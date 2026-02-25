"""Relic definitions -- passive items that trigger on game events."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from .actions import ActionNode


class RelicTier(str, Enum):
    """Determines where and how often a relic can appear."""

    STARTER = "STARTER"
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    BOSS = "BOSS"
    SHOP = "SHOP"
    EVENT = "EVENT"


class RelicDefinition(BaseModel):
    """Complete definition of a single relic in the IR."""

    id: str
    """Unique identifier (e.g. 'my_mod:BurningLantern')."""

    name: str
    """Display name shown in the relic tooltip."""

    tier: RelicTier
    """Controls the pool this relic is drawn from."""

    description: str
    """Flavour / rules text shown in the tooltip."""

    trigger: str
    """Event name that activates this relic.

    Common values: 'on_combat_start', 'on_combat_end', 'on_turn_start',
    'on_turn_end', 'on_card_played', 'on_attack', 'on_attacked',
    'on_hp_loss', 'on_pickup', 'on_enter_room', 'on_rest', 'on_smith',
    'on_chest_open', 'on_spend_gold', 'passive'.
    """

    actions: list[ActionNode]
    """The action tree executed when the trigger fires."""

    counter: int | None = None
    """Threshold for counter-based relics (e.g. 10 for Nunchaku, 3 for Shuriken).

    ``None`` means the relic does not use a counter.
    """

    counter_per_turn: bool = False
    """If ``True``, the counter resets to 0 at the start of each turn.

    Used by Shuriken, Kunai, Ornamental Fan (counter resets per turn, can
    trigger multiple times per turn).  Nunchaku is ``False`` (counter persists
    across turns).
    """
