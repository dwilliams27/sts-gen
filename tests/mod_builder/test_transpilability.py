"""Tests for transpilability validation on ContentSet."""

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
)
from sts_gen.ir.content_set import ContentSet
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)


def _card(card_id: str, actions: list[ActionNode], **kwargs) -> CardDefinition:
    """Helper to create a minimal card."""
    defaults = dict(
        id=card_id,
        name=card_id.title(),
        type=CardType.ATTACK,
        rarity=CardRarity.COMMON,
        cost=1,
        target=CardTarget.ENEMY,
        description="Test card.",
        actions=actions,
    )
    defaults.update(kwargs)
    return CardDefinition(**defaults)


class TestTriggerCustomRejected:
    def test_trigger_custom_rejected(self):
        card = _card(
            "bad_card",
            [ActionNode(action_type=ActionType.TRIGGER_CUSTOM, condition="summon_skeleton")],
        )
        with pytest.raises(ValueError, match="trigger_custom"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_trigger_custom_in_children_rejected(self):
        card = _card(
            "bad_card",
            [
                ActionNode(
                    action_type=ActionType.CONDITIONAL,
                    condition="no_block",
                    children=[
                        ActionNode(
                            action_type=ActionType.TRIGGER_CUSTOM,
                            condition="raise_dead",
                        )
                    ],
                )
            ],
        )
        with pytest.raises(ValueError, match="trigger_custom"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_error_names_offending_card(self):
        card = _card(
            "soul_harvest",
            [ActionNode(action_type=ActionType.TRIGGER_CUSTOM, condition="reap_souls")],
        )
        with pytest.raises(ValueError, match="soul_harvest"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_error_includes_condition_string(self):
        card = _card(
            "bad",
            [ActionNode(action_type=ActionType.TRIGGER_CUSTOM, condition="my_custom_thing")],
        )
        with pytest.raises(ValueError, match="my_custom_thing"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])


class TestUnknownConditionsRejected:
    def test_unknown_deal_damage_condition(self):
        card = _card(
            "bad",
            [
                ActionNode(
                    action_type=ActionType.DEAL_DAMAGE,
                    value=5,
                    target="enemy",
                    condition="based_on_souls",
                )
            ],
        )
        with pytest.raises(ValueError, match="unknown condition"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_condition_on_type_that_disallows_it(self):
        card = _card(
            "bad",
            [
                ActionNode(
                    action_type=ActionType.GAIN_GOLD,
                    value=10,
                    condition="some_condition",
                )
            ],
        )
        with pytest.raises(ValueError, match="does not accept conditions"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_unknown_conditional_condition(self):
        card = _card(
            "bad",
            [
                ActionNode(
                    action_type=ActionType.CONDITIONAL,
                    condition="is_full_moon",
                    children=[
                        ActionNode(action_type=ActionType.DRAW_CARDS, value=1)
                    ],
                )
            ],
        )
        with pytest.raises(ValueError, match="unknown condition"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])


class TestMissingRequiredFields:
    def test_apply_status_without_status_name(self):
        card = _card(
            "bad",
            [
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=2,
                    target="enemy",
                    # status_name is missing
                )
            ],
        )
        with pytest.raises(ValueError, match="status_name"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_remove_status_without_status_name(self):
        card = _card(
            "bad",
            [
                ActionNode(
                    action_type=ActionType.REMOVE_STATUS,
                    target="self",
                    # status_name is missing
                )
            ],
        )
        with pytest.raises(ValueError, match="status_name"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])


class TestValidCardsPass:
    def test_basic_damage_card(self):
        card = _card(
            "slash",
            [ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy")],
        )
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("slash") is not None

    def test_damage_with_valid_condition(self):
        card = _card(
            "slam",
            [
                ActionNode(
                    action_type=ActionType.DEAL_DAMAGE,
                    value=-1,
                    target="enemy",
                    condition="use_block_as_damage",
                )
            ],
        )
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("slam") is not None

    def test_conditional_with_valid_condition(self):
        card = _card(
            "finisher",
            [
                ActionNode(
                    action_type=ActionType.CONDITIONAL,
                    condition="target_is_dead",
                    children=[
                        ActionNode(action_type=ActionType.DRAW_CARDS, value=1)
                    ],
                )
            ],
        )
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("finisher") is not None

    def test_apply_status_with_status_name(self):
        card = _card(
            "debuff",
            [
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=2,
                    target="enemy",
                    status_name="Vulnerable",
                )
            ],
        )
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("debuff") is not None

    def test_no_condition_always_valid(self):
        """Actions without conditions should always pass."""
        card = _card(
            "simple",
            [
                ActionNode(action_type=ActionType.GAIN_ENERGY, value=2),
                ActionNode(action_type=ActionType.HEAL, value=5, target="self"),
                ActionNode(action_type=ActionType.LOSE_HP, value=3, target="self"),
            ],
        )
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("simple") is not None

    def test_parameterised_conditional(self):
        card = _card(
            "check",
            [
                ActionNode(
                    action_type=ActionType.CONDITIONAL,
                    condition="has_status:Vulnerable",
                    children=[
                        ActionNode(action_type=ActionType.DRAW_CARDS, value=1)
                    ],
                )
            ],
        )
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("check") is not None


class TestStatusTriggerValidation:
    def test_invalid_condition_in_status_trigger(self):
        status = StatusEffectDefinition(
            id="mod:BadBuff",
            name="Bad Buff",
            description="Test.",
            is_debuff=False,
            stack_behavior=StackBehavior.INTENSITY,
            triggers={
                StatusTrigger.ON_TURN_START: [
                    ActionNode(
                        action_type=ActionType.DEAL_DAMAGE,
                        value=5,
                        target="all_enemies",
                        condition="soul_power_scaling",
                    )
                ]
            },
        )
        with pytest.raises(ValueError, match="unknown condition"):
            ContentSet(
                mod_id="test", mod_name="Test", status_effects=[status]
            )

    def test_valid_per_stack_in_status_trigger(self):
        status = StatusEffectDefinition(
            id="mod:Burn",
            name="Burn",
            description="Deal damage at end of turn.",
            is_debuff=True,
            stack_behavior=StackBehavior.INTENSITY,
            triggers={
                StatusTrigger.ON_TURN_END: [
                    ActionNode(
                        action_type=ActionType.LOSE_HP,
                        value=1,
                        target="self",
                        condition="per_stack",
                    )
                ]
            },
        )
        cs = ContentSet(
            mod_id="test", mod_name="Test", status_effects=[status]
        )
        assert len(cs.status_effects) == 1
