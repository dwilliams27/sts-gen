"""Tests for IR id → Java naming conventions."""

import pytest

from sts_gen.mod_builder.transpiler.naming import (
    character_class_name,
    mod_class_name,
    to_card_class_name,
    to_class_name,
    to_image_path,
    to_package_name,
    to_package_path,
    to_potion_class_name,
    to_power_class_name,
    to_relic_class_name,
    to_sts_id,
)


class TestToClassName:
    def test_snake_case(self):
        assert to_class_name("fire_slash") == "FireSlash"

    def test_already_pascal(self):
        assert to_class_name("FireSlash") == "Fireslash"

    def test_single_word(self):
        assert to_class_name("strike") == "Strike"

    def test_with_mod_prefix(self):
        assert to_class_name("my_mod:burning_rage") == "BurningRage"

    def test_spaces_and_hyphens(self):
        assert to_class_name("fire-ball blast") == "FireBallBlast"

    def test_multiple_underscores(self):
        assert to_class_name("deep__dark__slash") == "DeepDarkSlash"


class TestToStsId:
    def test_basic(self):
        assert to_sts_id("pyromancer", "fire_slash") == "pyromancer:FireSlash"

    def test_with_mod_prefix(self):
        assert to_sts_id("user:Pyromancer", "fire_slash") == "Pyromancer:FireSlash"


class TestToPowerClassName:
    def test_adds_suffix(self):
        assert to_power_class_name("Burning") == "BurningPower"

    def test_already_has_suffix(self):
        assert to_power_class_name("BurningPower") == "BurningPower"

    def test_snake_case(self):
        assert to_power_class_name("soul_fire") == "SoulFirePower"


class TestToCardClassName:
    def test_basic(self):
        assert to_card_class_name("fire_slash") == "FireSlash"


class TestToRelicClassName:
    def test_basic(self):
        assert to_relic_class_name("burning_lantern") == "BurningLantern"


class TestToPotionClassName:
    def test_basic(self):
        assert to_potion_class_name("liquid_flame") == "LiquidFlame"


class TestToImagePath:
    def test_card_image(self):
        result = to_image_path("pyromancer", "cards", "fire_slash")
        assert result == "pyromancerResources/img/cards/FireSlash.png"

    def test_power_image(self):
        result = to_image_path("pyromancer", "powers/84", "burning")
        assert result == "pyromancerResources/img/powers/84/Burning.png"

    def test_relic_image(self):
        result = to_image_path("pyromancer", "relics", "flame_orb")
        assert result == "pyromancerResources/img/relics/FlameOrb.png"


class TestToPackageName:
    def test_simple(self):
        assert to_package_name("pyromancer") == "pyromancer"

    def test_with_prefix(self):
        assert to_package_name("user:Pyromancer") == "pyromancer"

    def test_capital(self):
        assert to_package_name("Pyromancer") == "pyromancer"


class TestToPackagePath:
    def test_basic(self):
        assert to_package_path("pyromancer") == "sts_gen.pyromancer"


class TestModClassName:
    def test_basic(self):
        assert mod_class_name("pyromancer") == "PyromancerMod"

    def test_already_capitalized(self):
        assert mod_class_name("Pyromancer") == "PyromancerMod"

    def test_already_has_suffix(self):
        assert mod_class_name("PyromancerMod") == "PyromancerMod"


class TestCharacterClassName:
    def test_basic(self):
        assert character_class_name("pyromancer") == "Pyromancer"

    def test_already_capitalized(self):
        assert character_class_name("Pyromancer") == "Pyromancer"
