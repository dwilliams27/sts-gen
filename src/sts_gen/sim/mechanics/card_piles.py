"""Card pile manipulation helpers.

Wraps the BattleState.card_piles to provide convenient functions
for drawing, discarding, exhausting, and shuffling cards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.sim.core.game_state import BattleState, CardInstance


def draw_cards(battle: BattleState, n: int) -> list[CardInstance]:
    """Draw n cards from the draw pile into the hand.

    Returns the list of cards actually drawn.
    """
    return battle.card_piles.draw_cards(n, battle.rng)


def discard_card(battle: BattleState, card: CardInstance) -> None:
    """Move a specific card from the hand to the discard pile."""
    battle.card_piles.move_to_discard(card)


def exhaust_card(battle: BattleState, card: CardInstance) -> None:
    """Move a specific card from the hand to the exhaust pile."""
    battle.card_piles.move_to_exhaust(card)


def discard_hand(battle: BattleState) -> None:
    """Move the entire hand to the discard pile."""
    battle.card_piles.discard_hand()


def add_to_draw_pile(
    battle: BattleState,
    card: CardInstance,
    position: str = "random",
) -> None:
    """Add a card to the draw pile at the given position."""
    battle.card_piles.add_to_draw(card, position=position, rng=battle.rng)


def shuffle_draw_pile(battle: BattleState) -> None:
    """Shuffle the draw pile in-place."""
    battle.card_piles.shuffle_draw(battle.rng)
