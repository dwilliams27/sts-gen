"""StatusEffectDefinition → Java Power class template context transpiler."""

from __future__ import annotations

from sts_gen.ir.status_effects import StatusEffectDefinition, StatusTrigger

from .actions import ActionTranspiler, TranspileContext
from .naming import to_image_path, to_power_class_name, to_sts_id


# StatusTrigger → Java method name
_TRIGGER_METHOD_MAP: dict[StatusTrigger, str] = {
    StatusTrigger.ON_TURN_START: "atStartOfTurn",
    StatusTrigger.ON_TURN_END: "atEndOfTurn",
    StatusTrigger.ON_ATTACK: "onAttack",
    StatusTrigger.ON_ATTACKED: "wasHPLost",
    StatusTrigger.ON_CARD_PLAYED: "onAfterUseCard",
    StatusTrigger.ON_CARD_DRAWN: "onCardDraw",
    StatusTrigger.ON_CARD_EXHAUSTED: "onExhaust",
    StatusTrigger.ON_ATTACK_PLAYED: "onAfterUseCard",
    StatusTrigger.ON_BLOCK_GAINED: "onGainedBlock",
    StatusTrigger.ON_HP_LOSS: "wasHPLost",
    StatusTrigger.ON_DEATH: "onDeath",
}

# Trigger → Java method signature (params after method name)
_TRIGGER_SIGNATURE_MAP: dict[StatusTrigger, str] = {
    StatusTrigger.ON_TURN_START: "()",
    StatusTrigger.ON_TURN_END: "(boolean isPlayer)",
    StatusTrigger.ON_ATTACK: "(DamageInfo info, int damageAmount, AbstractCreature target)",
    StatusTrigger.ON_ATTACKED: "(DamageInfo info, int damageAmount)",
    StatusTrigger.ON_CARD_PLAYED: "(AbstractCard card, UseCardAction action)",
    StatusTrigger.ON_CARD_DRAWN: "(AbstractCard card)",
    StatusTrigger.ON_CARD_EXHAUSTED: "(AbstractCard card)",
    StatusTrigger.ON_ATTACK_PLAYED: "(AbstractCard card, UseCardAction action)",
    StatusTrigger.ON_BLOCK_GAINED: "(float blockAmount)",
    StatusTrigger.ON_HP_LOSS: "(DamageInfo info, int damageAmount)",
    StatusTrigger.ON_DEATH: "()",
}

# Triggers that need an isPlayer guard
_NEEDS_PLAYER_GUARD: set[StatusTrigger] = {StatusTrigger.ON_TURN_END}

# Triggers that need an attack-type card guard
_NEEDS_ATTACK_GUARD: set[StatusTrigger] = {StatusTrigger.ON_ATTACK_PLAYED}


class PowerTranspiler:
    """Transpiles StatusEffectDefinition → Jinja2 template context."""

    def __init__(self, mod_id: str, status_id_map: dict[str, str] | None = None):
        self.mod_id = mod_id
        self.action_transpiler = ActionTranspiler()
        self.status_id_map = status_id_map or {}

    def transpile(self, status: StatusEffectDefinition) -> dict:
        """Build template context dict for a single Power class."""
        class_name = to_power_class_name(status.id)
        power_id = to_sts_id(self.mod_id, status.id)
        img_path_84 = to_image_path(self.mod_id, "powers/84", status.id)
        img_path_32 = to_image_path(self.mod_id, "powers/32", status.id)

        # Build trigger method overrides
        triggers = []
        for trigger, actions in status.triggers.items():
            if trigger == StatusTrigger.PASSIVE:
                continue  # handled separately

            method_name = _TRIGGER_METHOD_MAP.get(trigger)
            if method_name is None:
                continue

            signature = _TRIGGER_SIGNATURE_MAP.get(trigger, "()")

            ctx = TranspileContext(
                source_var="this.owner",
                target_var="this.owner",
                is_power=True,
                indent=2,
                status_id_map=self.status_id_map,
                mod_id=self.mod_id,
            )

            body = self.action_transpiler.transpile(actions, ctx)

            # Wrap in guards if needed
            if trigger in _NEEDS_PLAYER_GUARD:
                body = f"        if (isPlayer) {{\n{body}\n        }}"
            elif trigger in _NEEDS_ATTACK_GUARD:
                body = f"        if (card.type == AbstractCard.CardType.ATTACK) {{\n{body}\n        }}"

            triggers.append({
                "method_name": method_name,
                "signature": signature,
                "body": body,
                "trigger": trigger.value,
            })

        # Passive effects (modify damage/block)
        passive_body = None
        if StatusTrigger.PASSIVE in status.triggers:
            passive_actions = status.triggers[StatusTrigger.PASSIVE]
            passive_body = self._build_passive(passive_actions)

        # Decay handling
        decay_method = None
        if status.decay_per_turn > 0:
            decay_method = {
                "amount": status.decay_per_turn,
            }
        elif status.decay_per_turn == -1:
            # Temporary — remove at end of turn
            decay_method = {
                "amount": -1,  # sentinel for "remove entirely"
            }

        return {
            "class_name": class_name,
            "power_id": power_id,
            "img_path_84": img_path_84,
            "img_path_32": img_path_32,
            "name": status.name,
            "is_debuff": status.is_debuff,
            "triggers": triggers,
            "passive_body": passive_body,
            "decay_method": decay_method,
            "description": status.description,
            "package_path": f"sts_gen.{self.mod_id.lower()}",
        }

    def _build_passive(self, actions: list) -> dict | None:
        """Build passive override methods (atDamageGive, modifyBlock, etc.)."""
        # Analyze what the passive affects
        from sts_gen.ir.actions import ActionType

        for action in actions:
            if action.action_type == ActionType.DEAL_DAMAGE:
                return {"type": "damage", "value_expr": "this.amount"}
            if action.action_type == ActionType.GAIN_BLOCK:
                return {"type": "block", "value_expr": "this.amount"}
        return None
