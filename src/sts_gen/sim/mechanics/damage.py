"""Damage calculation and application.

Implements the STS damage pipeline:
    base + strength -> vulnerable multiplier -> weak multiplier -> floor(0)

Then applies damage to target: block absorbs first, remainder hits HP.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.sim.core.entities import Entity
    from sts_gen.sim.core.game_state import BattleState

from .status_effects import get_status_stacks, has_status


def calculate_damage(base: int, source_entity: Entity, target_entity: Entity) -> int:
    """Calculate final damage after all modifiers.

    Pipeline (order matters -- matches real STS):
        1. Add source's strength to base damage
        2. If target is vulnerable: multiply by 1.5 (floor)
        3. If source is weak: multiply by 0.75 (floor)
        4. Floor at 0
    """
    damage = float(base)

    # Step 1: Add strength
    strength = get_status_stacks(source_entity, "strength")
    damage += strength

    # Step 2: Vulnerable multiplier (on target)
    if has_status(target_entity, "vulnerable"):
        damage = math.floor(damage * 1.5)

    # Step 3: Weak multiplier (on source)
    if has_status(source_entity, "weak"):
        damage = math.floor(damage * 0.75)

    # Step 4: Floor at 0
    return max(0, int(damage))


def deal_damage(
    battle: BattleState,
    source_idx: int | str,
    target_idx: int | str,
    base_damage: int,
    hits: int = 1,
) -> int:
    """Deal damage from source to target, respecting block and multi-hit.

    Returns total HP actually lost by the target across all hits.
    """
    source_entity = _resolve_entity(battle, source_idx)
    target_entity = _resolve_entity(battle, target_idx)

    total_hp_lost = 0

    for _ in range(hits):
        if target_entity.is_dead:
            break

        final_damage = calculate_damage(base_damage, source_entity, target_entity)
        hp_lost = target_entity.take_damage(final_damage)
        total_hp_lost += hp_lost

    return total_hp_lost


def _resolve_entity(battle: BattleState, idx: int | str) -> Entity:
    """Resolve a source/target index to an Entity."""
    if idx == "player":
        return battle.player
    return battle.enemies[idx]
