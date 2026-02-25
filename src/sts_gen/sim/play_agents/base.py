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
    from sts_gen.ir.potions import PotionDefinition
    from sts_gen.sim.core.entities import Player
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

    @abstractmethod
    def choose_potion_to_use(
        self,
        battle: BattleState,
        available_potions: list[tuple[int, PotionDefinition]],
    ) -> tuple[int, PotionDefinition, int | None] | None:
        """Choose a potion to use before playing a card.

        Parameters
        ----------
        battle:
            The current combat state.
        available_potions:
            List of ``(slot_index, potion_definition)`` for each non-empty
            potion slot.

        Returns
        -------
        tuple[int, PotionDefinition, int | None] | None
            A 3-tuple of ``(slot_index, potion_definition, chosen_target)``
            where *chosen_target* is the enemy index for ENEMY-targeted
            potions, or ``None`` for self-target / AoE potions.

            Return ``None`` to skip using a potion this action.
        """

    @abstractmethod
    def choose_rest_action(
        self,
        player: Player,
        deck: list[CardInstance],
    ) -> str:
        """Choose what to do at a rest site.

        Parameters
        ----------
        player:
            The player entity (for HP checks).
        deck:
            The player's current deck.

        Returns
        -------
        str
            ``"rest"`` to heal 30% max HP, or ``"smith"`` to upgrade a card.
        """

    @abstractmethod
    def choose_card_to_upgrade(
        self,
        upgradable: list[CardInstance],
    ) -> CardInstance | None:
        """Choose a card to upgrade at a rest site Smith.

        Parameters
        ----------
        upgradable:
            List of card instances that can be upgraded.

        Returns
        -------
        CardInstance | None
            The card to upgrade, or ``None`` to skip.
        """
