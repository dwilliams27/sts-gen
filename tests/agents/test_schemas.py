"""Tests for designer agent stage-gate schemas -- pure Pydantic validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sts_gen.agents.schemas import (
    ArchetypeSpec,
    ArchitectureOutput,
    CardPoolOutput,
    CardRole,
    ConceptOutput,
    KeywordsOutput,
)
from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
)
from sts_gen.ir.keywords import KeywordDefinition
from sts_gen.ir.potions import PotionDefinition, PotionRarity
from sts_gen.ir.relics import RelicDefinition, RelicTier
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)


# =====================================================================
# Helpers
# =====================================================================

def _valid_status_effect(**overrides) -> StatusEffectDefinition:
    """Build a minimal valid StatusEffectDefinition."""
    defaults = {
        "id": "test:Heat",
        "name": "Heat",
        "description": "Gain 1 Strength per stack at turn start.",
        "is_debuff": False,
        "stack_behavior": StackBehavior.INTENSITY,
        "triggers": {
            StatusTrigger.ON_TURN_START: [
                ActionNode(
                    action_type=ActionType.GAIN_STRENGTH,
                    value=1,
                    target="self",
                    condition="per_stack",
                )
            ]
        },
    }
    defaults.update(overrides)
    return StatusEffectDefinition(**defaults)


def _valid_card(**overrides) -> CardDefinition:
    """Build a minimal valid CardDefinition."""
    defaults = {
        "id": "test:Fireball",
        "name": "Fireball",
        "type": CardType.ATTACK,
        "rarity": CardRarity.COMMON,
        "cost": 1,
        "target": CardTarget.ENEMY,
        "description": "Deal 8 damage.",
        "actions": [
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=8, target="enemy")
        ],
    }
    defaults.update(overrides)
    return CardDefinition(**defaults)


def _valid_relic(**overrides) -> RelicDefinition:
    """Build a minimal valid RelicDefinition."""
    defaults = {
        "id": "test:FlameRing",
        "name": "Flame Ring",
        "tier": RelicTier.COMMON,
        "description": "At the start of combat, gain 3 Strength.",
        "trigger": "on_combat_start",
        "actions": [
            ActionNode(action_type=ActionType.GAIN_STRENGTH, value=3, target="self")
        ],
    }
    defaults.update(overrides)
    return RelicDefinition(**defaults)


def _valid_potion(**overrides) -> PotionDefinition:
    """Build a minimal valid PotionDefinition."""
    defaults = {
        "id": "test:FlamePotion",
        "name": "Flame Potion",
        "rarity": PotionRarity.COMMON,
        "description": "Deal 20 damage.",
        "target": CardTarget.ENEMY,
        "actions": [
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=20, target="enemy")
        ],
    }
    defaults.update(overrides)
    return PotionDefinition(**defaults)


# =====================================================================
# ConceptOutput tests
# =====================================================================

class TestConceptOutput:
    def test_valid_data(self) -> None:
        """Valid concept data should pass validation."""
        concept = ConceptOutput(
            character_name="Pyromancer",
            fantasy="A fire mage who builds up heat and releases it in bursts.",
            signature_mechanic="Heat stacks that convert to Strength.",
            mechanic_status_effect=_valid_status_effect(),
            archetype_seeds=["Burn", "Inferno", "Ember Control"],
        )
        assert concept.character_name == "Pyromancer"
        assert len(concept.archetype_seeds) == 3

    def test_missing_character_name_fails(self) -> None:
        """Missing character_name should fail validation."""
        with pytest.raises(ValidationError, match="character_name"):
            ConceptOutput(
                fantasy="A fire mage.",
                signature_mechanic="Heat.",
                mechanic_status_effect=_valid_status_effect(),
                archetype_seeds=["Burn", "Inferno"],
            )

    def test_too_few_archetype_seeds_fails(self) -> None:
        """Fewer than 2 archetype seeds should fail."""
        with pytest.raises(ValidationError, match="At least 2"):
            ConceptOutput(
                character_name="Pyromancer",
                fantasy="A fire mage.",
                signature_mechanic="Heat.",
                mechanic_status_effect=_valid_status_effect(),
                archetype_seeds=["Burn"],
            )

    def test_too_many_archetype_seeds_fails(self) -> None:
        """More than 4 archetype seeds should fail."""
        with pytest.raises(ValidationError, match="At most 4"):
            ConceptOutput(
                character_name="Pyromancer",
                fantasy="A fire mage.",
                signature_mechanic="Heat.",
                mechanic_status_effect=_valid_status_effect(),
                archetype_seeds=["A", "B", "C", "D", "E"],
            )

    def test_invalid_status_effect_fails(self) -> None:
        """Bad StatusEffectDefinition (missing required field) should fail."""
        with pytest.raises(ValidationError):
            ConceptOutput(
                character_name="Pyromancer",
                fantasy="A fire mage.",
                signature_mechanic="Heat.",
                mechanic_status_effect={"id": "test:Bad"},  # Missing required fields
                archetype_seeds=["Burn", "Inferno"],
            )


# =====================================================================
# ArchetypeSpec and CardRole tests
# =====================================================================

class TestArchetypeSpec:
    def test_valid_data(self) -> None:
        """Valid archetype spec should pass."""
        spec = ArchetypeSpec(
            name="Burn",
            description="Applies persistent fire damage.",
            is_major=True,
            setup_roles=["Ignite Enabler"],
            payoff_roles=["Inferno Finisher"],
        )
        assert spec.is_major is True

    def test_empty_setup_roles_allowed(self) -> None:
        """Empty setup_roles is allowed (for minor archetypes)."""
        spec = ArchetypeSpec(
            name="Utility",
            description="Supporting tools.",
            is_major=False,
            setup_roles=[],
            payoff_roles=["Draw Engine"],
        )
        assert spec.setup_roles == []


class TestCardRole:
    def test_valid_data(self) -> None:
        """Valid card role should pass."""
        role = CardRole(
            role_name="Ignite Enabler",
            rarity=CardRarity.COMMON,
            card_type=CardType.ATTACK,
            archetypes=["Burn"],
            brief="Deal damage and apply Heat.",
        )
        assert role.rarity == CardRarity.COMMON

    def test_invalid_rarity_fails(self) -> None:
        """Invalid CardRarity value should fail."""
        with pytest.raises(ValidationError):
            CardRole(
                role_name="Bad Role",
                rarity="LEGENDARY",
                card_type=CardType.ATTACK,
                archetypes=["Burn"],
                brief="Does something.",
            )


# =====================================================================
# ArchitectureOutput tests
# =====================================================================

class TestArchitectureOutput:
    def test_valid_data(self) -> None:
        """Valid architecture should pass."""
        arch = ArchitectureOutput(
            archetypes=[
                ArchetypeSpec(
                    name="Burn", description="Fire damage.", is_major=True,
                    setup_roles=["Igniter"], payoff_roles=["Inferno"],
                ),
                ArchetypeSpec(
                    name="Shield", description="Block focus.", is_major=True,
                    setup_roles=["Fortifier"], payoff_roles=["Bastion"],
                ),
            ],
            card_skeleton=[
                CardRole(
                    role_name="Igniter", rarity=CardRarity.COMMON,
                    card_type=CardType.ATTACK, archetypes=["Burn"],
                    brief="Deal damage and apply Heat.",
                ),
            ],
        )
        assert len(arch.archetypes) == 2

    def test_too_few_archetypes_fails(self) -> None:
        """Fewer than 2 archetypes should fail."""
        with pytest.raises(ValidationError, match="At least 2"):
            ArchitectureOutput(
                archetypes=[
                    ArchetypeSpec(
                        name="Burn", description="Fire.", is_major=True,
                        setup_roles=[], payoff_roles=[],
                    ),
                ],
                card_skeleton=[],
            )

    def test_too_many_archetypes_fails(self) -> None:
        """More than 4 archetypes should fail."""
        specs = [
            ArchetypeSpec(
                name=f"Arch{i}", description=".", is_major=True,
                setup_roles=[], payoff_roles=[],
            )
            for i in range(5)
        ]
        with pytest.raises(ValidationError, match="At most 4"):
            ArchitectureOutput(archetypes=specs, card_skeleton=[])


# =====================================================================
# KeywordsOutput tests
# =====================================================================

class TestKeywordsOutput:
    def test_valid_data(self) -> None:
        """Valid keywords output should pass."""
        kw = KeywordsOutput(
            status_effects=[_valid_status_effect()],
            keywords=[
                KeywordDefinition(
                    id="test:Heat",
                    name="Heat",
                    description="Stacks that convert to Strength.",
                )
            ],
        )
        assert len(kw.status_effects) == 1
        assert len(kw.keywords) == 1

    def test_bad_stack_behavior_fails(self) -> None:
        """Invalid StackBehavior in status effect should fail."""
        with pytest.raises(ValidationError):
            KeywordsOutput(
                status_effects=[
                    {
                        "id": "test:Bad",
                        "name": "Bad",
                        "description": "Bad status.",
                        "is_debuff": False,
                        "stack_behavior": "INVALID_BEHAVIOR",
                        "triggers": {},
                    }
                ],
                keywords=[],
            )


# =====================================================================
# CardPoolOutput tests
# =====================================================================

class TestCardPoolOutput:
    def test_valid_data(self) -> None:
        """Valid card pool output should pass."""
        pool = CardPoolOutput(
            cards=[_valid_card()],
            relics=[_valid_relic()],
            potions=[_valid_potion()],
        )
        assert len(pool.cards) == 1
        assert len(pool.relics) == 1
        assert len(pool.potions) == 1

    def test_bad_card_type_fails(self) -> None:
        """Invalid CardType should fail."""
        with pytest.raises(ValidationError):
            CardPoolOutput(
                cards=[
                    {
                        "id": "test:Bad",
                        "name": "Bad Card",
                        "type": "WEAPON",
                        "rarity": "COMMON",
                        "cost": 1,
                        "target": "ENEMY",
                        "description": "Bad.",
                        "actions": [],
                    }
                ],
                relics=[],
                potions=[],
            )

    def test_bad_action_type_in_card_fails(self) -> None:
        """Invalid ActionType in card actions should fail."""
        with pytest.raises(ValidationError):
            CardPoolOutput(
                cards=[
                    {
                        "id": "test:Bad",
                        "name": "Bad Card",
                        "type": "ATTACK",
                        "rarity": "COMMON",
                        "cost": 1,
                        "target": "ENEMY",
                        "description": "Bad.",
                        "actions": [
                            {"action_type": "cast_spell", "value": 10}
                        ],
                    }
                ],
                relics=[],
                potions=[],
            )
