"""Localization JSON generator for STS mods.

Generates the JSON localization files that STS uses for card names,
descriptions, power tooltips, relic descriptions, etc.
"""

from __future__ import annotations

import json
from typing import Any

from sts_gen.ir.cards import CardDefinition
from sts_gen.ir.content_set import ContentSet
from sts_gen.ir.potions import PotionDefinition
from sts_gen.ir.relics import RelicDefinition
from sts_gen.ir.status_effects import StatusEffectDefinition

from ..transpiler.cards import _extract_stats
from ..transpiler.naming import to_sts_id


class LocalizationGenerator:
    """Generates STS localization JSON from a ContentSet."""

    def __init__(self, content_set: ContentSet):
        self.cs = content_set
        self.mod_id = content_set.mod_id

    def generate_all(self) -> dict[str, str]:
        """Generate all localization files.

        Returns dict mapping filename → JSON string.
        """
        return {
            "cards.json": self._generate_cards(),
            "powers.json": self._generate_powers(),
            "relics.json": self._generate_relics(),
            "potions.json": self._generate_potions(),
            "character.json": self._generate_character(),
        }

    def _generate_cards(self) -> str:
        data: dict[str, Any] = {}
        for card in self.cs.cards:
            sts_id = to_sts_id(self.mod_id, card.id)
            entry: dict[str, str] = {
                "NAME": card.name,
                "DESCRIPTION": self._format_card_description(card),
            }
            if card.upgrade and card.upgrade.description:
                entry["UPGRADE_DESCRIPTION"] = self._format_card_description(
                    card, upgraded=True
                )
            data[sts_id] = entry
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _generate_powers(self) -> str:
        data: dict[str, Any] = {}
        for status in self.cs.status_effects:
            sts_id = to_sts_id(self.mod_id, status.id)
            data[sts_id] = {
                "NAME": status.name,
                "DESCRIPTIONS": [status.description],
            }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _generate_relics(self) -> str:
        data: dict[str, Any] = {}
        for relic in self.cs.relics:
            sts_id = to_sts_id(self.mod_id, relic.id)
            data[sts_id] = {
                "NAME": relic.name,
                "FLAVOR": "",
                "DESCRIPTIONS": [relic.description],
            }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _generate_potions(self) -> str:
        data: dict[str, Any] = {}
        for potion in self.cs.potions:
            sts_id = to_sts_id(self.mod_id, potion.id)
            data[sts_id] = {
                "NAME": potion.name,
                "DESCRIPTIONS": [potion.description],
            }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _generate_character(self) -> str:
        from ..transpiler.naming import to_package_path, character_class_name

        char_id = f"{to_package_path(self.mod_id)}.{character_class_name(self.mod_id)}"
        data = {
            char_id: {
                "NAMES": [self.cs.mod_name],
                "TEXT": [
                    f"The {self.cs.mod_name}. NL A custom character.",
                    "The heart before you beats with power...",
                ],
            }
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _format_card_description(
        self, card: CardDefinition, upgraded: bool = False
    ) -> str:
        """Format card description with STS dynamic placeholders.

        Cross-references the card's extracted stats (baseDamage, baseBlock,
        baseMagicNumber) against numeric values in the description text and
        replaces the first occurrence of each with !D!, !B!, !M! respectively.
        """
        desc = card.description
        if upgraded and card.upgrade and card.upgrade.description:
            desc = card.upgrade.description

        # Determine which action tree to extract stats from
        actions = card.actions
        if upgraded and card.upgrade and card.upgrade.actions:
            actions = card.upgrade.actions

        stats = _extract_stats(actions, card.target)

        # Replace first occurrence of each stat value with STS placeholder.
        # Order matters: replace damage first, then block, then magic number,
        # to avoid collisions when multiple stats share the same value.
        if stats.base_damage is not None:
            desc = desc.replace(str(stats.base_damage), "!D!", 1)
        if stats.base_block is not None:
            desc = desc.replace(str(stats.base_block), "!B!", 1)
        if stats.base_magic_number is not None:
            desc = desc.replace(str(stats.base_magic_number), "!M!", 1)

        # STS newlines
        desc = desc.replace("\n", " NL ")
        return desc
