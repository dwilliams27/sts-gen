"""RelicDefinition → Java Relic class template context transpiler."""

from __future__ import annotations

from sts_gen.ir.relics import RelicDefinition, RelicTier

from .actions import ActionTranspiler, TranspileContext
from .naming import to_image_path, to_power_class_name, to_relic_class_name, to_sts_id
from .vanilla_powers import is_vanilla_status


# Relic trigger → Java method name
_TRIGGER_METHOD_MAP: dict[str, str] = {
    "on_combat_start": "atBattleStart",
    "on_combat_end": "onVictory",
    "on_turn_start": "atTurnStart",
    "on_turn_end": "onPlayerEndTurn",
    "on_card_played": "onPlayCard",
    "on_attacked": "onAttacked",
    "on_hp_loss": "onLoseHp",
    "on_pickup": "onEquip",
}

# Trigger → Java method signature
_TRIGGER_SIGNATURE_MAP: dict[str, str] = {
    "on_combat_start": "()",
    "on_combat_end": "()",
    "on_turn_start": "()",
    "on_turn_end": "()",
    "on_card_played": "(AbstractCard c, AbstractMonster m)",
    "on_attacked": "(DamageInfo info, int damageAmount)",
    "on_hp_loss": "(int damageAmount)",
    "on_pickup": "()",
}

# Relic tier → STS RelicTier enum
_TIER_MAP: dict[RelicTier, str] = {
    RelicTier.STARTER: "STARTER",
    RelicTier.COMMON: "COMMON",
    RelicTier.UNCOMMON: "UNCOMMON",
    RelicTier.RARE: "RARE",
    RelicTier.BOSS: "BOSS",
    RelicTier.SHOP: "SHOP",
    RelicTier.EVENT: "SPECIAL",
}


class RelicTranspiler:
    """Transpiles RelicDefinition → Jinja2 template context."""

    def __init__(self, mod_id: str, status_id_map: dict[str, str] | None = None):
        self.mod_id = mod_id
        self.action_transpiler = ActionTranspiler()
        self.status_id_map = status_id_map or {}

    def transpile(self, relic: RelicDefinition) -> dict:
        """Build template context dict for a single Relic class."""
        class_name = to_relic_class_name(relic.id)
        sts_id = to_sts_id(self.mod_id, relic.id)
        img_path = to_image_path(self.mod_id, "relics", relic.id)
        outline_path = to_image_path(self.mod_id, "relics/outline", relic.id)

        method_name = _TRIGGER_METHOD_MAP.get(relic.trigger, "atBattleStart")
        signature = _TRIGGER_SIGNATURE_MAP.get(relic.trigger, "()")

        ctx = TranspileContext(
            source_var="AbstractDungeon.player",
            target_var="AbstractDungeon.player",
            is_relic=True,
            indent=2,
            status_id_map=self.status_id_map,
            mod_id=self.mod_id,
        )

        action_body = self.action_transpiler.transpile(relic.actions, ctx)

        # Counter relic handling
        counter_config = None
        if relic.counter is not None:
            counter_config = {
                "threshold": relic.counter,
                "per_turn": relic.counter_per_turn,
            }

        tier = _TIER_MAP.get(relic.tier, "COMMON")

        # Collect custom power imports
        from .cards import _collect_custom_power_refs

        custom_refs = _collect_custom_power_refs(relic.actions)
        pkg = f"sts_gen.{self.mod_id.lower()}"
        extra_imports = [
            f"{pkg}.powers.{to_power_class_name(ref)}" for ref in sorted(custom_refs)
        ]

        return {
            "class_name": class_name,
            "sts_id": sts_id,
            "img_path": img_path,
            "outline_path": outline_path,
            "tier": tier,
            "trigger_method": method_name,
            "trigger_signature": signature,
            "action_body": action_body,
            "counter_config": counter_config,
            "description": relic.description,
            "name": relic.name,
            "package_path": pkg,
            "extra_imports": extra_imports,
        }
