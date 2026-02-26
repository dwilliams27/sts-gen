"""Placeholder art generator using Pillow.

Generates simple colored PNGs for cards, powers, relics, and character
assets so the mod can load without missing texture errors.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from sts_gen.ir.cards import CardDefinition, CardType
from sts_gen.ir.content_set import ContentSet
from sts_gen.ir.potions import PotionDefinition
from sts_gen.ir.relics import RelicDefinition
from sts_gen.ir.status_effects import StatusEffectDefinition

from ..transpiler.naming import to_class_name, to_package_name

# Color schemes per card type
_CARD_COLORS: dict[CardType, tuple[int, int, int]] = {
    CardType.ATTACK: (180, 50, 50),    # Red
    CardType.SKILL: (50, 80, 180),     # Blue
    CardType.POWER: (50, 160, 50),     # Green
    CardType.STATUS: (120, 120, 120),  # Gray
    CardType.CURSE: (80, 20, 80),      # Purple
}

_POWER_COLOR = (200, 150, 50)    # Gold
_RELIC_COLOR = (160, 100, 40)    # Bronze
_POTION_COLOR = (50, 150, 150)   # Teal


def _get_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Get a font, falling back to default if no system font available."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _create_placeholder(
    width: int,
    height: int,
    color: tuple[int, int, int],
    label: str = "",
) -> Image.Image:
    """Create a simple placeholder image with optional text label."""
    img = Image.new("RGBA", (width, height), (*color, 255))
    if label:
        draw = ImageDraw.Draw(img)
        font = _get_font(max(12, min(width, height) // 6))
        # Center text
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2
        y = (height - th) // 2
        draw.text((x, y), label, fill=(255, 255, 255, 255), font=font)
    return img


class PlaceholderArtGenerator:
    """Generates all placeholder art for a mod."""

    def __init__(self, content_set: ContentSet):
        self.cs = content_set
        self.mod_id = content_set.mod_id

    def generate_all(self, output_dir: Path) -> list[Path]:
        """Generate all placeholder images under output_dir.

        Returns list of paths created.
        """
        created: list[Path] = []
        pkg = to_package_name(self.mod_id)
        base = output_dir / "src" / "main" / "resources" / f"{pkg}Resources" / "img"

        # Card images
        created.extend(self._generate_cards(base / "cards"))

        # Power icons
        created.extend(self._generate_powers(base / "powers"))

        # Relic icons
        created.extend(self._generate_relics(base / "relics"))

        # Character images
        created.extend(self._generate_character(base / "char"))

        # Card UI elements (backgrounds, orbs)
        created.extend(self._generate_card_ui(base / "cards"))

        return created

    def _generate_cards(self, cards_dir: Path) -> list[Path]:
        created: list[Path] = []
        cards_dir.mkdir(parents=True, exist_ok=True)

        for card in self.cs.cards:
            name = to_class_name(card.id)
            color = _CARD_COLORS.get(card.type, (100, 100, 100))

            # Standard card image (250x190)
            img = _create_placeholder(250, 190, color, card.name)
            path = cards_dir / f"{name}.png"
            img.save(path)
            created.append(path)

        return created

    def _generate_powers(self, powers_dir: Path) -> list[Path]:
        created: list[Path] = []

        for size in (84, 32):
            size_dir = powers_dir / str(size)
            size_dir.mkdir(parents=True, exist_ok=True)

            for status in self.cs.status_effects:
                name = to_class_name(status.id)
                label = status.name[:6] if size >= 64 else ""
                img = _create_placeholder(size, size, _POWER_COLOR, label)
                path = size_dir / f"{name}.png"
                img.save(path)
                created.append(path)

        return created

    def _generate_relics(self, relics_dir: Path) -> list[Path]:
        created: list[Path] = []
        relics_dir.mkdir(parents=True, exist_ok=True)
        outline_dir = relics_dir / "outline"
        outline_dir.mkdir(parents=True, exist_ok=True)

        for relic in self.cs.relics:
            name = to_class_name(relic.id)

            # Main relic image (128x128)
            img = _create_placeholder(128, 128, _RELIC_COLOR, relic.name[:8])
            path = relics_dir / f"{name}.png"
            img.save(path)
            created.append(path)

            # Outline (128x128, darker)
            darker = tuple(max(0, c - 60) for c in _RELIC_COLOR)
            outline = _create_placeholder(128, 128, darker, "")
            outline_path = outline_dir / f"{name}.png"
            outline.save(outline_path)
            created.append(outline_path)

        return created

    def _generate_character(self, char_dir: Path) -> list[Path]:
        created: list[Path] = []
        char_dir.mkdir(parents=True, exist_ok=True)

        # Character button (for select screen)
        btn = _create_placeholder(128, 128, (180, 60, 60), self.cs.mod_name[:8])
        btn_path = char_dir / "button.png"
        btn.save(btn_path)
        created.append(btn_path)

        # Portrait (1920x1200)
        portrait = _create_placeholder(
            1920, 1200, (60, 20, 20), self.cs.mod_name
        )
        portrait_path = char_dir / "portrait.png"
        portrait.save(portrait_path)
        created.append(portrait_path)

        # Shoulder images
        for name in ("shoulder.png", "shoulder2.png"):
            img = _create_placeholder(128, 128, (100, 40, 40), "")
            path = char_dir / name
            img.save(path)
            created.append(path)

        # Corpse
        corpse = _create_placeholder(128, 128, (60, 30, 30), "")
        corpse_path = char_dir / "corpse.png"
        corpse.save(corpse_path)
        created.append(corpse_path)

        return created

    def _generate_card_ui(self, cards_dir: Path) -> list[Path]:
        """Generate card background, orb, and banner images."""
        created: list[Path] = []
        cards_dir.mkdir(parents=True, exist_ok=True)

        bg_types = [
            ("bg_attack.png", (180, 50, 50), 512, 512),
            ("bg_skill.png", (50, 80, 180), 512, 512),
            ("bg_power.png", (50, 160, 50), 512, 512),
            ("bg_attack_s.png", (180, 50, 50), 256, 256),
            ("bg_skill_s.png", (50, 80, 180), 256, 256),
            ("bg_power_s.png", (50, 160, 50), 256, 256),
            ("card_orb.png", (200, 200, 200), 64, 64),
            ("card_orb_s.png", (200, 200, 200), 32, 32),
            ("energy_orb.png", (200, 50, 50), 128, 128),
            ("energy_orb_s.png", (200, 50, 50), 64, 64),
            ("energy_orb_portrait.png", (200, 50, 50), 164, 164),
        ]

        for name, color, w, h in bg_types:
            img = _create_placeholder(w, h, color, "")
            path = cards_dir / name
            img.save(path)
            created.append(path)

        return created
