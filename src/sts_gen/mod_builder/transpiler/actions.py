"""ActionNode tree → Java statement transpiler.

Converts IR ActionNode trees into Java source code strings that use STS's
action queue (``addToBot(new XAction(...))``).  The dispatch table mirrors
the sim interpreter's structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sts_gen.ir.actions import ActionNode, ActionType

from .naming import to_class_name, to_power_class_name
from .vanilla_powers import (
    VANILLA_POWER_MAP,
    get_vanilla_power_class,
    get_vanilla_power_id,
    is_vanilla_status,
)

if TYPE_CHECKING:
    pass


@dataclass
class TranspileContext:
    """Holds context that varies between cards, powers, and relics."""

    source_var: str = "p"
    """Java variable for the action source — ``"p"`` in cards,
    ``"this.owner"`` in powers/relics."""

    target_var: str = "m"
    """Java variable for the single-target — ``"m"`` in cards,
    computed in powers."""

    is_power: bool = False
    """True when transpiling power trigger actions."""

    is_relic: bool = False
    """True when transpiling relic trigger actions."""

    indent: int = 2
    """Current indentation level (number of 4-space indents)."""

    status_id_map: dict[str, str] = field(default_factory=dict)
    """Maps IR status id/name → Java Power class name (simple, not FQ).
    Populated from the content set's custom statuses."""

    mod_id: str = ""
    """Mod identifier for generating STS IDs."""

    def indent_str(self) -> str:
        """Return the current indentation whitespace."""
        return "    " * self.indent

    def indented(self, extra: int = 1) -> "TranspileContext":
        """Return a copy with increased indentation."""
        return TranspileContext(
            source_var=self.source_var,
            target_var=self.target_var,
            is_power=self.is_power,
            is_relic=self.is_relic,
            indent=self.indent + extra,
            status_id_map=self.status_id_map,
            mod_id=self.mod_id,
        )


class ActionTranspiler:
    """Transpiles ActionNode trees into Java statements.

    Uses a dispatch table mapping ActionType → handler, mirroring the
    sim interpreter pattern.
    """

    def __init__(self) -> None:
        self._dispatch: dict[ActionType, _Handler] = {
            ActionType.DEAL_DAMAGE: self._handle_deal_damage,
            ActionType.GAIN_BLOCK: self._handle_gain_block,
            ActionType.APPLY_STATUS: self._handle_apply_status,
            ActionType.REMOVE_STATUS: self._handle_remove_status,
            ActionType.DRAW_CARDS: self._handle_draw_cards,
            ActionType.DISCARD_CARDS: self._handle_discard_cards,
            ActionType.EXHAUST_CARDS: self._handle_exhaust_cards,
            ActionType.GAIN_ENERGY: self._handle_gain_energy,
            ActionType.LOSE_ENERGY: self._handle_lose_energy,
            ActionType.HEAL: self._handle_heal,
            ActionType.LOSE_HP: self._handle_lose_hp,
            ActionType.ADD_CARD_TO_PILE: self._handle_add_card_to_pile,
            ActionType.SHUFFLE_INTO_DRAW: self._handle_shuffle_into_draw,
            ActionType.GAIN_GOLD: self._handle_gain_gold,
            ActionType.GAIN_STRENGTH: self._handle_gain_strength,
            ActionType.GAIN_DEXTERITY: self._handle_gain_dexterity,
            ActionType.CONDITIONAL: self._handle_conditional,
            ActionType.FOR_EACH: self._handle_for_each,
            ActionType.REPEAT: self._handle_repeat,
            ActionType.TRIGGER_CUSTOM: self._handle_trigger_custom,
            ActionType.DOUBLE_BLOCK: self._handle_double_block,
            ActionType.MULTIPLY_STATUS: self._handle_multiply_status,
            ActionType.PLAY_TOP_CARD: self._handle_play_top_card,
        }

    def transpile(self, nodes: list[ActionNode], ctx: TranspileContext) -> str:
        """Transpile a list of action nodes into Java statements."""
        lines: list[str] = []
        for node in nodes:
            lines.append(self._transpile_node(node, ctx))
        return "\n".join(lines)

    def _transpile_node(self, node: ActionNode, ctx: TranspileContext) -> str:
        """Dispatch a single node to its handler."""
        handler = self._dispatch.get(node.action_type)
        if handler is None:
            return f"{ctx.indent_str()}// UNSUPPORTED: {node.action_type.value}"
        return handler(node, ctx)

    # -- Target resolution ---------------------------------------------------

    def _resolve_target(self, node: ActionNode, ctx: TranspileContext) -> str:
        """Resolve the target variable for an action node."""
        target = node.target or "default"
        if target == "self":
            return ctx.source_var
        if target == "enemy" or target == "default":
            return ctx.target_var
        if target == "all_enemies":
            return "null"  # handled specially in FOR_EACH
        if target == "random_enemy":
            return "AbstractDungeon.getMonsters().getRandomMonster(null, true)"
        return ctx.target_var

    def _is_all_enemies(self, node: ActionNode) -> bool:
        """Check if this action targets all enemies."""
        return node.target == "all_enemies"

    # -- Power class resolution -----------------------------------------------

    def _power_class(self, status_name: str, ctx: TranspileContext) -> str:
        """Get the Java Power class name for a status.

        Returns fully-qualified name for vanilla powers,
        simple class name for custom powers.
        """
        vanilla = get_vanilla_power_class(status_name)
        if vanilla:
            return vanilla
        # Custom power — use our generated class
        return to_power_class_name(status_name)

    def _power_id(self, status_name: str, ctx: TranspileContext) -> str:
        """Get the STS Power ID string for hasPower() checks."""
        vanilla_id = get_vanilla_power_id(status_name)
        if vanilla_id:
            return vanilla_id
        # Custom power — use the class's POWER_ID constant
        return f"{to_power_class_name(status_name)}.POWER_ID"

    def _power_id_literal(self, status_name: str, ctx: TranspileContext) -> str:
        """Get the STS Power ID as a Java string expression for hasPower()."""
        vanilla_id = get_vanilla_power_id(status_name)
        if vanilla_id:
            return f'"{vanilla_id}"'
        return f"{to_power_class_name(status_name)}.POWER_ID"

    # -- Value resolution -----------------------------------------------------

    def _value_expr(self, node: ActionNode, ctx: TranspileContext) -> str:
        """Get the Java expression for an action's numeric value."""
        if ctx.is_power and node.condition and "per_stack" in node.condition:
            return "this.amount"
        if node.value is not None:
            return str(node.value)
        return "0"

    # -- Handlers: Damage & Block --------------------------------------------

    def _handle_deal_damage(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        condition = node.condition or ""

        # Special: use_block_as_damage (Body Slam)
        if condition == "use_block_as_damage":
            return f"{ind}addToBot(new DamageAction({ctx.target_var}, new DamageInfo({ctx.source_var}, {ctx.source_var}.currentBlock, DamageInfo.DamageType.NORMAL), AbstractGameAction.AttackEffect.BLUNT_HEAVY));"

        # Special: times_from_x_cost (Whirlwind)
        if condition == "times_from_x_cost":
            times = "this.energyOnUse"
            inner_ctx = ctx.indented()
            inner_ind = inner_ctx.indent_str()
            return (
                f"{ind}for (int i = 0; i < {times}; i++) {{\n"
                f"{inner_ind}addToBot(new DamageAction({ctx.target_var}, new DamageInfo({ctx.source_var}, this.damage, this.damageTypeForTurn), AbstractGameAction.AttackEffect.SLASH_HORIZONTAL));\n"
                f"{ind}}}"
            )

        # Determine damage type
        if condition == "no_strength" or (
            ctx.is_power
            and node.condition
            and "per_stack_no_strength" in node.condition
        ):
            damage_type = "DamageInfo.DamageType.THORNS"
        else:
            damage_type = "this.damageTypeForTurn" if not ctx.is_power else "DamageInfo.DamageType.NORMAL"

        # Multi-hit via times
        if node.times and node.times > 1:
            inner_ctx = ctx.indented()
            inner_ind = inner_ctx.indent_str()
            return (
                f"{ind}for (int i = 0; i < {node.times}; i++) {{\n"
                f"{inner_ind}addToBot(new DamageAction({ctx.target_var}, new DamageInfo({ctx.source_var}, this.damage, {damage_type}), AbstractGameAction.AttackEffect.SLASH_HORIZONTAL));\n"
                f"{ind}}}"
            )

        # All enemies
        if self._is_all_enemies(node):
            if ctx.is_power:
                value = self._value_expr(node, ctx)
                return (
                    f"{ind}for (AbstractMonster mo : AbstractDungeon.getCurrRoom().monsters.monsters) {{\n"
                    f"{ind}    if (!mo.isDeadOrEscaped()) {{\n"
                    f"{ind}        addToBot(new DamageAction(mo, new DamageInfo(this.owner, {value}, {damage_type}), AbstractGameAction.AttackEffect.FIRE));\n"
                    f"{ind}    }}\n"
                    f"{ind}}}"
                )
            return f"{ind}addToBot(new DamageAllEnemiesAction({ctx.source_var}, this.multiDamage, {damage_type}, AbstractGameAction.AttackEffect.FIRE));"

        # Standard single-target damage
        if ctx.is_power:
            value = self._value_expr(node, ctx)
            return f"{ind}addToBot(new DamageAction({ctx.target_var}, new DamageInfo(this.owner, {value}, {damage_type}), AbstractGameAction.AttackEffect.FIRE));"

        return f"{ind}addToBot(new DamageAction({ctx.target_var}, new DamageInfo({ctx.source_var}, this.damage, {damage_type}), AbstractGameAction.AttackEffect.SLASH_DIAGONAL));"

    def _handle_gain_block(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        src = ctx.source_var

        if ctx.is_power and node.condition and "per_stack" in node.condition:
            return f"{ind}addToBot(new GainBlockAction({src}, {src}, this.amount));"

        if not ctx.is_power:
            return f"{ind}addToBot(new GainBlockAction({src}, {src}, this.block));"

        value = self._value_expr(node, ctx)
        return f"{ind}addToBot(new GainBlockAction({src}, {src}, {value}));"

    def _handle_double_block(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        src = ctx.source_var
        return f"{ind}addToBot(new GainBlockAction({src}, {src}, {src}.currentBlock));"

    # -- Handlers: Status Effects --------------------------------------------

    def _handle_apply_status(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        status = node.status_name or "Unknown"
        value = self._value_expr(node, ctx)
        target = self._resolve_target(node, ctx)
        src = ctx.source_var

        power_class = self._power_class(status, ctx)

        # Determine if we need "new FQClass(target, N)" or "new SimpleClass(target, N)"
        if is_vanilla_status(status):
            constructor = f"new {power_class}({target}, {value})"
        else:
            constructor = f"new {power_class}({target}, {src}, {value})"

        return f"{ind}addToBot(new ApplyPowerAction({target}, {src}, {constructor}, {value}));"

    def _handle_remove_status(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        status = node.status_name or "Unknown"
        target = self._resolve_target(node, ctx)
        power_id = self._power_id_literal(status, ctx)
        return f"{ind}addToBot(new RemoveSpecificPowerAction({target}, {target}, {power_id}));"

    def _handle_multiply_status(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        status = node.status_name or "Unknown"
        target = self._resolve_target(node, ctx)
        power_id = self._power_id_literal(status, ctx)
        multiplier = node.value if node.value is not None else 2
        return (
            f"{ind}{{\n"
            f"{ind}    AbstractPower pow = {target}.getPower({power_id});\n"
            f"{ind}    if (pow != null) {{\n"
            f"{ind}        pow.amount *= {multiplier};\n"
            f"{ind}        pow.updateDescription();\n"
            f"{ind}    }}\n"
            f"{ind}}}"
        )

    # -- Handlers: Card Manipulation -----------------------------------------

    def _handle_draw_cards(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        return f"{ind}addToBot(new DrawCardAction({ctx.source_var}, {value}));"

    def _handle_discard_cards(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        src = ctx.source_var
        return f"{ind}addToBot(new DiscardAction({src}, {src}, {value}, false));"

    def _handle_exhaust_cards(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        condition = node.condition or ""

        if node.value == -1 and condition == "non_attack":
            # Exhaust all non-attack cards (Sever Soul)
            return (
                f"{ind}for (AbstractCard c : new ArrayList<>(p.hand.group)) {{\n"
                f"{ind}    if (c.type != AbstractCard.CardType.ATTACK) {{\n"
                f"{ind}        addToBot(new ExhaustSpecificCardAction(c, p.hand));\n"
                f"{ind}    }}\n"
                f"{ind}}}"
            )
        if node.value == -1:
            # Exhaust entire hand
            return (
                f"{ind}for (AbstractCard c : new ArrayList<>(p.hand.group)) {{\n"
                f"{ind}    addToBot(new ExhaustSpecificCardAction(c, p.hand));\n"
                f"{ind}}}"
            )

        value = self._value_expr(node, ctx)
        return f"{ind}addToBot(new ExhaustAction({value}, false));"

    def _handle_add_card_to_pile(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        pile = node.pile or "hand"
        card_id = node.card_id or "Strike"
        card_class = to_class_name(card_id)

        action_map = {
            "hand": "MakeTempCardInHandAction",
            "discard": "MakeTempCardInDiscardAction",
            "draw": "MakeTempCardInDrawPileAction",
        }
        action_class = action_map.get(pile, "MakeTempCardInHandAction")
        return f"{ind}addToBot(new {action_class}(new {card_class}()));"

    def _handle_shuffle_into_draw(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        return f"{ind}addToBot(new ShuffleAction({ctx.source_var}.drawPile));"

    def _handle_play_top_card(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        return (
            f"{ind}if (!{ctx.source_var}.drawPile.isEmpty()) {{\n"
            f"{ind}    AbstractCard c = {ctx.source_var}.drawPile.getTopCard();\n"
            f"{ind}    addToBot(new NewQueueCardAction(c, true, false, true));\n"
            f"{ind}}}"
        )

    # -- Handlers: Resources -------------------------------------------------

    def _handle_gain_energy(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        return f"{ind}addToBot(new GainEnergyAction({value}));"

    def _handle_lose_energy(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        return f"{ind}AbstractDungeon.player.energy.use({value});"

    def _handle_heal(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        src = ctx.source_var
        value = self._value_expr(node, ctx)
        target = self._resolve_target(node, ctx)

        if node.condition == "raise_max_hp":
            return f"{ind}{target}.increaseMaxHp({value}, true);"

        return f"{ind}addToBot(new HealAction({target}, {src}, {value}));"

    def _handle_lose_hp(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        src = ctx.source_var
        value = self._value_expr(node, ctx)
        target = self._resolve_target(node, ctx)
        return f"{ind}addToBot(new LoseHPAction({target}, {src}, {value}, AbstractGameAction.AttackEffect.NONE));"

    def _handle_gain_gold(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        return f"{ind}addToBot(new GainGoldAction({value}));"

    # -- Handlers: Strength / Dexterity shortcuts ----------------------------

    def _handle_gain_strength(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        target = self._resolve_target(node, ctx)
        src = ctx.source_var
        return f"{ind}addToBot(new ApplyPowerAction({target}, {src}, new StrengthPower({target}, {value}), {value}));"

    def _handle_gain_dexterity(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        value = self._value_expr(node, ctx)
        target = self._resolve_target(node, ctx)
        src = ctx.source_var
        return f"{ind}addToBot(new ApplyPowerAction({target}, {src}, new DexterityPower({target}, {value}), {value}));"

    # -- Handlers: Control Flow ----------------------------------------------

    def _handle_conditional(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        condition = node.condition or "true"
        java_cond = self._condition_to_java(condition, ctx)
        children = node.children or []

        inner_ctx = ctx.indented()
        body = self.transpile(children, inner_ctx)

        return f"{ind}if ({java_cond}) {{\n{body}\n{ind}}}"

    def _handle_for_each(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        condition = node.condition or "enemy"
        children = node.children or []
        inner_ctx = ctx.indented()

        if condition == "enemy":
            inner_ctx = TranspileContext(
                source_var=ctx.source_var,
                target_var="mo",
                is_power=ctx.is_power,
                is_relic=ctx.is_relic,
                indent=ctx.indent + 2,
                status_id_map=ctx.status_id_map,
                mod_id=ctx.mod_id,
            )
            body = self.transpile(children, inner_ctx)
            return (
                f"{ind}for (AbstractMonster mo : AbstractDungeon.getCurrRoom().monsters.monsters) {{\n"
                f"{ind}    if (!mo.isDeadOrEscaped()) {{\n"
                f"{body}\n"
                f"{ind}    }}\n"
                f"{ind}}}"
            )

        # Default: just iterate children with extra indent
        body = self.transpile(children, inner_ctx)
        return f"{ind}// FOR_EACH({condition})\n{body}"

    def _handle_repeat(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        times = node.times if node.times else (node.value or 1)

        # X-cost repeat
        if node.condition == "times_from_x_cost":
            times_expr = "this.energyOnUse"
        else:
            times_expr = str(times)

        children = node.children or []
        inner_ctx = ctx.indented()
        body = self.transpile(children, inner_ctx)
        return (
            f"{ind}for (int i = 0; i < {times_expr}; i++) {{\n"
            f"{body}\n"
            f"{ind}}}"
        )

    def _handle_trigger_custom(
        self, node: ActionNode, ctx: TranspileContext
    ) -> str:
        ind = ctx.indent_str()
        condition = node.condition or ""

        if condition == "exhume":
            return (
                f"{ind}if (!{ctx.source_var}.exhaustPile.isEmpty()) {{\n"
                f"{ind}    addToBot(new ExhumeAction());\n"
                f"{ind}}}"
            )

        if condition.startswith("armaments"):
            if condition == "armaments_all":
                return (
                    f"{ind}for (AbstractCard c : {ctx.source_var}.hand.group) {{\n"
                    f"{ind}    if (c.canUpgrade()) {{\n"
                    f"{ind}        addToBot(new ArmamentsAction(true));\n"
                    f"{ind}        break;\n"
                    f"{ind}    }}\n"
                    f"{ind}}}"
                )
            # armaments (upgrade 1)
            return f"{ind}addToBot(new ArmamentsAction(false));"

        if condition.startswith("dual_wield"):
            return f"{ind}addToBot(new DualWieldAction());"

        if condition == "infernal_blade":
            return f"{ind}addToBot(new InfernalBladeAction());"

        return f"{ind}// TRIGGER_CUSTOM: {condition}"

    # -- Condition → Java expression -----------------------------------------

    def _condition_to_java(
        self, condition: str, ctx: TranspileContext
    ) -> str:
        """Convert an IR condition string to a Java boolean expression."""
        src = ctx.source_var
        tgt = ctx.target_var

        if condition.startswith("has_status:"):
            status = condition.split(":", 1)[1]
            power_id = self._power_id_literal(status, ctx)
            return f"{src}.hasPower({power_id})"

        if condition.startswith("target_has_status:"):
            status = condition.split(":", 1)[1]
            power_id = self._power_id_literal(status, ctx)
            return f"{tgt}.hasPower({power_id})"

        if condition.startswith("hp_below:"):
            pct = condition.split(":", 1)[1]
            return f"{src}.currentHealth < {src}.maxHealth * {pct} / 100"

        if condition.startswith("hp_above:"):
            pct = condition.split(":", 1)[1]
            return f"{src}.currentHealth > {src}.maxHealth * {pct} / 100"

        if condition == "no_block":
            return f"{src}.currentBlock == 0"

        if condition == "hand_empty":
            return f"{src}.hand.size() == 0"

        if condition.startswith("hand_size_gte:"):
            n = condition.split(":", 1)[1]
            return f"{src}.hand.size() >= {n}"

        if condition == "only_attacks_in_hand":
            return f"onlyAttacksInHand()"

        if condition == "enemy_intends_attack":
            return f"{tgt}.getIntentBaseDmg() > 0"

        if condition == "target_is_dead":
            return f"{tgt}.isDeadOrEscaped()"

        if condition.startswith("turn_eq:"):
            n = condition.split(":", 1)[1]
            return f"AbstractDungeon.actionManager.turn == {n}"

        # Fallback: embed as comment
        return f"true /* {condition} */"


# Type alias for handler functions
_Handler = type(ActionTranspiler._handle_deal_damage)
