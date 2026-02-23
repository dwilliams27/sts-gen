"""Tests for CardPiles and BattleState."""

import pytest

from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(card_id: str) -> CardInstance:
    return CardInstance(card_id=card_id)


def _make_player(**kwargs) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(**kwargs) -> Enemy:
    defaults = dict(name="Jaw Worm", enemy_id="jaw_worm", max_hp=44, current_hp=44)
    defaults.update(kwargs)
    return Enemy(**defaults)


def _make_battle(
    draw_ids: list[str] | None = None,
    hand_ids: list[str] | None = None,
    enemies: list[Enemy] | None = None,
    seed: int = 42,
) -> BattleState:
    piles = CardPiles(
        draw=[_make_card(cid) for cid in (draw_ids or [])],
        hand=[_make_card(cid) for cid in (hand_ids or [])],
    )
    return BattleState(
        player=_make_player(),
        enemies=enemies or [_make_enemy()],
        card_piles=piles,
        rng=GameRNG(seed),
    )


# ---------------------------------------------------------------------------
# CardPiles -- draw_cards basic
# ---------------------------------------------------------------------------

class TestCardPilesDrawBasic:
    def test_draw_cards_from_draw_pile(self):
        rng = GameRNG(42)
        piles = CardPiles(
            draw=[_make_card("strike") for _ in range(5)],
        )
        drawn = piles.draw_cards(3, rng)

        assert len(drawn) == 3
        assert piles.hand_size == 3
        assert len(piles.draw) == 2

    def test_draw_fewer_than_requested(self):
        """If draw + discard < n, draw what is available."""
        rng = GameRNG(42)
        piles = CardPiles(
            draw=[_make_card("strike"), _make_card("defend")],
        )
        drawn = piles.draw_cards(5, rng)

        assert len(drawn) == 2
        assert piles.hand_size == 2
        assert len(piles.draw) == 0

    def test_draw_zero(self):
        rng = GameRNG(42)
        piles = CardPiles(
            draw=[_make_card("strike") for _ in range(5)],
        )
        drawn = piles.draw_cards(0, rng)

        assert len(drawn) == 0
        assert piles.hand_size == 0


# ---------------------------------------------------------------------------
# CardPiles -- draw_cards triggers reshuffle when draw empty
# ---------------------------------------------------------------------------

class TestCardPilesReshuffle:
    def test_reshuffle_when_draw_empty(self):
        rng = GameRNG(42)
        piles = CardPiles(
            draw=[_make_card("strike")],
            discard=[_make_card("defend") for _ in range(4)],
        )
        drawn = piles.draw_cards(3, rng)

        assert len(drawn) == 3
        assert piles.hand_size == 3
        # 1 from draw + 4 from reshuffled discard = 5 total, drew 3, so 2 remain in draw
        assert len(piles.draw) == 2
        assert len(piles.discard) == 0

    def test_reshuffle_exact_boundary(self):
        """Draw pile has exactly 0 cards, all are in discard."""
        rng = GameRNG(42)
        piles = CardPiles(
            draw=[],
            discard=[_make_card("strike") for _ in range(5)],
        )
        drawn = piles.draw_cards(2, rng)

        assert len(drawn) == 2
        assert len(piles.draw) == 3  # 5 reshuffled minus 2 drawn


# ---------------------------------------------------------------------------
# CardPiles -- discard_hand moves all cards
# ---------------------------------------------------------------------------

class TestCardPilesDiscardHand:
    def test_discard_hand(self):
        piles = CardPiles(
            hand=[_make_card("strike"), _make_card("defend"), _make_card("bash")],
            discard=[_make_card("strike")],
        )
        piles.discard_hand()

        assert piles.hand_size == 0
        assert len(piles.discard) == 4  # 1 original + 3 from hand

    def test_discard_empty_hand(self):
        piles = CardPiles(hand=[])
        piles.discard_hand()

        assert piles.hand_size == 0
        assert len(piles.discard) == 0


# ---------------------------------------------------------------------------
# BattleState -- start_turn resets energy and block
# ---------------------------------------------------------------------------

class TestBattleStateStartTurn:
    def test_start_turn_resets_energy(self):
        battle = _make_battle()
        battle.player.energy = 0
        battle.start_turn()

        assert battle.player.energy == 3  # max_energy
        assert battle.turn == 1

    def test_start_turn_clears_block(self):
        battle = _make_battle()
        battle.player.block = 15
        battle.start_turn()

        assert battle.player.block == 0

    def test_start_turn_custom_energy(self):
        battle = _make_battle()
        battle.start_turn(energy=5)

        assert battle.player.energy == 5

    def test_start_turn_increments_turn(self):
        battle = _make_battle()
        battle.start_turn()
        battle.start_turn()
        battle.start_turn()

        assert battle.turn == 3


# ---------------------------------------------------------------------------
# BattleState -- end_turn discards hand
# ---------------------------------------------------------------------------

class TestBattleStateEndTurn:
    def test_end_turn_discards_hand(self):
        battle = _make_battle(hand_ids=["strike", "defend", "bash"])
        battle.end_turn()

        assert battle.card_piles.hand_size == 0
        assert len(battle.card_piles.discard) == 3

    def test_end_turn_clears_enemy_block(self):
        battle = _make_battle()
        battle.enemies[0].block = 10
        battle.end_turn()

        assert battle.enemies[0].block == 0


# ---------------------------------------------------------------------------
# BattleState -- detects win/loss
# ---------------------------------------------------------------------------

class TestBattleStateWinLoss:
    def test_detect_win(self):
        battle = _make_battle()
        # Kill the enemy
        battle.enemies[0].current_hp = 0
        battle._check_battle_over()

        assert battle.is_over
        assert battle.battle_result == "win"

    def test_detect_loss(self):
        battle = _make_battle()
        battle.player.current_hp = 0
        battle._check_battle_over()

        assert battle.is_over
        assert battle.battle_result == "loss"

    def test_not_over(self):
        battle = _make_battle()
        battle._check_battle_over()

        assert not battle.is_over
        assert battle.battle_result is None

    def test_living_enemies(self):
        enemies = [
            _make_enemy(enemy_id="a", current_hp=10),
            _make_enemy(enemy_id="b", current_hp=0),
            _make_enemy(enemy_id="c", current_hp=5),
        ]
        battle = _make_battle(enemies=enemies)

        assert len(battle.living_enemies) == 2

    def test_win_with_multiple_enemies(self):
        enemies = [
            _make_enemy(enemy_id="a", current_hp=0),
            _make_enemy(enemy_id="b", current_hp=0),
        ]
        battle = _make_battle(enemies=enemies)
        battle._check_battle_over()

        assert battle.is_over
        assert battle.battle_result == "win"


# ---------------------------------------------------------------------------
# CardInstance
# ---------------------------------------------------------------------------

class TestCardInstance:
    def test_auto_generated_id(self):
        c1 = CardInstance(card_id="strike")
        c2 = CardInstance(card_id="strike")

        assert c1.id != c2.id
        assert c1.card_id == c2.card_id == "strike"

    def test_defaults(self):
        c = CardInstance(card_id="defend")
        assert c.upgraded is False
        assert c.cost_override is None
