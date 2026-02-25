"""Game and battle state for a headless Slay the Spire combat simulator.

Houses the full mutable state of a run (``GameState``) and a single
encounter (``BattleState``), plus the card-pile management logic that
drives the draw-discard-exhaust cycle.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.rng import GameRNG


# ---------------------------------------------------------------------------
# CardInstance
# ---------------------------------------------------------------------------

class CardInstance(BaseModel):
    """A single card residing in a pile.

    Each physical copy has its own ``id`` so we can track it across
    piles even when several copies of the same ``card_id`` exist.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    card_id: str
    """References the card definition in the IR."""

    upgraded: bool = False
    cost_override: int | None = None
    """If set, overrides the base energy cost from the IR definition."""


# ---------------------------------------------------------------------------
# CardPiles
# ---------------------------------------------------------------------------

class CardPiles(BaseModel):
    """Manages the four card piles that exist during combat.

    The ``draw_cards`` method correctly handles reshuffling the discard
    pile back into the draw pile when the draw pile is exhausted.
    """

    draw: list[CardInstance] = Field(default_factory=list)
    hand: list[CardInstance] = Field(default_factory=list)
    discard: list[CardInstance] = Field(default_factory=list)
    exhaust: list[CardInstance] = Field(default_factory=list)

    # -- queries -------------------------------------------------------------

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    # -- drawing -------------------------------------------------------------

    def draw_cards(self, n: int, rng: GameRNG) -> list[CardInstance]:
        """Draw up to *n* cards into the hand.

        If the draw pile runs out mid-draw, the discard pile is shuffled
        and becomes the new draw pile, then drawing continues.

        Returns the list of cards actually drawn (may be fewer than *n*
        if both piles are empty).
        """
        drawn: list[CardInstance] = []
        for _ in range(n):
            if not self.draw:
                if not self.discard:
                    break  # nothing left to draw
                self._reshuffle_discard_into_draw(rng)
            if self.draw:
                card = self.draw.pop(0)
                self.hand.append(card)
                drawn.append(card)
        return drawn

    def _reshuffle_discard_into_draw(self, rng: GameRNG) -> None:
        """Move all cards from discard into draw, then shuffle."""
        self.draw.extend(self.discard)
        self.discard.clear()
        rng.shuffle(self.draw)

    # -- pile movement -------------------------------------------------------

    def discard_hand(self) -> None:
        """Move every card in the hand to the discard pile."""
        self.discard.extend(self.hand)
        self.hand.clear()

    def move_to_discard(self, card: CardInstance) -> None:
        """Remove *card* from the hand and place it in the discard pile."""
        self._remove_from_hand(card)
        self.discard.append(card)

    def move_to_exhaust(self, card: CardInstance) -> None:
        """Remove *card* from the hand and exhaust it."""
        self._remove_from_hand(card)
        self.exhaust.append(card)

    def add_to_hand(self, card: CardInstance) -> None:
        """Add a card directly to the hand (e.g. via a relic or power)."""
        self.hand.append(card)

    def add_to_draw(
        self,
        card: CardInstance,
        position: Literal["top", "random", "bottom"] = "top",
        rng: GameRNG | None = None,
    ) -> None:
        """Insert a card into the draw pile at the given *position*.

        ``"random"`` requires an *rng* instance.
        """
        if position == "top":
            self.draw.insert(0, card)
        elif position == "bottom":
            self.draw.append(card)
        elif position == "random":
            if rng is None:
                raise ValueError("rng is required when position='random'")
            idx = rng.random_int(0, max(len(self.draw), 0))
            self.draw.insert(idx, card)
        else:
            raise ValueError(f"Invalid position: {position!r}")

    def shuffle_draw(self, rng: GameRNG) -> None:
        """Shuffle the draw pile in-place."""
        rng.shuffle(self.draw)

    # -- internal helpers ----------------------------------------------------

    def _remove_from_hand(self, card: CardInstance) -> None:
        """Remove a card from the hand by identity (``id`` field)."""
        for i, c in enumerate(self.hand):
            if c.id == card.id:
                self.hand.pop(i)
                return
        raise ValueError(
            f"Card {card.id!r} ({card.card_id}) not found in hand"
        )


# ---------------------------------------------------------------------------
# BattleState
# ---------------------------------------------------------------------------

class BattleState(BaseModel):
    """Full mutable state of a single combat encounter."""

    model_config = {"arbitrary_types_allowed": True}

    player: Player
    enemies: list[Enemy]
    card_piles: CardPiles = Field(default_factory=CardPiles)
    turn: int = 0
    rng: Any = Field(default=None, exclude=True)
    """Combat-specific RNG.  Excluded from serialization."""

    is_over: bool = False
    battle_result: str | None = None
    """``"win"`` or ``"loss"`` once the battle is over."""

    actions_this_turn: int = 0

    relics: list[str] = Field(default_factory=list)
    """Relic ids equipped for this combat."""

    potions: list[str | None] = Field(
        default_factory=lambda: [None, None, None]
    )
    """Potion belt (3 slots). ``None`` means empty."""

    # -- queries -------------------------------------------------------------

    @property
    def living_enemies(self) -> list[Enemy]:
        """Return the sub-list of enemies that are still alive."""
        return [e for e in self.enemies if not e.is_dead]

    @property
    def is_battle_won(self) -> bool:
        return all(e.is_dead for e in self.enemies)

    @property
    def is_battle_lost(self) -> bool:
        return self.player.is_dead

    # -- turn lifecycle ------------------------------------------------------

    def start_turn(self, energy: int | None = None, clear_block: bool = True) -> None:
        """Begin a new player turn.

        * Increments ``turn``.
        * Resets player block (unless *clear_block* is ``False``, e.g. Barricade).
        * Refills energy to ``max_energy`` (or a custom *energy* value).
        * Resets ``actions_this_turn``.
        """
        self.turn += 1
        if clear_block:
            self.player.clear_block()
        self.player.energy = (
            energy if energy is not None else self.player.max_energy
        )
        self.actions_this_turn = 0

    def end_turn(self) -> None:
        """Finalise the player turn.

        * Discards the hand.
        * Clears enemy block.
        * Checks win/loss conditions.
        """
        self.card_piles.discard_hand()

        for enemy in self.living_enemies:
            enemy.clear_block()

        self._check_battle_over()

    # -- internal ------------------------------------------------------------

    def _check_battle_over(self) -> None:
        if self.is_battle_won:
            self.is_over = True
            self.battle_result = "win"
        elif self.is_battle_lost:
            self.is_over = True
            self.battle_result = "loss"


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

class GameState(BaseModel):
    """Top-level state for an entire Slay the Spire run."""

    model_config = {"arbitrary_types_allowed": True}

    player: Player
    battle: BattleState | None = None
    floor: int = 0
    act: int = 1
    deck: list[CardInstance] = Field(default_factory=list)
    rng: Any = Field(default=None, exclude=True)
    """Master ``GameRNG`` for the run.  Excluded from serialization."""

    relics: list[str] = Field(default_factory=list)
    """List of relic identifiers the player has collected."""

    potions: list[str | None] = Field(
        default_factory=lambda: [None, None, None]
    )
    """Fixed-size potion belt (3 slots).  ``None`` means empty."""
