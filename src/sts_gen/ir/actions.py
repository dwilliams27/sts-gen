"""Primitive action nodes that form the behavioral IR for all game entities."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ActionType(str, Enum):
    """Primitive action types that map 1-to-1 onto Slay the Spire mechanics."""

    DEAL_DAMAGE = "deal_damage"
    GAIN_BLOCK = "gain_block"
    APPLY_STATUS = "apply_status"
    REMOVE_STATUS = "remove_status"
    DRAW_CARDS = "draw_cards"
    DISCARD_CARDS = "discard_cards"
    EXHAUST_CARDS = "exhaust_cards"
    GAIN_ENERGY = "gain_energy"
    LOSE_ENERGY = "lose_energy"
    HEAL = "heal"
    LOSE_HP = "lose_hp"
    ADD_CARD_TO_PILE = "add_card_to_pile"
    SHUFFLE_INTO_DRAW = "shuffle_into_draw"
    GAIN_GOLD = "gain_gold"
    GAIN_STRENGTH = "gain_strength"
    GAIN_DEXTERITY = "gain_dexterity"
    CONDITIONAL = "conditional"
    FOR_EACH = "for_each"
    REPEAT = "repeat"
    TRIGGER_CUSTOM = "trigger_custom"


class ActionNode(BaseModel):
    """A single node in an action tree.

    Leaf nodes represent concrete game actions (deal damage, gain block, etc.).
    Branch nodes (conditional, for_each, repeat) contain children that form
    sub-trees, making the IR a recursive tree structure.
    """

    action_type: ActionType
    """Which primitive action this node represents."""

    value: int | None = None
    """Numeric parameter -- damage amount, block amount, card count, etc."""

    target: str | None = "default"
    """Who this action targets.  Common values: 'self', 'enemy', 'all_enemies',
    'random_enemy'.  Defaults to 'default' which lets the card/relic context
    decide."""

    status_name: str | None = None
    """Status effect id to apply/remove (for apply_status / remove_status)."""

    card_id: str | None = None
    """Card id reference (for add_card_to_pile, shuffle_into_draw, etc.)."""

    pile: str | None = None
    """Which pile to interact with: 'draw', 'discard', 'exhaust', 'hand'."""

    condition: str | None = None
    """Boolean expression string for CONDITIONAL nodes (e.g. 'hp < 50%')."""

    children: list[ActionNode] | None = None
    """Sub-actions for branch nodes (conditional, for_each, repeat)."""

    times: int | None = None
    """Repetition count for REPEAT nodes."""

    model_config = {"frozen": False, "populate_by_name": True}
