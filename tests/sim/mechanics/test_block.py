"""Tests for block mechanics -- gain, clear, decay."""

import pytest

from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.mechanics.block import clear_block, decay_block, gain_block
from sts_gen.sim.mechanics.status_effects import apply_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(**kwargs) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(**kwargs) -> Enemy:
    defaults = dict(name="Jaw Worm", enemy_id="jaw_worm", max_hp=44, current_hp=44)
    defaults.update(kwargs)
    return Enemy(**defaults)


# ---------------------------------------------------------------------------
# gain_block -- basic
# ---------------------------------------------------------------------------

class TestGainBlockBasic:
    def test_gain_block(self):
        player = _make_player()
        gain_block(player, 5)

        assert player.block == 5

    def test_gain_block_stacks(self):
        player = _make_player()
        gain_block(player, 5)
        gain_block(player, 3)

        assert player.block == 8

    def test_gain_block_zero(self):
        player = _make_player()
        gain_block(player, 0)

        assert player.block == 0


# ---------------------------------------------------------------------------
# gain_block -- with dexterity
# ---------------------------------------------------------------------------

class TestGainBlockWithDexterity:
    def test_dexterity_adds_block(self):
        player = _make_player()
        apply_status(player, "dexterity", 2)
        gain_block(player, 5)

        # 5 base + 2 dexterity = 7
        assert player.block == 7

    def test_negative_dexterity_reduces_block(self):
        player = _make_player()
        apply_status(player, "dexterity", -3)
        gain_block(player, 5)

        # 5 base + (-3) dexterity = 2
        assert player.block == 2

    def test_dexterity_cannot_make_block_negative(self):
        """If dexterity is very negative, block should be floored at 0."""
        player = _make_player()
        apply_status(player, "dexterity", -10)
        gain_block(player, 5)

        assert player.block == 0


# ---------------------------------------------------------------------------
# gain_block -- with frail
# ---------------------------------------------------------------------------

class TestGainBlockWithFrail:
    def test_frail_reduces_block(self):
        player = _make_player()
        apply_status(player, "frail", 2)
        gain_block(player, 8)

        # floor(8 * 0.75) = 6
        assert player.block == 6

    def test_frail_and_dexterity_combined(self):
        """Dexterity is added before frail multiplier."""
        player = _make_player()
        apply_status(player, "dexterity", 2)
        apply_status(player, "frail", 1)
        gain_block(player, 5)

        # (5 + 2) * 0.75 = floor(5.25) = 5
        assert player.block == 5


# ---------------------------------------------------------------------------
# clear_block / decay_block
# ---------------------------------------------------------------------------

class TestClearAndDecayBlock:
    def test_clear_block(self):
        player = _make_player()
        player.block = 15
        clear_block(player)

        assert player.block == 0

    def test_decay_block_clears_all(self):
        player = _make_player()
        player.block = 20
        enemy = _make_enemy()
        enemy.block = 10

        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=GameRNG(42),
        )
        decay_block(battle)

        assert player.block == 0
        assert enemy.block == 0

    def test_decay_block_skips_dead_enemies(self):
        player = _make_player()
        enemy_alive = _make_enemy(enemy_id="a", current_hp=10)
        enemy_alive.block = 5
        enemy_dead = _make_enemy(enemy_id="b", current_hp=0)
        enemy_dead.block = 99

        battle = BattleState(
            player=player,
            enemies=[enemy_alive, enemy_dead],
            card_piles=CardPiles(),
            rng=GameRNG(42),
        )
        decay_block(battle)

        assert enemy_alive.block == 0
        # Dead enemy's block is not cleared (skipped)
        assert enemy_dead.block == 99
