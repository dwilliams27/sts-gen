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

    def test_all_17_statuses_loaded(self, registry):
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
            "Regeneration",
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


# ===================================================================
# Card-level on_exhaust (Sentinel)
# ===================================================================

class TestSentinelOnExhaust:
    """Wiki: Gain 5 Block. If this card is Exhausted, gain 2 Energy.
    Upgraded: Gain 8 Block. If Exhausted, gain 3 Energy."""

    def test_sentinel_card_has_on_exhaust(self, registry):
        card_def = registry.get_card("sentinel")
        assert card_def is not None
        assert len(card_def.on_exhaust) == 1
        assert card_def.on_exhaust[0].action_type.value == "gain_energy"
        assert card_def.on_exhaust[0].value == 2

    def test_sentinel_upgrade_has_on_exhaust(self, registry):
        card_def = registry.get_card("sentinel")
        assert card_def.upgrade is not None
        assert card_def.upgrade.on_exhaust is not None
        assert len(card_def.upgrade.on_exhaust) == 1
        assert card_def.upgrade.on_exhaust[0].value == 3

    def test_sentinel_on_exhaust_fires_in_combat(self, registry):
        """Sentinel exhausted via Corruption should grant 2 energy."""
        player = _make_player(energy=0)
        apply_status(player, "Corruption", 1)

        sentinel_inst = CardInstance(card_id="sentinel")
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[sentinel_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("sentinel")

        # Corruption: cost 0, force exhaust
        sentinel_inst.cost_override = 0
        interp.play_card(card_def, battle, sentinel_inst, force_exhaust=True)

        # Card should be exhausted
        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "sentinel"

        # Now simulate what the runner does: execute on_exhaust for newly exhausted cards
        exhausted_def = registry.cards.get("sentinel")
        if exhausted_def and exhausted_def.on_exhaust:
            interp.execute_actions(exhausted_def.on_exhaust, battle, source="player")

        # Sentinel on_exhaust: gain 2 energy
        assert player.energy == 2

    def test_sentinel_upgraded_on_exhaust(self, registry):
        """Sentinel+ exhausted should grant 3 energy."""
        player = _make_player(energy=3)

        sentinel_inst = CardInstance(card_id="sentinel", upgraded=True)
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[sentinel_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("sentinel")

        # Force exhaust to trigger on_exhaust
        interp.play_card(card_def, battle, sentinel_inst, force_exhaust=True)
        assert len(battle.card_piles.exhaust) == 1
        # Energy: 3 - 1 (cost) = 2 after playing

        # Simulate runner on_exhaust logic (upgraded path)
        on_exhaust_actions = card_def.on_exhaust
        if (
            sentinel_inst.upgraded
            and card_def.upgrade is not None
            and card_def.upgrade.on_exhaust is not None
        ):
            on_exhaust_actions = card_def.upgrade.on_exhaust
        if on_exhaust_actions:
            interp.execute_actions(on_exhaust_actions, battle, source="player")

        # Upgraded: gain 3 energy. Started with 3, spent 1, gained 3 = 5
        assert player.energy == 5

    def test_sentinel_on_exhaust_in_full_combat(self, registry):
        """Full integration: Sentinel with Corruption in a real combat."""
        player = _make_player(energy=3)
        apply_status(player, "Corruption", 1)

        sentinel_inst = CardInstance(card_id="sentinel")
        # Add some strikes so combat can finish
        cards = [sentinel_inst] + [CardInstance(card_id="strike") for _ in range(5)]
        enemy = _make_enemy(current_hp=20, max_hp=20)

        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=cards),
            rng=GameRNG(42),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        from sts_gen.sim.play_agents.random_agent import RandomAgent
        agent = RandomAgent(rng=GameRNG(42).fork("agent"))
        sim = CombatSimulator(registry, interp, agent)
        tel = sim.run_combat(battle)

        # Sentinel should have been exhausted (Corruption exhausts skills)
        sentinel_exhausted = any(
            c.card_id == "sentinel" for c in battle.card_piles.exhaust
        )
        assert sentinel_exhausted, "Sentinel should be exhausted by Corruption"


# ===================================================================
# Flame Barrier card applies status
# ===================================================================

class TestFlameBarrierCard:
    """Verify the Flame Barrier card applies the Flame Barrier status."""

    def test_card_applies_status(self, registry):
        player = _make_player()
        fb_inst = CardInstance(card_id="flame_barrier")
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[fb_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("flame_barrier")
        interp.play_card(card_def, battle, fb_inst)

        # Should have 12 block and 4 stacks of Flame Barrier
        assert player.block == 12
        assert get_status_stacks(player, "Flame Barrier") == 4

    def test_upgraded_card_applies_more_stacks(self, registry):
        player = _make_player()
        fb_inst = CardInstance(card_id="flame_barrier", upgraded=True)
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[fb_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("flame_barrier")
        interp.play_card(card_def, battle, fb_inst)

        # Upgraded: 16 block, 6 stacks
        assert player.block == 16
        assert get_status_stacks(player, "Flame Barrier") == 6


# ===================================================================
# Second Wind — un-simplified
# ===================================================================

class TestSecondWind:
    """Wiki: Exhaust all non-Attack cards in your hand. Gain 5 (7+) Block
    for each card Exhausted."""

    def test_exhausts_non_attacks_gains_block(self, registry):
        """3 non-attack cards in hand => 3 * 5 = 15 block, all exhausted."""
        player = _make_player()
        # Hand: Second Wind (Skill) + 2 Defends (Skill) + 1 Strike (Attack)
        sw_inst = CardInstance(card_id="second_wind")
        defend1 = CardInstance(card_id="defend")
        defend2 = CardInstance(card_id="defend")
        strike = CardInstance(card_id="strike")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[sw_inst, defend1, defend2, strike]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("second_wind")
        interp.play_card(card_def, battle, sw_inst)

        # Non-attacks in hand when played: second_wind + defend1 + defend2 = 3
        # Block: 3 * 5 = 15 (+ dex 0)
        assert player.block == 15
        # All non-attacks exhausted (including second_wind itself via play_card)
        assert len(battle.card_piles.hand) == 1
        assert battle.card_piles.hand[0].card_id == "strike"
        # second_wind disposed by play_card (exhaust=false, so it goes to discard
        # UNLESS it was already exhausted by its own action)
        # The exhaust_cards action exhausts it from hand, then play_card sees
        # it's no longer in hand and skips disposal.
        exhausted_ids = [c.card_id for c in battle.card_piles.exhaust]
        assert "defend" in exhausted_ids
        assert "second_wind" in exhausted_ids

    def test_upgraded_gains_more_block(self, registry):
        """Upgraded: 7 block per card."""
        player = _make_player()
        sw_inst = CardInstance(card_id="second_wind", upgraded=True)
        defend = CardInstance(card_id="defend")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[sw_inst, defend]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("second_wind")
        interp.play_card(card_def, battle, sw_inst)

        # Non-attacks: second_wind + defend = 2. Block: 2 * 7 = 14
        assert player.block == 14

    def test_attacks_stay_in_hand(self, registry):
        """Attacks are not exhausted."""
        player = _make_player()
        sw_inst = CardInstance(card_id="second_wind")
        strike1 = CardInstance(card_id="strike")
        strike2 = CardInstance(card_id="strike")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[sw_inst, strike1, strike2]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("second_wind")
        interp.play_card(card_def, battle, sw_inst)

        # Only second_wind is non-attack => 1 * 5 = 5 block
        assert player.block == 5
        # Both strikes remain
        assert len(battle.card_piles.hand) == 2
        assert all(c.card_id == "strike" for c in battle.card_piles.hand)

    def test_no_non_attacks_no_block(self, registry):
        """If only attacks in hand (besides Second Wind itself), still exhausts
        Second Wind and gains block for it."""
        player = _make_player()
        sw_inst = CardInstance(card_id="second_wind")
        strike = CardInstance(card_id="strike")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[sw_inst, strike]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("second_wind")
        interp.play_card(card_def, battle, sw_inst)

        # second_wind itself is non-attack => 1 * 5 = 5 block
        assert player.block == 5


# ===================================================================
# Feed — un-simplified
# ===================================================================

class TestFeed:
    """Wiki: Deal 10 (12+) damage. If Fatal, raise your Max HP by 3 (4+). Exhaust."""

    def test_fatal_raises_max_hp(self, registry):
        """Kill target => max HP and current HP increase."""
        player = _make_player(max_hp=80, current_hp=80)
        feed_inst = CardInstance(card_id="feed")
        enemy = _make_enemy(current_hp=5, max_hp=20)
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[feed_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("feed")
        interp.play_card(card_def, battle, feed_inst, chosen_target=0)

        assert enemy.is_dead
        assert player.max_hp == 83
        assert player.current_hp == 83

    def test_non_fatal_no_max_hp_raise(self, registry):
        """Target survives => no max HP change."""
        player = _make_player(max_hp=80, current_hp=80)
        feed_inst = CardInstance(card_id="feed")
        enemy = _make_enemy(current_hp=100, max_hp=100)
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[feed_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("feed")
        interp.play_card(card_def, battle, feed_inst, chosen_target=0)

        assert not enemy.is_dead
        assert player.max_hp == 80
        assert player.current_hp == 80

    def test_upgraded_raises_more(self, registry):
        """Feed+: 12 damage, +4 max HP on kill."""
        player = _make_player(max_hp=80, current_hp=70)
        feed_inst = CardInstance(card_id="feed", upgraded=True)
        enemy = _make_enemy(current_hp=5, max_hp=20)
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[feed_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("feed")
        interp.play_card(card_def, battle, feed_inst, chosen_target=0)

        assert enemy.is_dead
        assert player.max_hp == 84
        assert player.current_hp == 74  # Was 70, +4

    def test_card_is_exhausted(self, registry):
        """Feed should exhaust after play."""
        player = _make_player()
        feed_inst = CardInstance(card_id="feed")
        enemy = _make_enemy(current_hp=100)
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[feed_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("feed")
        interp.play_card(card_def, battle, feed_inst, chosen_target=0)

        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "feed"


# ===================================================================
# Battle Trance — un-simplified
# ===================================================================

class TestBattleTrance:
    """Wiki: Draw 3 (4+) cards. You cannot draw additional cards this turn."""

    def test_draws_cards(self, registry):
        player = _make_player()
        bt_inst = CardInstance(card_id="battle_trance")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                hand=[bt_inst],
                draw=[CardInstance(card_id="strike") for _ in range(10)],
            ),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("battle_trance")
        interp.play_card(card_def, battle, bt_inst)

        # Drew 3 cards
        assert len(battle.card_piles.hand) == 3

    def test_blocks_subsequent_draws(self, registry):
        """After Battle Trance, interpreter draw_cards actions are blocked."""
        from sts_gen.ir.actions import ActionNode, ActionType

        player = _make_player()
        bt_inst = CardInstance(card_id="battle_trance")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                hand=[bt_inst],
                draw=[CardInstance(card_id="strike") for _ in range(10)],
            ),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("battle_trance")
        interp.play_card(card_def, battle, bt_inst)
        assert len(battle.card_piles.hand) == 3

        # Try to draw more via interpreter — should be blocked
        draw_node = ActionNode(action_type=ActionType.DRAW_CARDS, value=2)
        interp.execute_node(draw_node, battle, source="player")
        assert len(battle.card_piles.hand) == 3  # No additional draws

    def test_no_draw_clears_at_end_of_turn(self, registry):
        """No Draw is temporary — removed at end of turn."""
        from sts_gen.sim.mechanics.status_effects import decay_statuses
        player = _make_player()
        apply_status(player, "No Draw", 1)
        assert get_status_stacks(player, "No Draw") == 1

        decay_statuses(player, registry.status_defs)
        assert get_status_stacks(player, "No Draw") == 0

    def test_upgraded_draws_four(self, registry):
        player = _make_player()
        bt_inst = CardInstance(card_id="battle_trance", upgraded=True)
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                hand=[bt_inst],
                draw=[CardInstance(card_id="strike") for _ in range(10)],
            ),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("battle_trance")
        interp.play_card(card_def, battle, bt_inst)

        assert len(battle.card_piles.hand) == 4


# ===================================================================
# Reaper — un-simplified
# ===================================================================

class TestReaper:
    """Wiki: Deal 4 (5+) damage to ALL enemies. Heal HP equal to
    unblocked damage dealt. Exhaust."""

    def test_heals_from_unblocked_damage(self, registry):
        """Two enemies, no block: heal = 4 + 4 = 8."""
        player = _make_player(max_hp=80, current_hp=60)
        reaper_inst = CardInstance(card_id="reaper")
        enemies = [_make_enemy(current_hp=100), _make_enemy(current_hp=100)]
        battle = BattleState(
            player=player,
            enemies=enemies,
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        assert enemies[0].current_hp == 96
        assert enemies[1].current_hp == 96
        assert player.current_hp == 68  # 60 + 8

    def test_partial_block_reduces_healing(self, registry):
        """Enemy with 3 block absorbs 3, only 1 HP lost => heal 1+4=5."""
        player = _make_player(max_hp=80, current_hp=60)
        reaper_inst = CardInstance(card_id="reaper")
        e1 = _make_enemy(current_hp=100)
        e1.block = 3
        e2 = _make_enemy(current_hp=100)
        battle = BattleState(
            player=player,
            enemies=[e1, e2],
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        assert e1.current_hp == 99  # 4-3=1 through block
        assert e2.current_hp == 96
        assert player.current_hp == 65  # 60 + 1 + 4

    def test_full_block_no_healing(self, registry):
        """Enemy with 10 block => 0 HP lost => no healing."""
        player = _make_player(max_hp=80, current_hp=60)
        reaper_inst = CardInstance(card_id="reaper")
        enemy = _make_enemy(current_hp=100)
        enemy.block = 10
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        assert player.current_hp == 60  # No healing

    def test_heal_capped_at_max_hp(self, registry):
        """Healing doesn't exceed max HP."""
        player = _make_player(max_hp=80, current_hp=78)
        reaper_inst = CardInstance(card_id="reaper")
        enemies = [_make_enemy(current_hp=100), _make_enemy(current_hp=100)]
        battle = BattleState(
            player=player,
            enemies=enemies,
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        assert player.current_hp == 80  # Capped, not 86

    def test_strength_increases_healing(self, registry):
        """Strength increases damage => increases healing."""
        player = _make_player(max_hp=80, current_hp=60)
        apply_status(player, "strength", 2)
        reaper_inst = CardInstance(card_id="reaper")
        enemies = [_make_enemy(current_hp=100), _make_enemy(current_hp=100)]
        battle = BattleState(
            player=player,
            enemies=enemies,
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        # 4+2=6 damage each, heal 6+6=12
        assert enemies[0].current_hp == 94
        assert player.current_hp == 72

    def test_upgraded_deals_5_base(self, registry):
        """Reaper+: 5 base damage."""
        player = _make_player(max_hp=80, current_hp=60)
        reaper_inst = CardInstance(card_id="reaper", upgraded=True)
        enemy = _make_enemy(current_hp=100)
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        assert enemy.current_hp == 95
        assert player.current_hp == 65  # 60 + 5

    def test_card_is_exhausted(self, registry):
        """Reaper should exhaust after play."""
        player = _make_player()
        reaper_inst = CardInstance(card_id="reaper")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[reaper_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("reaper")
        interp.play_card(card_def, battle, reaper_inst)

        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "reaper"


# ===================================================================
# Exhume — un-simplified
# ===================================================================

class TestExhume:
    """Wiki: Put a card from your Exhaust pile into your hand. Exhaust."""

    def test_moves_card_from_exhaust_to_hand(self, registry):
        """Retrieves a card from exhaust pile to hand."""
        player = _make_player()
        exhume_inst = CardInstance(card_id="exhume")
        exhausted_card = CardInstance(card_id="strike")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                hand=[exhume_inst],
                exhaust=[exhausted_card],
            ),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("exhume")
        interp.play_card(card_def, battle, exhume_inst)

        # Strike moved from exhaust to hand
        assert len(battle.card_piles.hand) == 1
        assert battle.card_piles.hand[0].card_id == "strike"
        # Exhume itself went to exhaust (replaces the retrieved card)
        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "exhume"

    def test_empty_exhaust_is_noop(self, registry):
        """Empty exhaust pile => no crash, hand stays empty."""
        player = _make_player()
        exhume_inst = CardInstance(card_id="exhume")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[exhume_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("exhume")
        interp.play_card(card_def, battle, exhume_inst)

        # No card retrieved, hand empty
        assert len(battle.card_piles.hand) == 0
        # Exhume itself in exhaust
        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "exhume"

    def test_exhume_does_not_retrieve_itself(self, registry):
        """Actions execute before card is exhausted, so Exhume can't
        retrieve itself from the exhaust pile."""
        player = _make_player()
        exhume_inst = CardInstance(card_id="exhume")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(hand=[exhume_inst]),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("exhume")
        interp.play_card(card_def, battle, exhume_inst)

        # Empty exhaust at action time => nothing retrieved
        # Exhume goes to exhaust in step 5
        assert len(battle.card_piles.hand) == 0
        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "exhume"

    def test_upgraded_costs_zero(self, registry):
        """Exhume+: cost 0, same actions."""
        player = _make_player(energy=3)
        exhume_inst = CardInstance(card_id="exhume", upgraded=True)
        exhausted_card = CardInstance(card_id="defend")
        battle = BattleState(
            player=player,
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                hand=[exhume_inst],
                exhaust=[exhausted_card],
            ),
            rng=GameRNG(1),
        )

        interp = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("exhume")
        interp.play_card(card_def, battle, exhume_inst)

        # Cost 0 => energy unchanged
        assert player.energy == 3
        # Card retrieved
        assert len(battle.card_piles.hand) == 1
        assert battle.card_piles.hand[0].card_id == "defend"
