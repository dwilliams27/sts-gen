"""Random action agent -- picks cards and targets uniformly at random.

The ``RandomAgent`` is the simplest possible play agent.  It is used as
the baseline for batch simulation runs: it lets us verify that the full
combat loop works end-to-end and provides a lower-bound on card-set
quality (a card set that cannot beat encounters even with many random
tries is probably unplayable).

Behaviour:
    - Each time the agent is asked to play a card, there is a 10 % chance
      it will choose to end the turn early (simulating "pass").
    - Otherwise it picks a random card from the playable set.
    - For single-target cards it picks a random living enemy.
    - For card rewards it picks a random card (never skips).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts_gen.sim.play_agents.base import PlayAgent

if TYPE_CHECKING:
    from sts_gen.ir.cards import CardDefinition
    from sts_gen.ir.potions import PotionDefinition
    from sts_gen.sim.core.game_state import BattleState, CardInstance

from sts_gen.ir.cards import CardTarget
from sts_gen.sim.core.rng import GameRNG


class RandomAgent(PlayAgent):
    """Agent that plays random playable cards each turn.

    Parameters
    ----------
    rng:
        Seeded RNG for deterministic randomness.  If ``None``, a default
        ``GameRNG(seed=0)`` is created.
    end_turn_chance:
        Probability (0.0 -- 1.0) that the agent voluntarily ends the turn
        instead of playing another card.  Default is 0.10 (10 %).
    """

    def __init__(
        self,
        rng: GameRNG | None = None,
        end_turn_chance: float = 0.10,
    ) -> None:
        self._rng = rng or GameRNG(seed=0)
        self._end_turn_chance = end_turn_chance

    # ------------------------------------------------------------------
    # PlayAgent interface
    # ------------------------------------------------------------------

    def choose_card_to_play(
        self,
        battle: BattleState,
        playable_cards: list[tuple[CardInstance, CardDefinition]],
    ) -> tuple[CardInstance, CardDefinition, int | None] | None:
        """Pick a random playable card, with a chance to end the turn early."""
        if not playable_cards:
            return None

        # Random chance to end the turn early
        if self._rng.random_float() < self._end_turn_chance:
            return None

        # Pick a random card
        card_instance, card_def = self._rng.random_choice(playable_cards)

        # Pick a target if the card requires one
        chosen_target: int | None = None
        if card_def.target == CardTarget.ENEMY:
            living = battle.living_enemies
            if living:
                # Pick a random living enemy by index
                living_indices = [
                    i for i, e in enumerate(battle.enemies) if not e.is_dead
                ]
                chosen_target = self._rng.random_choice(living_indices)
            else:
                # No living enemies -- should not happen if battle is not over
                return None

        return card_instance, card_def, chosen_target

    def choose_card_reward(
        self,
        cards: list[CardDefinition],
        deck: list[str],
    ) -> CardDefinition | None:
        """Always pick a random card from the reward options."""
        if not cards:
            return None
        return self._rng.random_choice(cards)

    def choose_potion_to_use(
        self,
        battle: BattleState,
        available_potions: list[tuple[int, PotionDefinition]],
    ) -> tuple[int, PotionDefinition, int | None] | None:
        """5% chance to use a random potion; pick random target for ENEMY potions."""
        if not available_potions:
            return None

        if self._rng.random_float() >= 0.05:
            return None

        slot, potion_def = self._rng.random_choice(available_potions)

        chosen_target: int | None = None
        if potion_def.target == CardTarget.ENEMY:
            living_indices = [
                i for i, e in enumerate(battle.enemies) if not e.is_dead
            ]
            if living_indices:
                chosen_target = self._rng.random_choice(living_indices)
            else:
                return None

        return slot, potion_def, chosen_target
