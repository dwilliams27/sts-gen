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

        Replaces numeric values with !D! (damage), !B! (block), !M! (magic).
        """
        desc = card.description
        if upgraded and card.upgrade and card.upgrade.description:
            desc = card.upgrade.description

        # STS uses !D! for damage, !B! for block, !M! for magic number
        # The descriptions from the IR typically already have the numbers
        # We can leave them as-is since STS will override with computed values
        # if the card has baseDamage/baseBlock/baseMagicNumber set
        return desc
