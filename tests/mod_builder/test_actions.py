"""Tests for ActionNode → Java transpiler."""

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.mod_builder.transpiler.actions import ActionTranspiler, TranspileContext


@pytest.fixture
def transpiler():
    return ActionTranspiler()


@pytest.fixture
def card_ctx():
    return TranspileContext(source_var="p", target_var="m", indent=2)


@pytest.fixture
def power_ctx():
    return TranspileContext(
        source_var="this.owner",
        target_var="this.owner",
        is_power=True,
        indent=2,
    )


class TestDealDamage:
    def test_single_target(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy")
        result = transpiler.transpile([node], card_ctx)
        assert "DamageAction" in result
        assert "this.damage" in result
        assert "this.damageTypeForTurn" in result

    def test_all_enemies(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.DEAL_DAMAGE, value=8, target="all_enemies"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "DamageAllEnemiesAction" in result
        assert "this.multiDamage" in result

    def test_multi_hit(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.DEAL_DAMAGE, value=2, target="enemy", times=3
        )
        result = transpiler.transpile([node], card_ctx)
        assert "for (int i = 0; i < 3; i++)" in result
        assert "DamageAction" in result

    def test_no_strength(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.DEAL_DAMAGE,
            value=5,
            target="all_enemies",
            condition="no_strength",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "DamageType.THORNS" in result

    def test_use_block_as_damage(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.DEAL_DAMAGE,
            value=-1,
            target="enemy",
            condition="use_block_as_damage",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "p.currentBlock" in result

    def test_times_from_x_cost(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.DEAL_DAMAGE,
            value=5,
            target="enemy",
            condition="times_from_x_cost",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "this.energyOnUse" in result
        assert "for (int i = 0;" in result

    def test_power_per_stack_no_strength(self, transpiler, power_ctx):
        node = ActionNode(
            action_type=ActionType.DEAL_DAMAGE,
            value=5,
            target="all_enemies",
            condition="per_stack_no_strength",
        )
        result = transpiler.transpile([node], power_ctx)
        assert "DamageType.THORNS" in result
        assert "this.amount" in result


class TestGainBlock:
    def test_basic(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self")
        result = transpiler.transpile([node], card_ctx)
        assert "GainBlockAction" in result
        assert "this.block" in result

    def test_power_per_stack(self, transpiler, power_ctx):
        node = ActionNode(
            action_type=ActionType.GAIN_BLOCK,
            value=1,
            target="self",
            condition="per_stack_raw",
        )
        result = transpiler.transpile([node], power_ctx)
        assert "this.amount" in result

    def test_double_block(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.DOUBLE_BLOCK, target="self")
        result = transpiler.transpile([node], card_ctx)
        assert "p.currentBlock" in result


class TestApplyStatus:
    def test_vanilla_status(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.APPLY_STATUS,
            value=2,
            target="enemy",
            status_name="Vulnerable",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "ApplyPowerAction" in result
        assert "VulnerablePower" in result

    def test_custom_status(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.APPLY_STATUS,
            value=3,
            target="self",
            status_name="Burning",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "BurningPower" in result
        assert "ApplyPowerAction" in result

    def test_remove_status(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.REMOVE_STATUS,
            target="self",
            status_name="Vulnerable",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "RemoveSpecificPowerAction" in result
        assert '"Vulnerable"' in result


class TestMultiplyStatus:
    def test_basic(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.MULTIPLY_STATUS,
            value=2,
            target="self",
            status_name="Strength",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "getPower" in result
        assert "pow.amount *= 2" in result


class TestCardManipulation:
    def test_draw_cards(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.DRAW_CARDS, value=2)
        result = transpiler.transpile([node], card_ctx)
        assert "DrawCardAction" in result
        assert "2" in result

    def test_discard_cards(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.DISCARD_CARDS, value=1)
        result = transpiler.transpile([node], card_ctx)
        assert "DiscardAction" in result

    def test_exhaust_cards(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.EXHAUST_CARDS, value=1)
        result = transpiler.transpile([node], card_ctx)
        assert "ExhaustAction" in result

    def test_exhaust_all(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.EXHAUST_CARDS, value=-1)
        result = transpiler.transpile([node], card_ctx)
        assert "ExhaustSpecificCardAction" in result
        assert "p.hand.group" in result

    def test_exhaust_non_attack(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.EXHAUST_CARDS, value=-1, condition="non_attack"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "CardType.ATTACK" in result

    def test_add_card_to_hand(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.ADD_CARD_TO_PILE,
            card_id="wound",
            pile="hand",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "MakeTempCardInHandAction" in result
        assert "Wound" in result

    def test_add_card_to_discard(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.ADD_CARD_TO_PILE,
            card_id="anger",
            pile="discard",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "MakeTempCardInDiscardAction" in result

    def test_add_card_to_draw(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.ADD_CARD_TO_PILE,
            card_id="wound",
            pile="draw",
        )
        result = transpiler.transpile([node], card_ctx)
        assert "MakeTempCardInDrawPileAction" in result

    def test_shuffle_into_draw(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.SHUFFLE_INTO_DRAW)
        result = transpiler.transpile([node], card_ctx)
        assert "ShuffleAction" in result

    def test_play_top_card(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.PLAY_TOP_CARD)
        result = transpiler.transpile([node], card_ctx)
        assert "NewQueueCardAction" in result
        assert "drawPile.getTopCard()" in result


class TestResources:
    def test_gain_energy(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.GAIN_ENERGY, value=2)
        result = transpiler.transpile([node], card_ctx)
        assert "GainEnergyAction" in result

    def test_lose_energy(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.LOSE_ENERGY, value=1)
        result = transpiler.transpile([node], card_ctx)
        assert "energy.use" in result

    def test_heal(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.HEAL, value=6, target="self")
        result = transpiler.transpile([node], card_ctx)
        assert "HealAction" in result

    def test_heal_raise_max(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.HEAL, value=5, target="self", condition="raise_max_hp"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "increaseMaxHp" in result

    def test_lose_hp(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.LOSE_HP, value=3, target="self")
        result = transpiler.transpile([node], card_ctx)
        assert "LoseHPAction" in result

    def test_gain_gold(self, transpiler, card_ctx):
        node = ActionNode(action_type=ActionType.GAIN_GOLD, value=15)
        result = transpiler.transpile([node], card_ctx)
        assert "GainGoldAction" in result


class TestStrengthDexterity:
    def test_gain_strength(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.GAIN_STRENGTH, value=2, target="self"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "StrengthPower" in result
        assert "ApplyPowerAction" in result

    def test_gain_dexterity(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.GAIN_DEXTERITY, value=1, target="self"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "DexterityPower" in result
        assert "ApplyPowerAction" in result

    def test_negative_strength(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.GAIN_STRENGTH, value=-6, target="enemy"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "-6" in result
        assert "StrengthPower" in result


class TestControlFlow:
    def test_conditional(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.CONDITIONAL,
            condition="has_status:Vulnerable",
            children=[
                ActionNode(action_type=ActionType.DRAW_CARDS, value=1),
            ],
        )
        result = transpiler.transpile([node], card_ctx)
        assert "if (" in result
        assert "hasPower" in result
        assert '"Vulnerable"' in result
        assert "DrawCardAction" in result

    def test_conditional_no_block(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.CONDITIONAL,
            condition="no_block",
            children=[
                ActionNode(action_type=ActionType.GAIN_BLOCK, value=6, target="self"),
            ],
        )
        result = transpiler.transpile([node], card_ctx)
        assert "p.currentBlock == 0" in result

    def test_conditional_hp_below(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.CONDITIONAL,
            condition="hp_below:50",
            children=[
                ActionNode(action_type=ActionType.HEAL, value=5, target="self"),
            ],
        )
        result = transpiler.transpile([node], card_ctx)
        assert "p.currentHealth < p.maxHealth * 50 / 100" in result

    def test_for_each_enemy(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.FOR_EACH,
            condition="enemy",
            children=[
                ActionNode(
                    action_type=ActionType.DEAL_DAMAGE, value=5, target="enemy"
                ),
            ],
        )
        result = transpiler.transpile([node], card_ctx)
        assert "for (AbstractMonster mo" in result
        assert "isDeadOrEscaped" in result

    def test_repeat(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.REPEAT,
            times=3,
            children=[
                ActionNode(action_type=ActionType.DRAW_CARDS, value=1),
            ],
        )
        result = transpiler.transpile([node], card_ctx)
        assert "for (int i = 0; i < 3; i++)" in result
        assert "DrawCardAction" in result

    def test_repeat_x_cost(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.REPEAT,
            condition="times_from_x_cost",
            children=[
                ActionNode(action_type=ActionType.DRAW_CARDS, value=1),
            ],
        )
        result = transpiler.transpile([node], card_ctx)
        assert "this.energyOnUse" in result


class TestTriggerCustom:
    def test_exhume(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.TRIGGER_CUSTOM, condition="exhume"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "ExhumeAction" in result

    def test_armaments(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.TRIGGER_CUSTOM, condition="armaments"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "ArmamentsAction" in result

    def test_armaments_all(self, transpiler, card_ctx):
        node = ActionNode(
            action_type=ActionType.TRIGGER_CUSTOM, condition="armaments_all"
        )
        result = transpiler.transpile([node], card_ctx)
        assert "ArmamentsAction(true)" in result


class TestConditionToJava:
    def test_has_status_vanilla(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("has_status:Vulnerable", card_ctx)
        assert result == 'p.hasPower("Vulnerable")'

    def test_target_has_status(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("target_has_status:Weak", card_ctx)
        assert result == 'm.hasPower("Weakened")'

    def test_hand_empty(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("hand_empty", card_ctx)
        assert result == "p.hand.size() == 0"

    def test_hand_size_gte(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("hand_size_gte:3", card_ctx)
        assert result == "p.hand.size() >= 3"

    def test_only_attacks_in_hand(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("only_attacks_in_hand", card_ctx)
        assert "onlyAttacksInHand" in result

    def test_enemy_intends_attack(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("enemy_intends_attack", card_ctx)
        assert "getIntentBaseDmg" in result

    def test_target_is_dead(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("target_is_dead", card_ctx)
        assert "isDeadOrEscaped" in result

    def test_turn_eq(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("turn_eq:1", card_ctx)
        assert "actionManager.turn == 1" in result

    def test_unknown_condition_fallback(self, transpiler, card_ctx):
        result = transpiler._condition_to_java("something_unknown", card_ctx)
        assert "true" in result
        assert "something_unknown" in result

    def test_has_status_custom(self, transpiler, card_ctx):
        """Custom status uses POWER_ID constant."""
        result = transpiler._condition_to_java("has_status:Burning", card_ctx)
        assert "BurningPower.POWER_ID" in result


class TestMultipleNodes:
    def test_two_actions(self, transpiler, card_ctx):
        nodes = [
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
            ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
        ]
        result = transpiler.transpile(nodes, card_ctx)
        assert "DamageAction" in result
        assert "GainBlockAction" in result
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_nested_conditional(self, transpiler, card_ctx):
        nodes = [
            ActionNode(
                action_type=ActionType.CONDITIONAL,
                condition="no_block",
                children=[
                    ActionNode(
                        action_type=ActionType.GAIN_BLOCK,
                        value=6,
                        target="self",
                    ),
                    ActionNode(
                        action_type=ActionType.DRAW_CARDS,
                        value=1,
                    ),
                ],
            ),
        ]
        result = transpiler.transpile(nodes, card_ctx)
        assert "if (" in result
        assert "GainBlockAction" in result
        assert "DrawCardAction" in result
