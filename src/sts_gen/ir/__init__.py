"""Intermediate Representation (IR) schema for Slay the Spire mod content.

All mod content -- cards, relics, potions, keywords, and status effects --
is represented as Pydantic models that serialise cleanly to/from JSON.
The :class:`ContentSet` is the top-level container handed to the transpiler
(for Java code generation) and the simulator (for balance testing).
"""

from .actions import ActionNode, ActionType
from .cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    UpgradeDefinition,
)
from .content_set import VANILLA_STATUSES, ContentSet
from .keywords import KeywordDefinition
from .potions import PotionDefinition, PotionRarity
from .relics import RelicDefinition, RelicTier
from .status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)

__all__ = [
    # actions
    "ActionNode",
    "ActionType",
    # cards
    "CardDefinition",
    "CardRarity",
    "CardTarget",
    "CardType",
    "UpgradeDefinition",
    # content_set
    "ContentSet",
    "VANILLA_STATUSES",
    # keywords
    "KeywordDefinition",
    # potions
    "PotionDefinition",
    "PotionRarity",
    # relics
    "RelicDefinition",
    "RelicTier",
    # status_effects
    "StackBehavior",
    "StatusEffectDefinition",
    "StatusTrigger",
]
