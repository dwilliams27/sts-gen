"""Energy system -- reset, spend, and gain.

STS energy rules:
    - Player starts each turn with their max energy (usually 3).
    - Playing a card spends its cost from the energy pool.
    - Some effects grant additional energy mid-turn.
    - Energy does NOT carry over between turns (unless Conserve modifier).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.sim.core.entities import Player


def reset_energy(player: Player, amount: int | None = None) -> None:
    """Reset the player's energy to their max (or a specified amount).

    Called at the start of each turn.

    Parameters
    ----------
    player:
        The player entity.
    amount:
        If provided, set energy to this value instead of max_energy.
    """
    if amount is not None:
        player.energy = amount
    else:
        player.energy = player.max_energy


def spend_energy(player: Player, amount: int) -> bool:
    """Attempt to spend energy.  Returns False if insufficient.

    Parameters
    ----------
    player:
        The player entity.
    amount:
        Energy cost to pay.

    Returns
    -------
    bool
        True if the energy was successfully spent, False if the player
        did not have enough energy.
    """
    if player.energy < amount:
        return False
    player.energy -= amount
    return True


def gain_energy(player: Player, amount: int) -> None:
    """Add energy to the player's current pool.

    Parameters
    ----------
    player:
        The player entity.
    amount:
        Energy to add (can be 0 or negative in theory, but typically positive).
    """
    player.energy += amount
