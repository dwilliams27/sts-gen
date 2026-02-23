"""Base class for AI agents that play Slay the Spire battles.

All play agents must subclass ``PlayAgent`` and implement the two abstract
methods.  The combat simulator calls these at decision points to determine
which card to play and which reward to pick.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sts_gen.ir.cards import CardDefinition
    from sts_gen.sim.core.game_state import BattleState, CardInstance


class PlayAgent(ABC):
    """Base class for AI agents that play the game."""

    @abstractmethod
    def choose_card_to_play(
        self,
        battle: BattleState,
        playable_cards: list[tuple[CardInstance, CardDefinition]],
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """Choose a card to play from the playable cards.

        Parameters
        ----------
        battle:
            The current combat state, giving the agent full observability.
        playable_cards:
            List of ``(card_instance, card_definition)`` tuples for every card
            in hand whose energy cost the player can currently afford and that
            is not unplayable (cost != -2).

        Returns
        -------
        tuple[CardInstance, CardDefinition, int | None] | None
            A 3-tuple of ``(card_instance, card_definition, chosen_target_index)``
            where *chosen_target_index* is the enemy index for single-target
            cards (``CardTarget.ENEMY``), or ``None`` for self-targeting /
            AoE cards.

            Return ``None`` to signal that the agent wants to end the turn
            without playing any more cards.
        """

    @abstractmethod
    def choose_card_reward(
        self,
        cards: list[CardDefinition],
        deck: list[str],
    ) -> CardDefinition | None:
        """Choose a card from the reward screen (or ``None`` to skip).

        Parameters
        ----------
        cards:
            List of card definitions offered as a reward (typically 3).
        deck:
            The player's current deck as a list of card IDs, giving the
            agent context about what they already have.

        Returns
        -------
        CardDefinition | None
            The chosen card, or ``None`` to skip the reward.
        """
