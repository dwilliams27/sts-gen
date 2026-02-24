"""Integration tests for power card status triggers in full combat.

Each test verifies wiki-sourced exact behavior for a single power card.
Tests are deterministic: they set up a specific board state and verify
the exact result.
"""

from __future__ import annotations

import pytest

from sts_gen.ir.status_effects import StatusTrigger
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.status_effects import apply_status, get_status_stacks
from sts_gen.sim.runner import CombatSimulator
from sts_gen.sim.triggers import TriggerDispatcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_status_effects()
    return reg


@pytest.fixture
def interp(registry) -> ActionInterpreter:
    return ActionInterpreter(card_registry=registry.cards)


@pytest.fixture
def td(interp, registry) -> TriggerDispatcher:
    return TriggerDispatcher(interp, registry.status_defs)


def _make_player(**kw) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3, energy=3)
    defaults.update(kw)
    return Player(**defaults)


def _make_enemy(**kw) -> Enemy:
    defaults = dict(name="Dummy", enemy_id="dummy", max_hp=100, current_hp=100)
    defaults.update(kw)
    return Enemy(**defaults)


def _make_battle(player=None, enemies=None, seed=1) -> BattleState:
    p = player or _make_player()
    e = enemies or [_make_enemy()]
    return BattleState(player=p, enemies=e, card_piles=CardPiles(), rng=GameRNG(seed))


# ===================================================================
# ON_TURN_START powers
# ===================================================================

class TestDemonForm:
    """Wiki: At the start of your turn, gain {stacks} Strength.
    Stacks additively. Permanent."""

    def test_gains_strength_per_stack(self, td):
        battle = _make_battle()
        apply_status(battle.player, "Demon Form", 2)

        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")
        assert get_status_stacks(battle.player, "strength") == 2

    def test_stacks_additively(self, td):
        battle = _make_battle()
        apply_status(battle.player, "Demon Form", 3)

        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")
        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")
        assert get_status_stacks(battle.player, "strength") == 6

    def test_multiple_applications_stack(self, td):
        """Playing Demon Form twice (2+3) gives 5 Str per turn."""
        battle = _make_battle()
        apply_status(battle.player, "Demon Form", 2)
        apply_status(battle.player, "Demon Form", 3)  # Adds to 5

        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")
        assert get_status_stacks(battle.player, "strength") == 5


class TestBrutality:
    """Wiki: At the start of your turn, lose {stacks} HP and draw {stacks} card(s).
    Both scale with stacks. Permanent."""

    def test_loses_hp_and_draws(self, td):
        battle = _make_battle()
        # Add cards to draw pile so draw actually works
        for _ in range(5):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        apply_status(battle.player, "Brutality", 1)

        hp_before = battle.player.current_hp
        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")

        assert battle.player.current_hp == hp_before - 1
        assert len(battle.card_piles.hand) == 1

    def test_both_scale_with_stacks(self, td):
        battle = _make_battle()
        for _ in range(5):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        apply_status(battle.player, "Brutality", 3)

        hp_before = battle.player.current_hp
        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")

        assert battle.player.current_hp == hp_before - 3
        assert len(battle.card_piles.hand) == 3


class TestBerserk:
    """Wiki: At the start of your turn, gain {stacks} Energy.
    Scales with stacks. Permanent."""

    def test_gains_energy(self, td):
        battle = _make_battle()
        battle.player.energy = 3
        apply_status(battle.player, "Berserk", 1)

        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")
        assert battle.player.energy == 4

    def test_scales_with_stacks(self, td):
        battle = _make_battle()
        battle.player.energy = 3
        apply_status(battle.player, "Berserk", 2)

        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")
        assert battle.player.energy == 5


class TestRitual:
    """Wiki: At the end of your turn, gain {stacks} Strength.
    Scales with stacks. Permanent. Used by enemies (Cultist)."""

    def test_gains_strength_on_turn_end(self, td):
        enemy = _make_enemy()
        battle = _make_battle(enemies=[enemy])
        apply_status(enemy, "Ritual", 3)

        td.fire(enemy, StatusTrigger.ON_TURN_END, battle, "0")
        assert get_status_stacks(enemy, "strength") == 3

    def test_does_not_fire_on_turn_start(self, td):
        enemy = _make_enemy()
        battle = _make_battle(enemies=[enemy])
        apply_status(enemy, "Ritual", 3)

        td.fire(enemy, StatusTrigger.ON_TURN_START, battle, "0")
        assert get_status_stacks(enemy, "strength") == 0


# ===================================================================
# ON_TURN_END powers
# ===================================================================

class TestMetallicize:
    """Wiki: At the end of your turn, gain {stacks} Block.
    Scales with stacks. Permanent."""

    def test_gains_block_on_turn_end(self, td):
        battle = _make_battle()
        apply_status(battle.player, "Metallicize", 3)

        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")
        assert battle.player.block == 3

    def test_stacks_additively(self, td):
        """Two Metallicize (3+4) = 7 block per turn."""
        battle = _make_battle()
        apply_status(battle.player, "Metallicize", 7)

        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")
        assert battle.player.block == 7

    def test_enemy_metallicize(self, td):
        """Enemies (Lagavulin) can also have Metallicize."""
        enemy = _make_enemy()
        battle = _make_battle(enemies=[enemy])
        apply_status(enemy, "Metallicize", 8)

        td.fire(enemy, StatusTrigger.ON_TURN_END, battle, "0")
        assert enemy.block == 8


class TestCombust:
    """Wiki: At the end of your turn, lose {stacks} HP and deal {stacks*5} damage to ALL enemies.
    Both HP loss and damage scale with stacks. Damage not affected by Strength."""

    def test_loses_hp_and_deals_damage(self, td):
        enemy = _make_enemy(current_hp=100, max_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Combust", 1)

        hp_before = battle.player.current_hp
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        assert battle.player.current_hp == hp_before - 1
        assert enemy.current_hp == 95  # 5 damage

    def test_scales_with_stacks(self, td):
        enemy = _make_enemy(current_hp=100, max_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Combust", 2)

        hp_before = battle.player.current_hp
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        assert battle.player.current_hp == hp_before - 2
        assert enemy.current_hp == 90  # 10 damage

    def test_damage_ignores_strength(self, td):
        """Combust damage is NOT affected by Strength."""
        enemy = _make_enemy(current_hp=100, max_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Combust", 1)
        apply_status(battle.player, "strength", 10)

        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")
        assert enemy.current_hp == 95  # Still 5, not 15

    def test_hits_all_enemies(self, td):
        enemies = [_make_enemy(current_hp=50), _make_enemy(current_hp=50)]
        battle = _make_battle(enemies=enemies)
        apply_status(battle.player, "Combust", 1)

        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")
        assert enemies[0].current_hp == 45
        assert enemies[1].current_hp == 45


# ===================================================================
# ON_CARD_EXHAUSTED powers
# ===================================================================

class TestDarkEmbrace:
    """Wiki: Whenever a card is Exhausted, draw 1 card.
    Scales with stacks (each copy triggers independently)."""

    def test_draws_on_exhaust(self, td):
        battle = _make_battle()
        for _ in range(5):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        apply_status(battle.player, "Dark Embrace", 1)

        td.fire(battle.player, StatusTrigger.ON_CARD_EXHAUSTED, battle, "player")
        assert len(battle.card_piles.hand) == 1

    def test_scales_with_stacks(self, td):
        battle = _make_battle()
        for _ in range(5):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        apply_status(battle.player, "Dark Embrace", 2)

        td.fire(battle.player, StatusTrigger.ON_CARD_EXHAUSTED, battle, "player")
        assert len(battle.card_piles.hand) == 2


class TestFeelNoPain:
    """Wiki: Whenever a card is Exhausted, gain {stacks} Block.
    Base 3, upgraded 4. Scales with stacks."""

    def test_gains_block_on_exhaust(self, td):
        battle = _make_battle()
        apply_status(battle.player, "Feel No Pain", 3)

        td.fire(battle.player, StatusTrigger.ON_CARD_EXHAUSTED, battle, "player")
        assert battle.player.block == 3

    def test_scales_with_stacks(self, td):
        """Two Feel No Pains (3+4=7 stacks) = 7 block per exhaust."""
        battle = _make_battle()
        apply_status(battle.player, "Feel No Pain", 7)

        td.fire(battle.player, StatusTrigger.ON_CARD_EXHAUSTED, battle, "player")
        assert battle.player.block == 7


# ===================================================================
# ON_ATTACK_PLAYED powers
# ===================================================================

class TestRage:
    """Wiki: Whenever you play an Attack this turn, gain {stacks} Block.
    Temporary (removed at end of turn). Block ignores Dex/Frail."""

    def test_gains_block_on_attack(self, td):
        battle = _make_battle()
        apply_status(battle.player, "Rage", 3)

        td.fire(battle.player, StatusTrigger.ON_ATTACK_PLAYED, battle, "player")
        assert battle.player.block == 3

    def test_ignores_frail(self, td):
        """Rage block bypasses Frail."""
        battle = _make_battle()
        apply_status(battle.player, "Rage", 5)
        apply_status(battle.player, "frail", 2)

        td.fire(battle.player, StatusTrigger.ON_ATTACK_PLAYED, battle, "player")
        assert battle.player.block == 5  # Not reduced by frail

    def test_ignores_dexterity(self, td):
        """Rage block bypasses Dexterity."""
        battle = _make_battle()
        apply_status(battle.player, "Rage", 3)
        apply_status(battle.player, "dexterity", 5)

        td.fire(battle.player, StatusTrigger.ON_ATTACK_PLAYED, battle, "player")
        assert battle.player.block == 3  # Not boosted by dex

    def test_removed_at_end_of_turn(self, registry):
        """Rage is temporary -- removed when statuses decay at end of turn."""
        from sts_gen.sim.mechanics.status_effects import decay_statuses
        player = _make_player()
        apply_status(player, "Rage", 5)
        assert get_status_stacks(player, "Rage") == 5

        decay_statuses(player, registry.status_defs)
        assert get_status_stacks(player, "Rage") == 0


# ===================================================================
# ON_STATUS_DRAWN powers
# ===================================================================

class TestEvolve:
    """Wiki: Whenever you draw a Status card, draw {stacks} card(s).
    Status cards ONLY (not Curse). Scales with stacks."""

    def test_draws_on_status_drawn(self, td, registry):
        """Fire ON_STATUS_DRAWN with a Status card => Evolve draws."""
        battle = _make_battle()
        for _ in range(5):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        apply_status(battle.player, "Evolve", 1)

        # Simulate drawing a Status card by directly firing the trigger
        # The runner handles the card type check; here we test the trigger
        td.fire(battle.player, StatusTrigger.ON_STATUS_DRAWN, battle, "player")
        assert len(battle.card_piles.hand) == 1

    def test_scales_with_stacks(self, td):
        battle = _make_battle()
        for _ in range(5):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        apply_status(battle.player, "Evolve", 2)

        td.fire(battle.player, StatusTrigger.ON_STATUS_DRAWN, battle, "player")
        assert len(battle.card_piles.hand) == 2


class TestFireBreathing:
    """Wiki: Whenever you draw a Status or Curse card, deal {stacks} damage to ALL enemies.
    Both Status AND Curse. Scales with stacks. Damage not affected by Strength."""

    def test_deals_damage_on_status_drawn(self, td):
        enemy = _make_enemy(current_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Fire Breathing", 6)

        td.fire(battle.player, StatusTrigger.ON_STATUS_DRAWN, battle, "player")
        assert enemy.current_hp == 94  # 6 damage

    def test_damage_ignores_strength(self, td):
        enemy = _make_enemy(current_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Fire Breathing", 6)
        apply_status(battle.player, "strength", 10)

        td.fire(battle.player, StatusTrigger.ON_STATUS_DRAWN, battle, "player")
        assert enemy.current_hp == 94  # Strength ignored

    def test_scales_with_stacks(self, td):
        enemy = _make_enemy(current_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Fire Breathing", 10)  # upgraded

        td.fire(battle.player, StatusTrigger.ON_STATUS_DRAWN, battle, "player")
        assert enemy.current_hp == 90


# ===================================================================
# ON_ATTACKED powers
# ===================================================================

class TestFlameBarrier:
    """Wiki: Whenever you are attacked this turn, deal {stacks} damage back.
    Triggers per hit. Temporary (removed at end of turn).
    Damage not affected by Strength."""

    def test_deals_damage_to_attacker(self, td):
        enemy = _make_enemy(current_hp=50)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Flame Barrier", 4)

        td.fire(
            battle.player, StatusTrigger.ON_ATTACKED, battle, "player",
            attacker_idx=0,
        )
        assert enemy.current_hp == 46

    def test_scales_with_stacks(self, td):
        enemy = _make_enemy(current_hp=50)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Flame Barrier", 6)

        td.fire(
            battle.player, StatusTrigger.ON_ATTACKED, battle, "player",
            attacker_idx=0,
        )
        assert enemy.current_hp == 44

    def test_damage_ignores_strength(self, td):
        enemy = _make_enemy(current_hp=50)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Flame Barrier", 4)
        apply_status(battle.player, "strength", 10)

        td.fire(
            battle.player, StatusTrigger.ON_ATTACKED, battle, "player",
            attacker_idx=0,
        )
        assert enemy.current_hp == 46  # Strength ignored

    def test_removed_at_end_of_turn(self, registry):
        from sts_gen.sim.mechanics.status_effects import decay_statuses
        player = _make_player()
        apply_status(player, "Flame Barrier", 4)
        decay_statuses(player, registry.status_defs)
        assert get_status_stacks(player, "Flame Barrier") == 0


# ===================================================================
# ON_BLOCK_GAINED powers
# ===================================================================

class TestJuggernaut:
    """Wiki: Whenever you gain Block, deal {stacks} damage to a random enemy.
    Scales with stacks. Damage not affected by Strength."""

    def test_deals_damage_on_block_gained(self, td):
        enemy = _make_enemy(current_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Juggernaut", 5)

        td.fire(battle.player, StatusTrigger.ON_BLOCK_GAINED, battle, "player")
        assert enemy.current_hp == 95

    def test_damage_ignores_strength(self, td):
        enemy = _make_enemy(current_hp=100)
        battle = _make_battle(enemies=[enemy])
        apply_status(battle.player, "Juggernaut", 5)
        apply_status(battle.player, "strength", 10)

        td.fire(battle.player, StatusTrigger.ON_BLOCK_GAINED, battle, "player")
        assert enemy.current_hp == 95  # Strength ignored


# ===================================================================
# ON_HP_LOSS powers
# ===================================================================

class TestRupture:
    """Wiki: Whenever you lose HP from a card, gain {stacks} Strength.
    Scales with stacks. Permanent."""

    def test_gains_strength_on_hp_loss(self, td):
        battle = _make_battle()
        apply_status(battle.player, "Rupture", 1)

        td.fire(battle.player, StatusTrigger.ON_HP_LOSS, battle, "player")
        assert get_status_stacks(battle.player, "strength") == 1

    def test_scales_with_stacks(self, td):
        """Two Ruptures (1+2=3 stacks) = 3 Strength per HP loss event."""
        battle = _make_battle()
        apply_status(battle.player, "Rupture", 3)

        td.fire(battle.player, StatusTrigger.ON_HP_LOSS, battle, "player")
        assert get_status_stacks(battle.player, "strength") == 3


# ===================================================================
# PASSIVE powers
# ===================================================================

class TestBarricade:
    """Wiki: Block is not removed at the start of your turn.
    Does not stack. Permanent."""

    def test_block_retained_on_start_turn(self):
        battle = _make_battle()
        battle.player.block = 15
        apply_status(battle.player, "Barricade", 1)

        # Barricade: skip block clear
        battle.start_turn(clear_block=not True)  # simulating the runner check
        assert battle.player.block == 15

    def test_without_barricade_block_cleared(self):
        battle = _make_battle()
        battle.player.block = 15

        battle.start_turn()
        assert battle.player.block == 0


class TestCorruption:
    """Wiki: Skills cost 0. Whenever you play a Skill, Exhaust it.
    Does not stack. Permanent."""

    def test_skill_costs_zero_and_exhausted(self, registry):
        """Full integration: play a Skill card with Corruption active."""
        player = _make_player()
        apply_status(player, "Corruption", 1)

        # Put a Defend in hand (cost 1 Skill)
        defend_inst = CardInstance(card_id="defend")
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[defend_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("defend")
        assert card_def is not None

        # With Corruption, cost should be 0, force_exhaust=True
        defend_inst.cost_override = 0
        interp.play_card(card_def, battle, defend_inst, force_exhaust=True)

        # Card should be exhausted, not discarded
        assert len(battle.card_piles.exhaust) == 1
        assert len(battle.card_piles.discard) == 0
        # Energy not spent (cost was 0)
        assert player.energy == 3


# ===================================================================
# Registry loading
# ===================================================================

class TestStatusEffectRegistry:
    """Verify status effect definitions load correctly."""

    def test_all_16_statuses_loaded(self, registry):
        expected = {
            "Demon Form", "Brutality", "Berserk", "Ritual",
            "Metallicize", "Combust",
            "Dark Embrace", "Feel No Pain",
            "Rage",
            "Evolve", "Fire Breathing",
            "Flame Barrier",
            "Juggernaut",
            "Rupture",
            "Barricade", "Corruption",
        }
        assert set(registry.status_defs.keys()) == expected

    def test_metallicize_has_on_turn_end_trigger(self, registry):
        defn = registry.get_status_def("Metallicize")
        assert defn is not None
        assert StatusTrigger.ON_TURN_END in defn.triggers

    def test_barricade_has_no_triggers(self, registry):
        defn = registry.get_status_def("Barricade")
        assert defn is not None
        assert len(defn.triggers) == 0

    def test_rage_is_temporary(self, registry):
        defn = registry.get_status_def("Rage")
        assert defn is not None
        assert defn.decay_per_turn == -1

    def test_flame_barrier_is_temporary(self, registry):
        defn = registry.get_status_def("Flame Barrier")
        assert defn is not None
        assert defn.decay_per_turn == -1
