"""Character class template context transpiler.

Generates context for the Character, Enums, and ModInit templates.
"""

from __future__ import annotations

from sts_gen.ir.cards import CardDefinition, CardRarity
from sts_gen.ir.content_set import ContentSet
from sts_gen.ir.relics import RelicTier

from .naming import (
    character_class_name,
    mod_class_name,
    to_card_class_name,
    to_package_name,
    to_power_class_name,
    to_potion_class_name,
    to_relic_class_name,
)


class CharacterTranspiler:
    """Transpiles ContentSet → character/enum/mod init template contexts."""

    def __init__(self, content_set: ContentSet):
        self.cs = content_set
        self.mod_id = content_set.mod_id

    def transpile_character(self) -> dict:
        """Build template context for Character.java.j2."""
        char_name = character_class_name(self.mod_id)
        pkg = to_package_name(self.mod_id)

        # Find starter deck (BASIC cards)
        starter_cards = [c for c in self.cs.cards if c.rarity == CardRarity.BASIC]
        starter_card_classes = []
        for card in starter_cards:
            cls = to_card_class_name(card.id)
            # Typically 5 strikes + 4 defends + 1 special
            starter_card_classes.append(cls)

        # Find starter relic
        starter_relics = [r for r in self.cs.relics if r.tier == RelicTier.STARTER]
        starter_relic_class = (
            to_relic_class_name(starter_relics[0].id)
            if starter_relics
            else to_relic_class_name(self.cs.relics[0].id)
            if self.cs.relics
            else "BurningBlood"
        )

        return {
            "class_name": char_name,
            "mod_id": self.mod_id,
            "package_name": pkg,
            "package_path": f"sts_gen.{pkg}",
            "starter_card_classes": starter_card_classes,
            "starter_relic_class": starter_relic_class,
            "starting_hp": 80,
            "starting_gold": 99,
            "starting_energy": 3,
            "card_draw": 5,
            "mod_name": self.cs.mod_name,
        }

    def transpile_enums(self) -> dict:
        """Build template context for Enums.java.j2."""
        char_name = character_class_name(self.mod_id)
        pkg = to_package_name(self.mod_id)
        color_name = char_name.upper()

        return {
            "class_name": char_name,
            "package_name": pkg,
            "package_path": f"sts_gen.{pkg}",
            "color_name": color_name,
        }

    def transpile_mod_init(self) -> dict:
        """Build template context for ModInit.java.j2."""
        char_name = character_class_name(self.mod_id)
        mod_cls = mod_class_name(self.mod_id)
        pkg = to_package_name(self.mod_id)
        color_name = char_name.upper()

        # Collect all content class names
        card_classes = [to_card_class_name(c.id) for c in self.cs.cards]
        relic_classes = [to_relic_class_name(r.id) for r in self.cs.relics]
        potion_classes = [to_potion_class_name(p.id) for p in self.cs.potions]
        power_classes = [to_power_class_name(s.id) for s in self.cs.status_effects]

        return {
            "mod_class_name": mod_cls,
            "character_class_name": char_name,
            "mod_id": self.mod_id,
            "mod_name": self.cs.mod_name,
            "author": self.cs.author,
            "version": self.cs.version,
            "package_name": pkg,
            "package_path": f"sts_gen.{pkg}",
            "color_name": color_name,
            "card_classes": card_classes,
            "relic_classes": relic_classes,
            "potion_classes": potion_classes,
            "power_classes": power_classes,
            "has_keywords": bool(self.cs.keywords),
        }
