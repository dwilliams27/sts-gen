"""Tests for localization JSON generator."""

import json

import pytest

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
from sts_gen.mod_builder.localization.generator import LocalizationGenerator


def _make_content_set():
    return ContentSet(
        mod_id="testmod",
        mod_name="Test Mod",
        cards=[
            CardDefinition(
                id="fire_strike",
                name="Fire Strike",
                type=CardType.ATTACK,
                rarity=CardRarity.COMMON,
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
                triggers={},
            ),
        ],
    )


class TestLocalizationGenerator:
    def test_cards_json(self):
        gen = LocalizationGenerator(_make_content_set())
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])

        assert "testmod:FireStrike" in cards
        entry = cards["testmod:FireStrike"]
        assert entry["NAME"] == "Fire Strike"
        assert entry["DESCRIPTION"] == "Deal !D! damage."
        assert entry["UPGRADE_DESCRIPTION"] == "Deal !D! damage."

    def test_powers_json(self):
        gen = LocalizationGenerator(_make_content_set())
        files = gen.generate_all()
        powers = json.loads(files["powers.json"])

        assert "testmod:Burning" in powers
        assert powers["testmod:Burning"]["NAME"] == "Burning"

    def test_relics_json(self):
        gen = LocalizationGenerator(_make_content_set())
        files = gen.generate_all()
        relics = json.loads(files["relics.json"])

        assert "testmod:FlameOrb" in relics
        assert relics["testmod:FlameOrb"]["NAME"] == "Flame Orb"

    def test_potions_json(self):
        gen = LocalizationGenerator(_make_content_set())
        files = gen.generate_all()
        potions = json.loads(files["potions.json"])

        assert "testmod:FirePotion" in potions
        assert potions["testmod:FirePotion"]["NAME"] == "Fire Potion"

    def test_character_json(self):
        gen = LocalizationGenerator(_make_content_set())
        files = gen.generate_all()
        char = json.loads(files["character.json"])
        # Should have an entry keyed by character ID
        assert len(char) == 1
        key = list(char.keys())[0]
        assert "Test Mod" in char[key]["NAMES"]

    def test_all_files_generated(self):
        gen = LocalizationGenerator(_make_content_set())
        files = gen.generate_all()
        assert set(files.keys()) == {
            "cards.json",
            "powers.json",
            "relics.json",
            "potions.json",
            "character.json",
        }


class TestDynamicPlaceholders:
    def _make_cs(self, cards):
        return ContentSet(mod_id="t", mod_name="T", cards=cards)

    def test_damage_placeholder(self):
        card = CardDefinition(
            id="slash", name="Slash", type=CardType.ATTACK,
            rarity=CardRarity.COMMON, cost=1, target=CardTarget.ENEMY,
            description="Deal 6 damage.",
            actions=[ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy")],
        )
        gen = LocalizationGenerator(self._make_cs([card]))
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])
        assert cards["t:Slash"]["DESCRIPTION"] == "Deal !D! damage."

    def test_block_placeholder(self):
        card = CardDefinition(
            id="guard", name="Guard", type=CardType.SKILL,
            rarity=CardRarity.COMMON, cost=1, target=CardTarget.SELF,
            description="Gain 5 Block.",
            actions=[ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self")],
        )
        gen = LocalizationGenerator(self._make_cs([card]))
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])
        assert cards["t:Guard"]["DESCRIPTION"] == "Gain !B! Block."

    def test_damage_and_magic_number(self):
        card = CardDefinition(
            id="bash", name="Bash", type=CardType.ATTACK,
            rarity=CardRarity.BASIC, cost=2, target=CardTarget.ENEMY,
            description="Deal 8 damage. Apply 2 Vulnerable.",
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=8, target="enemy"),
                ActionNode(action_type=ActionType.APPLY_STATUS, value=2, target="enemy", status_name="Vulnerable"),
            ],
        )
        gen = LocalizationGenerator(self._make_cs([card]))
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])
        assert cards["t:Bash"]["DESCRIPTION"] == "Deal !D! damage. Apply !M! Vulnerable."

    def test_upgraded_description_uses_upgraded_stats(self):
        card = CardDefinition(
            id="strike", name="Strike", type=CardType.ATTACK,
            rarity=CardRarity.BASIC, cost=1, target=CardTarget.ENEMY,
            description="Deal 6 damage.",
            actions=[ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy")],
            upgrade=UpgradeDefinition(
                actions=[ActionNode(action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy")],
                description="Deal 9 damage.",
            ),
        )
        gen = LocalizationGenerator(self._make_cs([card]))
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])
        assert cards["t:Strike"]["DESCRIPTION"] == "Deal !D! damage."
        assert cards["t:Strike"]["UPGRADE_DESCRIPTION"] == "Deal !D! damage."

    def test_description_without_stats_unchanged(self):
        card = CardDefinition(
            id="escape", name="Escape", type=CardType.SKILL,
            rarity=CardRarity.COMMON, cost=0, target=CardTarget.SELF,
            description="End your turn. Draw a card next turn.",
            actions=[ActionNode(action_type=ActionType.DRAW_CARDS, value=1)],
        )
        gen = LocalizationGenerator(self._make_cs([card]))
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])
        # draw_cards doesn't map to !D!/!B!/!M!
        assert cards["t:Escape"]["DESCRIPTION"] == "End your turn. Draw a card next turn."

    def test_newline_replaced_with_nl(self):
        card = CardDefinition(
            id="combo", name="Combo", type=CardType.ATTACK,
            rarity=CardRarity.COMMON, cost=1, target=CardTarget.ENEMY,
            description="Deal 4 damage.\nDraw 1 card.",
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=4, target="enemy"),
                ActionNode(action_type=ActionType.DRAW_CARDS, value=1),
            ],
        )
        gen = LocalizationGenerator(self._make_cs([card]))
        files = gen.generate_all()
        cards = json.loads(files["cards.json"])
        assert cards["t:Combo"]["DESCRIPTION"] == "Deal !D! damage. NL Draw 1 card."
