"""Priority action queue for the STS combat simulator.

Actions produced by cards, relics, powers, and enemies are pushed onto
this queue and then resolved one at a time by the simulation loop.
``push_front`` allows chain-reaction effects (e.g. a card that draws
another card) to be inserted *before* previously queued actions.
"""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# QueuedAction (value object)
# ---------------------------------------------------------------------------

class QueuedAction(BaseModel):
    """A single action waiting to be resolved.

    Parameters
    ----------
    action_type:
        Identifier for the action (e.g. ``"deal_damage"``, ``"gain_block"``,
        ``"apply_status"``).
    source:
        Who or what produced the action (entity name, card id, relic id, ...).
    target:
        Optional target identifier (enemy name / index, ``"player"``, ...).
    params:
        Arbitrary parameters consumed by the action resolver.
    """

    action_type: str
    source: str
    target: str | None = None
    params: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# ActionQueue
# ---------------------------------------------------------------------------

class ActionQueue:
    """FIFO queue of ``QueuedAction`` objects with front-insertion support.

    This is a plain Python class (not a Pydantic model) because it holds
    mutable internal state that should not be serialized.
    """

    def __init__(self) -> None:
        self._queue: deque[QueuedAction] = deque()

    # -- mutations -----------------------------------------------------------

    def push(self, action: QueuedAction) -> None:
        """Append *action* to the back of the queue (normal priority)."""
        self._queue.append(action)

    def push_front(self, action: QueuedAction) -> None:
        """Insert *action* at the front of the queue.

        Use this for chain-reaction effects that must resolve before
        previously enqueued actions.
        """
        self._queue.appendleft(action)

    def pop(self) -> QueuedAction | None:
        """Remove and return the next action, or ``None`` if the queue is
        empty."""
        if self._queue:
            return self._queue.popleft()
        return None

    def clear(self) -> None:
        """Discard all queued actions."""
        self._queue.clear()

    # -- queries -------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def __len__(self) -> int:
        return len(self._queue)

    def __repr__(self) -> str:
        return f"ActionQueue(length={len(self._queue)})"
