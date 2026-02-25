"""RelicDispatcher -- fires relic triggers during combat.

Iterates the player's equipped relics, matches triggers to the current game
event, handles counter-based relics (Nunchaku, Shuriken, Kunai, Ornamental Fan),
resolves ``"attacker"`` targets, and executes resulting actions via the interpreter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.ir.relics import RelicDefinition
    from sts_gen.sim.core.game_state import BattleState
    from sts_gen.sim.interpreter import ActionInterpreter

logger = logging.getLogger(__name__)


class RelicDispatcher:
    """Fires relic triggers for the player's equipped relics.

    Parameters
    ----------
    interpreter:
        The ActionInterpreter used to execute relic action nodes.
    relic_defs:
        Mapping of relic_id to RelicDefinition.
    """

    def __init__(
        self,
        interpreter: ActionInterpreter,
        relic_defs: dict[str, RelicDefinition],
    ) -> None:
        self.interpreter = interpreter
        self.relic_defs = relic_defs
        self._counters: dict[str, int] = {}

    def fire(
        self,
        trigger: str,
        battle: BattleState,
        relic_ids: list[str],
        *,
        attacker_idx: int | str | None = None,
    ) -> None:
        """Fire all matching relic triggers.

        Parameters
        ----------
        trigger:
            The game event trigger name (e.g. ``"on_combat_start"``).
        battle:
            The current combat state.
        relic_ids:
            The player's equipped relic ids.
        attacker_idx:
            For ``on_attacked``, the index of the attacking enemy.
        """
        for relic_id in relic_ids:
            if battle.is_over:
                break

            defn = self.relic_defs.get(relic_id)
            if defn is None:
                continue

            if defn.trigger != trigger:
                continue

            # Counter-based relics: increment and check threshold
            if defn.counter is not None:
                current = self._counters.get(relic_id, 0) + 1
                if current < defn.counter:
                    self._counters[relic_id] = current
                    continue
                # Threshold reached: reset and fire
                self._counters[relic_id] = 0

            # Resolve attacker targets in actions
            actions = defn.actions
            if attacker_idx is not None:
                actions = self._resolve_attacker(actions, attacker_idx)

            self.interpreter.execute_actions(
                actions, battle, source="player",
            )

    def reset_counters(self) -> None:
        """Reset all counters (called at combat start)."""
        self._counters.clear()

    def reset_turn_counters(self) -> None:
        """Reset per-turn counters (called at start of each turn)."""
        for relic_id, defn in self.relic_defs.items():
            if defn.counter_per_turn and relic_id in self._counters:
                self._counters[relic_id] = 0

    def _resolve_attacker(
        self,
        actions: list,
        attacker_idx: int | str,
    ) -> list:
        """Clone actions and replace ``"attacker"`` targets with the actual index."""
        resolved = []
        for node in actions:
            if node.target == "attacker":
                new_node = node.model_copy(deep=True)
                new_node.target = str(attacker_idx)
                resolved.append(new_node)
            else:
                resolved.append(node)
        return resolved
