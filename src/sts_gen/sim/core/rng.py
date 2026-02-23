"""Seeded random number generator for deterministic STS combat simulation.

Wraps Python's random.Random to provide reproducible randomness.  Each
sub-system (card rewards, combat, map generation, ...) should use a
*forked* RNG so that consuming random values in one system does not
perturb another.
"""

from __future__ import annotations

import hashlib
import random
from typing import Sequence, TypeVar

T = TypeVar("T")


class GameRNG:
    """Deterministic RNG that can be forked into independent sub-streams.

    Parameters
    ----------
    seed:
        Integer seed for the underlying Mersenne Twister.
    """

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._rng = random.Random(seed)

    # -- public properties ---------------------------------------------------

    @property
    def seed(self) -> int:
        """Return the seed this RNG was initialised with."""
        return self._seed

    # -- core random methods -------------------------------------------------

    def random_int(self, low: int, high: int) -> int:
        """Return a random integer *N* such that ``low <= N <= high``."""
        return self._rng.randint(low, high)

    def random_float(self) -> float:
        """Return a random float in the half-open interval ``[0.0, 1.0)``."""
        return self._rng.random()

    def random_choice(self, seq: Sequence[T]) -> T:
        """Return a random element from a non-empty sequence."""
        return self._rng.choice(seq)

    def shuffle(self, lst: list[T]) -> None:
        """Shuffle *lst* in-place."""
        self._rng.shuffle(lst)

    # -- forking -------------------------------------------------------------

    def fork(self, name: str) -> GameRNG:
        """Create a child RNG whose seed is derived from this RNG's seed and
        *name*.

        The derivation is deterministic: forking with the same *name*
        from an RNG in the same state always produces the same child
        seed.  This lets sub-systems (e.g. ``"combat"``, ``"rewards"``,
        ``"map"``) each have their own independent random stream.
        """
        # Derive a stable child seed by hashing (parent_seed, name).
        digest = hashlib.sha256(f"{self._seed}:{name}".encode()).digest()
        child_seed = int.from_bytes(digest[:8], "big")
        return GameRNG(child_seed)

    # -- dunder helpers ------------------------------------------------------

    def __repr__(self) -> str:
        return f"GameRNG(seed={self._seed})"
