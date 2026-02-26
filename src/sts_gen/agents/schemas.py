"""Pydantic output schemas for DesignerAgent stage gates.

Each stage of the designer pipeline produces structured output validated by
these schemas.  Stages 3-4 embed real IR types (StatusEffectDefinition,
CardDefinition, etc.) so Pydantic validation catches schema errors at
generation time.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from sts_gen.ir.cards import CardDefinition, CardRarity, CardType
from sts_gen.ir.keywords import KeywordDefinition
from sts_gen.ir.potions import PotionDefinition
from sts_gen.ir.relics import RelicDefinition
from sts_gen.ir.status_effects import StatusEffectDefinition


# =====================================================================
# Stage 1: Concept
# =====================================================================

class ConceptOutput(BaseModel):
    """Stage 1 gate: character concept and signature mechanic."""

    character_name: str
    fantasy: str
    """1-2 sentence character fantasy."""

    signature_mechanic: str
    """1 sentence mechanic description."""

    mechanic_status_effect: StatusEffectDefinition
    """IR proof: the signature mechanic expressed as a real status definition."""

    archetype_seeds: list[str]
    """2-3 archetype ideas (min 2, max 4)."""

    @field_validator("archetype_seeds")
    @classmethod
    def _validate_archetype_seeds(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("At least 2 archetype seeds required")
        if len(v) > 4:
            raise ValueError("At most 4 archetype seeds allowed")
        return v


# =====================================================================
# Stage 2: Architecture
# =====================================================================

class ArchetypeSpec(BaseModel):
    """Specification for a single archetype within a character."""

    name: str
    description: str
    is_major: bool
    """True for 2-3 major archetypes."""

    setup_roles: list[str]
    """Card roles that set up this archetype."""

    payoff_roles: list[str]
    """Card roles that pay off this archetype."""


class CardRole(BaseModel):
    """A single slot in the card skeleton."""

    role_name: str
    """e.g. 'Ignite Enabler'"""

    rarity: CardRarity
    card_type: CardType
    archetypes: list[str]
    """Which archetypes this role serves."""

    brief: str
    """1-line description of what the card does."""


class ArchitectureOutput(BaseModel):
    """Stage 2 gate: archetypes and card skeleton."""

    archetypes: list[ArchetypeSpec]
    """2-4 archetypes."""

    card_skeleton: list[CardRole]
    """~70 role slots matching vanilla distribution."""

    @field_validator("archetypes")
    @classmethod
    def _validate_archetypes(cls, v: list[ArchetypeSpec]) -> list[ArchetypeSpec]:
        if len(v) < 2:
            raise ValueError("At least 2 archetypes required")
        if len(v) > 4:
            raise ValueError("At most 4 archetypes allowed")
        return v


# =====================================================================
# Stage 3: Keywords & Status Effects
# =====================================================================

class KeywordsOutput(BaseModel):
    """Stage 3 gate: custom status effects and keywords."""

    status_effects: list[StatusEffectDefinition]
    """Full IR definitions for all custom status effects."""

    keywords: list[KeywordDefinition]
    """Full IR definitions for all custom keywords."""


# =====================================================================
# Stage 4: Card Pool
# =====================================================================

class CardPoolOutput(BaseModel):
    """Stage 4 gate: full card pool, relics, and potions."""

    cards: list[CardDefinition]
    """Full IR definitions (~70 cards)."""

    relics: list[RelicDefinition]
    """3-5 relics."""

    potions: list[PotionDefinition]
    """2-3 potions."""
