"""Tests for Entity, Player, and Enemy models."""

import pytest

from sts_gen.sim.core.entities import Enemy, Entity, Player


# ---------------------------------------------------------------------------
# Entity -- take_damage with block
# ---------------------------------------------------------------------------

class TestEntityTakeDamageWithBlock:
    def test_damage_fully_blocked(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50, block=10)
        hp_lost = entity.take_damage(5)

        assert hp_lost == 0
        assert entity.block == 5
        assert entity.current_hp == 50

    def test_damage_partially_blocked(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50, block=3)
        hp_lost = entity.take_damage(8)

        assert hp_lost == 5
        assert entity.block == 0
        assert entity.current_hp == 45

    def test_damage_exactly_matches_block(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50, block=7)
        hp_lost = entity.take_damage(7)

        assert hp_lost == 0
        assert entity.block == 0
        assert entity.current_hp == 50


# ---------------------------------------------------------------------------
# Entity -- take_damage without block
# ---------------------------------------------------------------------------

class TestEntityTakeDamageWithoutBlock:
    def test_direct_damage(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        hp_lost = entity.take_damage(10)

        assert hp_lost == 10
        assert entity.current_hp == 40

    def test_damage_exceeding_hp(self):
        entity = Entity(name="Test", max_hp=50, current_hp=5)
        hp_lost = entity.take_damage(20)

        # HP lost is capped at current_hp
        assert hp_lost == 5
        assert entity.current_hp == 0
        assert entity.is_dead

    def test_zero_damage(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        hp_lost = entity.take_damage(0)

        assert hp_lost == 0
        assert entity.current_hp == 50

    def test_negative_damage(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        hp_lost = entity.take_damage(-5)

        assert hp_lost == 0
        assert entity.current_hp == 50


# ---------------------------------------------------------------------------
# Entity -- heal
# ---------------------------------------------------------------------------

class TestEntityHeal:
    def test_heal_caps_at_max_hp(self):
        entity = Entity(name="Test", max_hp=50, current_hp=40)
        entity.heal(20)

        assert entity.current_hp == 50

    def test_heal_partial(self):
        entity = Entity(name="Test", max_hp=50, current_hp=30)
        entity.heal(10)

        assert entity.current_hp == 40

    def test_heal_zero(self):
        entity = Entity(name="Test", max_hp=50, current_hp=30)
        entity.heal(0)

        assert entity.current_hp == 30

    def test_heal_negative_is_noop(self):
        entity = Entity(name="Test", max_hp=50, current_hp=30)
        entity.heal(-5)

        assert entity.current_hp == 30


# ---------------------------------------------------------------------------
# Entity -- is_dead
# ---------------------------------------------------------------------------

class TestEntityIsDead:
    def test_alive(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        assert not entity.is_dead

    def test_dead_at_zero(self):
        entity = Entity(name="Test", max_hp=50, current_hp=0)
        assert entity.is_dead

    def test_dead_after_damage(self):
        entity = Entity(name="Test", max_hp=50, current_hp=5)
        entity.take_damage(10)
        assert entity.is_dead


# ---------------------------------------------------------------------------
# Entity -- status effects
# ---------------------------------------------------------------------------

class TestEntityStatusEffects:
    def test_apply_status(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        entity.apply_status("vulnerable", 2)

        assert entity.get_status("vulnerable") == 2

    def test_apply_status_stacks(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        entity.apply_status("vulnerable", 2)
        entity.apply_status("vulnerable", 3)

        assert entity.get_status("vulnerable") == 5

    def test_apply_status_negative_removes(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        entity.apply_status("vulnerable", 2)
        entity.apply_status("vulnerable", -3)

        # Total would be -1, so it gets removed
        assert entity.get_status("vulnerable") == 0
        assert "vulnerable" not in entity.status_effects

    def test_get_status_absent(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        assert entity.get_status("nonexistent") == 0

    def test_remove_status(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        entity.apply_status("weak", 3)
        entity.remove_status("weak")

        assert entity.get_status("weak") == 0
        assert "weak" not in entity.status_effects

    def test_remove_status_absent_is_noop(self):
        entity = Entity(name="Test", max_hp=50, current_hp=50)
        # Should not raise
        entity.remove_status("nonexistent")


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class TestPlayer:
    def test_energy_defaults(self):
        player = Player(name="Ironclad", max_hp=80, current_hp=80)
        assert player.energy == 0
        assert player.max_energy == 3

    def test_energy_custom(self):
        player = Player(name="Ironclad", max_hp=80, current_hp=80, energy=2, max_energy=4)
        assert player.energy == 2
        assert player.max_energy == 4

    def test_player_has_strength_and_dexterity(self):
        player = Player(name="Ironclad", max_hp=80, current_hp=80)
        assert player.strength == 0
        assert player.dexterity == 0

    def test_player_gold(self):
        player = Player(name="Ironclad", max_hp=80, current_hp=80, gold=99)
        assert player.gold == 99

    def test_player_inherits_entity(self):
        player = Player(name="Ironclad", max_hp=80, current_hp=80)
        player.take_damage(10)
        assert player.current_hp == 70


# ---------------------------------------------------------------------------
# Enemy
# ---------------------------------------------------------------------------

class TestEnemy:
    def test_enemy_fields(self):
        enemy = Enemy(
            name="Jaw Worm",
            enemy_id="jaw_worm",
            max_hp=44,
            current_hp=44,
        )
        assert enemy.enemy_id == "jaw_worm"
        assert enemy.strength == 0
        assert enemy.intent is None
        assert enemy.intent_damage is None
        assert enemy.intent_hits is None

    def test_enemy_intent(self):
        enemy = Enemy(
            name="Jaw Worm",
            enemy_id="jaw_worm",
            max_hp=44,
            current_hp=44,
            intent="Chomp",
            intent_damage=11,
            intent_hits=1,
        )
        assert enemy.intent == "Chomp"
        assert enemy.intent_damage == 11
        assert enemy.intent_hits == 1

    def test_enemy_inherits_entity(self):
        enemy = Enemy(
            name="Test",
            enemy_id="test",
            max_hp=30,
            current_hp=30,
        )
        enemy.take_damage(30)
        assert enemy.is_dead
