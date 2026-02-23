"""Tests for damage calculation and application."""

import pytest

from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.mechanics.damage import calculate_damage, deal_damage
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


def _make_battle(
    player: Player | None = None,
    enemies: list[Enemy] | None = None,
) -> BattleState:
    return BattleState(
        player=player or _make_player(),
        enemies=enemies or [_make_enemy()],
        card_piles=CardPiles(),
        rng=GameRNG(42),
    )


# ---------------------------------------------------------------------------
# calculate_damage -- base
# ---------------------------------------------------------------------------

class TestCalculateDamageBase:
    def test_base_damage(self):
        source = _make_player()
        target = _make_enemy()
        result = calculate_damage(6, source, target)
        assert result == 6

    def test_zero_base_damage(self):
        source = _make_player()
        target = _make_enemy()
        result = calculate_damage(0, source, target)
        assert result == 0


# ---------------------------------------------------------------------------
# calculate_damage -- strength
# ---------------------------------------------------------------------------

class TestCalculateDamageStrength:
    def test_strength_adds_to_damage(self):
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "strength", 3)

        result = calculate_damage(6, source, target)
        assert result == 9  # 6 + 3

    def test_negative_strength(self):
        """Negative strength reduces damage but floors at 0."""
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "strength", -10)

        result = calculate_damage(6, source, target)
        assert result == 0  # max(0, 6 + (-10)) = 0


# ---------------------------------------------------------------------------
# calculate_damage -- vulnerable
# ---------------------------------------------------------------------------

class TestCalculateDamageVulnerable:
    def test_vulnerable_multiplier(self):
        source = _make_player()
        target = _make_enemy()
        apply_status(target, "vulnerable", 2)

        result = calculate_damage(6, source, target)
        assert result == 9  # floor(6 * 1.5) = 9

    def test_vulnerable_rounds_down(self):
        """Vulnerable on 5 damage: floor(5 * 1.5) = 7."""
        source = _make_player()
        target = _make_enemy()
        apply_status(target, "vulnerable", 1)

        result = calculate_damage(5, source, target)
        assert result == 7  # floor(7.5) = 7


# ---------------------------------------------------------------------------
# calculate_damage -- weak
# ---------------------------------------------------------------------------

class TestCalculateDamageWeak:
    def test_weak_multiplier(self):
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "weak", 2)

        result = calculate_damage(6, source, target)
        assert result == 4  # floor(6 * 0.75) = 4

    def test_weak_rounds_down(self):
        """Weak on 5 damage: floor(5 * 0.75) = 3."""
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "weak", 1)

        result = calculate_damage(5, source, target)
        assert result == 3  # floor(3.75) = 3


# ---------------------------------------------------------------------------
# calculate_damage -- combined
# ---------------------------------------------------------------------------

class TestCalculateDamageCombined:
    def test_strength_and_vulnerable(self):
        """6 base + 3 str = 9, then vuln: floor(9 * 1.5) = 13."""
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "strength", 3)
        apply_status(target, "vulnerable", 2)

        result = calculate_damage(6, source, target)
        assert result == 13

    def test_strength_and_weak(self):
        """6 base + 3 str = 9, then weak: floor(9 * 0.75) = 6."""
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "strength", 3)
        apply_status(source, "weak", 2)

        result = calculate_damage(6, source, target)
        assert result == 6

    def test_strength_vulnerable_and_weak(self):
        """6 base + 3 str = 9, vuln: floor(9 * 1.5) = 13, weak: floor(13 * 0.75) = 9."""
        source = _make_player()
        target = _make_enemy()
        apply_status(source, "strength", 3)
        apply_status(target, "vulnerable", 2)
        apply_status(source, "weak", 2)

        result = calculate_damage(6, source, target)
        assert result == 9  # floor(floor(9 * 1.5) * 0.75) = floor(13 * 0.75) = 9


# ---------------------------------------------------------------------------
# deal_damage -- multi-hit
# ---------------------------------------------------------------------------

class TestDealDamageMultiHit:
    def test_single_hit(self):
        battle = _make_battle()
        hp_lost = deal_damage(battle, "player", 0, 6, hits=1)

        assert hp_lost == 6
        assert battle.enemies[0].current_hp == 38  # 44 - 6

    def test_multi_hit(self):
        battle = _make_battle()
        hp_lost = deal_damage(battle, "player", 0, 3, hits=3)

        # 3 hits of 3 = 9 total
        assert hp_lost == 9
        assert battle.enemies[0].current_hp == 35  # 44 - 9

    def test_multi_hit_enemy_dies_mid_sequence(self):
        """If enemy dies during multi-hit, remaining hits are skipped."""
        enemy = _make_enemy(max_hp=10, current_hp=10)
        battle = _make_battle(enemies=[enemy])

        hp_lost = deal_damage(battle, "player", 0, 6, hits=5)

        # 2 hits of 6 = 12 but capped at 10 HP
        assert hp_lost == 10
        assert battle.enemies[0].current_hp == 0
        assert battle.enemies[0].is_dead


# ---------------------------------------------------------------------------
# deal_damage -- with block
# ---------------------------------------------------------------------------

class TestDealDamageWithBlock:
    def test_block_absorbs_damage(self):
        battle = _make_battle()
        battle.enemies[0].block = 10
        hp_lost = deal_damage(battle, "player", 0, 6, hits=1)

        assert hp_lost == 0
        assert battle.enemies[0].block == 4
        assert battle.enemies[0].current_hp == 44

    def test_block_partially_absorbs(self):
        battle = _make_battle()
        battle.enemies[0].block = 3
        hp_lost = deal_damage(battle, "player", 0, 8, hits=1)

        assert hp_lost == 5
        assert battle.enemies[0].block == 0
        assert battle.enemies[0].current_hp == 39  # 44 - 5

    def test_multi_hit_with_block(self):
        """Block is consumed across hits (not per-hit block)."""
        battle = _make_battle()
        battle.enemies[0].block = 5
        hp_lost = deal_damage(battle, "player", 0, 4, hits=3)

        # Hit 1: 4 dmg vs 5 block -> 1 block remains, 0 HP lost
        # Hit 2: 4 dmg vs 1 block -> 0 block remains, 3 HP lost
        # Hit 3: 4 dmg vs 0 block -> 4 HP lost
        assert hp_lost == 7
        assert battle.enemies[0].block == 0
        assert battle.enemies[0].current_hp == 37  # 44 - 7
