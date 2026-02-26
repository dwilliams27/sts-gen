"""Tests for ModProject — full project assembly."""

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
from sts_gen.mod_builder.project import ModProject


def _make_minimal_content_set():
    """Minimal 3-card content set for testing."""
    return ContentSet(
        mod_id="testmod",
        mod_name="Test Mod",
        author="tester",
        version="1.0.0",
        cards=[
            CardDefinition(
                id="fire_strike",
                name="Fire Strike",
                type=CardType.ATTACK,
                rarity=CardRarity.BASIC,
                cost=1,
                target=CardTarget.ENEMY,
                description="Deal 6 damage.",
                actions=[
                    ActionNode(
                        action_type=ActionType.DEAL_DAMAGE,
                        value=6,
                        target="enemy",
                    ),
                ],
                upgrade=UpgradeDefinition(
                    actions=[
                        ActionNode(
                            action_type=ActionType.DEAL_DAMAGE,
                            value=9,
                            target="enemy",
                        ),
                    ],
                    description="Deal 9 damage.",
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
                id="ignite",
                name="Ignite",
                type=CardType.POWER,
                rarity=CardRarity.UNCOMMON,
                cost=2,
                target=CardTarget.SELF,
                description="Apply Burning to all enemies.",
                actions=[
                    ActionNode(
                        action_type=ActionType.APPLY_STATUS,
                        value=3,
                        target="self",
                        status_name="Burning",
                    ),
                ],
            ),
        ],
        relics=[
            RelicDefinition(
                id="flame_orb",
                name="Flame Orb",
                tier=RelicTier.STARTER,
                description="At the end of combat, heal 6 HP.",
                trigger="on_combat_end",
                actions=[
                    ActionNode(
                        action_type=ActionType.HEAL, value=6, target="self"
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
                    ),
                ],
            ),
        ],
        status_effects=[
            StatusEffectDefinition(
                id="Burning",
                name="Burning",
                description="Take damage at end of turn.",
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


class TestModProject:
    def test_assemble_creates_directory(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        result = project.assemble()
        assert result.is_dir()

    def test_java_source_files_created(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        java_root = tmp_path / "output" / "src" / "main" / "java" / "sts_gen" / "testmod"

        # Cards
        assert (java_root / "cards" / "FireStrike.java").is_file()
        assert (java_root / "cards" / "FireDefend.java").is_file()
        assert (java_root / "cards" / "Ignite.java").is_file()

        # Powers
        assert (java_root / "powers" / "BurningPower.java").is_file()

        # Relics
        assert (java_root / "relics" / "FlameOrb.java").is_file()

        # Potions
        assert (java_root / "potions" / "FirePotion.java").is_file()

        # Character
        assert (java_root / "characters" / "Testmod.java").is_file()
        assert (java_root / "characters" / "TestmodEnums.java").is_file()

        # Mod init
        assert (java_root / "TestmodMod.java").is_file()

    def test_localization_files_created(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        loc_dir = (
            tmp_path
            / "output"
            / "src"
            / "main"
            / "resources"
            / "testmodResources"
            / "localization"
            / "eng"
        )
        assert (loc_dir / "cards.json").is_file()
        assert (loc_dir / "powers.json").is_file()
        assert (loc_dir / "relics.json").is_file()
        assert (loc_dir / "potions.json").is_file()
        assert (loc_dir / "character.json").is_file()

    def test_placeholder_art_created(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        img_dir = (
            tmp_path
            / "output"
            / "src"
            / "main"
            / "resources"
            / "testmodResources"
            / "img"
        )

        # Card images
        assert (img_dir / "cards" / "FireStrike.png").is_file()
        assert (img_dir / "cards" / "FireDefend.png").is_file()

        # Card UI backgrounds
        assert (img_dir / "cards" / "bg_attack.png").is_file()
        assert (img_dir / "cards" / "energy_orb.png").is_file()

        # Power icons
        assert (img_dir / "powers" / "84" / "Burning.png").is_file()
        assert (img_dir / "powers" / "32" / "Burning.png").is_file()

        # Relic icons
        assert (img_dir / "relics" / "FlameOrb.png").is_file()
        assert (img_dir / "relics" / "outline" / "FlameOrb.png").is_file()

        # Character images
        assert (img_dir / "char" / "button.png").is_file()
        assert (img_dir / "char" / "portrait.png").is_file()

    def test_card_java_content(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        java_path = (
            tmp_path
            / "output"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "testmod"
            / "cards"
            / "FireStrike.java"
        )
        content = java_path.read_text()
        assert "public class FireStrike extends AbstractCard" in content
        assert "DamageAction" in content
        assert "this.baseDamage = DAMAGE" in content

    def test_power_java_content(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        java_path = (
            tmp_path
            / "output"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "testmod"
            / "powers"
            / "BurningPower.java"
        )
        content = java_path.read_text()
        assert "public class BurningPower extends AbstractPower" in content
        assert "POWER_ID" in content

    def test_mod_init_lists_all_cards(self, tmp_path):
        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        java_path = (
            tmp_path
            / "output"
            / "src"
            / "main"
            / "java"
            / "sts_gen"
            / "testmod"
            / "TestmodMod.java"
        )
        content = java_path.read_text()
        assert "FireStrike" in content
        assert "FireDefend" in content
        assert "Ignite" in content
        assert "FlameOrb" in content
        assert "FirePotion" in content

    def test_localization_content(self, tmp_path):
        import json

        cs = _make_minimal_content_set()
        project = ModProject(cs, tmp_path / "output")
        project.assemble()

        loc_dir = (
            tmp_path
            / "output"
            / "src"
            / "main"
            / "resources"
            / "testmodResources"
            / "localization"
            / "eng"
        )
        cards = json.loads((loc_dir / "cards.json").read_text())
        assert "testmod:FireStrike" in cards
        assert cards["testmod:FireStrike"]["NAME"] == "Fire Strike"
