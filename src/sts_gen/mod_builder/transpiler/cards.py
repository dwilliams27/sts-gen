"""Card IR → Java template context transpiler.

Extracts baseDamage/baseBlock/baseMagicNumber from ActionNode trees
and builds the template context dict for Card.java.j2.
"""

from __future__ import annotations

from dataclasses import dataclass

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import CardDefinition, CardTarget, CardType

from .actions import ActionTranspiler, TranspileContext
from .naming import to_card_class_name, to_image_path, to_power_class_name, to_sts_id
from .vanilla_powers import is_vanilla_status


@dataclass
class CardStats:
    """Base stats extracted from action trees for STS card constructor."""

    base_damage: int | None = None
    base_block: int | None = None
    base_magic_number: int | None = None
    is_multi_damage: bool = False


def _extract_stats(actions: list[ActionNode], target: CardTarget) -> CardStats:
    """Walk action tree to extract baseDamage, baseBlock, baseMagicNumber."""
    stats = CardStats()

    def walk(nodes: list[ActionNode]) -> None:
        for node in nodes:
            if (
                node.action_type == ActionType.DEAL_DAMAGE
                and stats.base_damage is None
                and node.value is not None
                and node.value > 0
            ):
                stats.base_damage = node.value
                if node.target == "all_enemies" or target == CardTarget.ALL_ENEMIES:
                    stats.is_multi_damage = True
            elif (
                node.action_type == ActionType.GAIN_BLOCK
                and stats.base_block is None
                and node.value is not None
                and node.value > 0
            ):
                stats.base_block = node.value
            elif (
                node.action_type == ActionType.APPLY_STATUS
                and stats.base_magic_number is None
                and node.value is not None
                and node.value > 0
            ):
                stats.base_magic_number = node.value
            if node.children:
                walk(node.children)

    walk(actions)
    return stats


def _collect_custom_power_refs(actions: list[ActionNode]) -> set[str]:
    """Walk action tree and collect all custom (non-vanilla) status names referenced."""
    refs: set[str] = set()

    def walk(nodes: list[ActionNode]) -> None:
        for node in nodes:
            if node.action_type == ActionType.APPLY_STATUS and node.status_name:
                if not is_vanilla_status(node.status_name):
                    refs.add(node.status_name)
            if node.children:
                walk(node.children)

    walk(actions)
    return refs


def _compute_upgrade_deltas(
    base: CardStats, upgraded: CardStats
) -> dict[str, int]:
    """Compute the delta calls needed: upgradeDamage(N), upgradeBlock(N), etc."""
    deltas: dict[str, int] = {}
    if (
        base.base_damage is not None
        and upgraded.base_damage is not None
        and upgraded.base_damage != base.base_damage
    ):
        deltas["damage"] = upgraded.base_damage - base.base_damage
    if (
        base.base_block is not None
        and upgraded.base_block is not None
        and upgraded.base_block != base.base_block
    ):
        deltas["block"] = upgraded.base_block - base.base_block
    if (
        base.base_magic_number is not None
        and upgraded.base_magic_number is not None
        and upgraded.base_magic_number != base.base_magic_number
    ):
        deltas["magic_number"] = upgraded.base_magic_number - base.base_magic_number
    return deltas


class CardTranspiler:
    """Transpiles CardDefinition → Jinja2 template context."""

    def __init__(self, mod_id: str, status_id_map: dict[str, str] | None = None):
        self.mod_id = mod_id
        self.action_transpiler = ActionTranspiler()
        self.status_id_map = status_id_map or {}

    def transpile(self, card: CardDefinition) -> dict:
        """Build template context dict for a single card."""
        class_name = to_card_class_name(card.id)
        sts_id = to_sts_id(self.mod_id, card.id)
        img_path = to_image_path(self.mod_id, "cards", card.id)

        # Extract base stats
        base_stats = _extract_stats(card.actions, card.target)

        # Card type → STS enum
        card_type_map = {
            CardType.ATTACK: "ATTACK",
            CardType.SKILL: "SKILL",
            CardType.POWER: "POWER",
            CardType.STATUS: "STATUS",
            CardType.CURSE: "CURSE",
        }

        # Card rarity → STS enum
        rarity_map = {
            "BASIC": "BASIC",
            "COMMON": "COMMON",
            "UNCOMMON": "UNCOMMON",
            "RARE": "RARE",
            "SPECIAL": "SPECIAL",
        }

        # Card target → STS enum (STS uses ALL_ENEMY, not ALL_ENEMIES)
        target_map = {
            CardTarget.ENEMY: "ENEMY",
            CardTarget.ALL_ENEMIES: "ALL_ENEMY",
            CardTarget.SELF: "SELF",
            CardTarget.NONE: "NONE",
        }

        # Build action body
        ctx = TranspileContext(
            source_var="p",
            target_var="m",
            indent=2,
            status_id_map=self.status_id_map,
            mod_id=self.mod_id,
        )
        action_body = self.action_transpiler.transpile(card.actions, ctx)

        # Upgrade handling
        upgrade = None
        if card.upgrade is not None:
            upg = card.upgrade
            upgrade_actions = upg.actions if upg.actions else card.actions
            upgraded_stats = _extract_stats(upgrade_actions, card.target)
            deltas = _compute_upgrade_deltas(base_stats, upgraded_stats)

            # Upgraded action body (only if actions changed)
            upgraded_action_body = None
            if upg.actions is not None:
                upgraded_action_body = self.action_transpiler.transpile(
                    upg.actions, ctx
                )

            upgrade = {
                "cost": upg.cost,
                "deltas": deltas,
                "action_body": upgraded_action_body,
                "exhaust": upg.exhaust,
                "innate": upg.innate,
            }

        # On-exhaust
        on_exhaust_body = None
        if card.on_exhaust:
            on_exhaust_body = self.action_transpiler.transpile(card.on_exhaust, ctx)

        # Play restriction → canUse override
        can_use_condition = None
        if card.play_restriction:
            can_use_condition = self.action_transpiler._condition_to_java(
                card.play_restriction, ctx
            )

        # Collect custom power imports (non-vanilla status refs need import)
        all_actions = list(card.actions)
        if card.upgrade and card.upgrade.actions:
            all_actions.extend(card.upgrade.actions)
        if card.on_exhaust:
            all_actions.extend(card.on_exhaust)
        custom_refs = _collect_custom_power_refs(all_actions)
        pkg = f"sts_gen.{self.mod_id.lower()}"
        extra_imports = [
            f"{pkg}.powers.{to_power_class_name(ref)}" for ref in sorted(custom_refs)
        ]

        return {
            "class_name": class_name,
            "sts_id": sts_id,
            "img_path": img_path,
            "card_type": card_type_map[card.type],
            "rarity": rarity_map[card.rarity.value],
            "target": target_map[card.target],
            "cost": card.cost,
            "base_damage": base_stats.base_damage,
            "base_block": base_stats.base_block,
            "base_magic_number": base_stats.base_magic_number,
            "is_multi_damage": base_stats.is_multi_damage,
            "exhaust": card.exhaust,
            "ethereal": card.ethereal,
            "innate": card.innate,
            "retain": card.retain,
            "action_body": action_body,
            "upgrade": upgrade,
            "on_exhaust_body": on_exhaust_body,
            "can_use_condition": can_use_condition,
            "is_x_cost": card.cost == -1,
            "package_path": pkg,
            "extra_imports": extra_imports,
        }
