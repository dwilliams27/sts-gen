"""Tests for status effect mechanics -- apply, decay, query."""

import pytest

from sts_gen.sim.core.entities import Entity, Player
from sts_gen.sim.mechanics.status_effects import (
    apply_status,
    decay_statuses,
    get_status_stacks,
    has_status,
    remove_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entity(**kwargs) -> Entity:
    defaults = dict(name="Test", max_hp=50, current_hp=50)
    defaults.update(kwargs)
    return Entity(**defaults)


# ---------------------------------------------------------------------------
# apply_status -- creates new
# ---------------------------------------------------------------------------

class TestApplyStatusNew:
    def test_apply_new_status(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 2)

        assert entity.status_effects["vulnerable"] == 2

    def test_apply_multiple_different_statuses(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 2)
        apply_status(entity, "weak", 3)

        assert entity.status_effects["vulnerable"] == 2
        assert entity.status_effects["weak"] == 3


# ---------------------------------------------------------------------------
# apply_status -- stacks
# ---------------------------------------------------------------------------

class TestApplyStatusStacks:
    def test_stacks_add(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 2)
        apply_status(entity, "vulnerable", 3)

        assert entity.status_effects["vulnerable"] == 5

    def test_reduce_to_zero_removes(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 2)
        apply_status(entity, "vulnerable", -2)

        assert "vulnerable" not in entity.status_effects

    def test_reduce_below_zero_removes(self):
        entity = _make_entity()
        apply_status(entity, "weak", 1)
        apply_status(entity, "weak", -5)

        assert "weak" not in entity.status_effects


# ---------------------------------------------------------------------------
# decay_statuses -- built-in decay
# ---------------------------------------------------------------------------

class TestDecayStatuses:
    def test_vulnerable_decays(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 3)
        decay_statuses(entity)

        assert entity.status_effects["vulnerable"] == 2

    def test_weak_decays(self):
        entity = _make_entity()
        apply_status(entity, "weak", 1)
        decay_statuses(entity)

        assert "weak" not in entity.status_effects

    def test_frail_decays(self):
        entity = _make_entity()
        apply_status(entity, "frail", 2)
        decay_statuses(entity)

        assert entity.status_effects["frail"] == 1

    def test_decay_removes_at_zero(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 1)
        decay_statuses(entity)

        assert "vulnerable" not in entity.status_effects

    def test_multiple_decays(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 3)
        apply_status(entity, "weak", 2)

        decay_statuses(entity)  # vuln 2, weak 1
        decay_statuses(entity)  # vuln 1, weak removed
        decay_statuses(entity)  # vuln removed

        assert "vulnerable" not in entity.status_effects
        assert "weak" not in entity.status_effects


# ---------------------------------------------------------------------------
# strength persists (permanent)
# ---------------------------------------------------------------------------

class TestStrengthPersists:
    def test_strength_does_not_decay(self):
        entity = _make_entity()
        apply_status(entity, "strength", 3)
        decay_statuses(entity)

        # Strength is permanent -- should not lose stacks
        assert entity.status_effects["strength"] == 3

    def test_dexterity_does_not_decay(self):
        entity = _make_entity()
        apply_status(entity, "dexterity", 2)
        decay_statuses(entity)

        assert entity.status_effects["dexterity"] == 2

    def test_negative_strength_persists(self):
        """Strength can be negative (e.g., Strength Down debuff)."""
        entity = _make_entity()
        apply_status(entity, "strength", -2)

        assert entity.status_effects["strength"] == -2
        # Should not be removed by decay
        decay_statuses(entity)
        assert entity.status_effects["strength"] == -2


# ---------------------------------------------------------------------------
# has_status / get_status_stacks
# ---------------------------------------------------------------------------

class TestQueryFunctions:
    def test_has_status_present(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 2)

        assert has_status(entity, "vulnerable") is True

    def test_has_status_absent(self):
        entity = _make_entity()

        assert has_status(entity, "vulnerable") is False

    def test_has_status_after_removal(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 1)
        remove_status(entity, "vulnerable")

        assert has_status(entity, "vulnerable") is False

    def test_has_status_permanent_negative(self):
        """Negative strength is still 'present' because it is permanent."""
        entity = _make_entity()
        apply_status(entity, "strength", -3)

        assert has_status(entity, "strength") is True

    def test_get_status_stacks(self):
        entity = _make_entity()
        apply_status(entity, "vulnerable", 4)

        assert get_status_stacks(entity, "vulnerable") == 4

    def test_get_status_stacks_absent(self):
        entity = _make_entity()

        assert get_status_stacks(entity, "nonexistent") == 0

    def test_remove_status(self):
        entity = _make_entity()
        apply_status(entity, "weak", 3)
        remove_status(entity, "weak")

        assert has_status(entity, "weak") is False
        assert get_status_stacks(entity, "weak") == 0
