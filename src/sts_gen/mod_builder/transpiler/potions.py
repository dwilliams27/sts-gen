"""PotionDefinition → Java Potion class template context transpiler."""

from __future__ import annotations

from sts_gen.ir.cards import CardTarget
from sts_gen.ir.potions import PotionDefinition, PotionRarity

from .actions import ActionTranspiler, TranspileContext
from .naming import to_image_path, to_potion_class_name, to_power_class_name, to_sts_id
from .vanilla_powers import is_vanilla_status

_RARITY_MAP: dict[PotionRarity, str] = {
    PotionRarity.COMMON: "COMMON",
    PotionRarity.UNCOMMON: "UNCOMMON",
    PotionRarity.RARE: "RARE",
}

_SIZE_MAP: dict[str, str] = {
    "ENEMY": "BOLT",
    "ALL_ENEMIES": "BOLT",
    "SELF": "BOTTLE",
    "NONE": "BOTTLE",
}


class PotionTranspiler:
    """Transpiles PotionDefinition → Jinja2 template context."""

    def __init__(self, mod_id: str, status_id_map: dict[str, str] | None = None):
        self.mod_id = mod_id
        self.action_transpiler = ActionTranspiler()
        self.status_id_map = status_id_map or {}

    def transpile(self, potion: PotionDefinition) -> dict:
        """Build template context dict for a single Potion class."""
        class_name = to_potion_class_name(potion.id)
        sts_id = to_sts_id(self.mod_id, potion.id)
        img_path = to_image_path(self.mod_id, "potions", potion.id)

        ctx = TranspileContext(
            source_var="AbstractDungeon.player",
            target_var="AbstractDungeon.player",
            indent=2,
            status_id_map=self.status_id_map,
            mod_id=self.mod_id,
        )

        # For enemy-targeted potions, target is the chosen enemy
        is_targeted = potion.target in (CardTarget.ENEMY,)
        if is_targeted:
            ctx = TranspileContext(
                source_var="AbstractDungeon.player",
                target_var="targetMonster",
                indent=2,
                status_id_map=self.status_id_map,
                mod_id=self.mod_id,
            )

        action_body = self.action_transpiler.transpile(potion.actions, ctx)
        rarity = _RARITY_MAP.get(potion.rarity, "COMMON")
        size = _SIZE_MAP.get(potion.target.value, "BOTTLE")

        # Collect custom power imports
        from .cards import _collect_custom_power_refs

        custom_refs = _collect_custom_power_refs(potion.actions)
        pkg = f"sts_gen.{self.mod_id.lower()}"
        extra_imports = [
            f"{pkg}.powers.{to_power_class_name(ref)}" for ref in sorted(custom_refs)
        ]

        return {
            "class_name": class_name,
            "sts_id": sts_id,
            "img_path": img_path,
            "rarity": rarity,
            "size": size,
            "is_targeted": is_targeted,
            "action_body": action_body,
            "description": potion.description,
            "name": potion.name,
            "package_path": pkg,
            "extra_imports": extra_imports,
        }
