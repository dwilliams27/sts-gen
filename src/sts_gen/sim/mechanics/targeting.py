"""Target resolution -- translate target specifiers to entity indices."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.sim.core.game_state import BattleState


def resolve_targets(
    battle: BattleState,
    source: str,
    target_spec: str,
    chosen_target: int | None = None,
) -> list[int]:
    """Resolve a targeting specifier to a list of enemy indices.

    Returns empty list for "self" and "none" targeting.
    """
    target_spec = target_spec.lower().strip()

    if target_spec in ("enemy", "default"):
        if chosen_target is not None:
            if (
                0 <= chosen_target < len(battle.enemies)
                and not battle.enemies[chosen_target].is_dead
            ):
                return [chosen_target]
        living = _get_living_enemy_indices(battle)
        return [living[0]] if living else []

    if target_spec == "all_enemies":
        return _get_living_enemy_indices(battle)

    if target_spec == "self":
        return []

    if target_spec in ("random", "random_enemy"):
        living = _get_living_enemy_indices(battle)
        if not living:
            return []
        idx = battle.rng.random_choice(living)
        return [idx]

    if target_spec == "none":
        return []

    return []


def _get_living_enemy_indices(battle: BattleState) -> list[int]:
    return [i for i, e in enumerate(battle.enemies) if not e.is_dead]
