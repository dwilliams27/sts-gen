"""Potion usage -- execute a potion's action list through the interpreter."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.ir.potions import PotionDefinition
    from sts_gen.sim.core.game_state import BattleState
    from sts_gen.sim.interpreter import ActionInterpreter


def use_potion(
    potion_def: PotionDefinition,
    battle: BattleState,
    interpreter: ActionInterpreter,
    chosen_target: int | None = None,
) -> None:
    """Use a potion, executing its actions through the interpreter.

    Parameters
    ----------
    potion_def:
        The potion definition to execute.
    battle:
        The current combat state (mutated in-place).
    interpreter:
        The action interpreter.
    chosen_target:
        Enemy index for single-target potions.
    """
    interpreter.execute_actions(
        potion_def.actions,
        battle,
        source="player",
        chosen_target=chosen_target,
    )
