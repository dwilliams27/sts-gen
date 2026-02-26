"""ModProject — assembles a complete STS mod project directory.

Takes a ContentSet and generates all Java source, localization JSON,
placeholder art, and build config in a structured Maven project layout.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from sts_gen.ir.content_set import ContentSet

from .art.placeholder import PlaceholderArtGenerator
from .localization.generator import LocalizationGenerator
from .transpiler.cards import CardTranspiler
from .transpiler.character import CharacterTranspiler
from .transpiler.naming import (
    character_class_name,
    to_package_name,
    to_power_class_name,
)
from .transpiler.potions import PotionTranspiler
from .transpiler.powers import PowerTranspiler
from .transpiler.relics import RelicTranspiler

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class ModProject:
    """Assembles a complete STS mod project from a ContentSet."""

    def __init__(self, content_set: ContentSet, output_dir: Path):
        self.cs = content_set
        self.output_dir = output_dir
        self.mod_id = content_set.mod_id

        # Build status_id_map for custom statuses
        self._status_id_map: dict[str, str] = {}
        for s in content_set.status_effects:
            cls = to_power_class_name(s.id)
            self._status_id_map[s.id] = cls
            self._status_id_map[s.name] = cls

        # Jinja2 environment
        self._jinja = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            keep_trailing_newline=True,
        )

        self._pkg = to_package_name(self.mod_id)
        self._char_name = character_class_name(self.mod_id)

    def assemble(self) -> Path:
        """Generate the complete project. Returns path to project root."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Java source root
        pkg_path = self._pkg.replace(".", "/")
        java_root = (
            self.output_dir / "src" / "main" / "java" / "sts_gen" / pkg_path
        )
        java_root.mkdir(parents=True, exist_ok=True)

        # Generate content
        self._generate_cards(java_root / "cards")
        self._generate_powers(java_root / "powers")
        self._generate_relics(java_root / "relics")
        self._generate_potions(java_root / "potions")
        self._generate_character(java_root / "characters")
        self._generate_mod_init(java_root)

        # Localization
        self._generate_localization()

        # Placeholder art
        art_gen = PlaceholderArtGenerator(self.cs)
        art_gen.generate_all(self.output_dir)

        return self.output_dir

    def _generate_cards(self, cards_dir: Path) -> None:
        cards_dir.mkdir(parents=True, exist_ok=True)
        transpiler = CardTranspiler(self.mod_id, self._status_id_map)
        template = self._jinja.get_template("Card.java.j2")

        for card in self.cs.cards:
            ctx = transpiler.transpile(card)
            ctx["character_class_name"] = self._char_name
            ctx["color_name"] = self._char_name.upper()
            java = template.render(**ctx)
            path = cards_dir / f"{ctx['class_name']}.java"
            path.write_text(java, encoding="utf-8")

    def _generate_powers(self, powers_dir: Path) -> None:
        powers_dir.mkdir(parents=True, exist_ok=True)
        transpiler = PowerTranspiler(self.mod_id, self._status_id_map)
        template = self._jinja.get_template("Power.java.j2")

        for status in self.cs.status_effects:
            ctx = transpiler.transpile(status)
            java = template.render(**ctx)
            path = powers_dir / f"{ctx['class_name']}.java"
            path.write_text(java, encoding="utf-8")

    def _generate_relics(self, relics_dir: Path) -> None:
        relics_dir.mkdir(parents=True, exist_ok=True)
        transpiler = RelicTranspiler(self.mod_id, self._status_id_map)
        template = self._jinja.get_template("Relic.java.j2")

        for relic in self.cs.relics:
            ctx = transpiler.transpile(relic)
            java = template.render(**ctx)
            path = relics_dir / f"{ctx['class_name']}.java"
            path.write_text(java, encoding="utf-8")

    def _generate_potions(self, potions_dir: Path) -> None:
        potions_dir.mkdir(parents=True, exist_ok=True)
        transpiler = PotionTranspiler(self.mod_id, self._status_id_map)
        template = self._jinja.get_template("Potion.java.j2")

        for potion in self.cs.potions:
            ctx = transpiler.transpile(potion)
            ctx["character_class_name"] = self._char_name
            java = template.render(**ctx)
            path = potions_dir / f"{ctx['class_name']}.java"
            path.write_text(java, encoding="utf-8")

    def _generate_character(self, char_dir: Path) -> None:
        char_dir.mkdir(parents=True, exist_ok=True)
        transpiler = CharacterTranspiler(self.cs)

        # Character class
        ctx = transpiler.transpile_character()
        template = self._jinja.get_template("Character.java.j2")
        java = template.render(**ctx)
        path = char_dir / f"{self._char_name}.java"
        path.write_text(java, encoding="utf-8")

        # Enums class
        enum_ctx = transpiler.transpile_enums()
        enum_template = self._jinja.get_template("Enums.java.j2")
        enum_java = enum_template.render(**enum_ctx)
        enum_path = char_dir / f"{self._char_name}Enums.java"
        enum_path.write_text(enum_java, encoding="utf-8")

    def _generate_mod_init(self, java_root: Path) -> None:
        transpiler = CharacterTranspiler(self.cs)
        ctx = transpiler.transpile_mod_init()
        template = self._jinja.get_template("ModInit.java.j2")
        java = template.render(**ctx)
        from .transpiler.naming import mod_class_name

        cls_name = mod_class_name(self.mod_id)
        path = java_root / f"{cls_name}.java"
        path.write_text(java, encoding="utf-8")

    def _generate_localization(self) -> None:
        gen = LocalizationGenerator(self.cs)
        files = gen.generate_all()

        pkg = to_package_name(self.mod_id)
        loc_dir = (
            self.output_dir
            / "src"
            / "main"
            / "resources"
            / f"{pkg}Resources"
            / "localization"
            / "eng"
        )
        loc_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            path = loc_dir / filename
            path.write_text(content, encoding="utf-8")
