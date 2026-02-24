"""TriggerDispatcher -- fires status effect triggers generically.

Central class that handles all triggered status effects: iterates an entity's
status_effects, looks up definitions, scales values by stacks when
``condition == "per_stack"``, and executes the resulting actions via the
interpreter.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from sts_gen.ir.actions import ActionNode
from sts_gen.ir.status_effects import StatusEffectDefinition, StatusTrigger
from sts_gen.sim.mechanics.status_effects import _PASSIVE_MODIFIERS

if TYPE_CHECKING:
    from sts_gen.sim.core.entities import Entity
    from sts_gen.sim.core.game_state import BattleState
    from sts_gen.sim.interpreter import ActionInterpreter

logger = logging.getLogger(__name__)

# Conditions that indicate the action's value should be multiplied by stacks.
_PER_STACK_CONDITIONS = frozenset({
    "per_stack",
    "per_stack_raw",
    "per_stack_no_strength",
})


class TriggerDispatcher:
    """Fires status triggers for entities based on their StatusEffectDefinitions.

    Parameters
    ----------
    interpreter:
        The ActionInterpreter used to execute action nodes.
    status_defs:
        Mapping of status_id to StatusEffectDefinition.
    """

    def __init__(
        self,
        interpreter: ActionInterpreter,
        status_defs: dict[str, StatusEffectDefinition],
    ) -> None:
        self.interpreter = interpreter
        self.status_defs = status_defs

    def fire(
        self,
        entity: Entity,
        trigger: StatusTrigger,
        battle: BattleState,
        source: str,
        *,
        attacker_idx: int | str | None = None,
    ) -> None:
        """Fire all matching triggers on an entity.

        Parameters
        ----------
        entity:
            The entity whose statuses to check.
        trigger:
            The game event trigger to fire.
        battle:
            The current combat state.
        source:
            Who owns the entity: ``"player"`` or an enemy index string.
        attacker_idx:
            For ON_ATTACKED, the index of the attacking enemy.
        """
        # Snapshot status_effects keys to avoid mutation issues during iteration
        for status_id in list(entity.status_effects.keys()):
            if status_id in _PASSIVE_MODIFIERS:
                continue

            stacks = entity.status_effects.get(status_id, 0)
            if stacks <= 0:
                continue

            defn = self.status_defs.get(status_id)
            if defn is None:
                continue

            actions = defn.triggers.get(trigger)
            if not actions:
                continue

            # Scale actions by stacks and execute
            scaled = self._scale_actions(actions, stacks, attacker_idx)
            self.interpreter.execute_actions(scaled, battle, source=source)

    def _scale_actions(
        self,
        actions: list[ActionNode],
        stacks: int,
        attacker_idx: int | str | None = None,
    ) -> list[ActionNode]:
        """Clone action nodes, scaling values by stack count where indicated.

        Actions with ``condition`` in ``_PER_STACK_CONDITIONS`` have their
        ``value`` multiplied by ``stacks``.  The condition is then cleared
        (or preserved for special handling) so the interpreter treats them
        normally.
        """
        scaled: list[ActionNode] = []
        for node in actions:
            condition = node.condition or ""

            if condition in _PER_STACK_CONDITIONS:
                new_node = node.model_copy(deep=True)
                new_value = (node.value or 1) * stacks
                new_node.value = new_value

                # For per_stack_raw, set a flag so gain_block bypasses dex/frail
                if condition == "per_stack_raw":
                    new_node.condition = "raw"
                elif condition == "per_stack_no_strength":
                    new_node.condition = "no_strength"
                else:
                    new_node.condition = None

                # Resolve attacker target
                if new_node.target == "attacker" and attacker_idx is not None:
                    new_node.target = str(attacker_idx)

                scaled.append(new_node)
            else:
                # No scaling needed, but may need attacker resolution
                if node.target == "attacker" and attacker_idx is not None:
                    new_node = node.model_copy(deep=True)
                    new_node.target = str(attacker_idx)
                    scaled.append(new_node)
                else:
                    scaled.append(node)

        return scaled
