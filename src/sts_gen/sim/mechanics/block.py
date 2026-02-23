"""Block mechanics -- gain, clear, and decay."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.sim.core.entities import Entity
    from sts_gen.sim.core.game_state import BattleState

from .status_effects import get_status_stacks, has_status


def gain_block(entity: Entity, amount: int) -> None:
    """Add block to an entity, applying dexterity and frail modifiers."""
    block = float(amount)

    dexterity = get_status_stacks(entity, "dexterity")
    block += dexterity

    if has_status(entity, "frail"):
        block = math.floor(block * 0.75)

    block = max(0, int(block))
    entity.block += block


def clear_block(entity: Entity) -> None:
    entity.block = 0


def decay_block(battle: BattleState) -> None:
    """Clear block on all entities at the start of a turn."""
    clear_block(battle.player)
    for enemy in battle.enemies:
        if not enemy.is_dead:
            clear_block(enemy)
