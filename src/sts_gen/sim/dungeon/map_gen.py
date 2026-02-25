"""Map generator for Act 1 dungeon runs.

Generates a linear 16-floor map with wiki-accurate floor distribution:
- Floor 1: always monster
- Floors 2-8: weighted random (monster 53%, event 22%, rest 12%, elite 8%, shop 5%)
- Floor 9: always treasure
- Floors 10-14: same weights as 2-8
- Floor 15: always rest site
- Floor 16: boss fight

Constraints:
- No elites or rests before floor 6
- No consecutive elite/rest/shop
"""

from __future__ import annotations

from dataclasses import dataclass

from sts_gen.sim.core.rng import GameRNG


@dataclass
class MapNode:
    """A single floor in the dungeon map."""

    floor: int
    node_type: str  # "monster", "elite", "rest", "shop", "event", "treasure", "boss"


# Weighted pool for random floors (weights sum to 100)
_RANDOM_WEIGHTS: list[tuple[str, int]] = [
    ("monster", 53),
    ("event", 22),
    ("rest", 12),
    ("elite", 8),
    ("shop", 5),
]

# Node types that cannot appear consecutively
_NO_CONSECUTIVE = {"elite", "rest", "shop"}


class MapGenerator:
    """Generates a linear 16-floor Act 1 map."""

    def generate_act_1(self, rng: GameRNG) -> list[MapNode]:
        """Generate a linear 16-floor Act 1 map.

        Returns a list of 16 MapNode objects, one per floor.
        """
        nodes: list[MapNode] = []

        # Fixed floor types to check for forward constraints
        fixed_types = {1: "monster", 9: "treasure", 15: "rest", 16: "boss"}

        for floor in range(1, 17):
            if floor in fixed_types:
                node_type = fixed_types[floor]
            else:
                prev_type = nodes[-1].node_type if nodes else None
                # Check if next floor is a fixed restricted type
                next_fixed = fixed_types.get(floor + 1)
                node_type = self._roll_random_floor(
                    rng, floor, prev_type, next_fixed,
                )

            nodes.append(MapNode(floor=floor, node_type=node_type))

        return nodes

    def _roll_random_floor(
        self,
        rng: GameRNG,
        floor: int,
        prev_type: str | None,
        next_fixed: str | None = None,
    ) -> str:
        """Roll a weighted random floor type with constraints."""
        available: list[tuple[str, int]] = []
        for node_type, weight in _RANDOM_WEIGHTS:
            # No elites or rests before floor 6
            if floor < 6 and node_type in ("elite", "rest"):
                continue
            # No consecutive elite/rest/shop (check previous)
            if prev_type in _NO_CONSECUTIVE and node_type == prev_type:
                continue
            # No consecutive with next fixed floor
            if (
                next_fixed in _NO_CONSECUTIVE
                and node_type == next_fixed
            ):
                continue
            available.append((node_type, weight))

        # Weighted random selection
        total = sum(w for _, w in available)
        roll = rng.random_float() * total
        cumulative = 0
        for node_type, weight in available:
            cumulative += weight
            if roll < cumulative:
                return node_type

        # Fallback to last option (shouldn't normally reach here)
        return available[-1][0]
