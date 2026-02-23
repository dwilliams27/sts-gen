"""Tests for the IR schema -- ActionNode, CardDefinition, ContentSet, etc."""

import json

import pytest

from sts_gen.ir import (
    ActionNode,
    ActionType,
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    ContentSet,
    UpgradeDefinition,
)
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strike() -> CardDefinition:
    """Minimal Strike card definition used across several tests."""
    return CardDefinition(
        id="strike",
        name="Strike",
        type=CardType.ATTACK,
        rarity=CardRarity.BASIC,
        cost=1,
        target=CardTarget.ENEMY,
        description="Deal 6 damage.",
        actions=[
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
        ],
    )


def _make_defend() -> CardDefinition:
    return CardDefinition(
        id="defend",
        name="Defend",
        type=CardType.SKILL,
        rarity=CardRarity.BASIC,
        cost=1,
        target=CardTarget.SELF,
        description="Gain 5 Block.",
        actions=[
            ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
        ],
    )


# ---------------------------------------------------------------------------
# Card serialization round-trip (JSON)
# ---------------------------------------------------------------------------

class TestCardSerializationRoundTrip:
    """Card definitions must survive a JSON round-trip via Pydantic."""

    def test_strike_round_trip(self):
        card = _make_strike()
        json_str = card.model_dump_json()
        restored = CardDefinition.model_validate_json(json_str)

        assert restored.id == card.id
        assert restored.name == card.name
        assert restored.type == card.type
        assert restored.rarity == card.rarity
        assert restored.cost == card.cost
        assert restored.target == card.target
        assert restored.description == card.description
        assert len(restored.actions) == 1
        assert restored.actions[0].action_type == ActionType.DEAL_DAMAGE
        assert restored.actions[0].value == 6
        assert restored.actions[0].target == "enemy"

    def test_card_with_upgrade_round_trip(self):
        card = CardDefinition(
            id="strike",
            name="Strike",
            type=CardType.ATTACK,
            rarity=CardRarity.BASIC,
            cost=1,
            target=CardTarget.ENEMY,
            description="Deal 6 damage.",
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
            ],
            upgrade=UpgradeDefinition(
                actions=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy"),
                ],
                description="Deal 9 damage.",
            ),
        )
        json_str = card.model_dump_json()
        restored = CardDefinition.model_validate_json(json_str)

        assert restored.upgrade is not None
        assert restored.upgrade.cost is None  # not changed
        assert len(restored.upgrade.actions) == 1
        assert restored.upgrade.actions[0].value == 9
        assert restored.upgrade.description == "Deal 9 damage."

    def test_round_trip_through_dict(self):
        card = _make_strike()
        d = card.model_dump()
        restored = CardDefinition.model_validate(d)
        assert restored == card


# ---------------------------------------------------------------------------
# ActionNode with children (recursive structure)
# ---------------------------------------------------------------------------

class TestActionNodeRecursive:
    def test_repeat_with_children(self):
        node = ActionNode(
            action_type=ActionType.REPEAT,
            times=3,
            children=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=3, target="random_enemy"),
            ],
        )
        assert node.times == 3
        assert len(node.children) == 1
        assert node.children[0].action_type == ActionType.DEAL_DAMAGE
        assert node.children[0].value == 3

    def test_conditional_with_children(self):
        node = ActionNode(
            action_type=ActionType.CONDITIONAL,
            condition="hp_below:50",
            children=[
                ActionNode(action_type=ActionType.GAIN_BLOCK, value=10, target="self"),
            ],
        )
        assert node.condition == "hp_below:50"
        assert len(node.children) == 1

    def test_nested_children_serialization(self):
        """A repeat containing a conditional containing a deal_damage."""
        node = ActionNode(
            action_type=ActionType.REPEAT,
            times=2,
            children=[
                ActionNode(
                    action_type=ActionType.CONDITIONAL,
                    condition="has_status:strength",
                    children=[
                        ActionNode(
                            action_type=ActionType.DEAL_DAMAGE,
                            value=5,
                            target="enemy",
                        ),
                    ],
                ),
            ],
        )
        json_str = node.model_dump_json()
        restored = ActionNode.model_validate_json(json_str)
        assert restored.times == 2
        assert len(restored.children) == 1
        inner = restored.children[0]
        assert inner.action_type == ActionType.CONDITIONAL
        assert len(inner.children) == 1
        assert inner.children[0].value == 5


# ---------------------------------------------------------------------------
# ContentSet validation catches bad status references
# ---------------------------------------------------------------------------

class TestContentSetValidation:
    def test_vanilla_status_reference_is_allowed(self):
        """Referencing a known vanilla status like 'Vulnerable' should work."""
        card = CardDefinition(
            id="test_card",
            name="Test Card",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Apply 2 Vulnerable.",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=2,
                    status_name="Vulnerable",
                    target="enemy",
                ),
            ],
        )
        # Should not raise
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("test_card") is not None

    def test_unknown_status_reference_raises(self):
        """Referencing a status that is neither vanilla nor defined should fail."""
        card = CardDefinition(
            id="bad_card",
            name="Bad Card",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Apply 2 TotallyFakeStatus.",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=2,
                    status_name="TotallyFakeStatus",
                    target="enemy",
                ),
            ],
        )
        with pytest.raises(ValueError, match="Unknown status effect"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_custom_status_defined_is_allowed(self):
        """Defining a custom status and referencing it should work."""
        custom_status = StatusEffectDefinition(
            id="my_mod:Burning",
            name="Burning",
            description="Take damage at end of turn.",
            is_debuff=True,
            stack_behavior=StackBehavior.INTENSITY,
            triggers={
                StatusTrigger.ON_TURN_END: [
                    ActionNode(
                        action_type=ActionType.DEAL_DAMAGE,
                        value=3,
                        target="self",
                    ),
                ],
            },
            decay_per_turn=0,
        )
        card = CardDefinition(
            id="ignite",
            name="Ignite",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Apply 3 Burning.",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=3,
                    status_name="my_mod:Burning",
                    target="enemy",
                ),
            ],
        )
        cs = ContentSet(
            mod_id="test",
            mod_name="Test",
            cards=[card],
            status_effects=[custom_status],
        )
        assert cs.get_status("my_mod:Burning") is not None


# ---------------------------------------------------------------------------
# CardDefinition with upgrade
# ---------------------------------------------------------------------------

class TestCardWithUpgrade:
    def test_upgrade_with_new_cost(self):
        card = CardDefinition(
            id="body_slam",
            name="Body Slam",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Deal damage equal to your Block.",
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=0, target="enemy"),
            ],
            upgrade=UpgradeDefinition(cost=0),
        )
        assert card.upgrade.cost == 0
        assert card.upgrade.actions is None  # not changed
        assert card.upgrade.description is None

    def test_upgrade_with_new_actions(self):
        card = _make_strike()
        card.upgrade = UpgradeDefinition(
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy"),
            ],
        )
        assert card.upgrade.actions[0].value == 9

    def test_no_upgrade(self):
        card = _make_strike()
        assert card.upgrade is None


# ---------------------------------------------------------------------------
# All card types, rarities, targets create successfully
# ---------------------------------------------------------------------------

class TestEnumCoverage:
    @pytest.mark.parametrize(
        "card_type",
        [CardType.ATTACK, CardType.SKILL, CardType.POWER, CardType.STATUS, CardType.CURSE],
    )
    def test_all_card_types(self, card_type):
        card = CardDefinition(
            id=f"test_{card_type.value.lower()}",
            name=f"Test {card_type.value}",
            type=card_type,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Test card.",
            actions=[],
        )
        assert card.type == card_type

    @pytest.mark.parametrize(
        "rarity",
        [CardRarity.BASIC, CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE, CardRarity.SPECIAL],
    )
    def test_all_card_rarities(self, rarity):
        card = CardDefinition(
            id=f"test_{rarity.value.lower()}",
            name=f"Test {rarity.value}",
            type=CardType.ATTACK,
            rarity=rarity,
            cost=1,
            target=CardTarget.ENEMY,
            description="Test card.",
            actions=[],
        )
        assert card.rarity == rarity

    @pytest.mark.parametrize(
        "target",
        [CardTarget.ENEMY, CardTarget.ALL_ENEMIES, CardTarget.SELF, CardTarget.NONE],
    )
    def test_all_card_targets(self, target):
        card = CardDefinition(
            id=f"test_{target.value.lower()}",
            name=f"Test {target.value}",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=target,
            description="Test card.",
            actions=[],
        )
        assert card.target == target

    @pytest.mark.parametrize(
        "action_type",
        list(ActionType),
    )
    def test_all_action_types_construct(self, action_type):
        node = ActionNode(action_type=action_type)
        assert node.action_type == action_type
