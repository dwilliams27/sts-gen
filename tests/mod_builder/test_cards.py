"""Tests for CardTranspiler → Java template context."""

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    UpgradeDefinition,
)
from sts_gen.mod_builder.transpiler.cards import CardTranspiler, _extract_stats


TEMPLATE_DIR = Path(__file__).parent.parent.parent / "src" / "sts_gen" / "mod_builder" / "templates"


@pytest.fixture
def transpiler():
    return CardTranspiler(mod_id="testmod")


@pytest.fixture
def jinja_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
    )


def _make_strike():
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
        upgrade=UpgradeDefinition(
            actions=[
                ActionNode(
                    action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy"
                ),
            ],
            description="Deal 9 damage.",
        ),
    )


def _make_defend():
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
        upgrade=UpgradeDefinition(
            actions=[
                ActionNode(
                    action_type=ActionType.GAIN_BLOCK, value=8, target="self"
                ),
            ],
            description="Gain 8 Block.",
        ),
    )


def _make_power_card():
    return CardDefinition(
        id="demon_form",
        name="Demon Form",
        type=CardType.POWER,
        rarity=CardRarity.RARE,
        cost=3,
        target=CardTarget.SELF,
        description="At the start of each turn, gain 2 Strength.",
        actions=[
            ActionNode(
                action_type=ActionType.APPLY_STATUS,
                value=2,
                target="self",
                status_name="Demon Form",
            ),
        ],
        upgrade=UpgradeDefinition(
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=3,
                    target="self",
                    status_name="Demon Form",
                ),
            ],
            description="At the start of each turn, gain 3 Strength.",
        ),
    )


class TestExtractStats:
    def test_strike_stats(self):
        card = _make_strike()
        stats = _extract_stats(card.actions, card.target)
        assert stats.base_damage == 6
        assert stats.base_block is None
        assert stats.base_magic_number is None
        assert not stats.is_multi_damage

    def test_defend_stats(self):
        card = _make_defend()
        stats = _extract_stats(card.actions, card.target)
        assert stats.base_damage is None
        assert stats.base_block == 5

    def test_power_card_magic_number(self):
        card = _make_power_card()
        stats = _extract_stats(card.actions, card.target)
        assert stats.base_magic_number == 2

    def test_all_enemies_marks_multi_damage(self):
        card = CardDefinition(
            id="whirlwind",
            name="Whirlwind",
            type=CardType.ATTACK,
            rarity=CardRarity.UNCOMMON,
            cost=-1,
            target=CardTarget.ALL_ENEMIES,
            description="Deal damage to ALL enemies.",
            actions=[
                ActionNode(
                    action_type=ActionType.DEAL_DAMAGE,
                    value=5,
                    target="all_enemies",
                ),
            ],
        )
        stats = _extract_stats(card.actions, card.target)
        assert stats.is_multi_damage


class TestCardTranspiler:
    def test_strike_context(self, transpiler):
        ctx = transpiler.transpile(_make_strike())
        assert ctx["class_name"] == "Strike"
        assert ctx["card_type"] == "ATTACK"
        assert ctx["base_damage"] == 6
        assert ctx["cost"] == 1
        assert ctx["upgrade"]["deltas"]["damage"] == 3

    def test_defend_context(self, transpiler):
        ctx = transpiler.transpile(_make_defend())
        assert ctx["class_name"] == "Defend"
        assert ctx["card_type"] == "SKILL"
        assert ctx["base_block"] == 5
        assert ctx["upgrade"]["deltas"]["block"] == 3

    def test_power_card_context(self, transpiler):
        ctx = transpiler.transpile(_make_power_card())
        assert ctx["card_type"] == "POWER"
        assert ctx["base_magic_number"] == 2
        assert ctx["upgrade"]["deltas"]["magic_number"] == 1

    def test_cost_only_upgrade(self, transpiler):
        card = CardDefinition(
            id="body_slam",
            name="Body Slam",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Deal damage equal to your block.",
            actions=[
                ActionNode(
                    action_type=ActionType.DEAL_DAMAGE,
                    value=-1,
                    target="enemy",
                    condition="use_block_as_damage",
                ),
            ],
            upgrade=UpgradeDefinition(cost=0),
        )
        ctx = transpiler.transpile(card)
        assert ctx["upgrade"]["cost"] == 0
        assert ctx["upgrade"]["deltas"] == {}

    def test_exhaust_card(self, transpiler):
        card = CardDefinition(
            id="offering",
            name="Offering",
            type=CardType.SKILL,
            rarity=CardRarity.RARE,
            cost=0,
            target=CardTarget.SELF,
            description="Lose 6 HP. Gain 2 Energy. Draw 3.",
            exhaust=True,
            actions=[
                ActionNode(action_type=ActionType.LOSE_HP, value=6, target="self"),
                ActionNode(action_type=ActionType.GAIN_ENERGY, value=2),
                ActionNode(action_type=ActionType.DRAW_CARDS, value=3),
            ],
        )
        ctx = transpiler.transpile(card)
        assert ctx["exhaust"] is True


class TestCardTemplate:
    def test_strike_renders(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_strike())
        ctx["character_class_name"] = "Testmod"
        ctx["color_name"] = "TESTMOD"
        template = jinja_env.get_template("Card.java.j2")
        java = template.render(**ctx)

        assert "public class Strike extends AbstractCard" in java
        assert "this.baseDamage = DAMAGE;" in java
        assert "this.upgradeDamage(3);" in java
        assert "DamageAction" in java

    def test_defend_renders(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_defend())
        ctx["character_class_name"] = "Testmod"
        ctx["color_name"] = "TESTMOD"
        template = jinja_env.get_template("Card.java.j2")
        java = template.render(**ctx)

        assert "public class Defend extends AbstractCard" in java
        assert "this.baseBlock = BLOCK;" in java
        assert "this.upgradeBlock(3);" in java

    def test_exhaust_flag_rendered(self, transpiler, jinja_env):
        card = CardDefinition(
            id="test_exhaust",
            name="Test Exhaust",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.SELF,
            description="Test",
            exhaust=True,
            actions=[
                ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
            ],
        )
        ctx = transpiler.transpile(card)
        ctx["character_class_name"] = "Testmod"
        ctx["color_name"] = "TESTMOD"
        template = jinja_env.get_template("Card.java.j2")
        java = template.render(**ctx)
        assert "this.exhaust = true;" in java
