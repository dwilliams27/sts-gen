"""Status effect lifecycle -- apply, remove, decay, trigger, query.

Manages the status_effects dict on Entity objects.  Built-in statuses
(vulnerable, weak, frail, strength, dexterity) are simple integer stacks.
Custom statuses are defined by StatusEffectDefinition from the IR and
support triggers and configurable decay.

Entity.status_effects is expected to be ``dict[str, int]`` mapping
status_id to current stack count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.ir.actions import ActionNode
    from sts_gen.ir.status_effects import StatusEffectDefinition
    from sts_gen.sim.core.entities import Entity

# Built-in statuses that decay by 1 stack at end of turn.
_BUILTIN_DECAY_STATUSES = frozenset({"vulnerable", "weak", "frail"})

# Built-in statuses that are permanent (no decay) -- strength, dexterity,
# Metallicize, Ritual.  They persist until explicitly removed or modified.
_BUILTIN_PERMANENT_STATUSES = frozenset({"strength", "dexterity", "Metallicize", "Ritual"})


def apply_status(entity: Entity, status_id: str, stacks: int) -> None:
    """Add or increase stacks of a status effect on an entity.

    If the entity already has the status, stacks are added.
    If the entity does not have the status, it is created with the given stacks.

    Parameters
    ----------
    entity:
        The entity receiving the status.
    status_id:
        Identifier of the status effect (e.g. ``"vulnerable"``, ``"strength"``).
    stacks:
        Number of stacks to add (can be negative for debuff removal effects
        like strength reduction).
    """
    if status_id in entity.status_effects:
        entity.status_effects[status_id] += stacks
    else:
        entity.status_effects[status_id] = stacks

    # Remove if stacks drop to 0 or below (for non-permanent statuses that
    # can go negative via strength-down type effects, keep them).
    # Strength and dexterity can be negative (e.g. Strength Down debuff).
    if status_id not in _BUILTIN_PERMANENT_STATUSES:
        if entity.status_effects.get(status_id, 0) <= 0:
            entity.status_effects.pop(status_id, None)


def remove_status(entity: Entity, status_id: str) -> None:
    """Completely remove a status effect from an entity.

    Parameters
    ----------
    entity:
        The entity to remove the status from.
    status_id:
        Identifier of the status effect to remove.
    """
    entity.status_effects.pop(status_id, None)


def decay_statuses(entity: Entity, status_defs: dict[str, StatusEffectDefinition] | None = None) -> None:
    """Decay status effects at end of turn.

    Built-in statuses (vulnerable, weak, frail) lose 1 stack per turn.
    Custom statuses use their ``decay_per_turn`` from their definition.
    Permanent statuses (strength, dexterity) do not decay.

    Statuses that reach 0 or fewer stacks are removed.

    Parameters
    ----------
    entity:
        The entity whose statuses should decay.
    status_defs:
        Mapping of status_id to StatusEffectDefinition for custom statuses.
        Can be None if only built-in statuses are present.
    """
    to_remove: list[str] = []

    for status_id, stacks in list(entity.status_effects.items()):
        # Skip permanent built-in statuses
        if status_id in _BUILTIN_PERMANENT_STATUSES:
            continue

        # Built-in decay statuses
        if status_id in _BUILTIN_DECAY_STATUSES:
            new_stacks = stacks - 1
            if new_stacks <= 0:
                to_remove.append(status_id)
            else:
                entity.status_effects[status_id] = new_stacks
            continue

        # Custom status -- use definition
        if status_defs and status_id in status_defs:
            defn = status_defs[status_id]
            if defn.decay_per_turn > 0:
                new_stacks = stacks - defn.decay_per_turn
                if new_stacks <= defn.min_stacks:
                    to_remove.append(status_id)
                else:
                    entity.status_effects[status_id] = new_stacks

    for status_id in to_remove:
        entity.status_effects.pop(status_id, None)


def trigger_status(
    entity: Entity,
    status_id: str,
    trigger: str,
    status_defs: dict[str, StatusEffectDefinition],
) -> list[ActionNode]:
    """Get action nodes to execute for a triggered status effect.

    Looks up the StatusEffectDefinition for the given status_id and returns
    the action list for the specified trigger.  Built-in statuses (vulnerable,
    weak, frail, strength, dexterity) are passive modifiers and return empty
    lists -- their effects are applied inline by calculate_damage / gain_block.

    Parameters
    ----------
    entity:
        The entity that has the status.
    status_id:
        Identifier of the status effect.
    trigger:
        The game event trigger (e.g. ``"ON_TURN_START"``, ``"ON_TURN_END"``).
    status_defs:
        Mapping of status_id to StatusEffectDefinition for looking up triggers.

    Returns
    -------
    list[ActionNode]
        Action nodes to execute, or empty list if no actions for this trigger.
    """
    # Built-in statuses are passive -- no triggered actions
    if status_id in _BUILTIN_DECAY_STATUSES or status_id in _BUILTIN_PERMANENT_STATUSES:
        return []

    # Entity must actually have the status
    if not has_status(entity, status_id):
        return []

    # Look up definition
    defn = status_defs.get(status_id)
    if defn is None:
        return []

    # Find actions for the trigger
    # The trigger key in the definition uses the StatusTrigger enum,
    # but we accept a string and match against enum values.
    for trigger_key, actions in defn.triggers.items():
        if trigger_key.value == trigger or trigger_key == trigger:
            return list(actions)

    return []


def has_status(entity: Entity, status_id: str) -> bool:
    """Check whether an entity currently has a given status effect.

    Parameters
    ----------
    entity:
        The entity to check.
    status_id:
        Identifier of the status effect.

    Returns
    -------
    bool
        True if the entity has the status with stacks > 0.
        For permanent statuses (strength, dexterity), returns True even
        if stacks are negative (a debuff like Strength Down is still "present").
    """
    if status_id not in entity.status_effects:
        return False

    # Permanent statuses can be negative and still count as "present"
    if status_id in _BUILTIN_PERMANENT_STATUSES:
        return True

    return entity.status_effects[status_id] > 0


def get_status_stacks(entity: Entity, status_id: str) -> int:
    """Get the current stack count of a status effect.

    Parameters
    ----------
    entity:
        The entity to query.
    status_id:
        Identifier of the status effect.

    Returns
    -------
    int
        Number of stacks, or 0 if the entity does not have the status.
    """
    return entity.status_effects.get(status_id, 0)
