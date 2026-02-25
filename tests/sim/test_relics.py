"""Tests for Phase 2E relic system: RelicDispatcher, relic data loading, and integration."""

from __future__ import annotations

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import CardDefinition, CardRarity, CardTarget, CardType
from sts_gen.ir.relics import RelicDefinition, RelicTier
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.status_effects import get_status_stacks
from sts_gen.sim.play_agents.base import PlayAgent
from sts_gen.sim.relic_dispatcher import RelicDispatcher
from sts_gen.sim.runner import CombatSimulator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    return reg


@pytest.fixture
def battle():
    """A simple battle with a player and one enemy."""
    rng = GameRNG(seed=42)
    player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
    enemy = Enemy(name="Cultist", enemy_id="cultist", max_hp=50, current_hp=50)
    return BattleState(
        player=player,
        enemies=[enemy],
        rng=rng,
        card_piles=CardPiles(),
    )


@pytest.fixture
def interpreter():
    return ActionInterpreter()


# ---------------------------------------------------------------------------
# Relic data loading
# ---------------------------------------------------------------------------

class TestRelicLoading:
    def test_load_vanilla_relics(self, registry):
        assert len(registry.relics) == 14

    def test_burning_blood_loaded(self, registry):
        relic = registry.get_relic("burning_blood")
        assert relic is not None
        assert relic.name == "Burning Blood"
        assert relic.tier == RelicTier.STARTER
        assert relic.trigger == "on_combat_end"

    def test_vajra_loaded(self, registry):
        relic = registry.get_relic("vajra")
        assert relic is not None
        assert relic.tier == RelicTier.COMMON
        assert relic.trigger == "on_combat_start"

    def test_shuriken_loaded(self, registry):
        relic = registry.get_relic("shuriken")
        assert relic is not None
        assert relic.counter == 3
        assert relic.counter_per_turn is True

    def test_nunchaku_loaded(self, registry):
        relic = registry.get_relic("nunchaku")
        assert relic is not None
        assert relic.counter == 10
        assert relic.counter_per_turn is False

    def test_get_nonexistent_relic(self, registry):
        assert registry.get_relic("does_not_exist") is None


# ---------------------------------------------------------------------------
# RelicDispatcher unit tests
# ---------------------------------------------------------------------------

class TestRelicDispatcher:
    def test_fire_matching_trigger(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["vajra"]

        rd.fire("on_combat_start", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 1

    def test_fire_non_matching_trigger(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["vajra"]

        rd.fire("on_turn_end", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 0

    def test_counter_relic_increments(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["nunchaku"]

        # Fire 9 times -- should not trigger yet
        for _ in range(9):
            rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.energy == 0

        # 10th time triggers
        rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.energy == 1

    def test_counter_resets_after_trigger(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["nunchaku"]

        # Trigger at 10
        for _ in range(10):
            rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.energy == 1

        # Need another 10 to trigger again
        for _ in range(9):
            rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.energy == 1

        rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.energy == 2

    def test_per_turn_counter_reset(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["shuriken"]

        # Play 2 attacks (not enough to trigger)
        rd.fire("on_attack_played", battle, battle.relics)
        rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 0

        # Reset turn counters
        rd.reset_turn_counters()

        # Counter is back to 0, need another 3
        rd.fire("on_attack_played", battle, battle.relics)
        rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 0

        rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 1

    def test_reset_counters(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["nunchaku"]

        for _ in range(5):
            rd.fire("on_attack_played", battle, battle.relics)

        rd.reset_counters()

        # After reset, need full 10 again
        for _ in range(9):
            rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.energy == 0

    def test_attacker_resolution(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["bronze_scales"]

        enemy_hp_before = battle.enemies[0].current_hp
        rd.fire("on_attacked", battle, battle.relics, attacker_idx=0)
        assert battle.enemies[0].current_hp == enemy_hp_before - 3


# ---------------------------------------------------------------------------
# Individual relic behavior tests
# ---------------------------------------------------------------------------

class TestBurningBlood:
    def test_heal_on_combat_end(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["burning_blood"]
        battle.player.current_hp = 60

        rd.fire("on_combat_end", battle, battle.relics)
        assert battle.player.current_hp == 66


class TestAnchor:
    def test_gain_block_on_combat_start(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["anchor"]

        rd.fire("on_combat_start", battle, battle.relics)
        assert battle.player.block == 10


class TestOddlySmoothStone:
    def test_gain_dexterity_on_combat_start(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["oddly_smooth_stone"]

        rd.fire("on_combat_start", battle, battle.relics)
        assert get_status_stacks(battle.player, "dexterity") == 1


class TestBagOfPreparation:
    def test_draw_extra_on_turn_1(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["bag_of_preparation"]

        # Add cards to draw pile
        for i in range(10):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))

        battle.turn = 1
        rd.fire("on_turn_start", battle, battle.relics)
        assert len(battle.card_piles.hand) == 2

    def test_no_draw_on_turn_2(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["bag_of_preparation"]

        for i in range(10):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))

        battle.turn = 2
        rd.fire("on_turn_start", battle, battle.relics)
        assert len(battle.card_piles.hand) == 0


class TestLantern:
    def test_gain_energy_on_turn_1(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["lantern"]

        battle.turn = 1
        rd.fire("on_turn_start", battle, battle.relics)
        assert battle.player.energy == 1

    def test_no_energy_on_turn_2(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["lantern"]

        battle.turn = 2
        rd.fire("on_turn_start", battle, battle.relics)
        assert battle.player.energy == 0


class TestOrichalcum:
    def test_gain_block_when_no_block(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["orichalcum"]
        battle.player.block = 0

        rd.fire("on_turn_end", battle, battle.relics)
        assert battle.player.block == 6

    def test_no_block_when_has_block(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["orichalcum"]
        battle.player.block = 5

        rd.fire("on_turn_end", battle, battle.relics)
        assert battle.player.block == 5


class TestHornCleat:
    def test_gain_block_on_turn_2(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["horn_cleat"]

        battle.turn = 2
        rd.fire("on_turn_start", battle, battle.relics)
        assert battle.player.block == 14

    def test_no_block_on_turn_1(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["horn_cleat"]

        battle.turn = 1
        rd.fire("on_turn_start", battle, battle.relics)
        assert battle.player.block == 0


class TestBronzeScales:
    def test_deal_damage_on_attacked(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["bronze_scales"]

        rd.fire("on_attacked", battle, battle.relics, attacker_idx=0)
        assert battle.enemies[0].current_hp == 47  # 50 - 3


class TestMeatOnTheBone:
    def test_heal_when_below_50_pct(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["meat_on_the_bone"]
        battle.player.current_hp = 30  # 37.5%, below 50%

        rd.fire("on_combat_end", battle, battle.relics)
        assert battle.player.current_hp == 42  # 30 + 12

    def test_heal_when_at_50_pct(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["meat_on_the_bone"]
        battle.player.current_hp = 40  # exactly 50%

        rd.fire("on_combat_end", battle, battle.relics)
        assert battle.player.current_hp == 52  # 40 + 12

    def test_no_heal_when_above_50_pct(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["meat_on_the_bone"]
        battle.player.current_hp = 60  # 75%

        rd.fire("on_combat_end", battle, battle.relics)
        assert battle.player.current_hp == 60


class TestShuriken:
    def test_gain_strength_after_3_attacks(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["shuriken"]

        for _ in range(3):
            rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 1

    def test_triggers_multiple_times_per_turn(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["shuriken"]

        for _ in range(6):
            rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 2


class TestKunai:
    def test_gain_dexterity_after_3_attacks(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["kunai"]

        for _ in range(3):
            rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "dexterity") == 1


class TestOrnamentalFan:
    def test_gain_block_after_3_attacks(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["ornamental_fan"]

        for _ in range(3):
            rd.fire("on_attack_played", battle, battle.relics)
        assert battle.player.block == 4


class TestMultipleRelics:
    def test_multiple_combat_start_relics(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["vajra", "anchor", "oddly_smooth_stone"]

        rd.fire("on_combat_start", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 1
        assert battle.player.block == 10
        assert get_status_stacks(battle.player, "dexterity") == 1

    def test_multiple_counter_relics(self, interpreter, battle, registry):
        rd = RelicDispatcher(interpreter, registry.relics)
        battle.relics = ["shuriken", "kunai", "ornamental_fan"]

        for _ in range(3):
            rd.fire("on_attack_played", battle, battle.relics)
        assert get_status_stacks(battle.player, "strength") == 1
        assert get_status_stacks(battle.player, "dexterity") == 1
        assert battle.player.block == 4


# ---------------------------------------------------------------------------
# Integration: relics in CombatSimulator
# ---------------------------------------------------------------------------

class _NoPlayAgent(PlayAgent):
    """Agent that never plays cards."""
    def choose_card_to_play(self, battle, playable_cards):
        return None
    def choose_card_reward(self, cards, deck):
        return None
    def choose_potion_to_use(self, battle, available_potions):
        return None
    def choose_rest_action(self, player, deck):
        return "rest"
    def choose_card_to_upgrade(self, upgradable):
        return None


class TestRelicIntegration:
    def test_vajra_in_combat(self, registry):
        rng = GameRNG(seed=99)
        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        enemy = Enemy(name="Cultist", enemy_id="cultist", max_hp=50, current_hp=50)
        deck = [CardInstance(card_id="strike") for _ in range(10)]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=rng,
            relics=["vajra"],
        )

        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter, _NoPlayAgent())
        sim.run_combat(battle)

        # The combat should have run; vajra should have given +1 strength
        # Since the NoPlayAgent doesn't play, the player will eventually lose
        # but strength should have been applied at combat start

    def test_orichalcum_in_combat(self, registry):
        rng = GameRNG(seed=99)
        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        # Use a weak enemy so combat doesn't go forever
        enemy = Enemy(name="Test", enemy_id="cultist", max_hp=5, current_hp=5)
        deck = [CardInstance(card_id="strike") for _ in range(10)]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=rng,
            relics=["orichalcum"],
        )

        interpreter = ActionInterpreter(card_registry=registry.cards)
        # Use NoPlayAgent to guarantee 0 block at end of turn
        sim = CombatSimulator(registry, interpreter, _NoPlayAgent())
        sim.run_combat(battle)
        # Just verify it doesn't crash; Orichalcum should fire each turn

    def test_burning_blood_heals_after_win(self, registry):
        """Burning Blood should heal 6 HP after a combat win."""
        rng = GameRNG(seed=99)
        player = Player(name="Ironclad", max_hp=80, current_hp=50, max_energy=3)
        enemy = Enemy(name="Test", enemy_id="cultist", max_hp=1, current_hp=1)
        deck = [CardInstance(card_id="strike") for _ in range(10)]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=rng,
            relics=["burning_blood"],
        )

        interpreter = ActionInterpreter(card_registry=registry.cards)

        class _OneHitAgent(PlayAgent):
            def choose_card_to_play(self, battle, playable_cards):
                if playable_cards:
                    ci, cd = playable_cards[0]
                    return (ci, cd, 0)
                return None
            def choose_card_reward(self, cards, deck):
                return None
            def choose_potion_to_use(self, battle, available_potions):
                return None
            def choose_rest_action(self, player, deck):
                return "rest"
            def choose_card_to_upgrade(self, upgradable):
                return None

        sim = CombatSimulator(registry, interpreter, _OneHitAgent())
        telemetry = sim.run_combat(battle)

        assert telemetry.result == "win"
        # Player should have been healed by 6 after the win
        assert player.current_hp == 56  # 50 + 6
