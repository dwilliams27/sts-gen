"""Core combat mechanics for the STS simulator.

Re-exports the primary functions from each mechanics module for convenience.

Usage::

    from sts_gen.sim.mechanics import (
        calculate_damage, deal_damage,
        gain_block, clear_block, decay_block,
        reset_energy, spend_energy, gain_energy,
        draw_cards, discard_card, exhaust_card, discard_hand,
        apply_status, remove_status, decay_statuses, has_status, get_status_stacks,
        resolve_targets,
    )
"""

# -- damage ------------------------------------------------------------------
from .damage import calculate_damage, deal_damage

# -- block -------------------------------------------------------------------
from .block import clear_block, decay_block, gain_block

# -- energy ------------------------------------------------------------------
from .energy import gain_energy, reset_energy, spend_energy

# -- card piles --------------------------------------------------------------
from .card_piles import (
    add_to_draw_pile,
    discard_card,
    discard_hand,
    draw_cards,
    exhaust_card,
    shuffle_draw_pile,
)

# -- status effects ----------------------------------------------------------
from .status_effects import (
    apply_status,
    decay_statuses,
    get_status_stacks,
    has_status,
    remove_status,
    trigger_status,
)

# -- targeting ---------------------------------------------------------------
from .targeting import resolve_targets

__all__ = [
    # damage
    "calculate_damage",
    "deal_damage",
    # block
    "gain_block",
    "clear_block",
    "decay_block",
    # energy
    "reset_energy",
    "spend_energy",
    "gain_energy",
    # card piles
    "draw_cards",
    "discard_card",
    "exhaust_card",
    "discard_hand",
    "add_to_draw_pile",
    "shuffle_draw_pile",
    # status effects
    "apply_status",
    "remove_status",
    "decay_statuses",
    "trigger_status",
    "has_status",
    "get_status_stacks",
    # targeting
    "resolve_targets",
]
