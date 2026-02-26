"""Tests for ModBuilder — top-level build orchestration."""

import json

import pytest
from pathlib import Path

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    UpgradeDefinition,
)
from sts_gen.ir.content_set import ContentSet
from sts_gen.ir.potions import PotionDefinition, PotionRarity
from sts_gen.ir.relics import RelicDefinition, RelicTier
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)
from sts_gen.mod_builder.builder import ModBuilder


def _make_content_set():
    """Content set with cards, relic, potion, status effect."""
    return ContentSet(
        mod_id="pyromancer",
        mod_name="The Pyromancer",
        author="sts-gen",
        version="0.1.0",
        cards=[
            CardDefinition(
                id="fire_strike",
                name="Fire Strike",
                type=CardType.ATTACK,
                rarity=CardRarity.BASIC,
                cost=1,
                target=CardTarget.ENEMY,
                description="Deal 6 damage. Apply 1 Burning.",
                actions=[
                    ActionNode(
                        action_type=ActionType.DEAL_DAMAGE,
                        value=6,
                        target="enemy",
                    ),
                    ActionNode(
                        action_type=ActionType.APPLY_STATUS,
                        value=1,
                        target="enemy",
                        status_name="Burning",
                    ),
                ],
                upgrade=UpgradeDefinition(
                    actions=[
                        ActionNode(
                            action_type=ActionType.DEAL_DAMAGE,
                            value=9,
                            target="enemy",
                        ),
                        ActionNode(
                            action_type=ActionType.APPLY_STATUS,
                            value=2,
                            target="enemy",
                            status_name="Burning",
                        ),
                    ],
                    description="Deal 9 damage. Apply 2 Burning.",
                ),
            ),
            CardDefinition(
                id="fire_defend",
                name="Fire Defend",
                type=CardType.SKILL,
                rarity=CardRarity.BASIC,
                cost=1,
                target=CardTarget.SELF,
                description="Gain 5 Block.",
                actions=[
                    ActionNode(
                        action_type=ActionType.GAIN_BLOCK,
                        value=5,
                        target="self",
                    ),
                ],
                upgrade=UpgradeDefinition(
                    actions=[
                        ActionNode(
                            action_type=ActionType.GAIN_BLOCK,
                            value=8,
                            target="self",
                        ),
                    ],
                    description="Gain 8 Block.",
                ),
            ),
            CardDefinition(
                id="inferno",
                name="Inferno",
                type=CardType.POWER,
                rarity=CardRarity.RARE,
                cost=3,
                target=CardTarget.SELF,
                description="Apply 5 Burning to self.",
                actions=[
                    ActionNode(
                        action_type=ActionType.APPLY_STATUS,
                        value=5,
                        target="self",
                        status_name="Burning",
                    ),
                ],
            ),
        ],
        relics=[
            RelicDefinition(
                id="ember_heart",
                name="Ember Heart",
                tier=RelicTier.STARTER,
                description="At the start of combat, gain 10 Block.",
                trigger="on_combat_start",
                actions=[
                    ActionNode(
                        action_type=ActionType.GAIN_BLOCK,
                        value=10,
                        target="self",
                        condition="raw",
                    ),
                ],
            ),
        ],
        potions=[
            PotionDefinition(
                id="fire_potion",
                name="Fire Potion",
                rarity=PotionRarity.COMMON,
                description="Deal 20 damage.",
                target=CardTarget.ENEMY,
                actions=[
                    ActionNode(
                        action_type=ActionType.DEAL_DAMAGE,
                        value=20,
                        target="enemy",
                        condition="no_strength",
                    ),
                ],
            ),
        ],
        status_effects=[
            StatusEffectDefinition(
                id="Burning",
                name="Burning",
                description="At the end of turn, lose HP.",
                is_debuff=True,
                stack_behavior=StackBehavior.INTENSITY,
                decay_per_turn=1,
                triggers={
                    StatusTrigger.ON_TURN_END: [
                        ActionNode(
                            action_type=ActionType.LOSE_HP,
                            value=1,
                            target="self",
                            condition="per_stack",
                        ),
                    ],
                },
            ),
        ],
    )


class TestModBuilder:
    def test_build_skip_compile(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        result = builder.build()

        assert result.is_dir()
        assert (result / "pom.xml").is_file()

    def test_pom_xml_generated(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        pom = (tmp_path / "pyromancer" / "pom.xml").read_text()
        assert "<artifactId>pyromancer</artifactId>" in pom
        assert "<version>0.1.0</version>" in pom
        assert "slaythespire" in pom

    def test_modthespire_json_generated(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        mts_path = (
            tmp_path / "pyromancer" / "src" / "main" / "resources" / "ModTheSpire.json"
        )
        mts = json.loads(mts_path.read_text())
        assert mts["name"] == "The Pyromancer"
        assert mts["modid"] == "pyromancer"
        assert "basemod" in mts["dependencies"]

    def test_full_project_structure(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        root = tmp_path / "pyromancer"
        java_root = root / "src" / "main" / "java" / "sts_gen" / "pyromancer"

        # Build files
        assert (root / "pom.xml").is_file()

        # Java source
        assert (java_root / "cards" / "FireStrike.java").is_file()
        assert (java_root / "cards" / "FireDefend.java").is_file()
        assert (java_root / "cards" / "Inferno.java").is_file()
        assert (java_root / "powers" / "BurningPower.java").is_file()
        assert (java_root / "relics" / "EmberHeart.java").is_file()
        assert (java_root / "potions" / "FirePotion.java").is_file()
        assert (java_root / "characters" / "Pyromancer.java").is_file()
        assert (java_root / "characters" / "PyromancerEnums.java").is_file()
        assert (java_root / "PyromancerMod.java").is_file()

        # Resources
        res = root / "src" / "main" / "resources"
        assert (res / "ModTheSpire.json").is_file()
        assert (
            res / "pyromancerResources" / "localization" / "eng" / "cards.json"
        ).is_file()
        assert (res / "pyromancerResources" / "img" / "cards" / "FireStrike.png").is_file()
        assert (res / "pyromancerResources" / "img" / "powers" / "84" / "Burning.png").is_file()
        assert (res / "pyromancerResources" / "img" / "relics" / "EmberHeart.png").is_file()
        assert (res / "pyromancerResources" / "img" / "char" / "button.png").is_file()

    def test_card_java_has_correct_structure(self, tmp_path):
        """Verify generated Java has proper class structure."""
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        java_path = (
            tmp_path
            / "pyromancer"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "pyromancer"
            / "cards"
            / "FireStrike.java"
        )
        java = java_path.read_text()

        # Package declaration
        assert "package sts_gen.pyromancer.cards;" in java
        # Class
        assert "public class FireStrike extends AbstractCard" in java
        # Constructor
        assert "public FireStrike()" in java
        # use() method
        assert "public void use(AbstractPlayer p, AbstractMonster m)" in java
        # upgrade() method
        assert "public void upgrade()" in java
        # Base stats
        assert "this.baseDamage = DAMAGE" in java
        # Damage action
        assert "DamageAction" in java
        # Status application (Burning)
        assert "BurningPower" in java

    def test_power_java_has_correct_structure(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        java_path = (
            tmp_path
            / "pyromancer"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "pyromancer"
            / "powers"
            / "BurningPower.java"
        )
        java = java_path.read_text()

        assert "package sts_gen.pyromancer.powers;" in java
        assert "public class BurningPower extends AbstractPower" in java
        assert "POWER_ID" in java
        assert "PowerType.DEBUFF" in java

    def test_cannot_compile_without_jars(self, tmp_path):
        """Without JARs, build returns project dir (not JAR)."""
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "out")
        result = builder.build()
        # Should be the project directory, not a JAR
        assert result.is_dir()
        assert not str(result).endswith(".jar")

    def test_character_class_generated(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        char_path = (
            tmp_path
            / "pyromancer"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "pyromancer"
            / "characters"
            / "Pyromancer.java"
        )
        java = char_path.read_text()
        assert "public class Pyromancer extends CustomPlayer" in java
        assert "STARTING_HP" in java
        assert "getStartingDeck" in java
        assert "FireStrike" in java

    def test_enums_generated(self, tmp_path):
        cs = _make_content_set()
        builder = ModBuilder(cs, tmp_path / "pyromancer", skip_compile=True)
        builder.build()

        enum_path = (
            tmp_path
            / "pyromancer"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "pyromancer"
            / "characters"
            / "PyromancerEnums.java"
        )
        java = enum_path.read_text()
        assert "@SpireEnum" in java
        assert "PYROMANCER" in java
