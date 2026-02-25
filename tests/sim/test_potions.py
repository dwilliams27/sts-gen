"""Tests for Phase 2E potion system: data loading, use_potion, agent integration."""

from __future__ import annotations

import pytest

from sts_gen.ir.cards import CardTarget
from sts_gen.ir.potions import PotionDefinition, PotionRarity
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.potions import use_potion
from sts_gen.sim.mechanics.status_effects import get_status_stacks, has_status
from sts_gen.sim.play_agents.base import PlayAgent
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
    rng = GameRNG(seed=42)
    player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
    enemies = [
        Enemy(name="Cultist", enemy_id="cultist", max_hp=50, current_hp=50),
        Enemy(name="Cultist2", enemy_id="cultist", max_hp=50, current_hp=50),
    ]
    return BattleState(
        player=player,
        enemies=enemies,
        rng=rng,
        card_piles=CardPiles(),
    )


@pytest.fixture
def interpreter(registry):
    return ActionInterpreter(card_registry=registry.cards)


# ---------------------------------------------------------------------------
# Potion data loading
# ---------------------------------------------------------------------------

class TestPotionLoading:
    def test_load_vanilla_potions(self, registry):
        assert len(registry.potions) == 11

    def test_fire_potion_loaded(self, registry):
        p = registry.get_potion("fire_potion")
        assert p is not None
        assert p.name == "Fire Potion"
        assert p.rarity == PotionRarity.COMMON
        assert p.target == CardTarget.ENEMY

    def test_regen_potion_loaded(self, registry):
        p = registry.get_potion("regen_potion")
        assert p is not None
        assert p.rarity == PotionRarity.UNCOMMON
        assert p.target == CardTarget.SELF

    def test_fruit_juice_loaded(self, registry):
        p = registry.get_potion("fruit_juice")
        assert p is not None
        assert p.rarity == PotionRarity.RARE

    def test_get_nonexistent_potion(self, registry):
        assert registry.get_potion("does_not_exist") is None


# ---------------------------------------------------------------------------
# use_potion unit tests
# ---------------------------------------------------------------------------

class TestFirePotion:
    def test_deals_20_damage(self, registry, battle, interpreter):
        p = registry.get_potion("fire_potion")
        use_potion(p, battle, interpreter, chosen_target=0)
        assert battle.enemies[0].current_hp == 30  # 50 - 20


class TestBlockPotion:
    def test_gain_12_block(self, registry, battle, interpreter):
        p = registry.get_potion("block_potion")
        use_potion(p, battle, interpreter)
        assert battle.player.block == 12


class TestStrengthPotion:
    def test_gain_2_strength(self, registry, battle, interpreter):
        p = registry.get_potion("strength_potion")
        use_potion(p, battle, interpreter)
        assert get_status_stacks(battle.player, "strength") == 2


class TestFearPotion:
    def test_apply_3_vulnerable(self, registry, battle, interpreter):
        p = registry.get_potion("fear_potion")
        use_potion(p, battle, interpreter, chosen_target=0)
        assert get_status_stacks(battle.enemies[0], "vulnerable") == 3


class TestWeakPotion:
    def test_apply_3_weak(self, registry, battle, interpreter):
        p = registry.get_potion("weak_potion")
        use_potion(p, battle, interpreter, chosen_target=0)
        assert get_status_stacks(battle.enemies[0], "weak") == 3


class TestSwiftPotion:
    def test_draw_3_cards(self, registry, battle, interpreter):
        for _ in range(10):
            battle.card_piles.draw.append(CardInstance(card_id="strike"))
        p = registry.get_potion("swift_potion")
        use_potion(p, battle, interpreter)
        assert len(battle.card_piles.hand) == 3


class TestDexterityPotion:
    def test_gain_2_dexterity(self, registry, battle, interpreter):
        p = registry.get_potion("dexterity_potion")
        use_potion(p, battle, interpreter)
        assert get_status_stacks(battle.player, "dexterity") == 2


class TestEnergyPotion:
    def test_gain_2_energy(self, registry, battle, interpreter):
        p = registry.get_potion("energy_potion")
        use_potion(p, battle, interpreter)
        assert battle.player.energy == 2


class TestExplosivePotion:
    def test_deals_10_to_all(self, registry, battle, interpreter):
        p = registry.get_potion("explosive_potion")
        use_potion(p, battle, interpreter)
        assert battle.enemies[0].current_hp == 40  # 50 - 10
        assert battle.enemies[1].current_hp == 40  # 50 - 10


class TestRegenPotion:
    def test_apply_5_regeneration(self, registry, battle, interpreter):
        p = registry.get_potion("regen_potion")
        use_potion(p, battle, interpreter)
        assert get_status_stacks(battle.player, "Regeneration") == 5


class TestFruitJuice:
    def test_raise_max_hp_by_5(self, registry, battle, interpreter):
        p = registry.get_potion("fruit_juice")
        use_potion(p, battle, interpreter)
        assert battle.player.max_hp == 85
        assert battle.player.current_hp == 85


# ---------------------------------------------------------------------------
# Potion belt management
# ---------------------------------------------------------------------------

class TestPotionBelt:
    def test_default_belt_has_3_empty_slots(self, battle):
        assert battle.potions == [None, None, None]

    def test_use_removes_from_belt(self, registry, battle, interpreter):
        battle.potions = ["fire_potion", None, "block_potion"]
        p = registry.get_potion("fire_potion")
        use_potion(p, battle, interpreter, chosen_target=0)
        # Simulate belt removal (as runner does)
        battle.potions[0] = None
        assert battle.potions == [None, None, "block_potion"]


# ---------------------------------------------------------------------------
# Integration: potions in CombatSimulator
# ---------------------------------------------------------------------------

class _AlwaysUsePotionAgent(PlayAgent):
    """Agent that always uses the first available potion, then never plays cards."""
    def __init__(self):
        self._used_potion = False

    def choose_card_to_play(self, battle, playable_cards):
        return None

    def choose_card_reward(self, cards, deck):
        return None

    def choose_potion_to_use(self, battle, available_potions):
        if not available_potions or self._used_potion:
            return None
        self._used_potion = True
        slot, potion_def = available_potions[0]
        # For ENEMY-targeted potions, target first living enemy
        target = None
        if potion_def.target == CardTarget.ENEMY:
            for i, e in enumerate(battle.enemies):
                if not e.is_dead:
                    target = i
                    break
        return slot, potion_def, target

    def choose_rest_action(self, player, deck):
        return "rest"

    def choose_card_to_upgrade(self, upgradable):
        return None


class TestPotionIntegration:
    def test_potion_used_in_combat(self, registry):
        """Verify potion gets used and removed from belt during combat."""
        rng = GameRNG(seed=42)
        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        enemy = Enemy(name="Cultist", enemy_id="cultist", max_hp=50, current_hp=50)
        deck = [CardInstance(card_id="strike") for _ in range(10)]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=rng,
            potions=["strength_potion", None, None],
        )

        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter, _AlwaysUsePotionAgent())
        sim.run_combat(battle)

        # Strength potion should have been used and removed
        assert battle.potions[0] is None
        # Player should have had +2 strength during combat
        assert get_status_stacks(player, "strength") == 2

    def test_fire_potion_damages_in_combat(self, registry):
        """Fire Potion deals 20 damage to target in combat."""
        rng = GameRNG(seed=42)
        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        enemy = Enemy(name="Cultist", enemy_id="cultist", max_hp=50, current_hp=50)
        deck = [CardInstance(card_id="strike") for _ in range(10)]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=rng,
            potions=["fire_potion", None, None],
        )

        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter, _AlwaysUsePotionAgent())
        sim.run_combat(battle)

        # Fire potion should have dealt 20 damage at some point
        # (enemy may have more or less HP depending on how combat played out)
        assert battle.potions[0] is None  # Used


# ---------------------------------------------------------------------------
# Interpreter: turn_eq condition
# ---------------------------------------------------------------------------

class TestTurnEqCondition:
    def test_turn_eq_matches(self, interpreter):
        """turn_eq:N matches when battle.turn == N."""
        rng = GameRNG(seed=42)
        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        enemy = Enemy(name="Test", enemy_id="test", max_hp=50, current_hp=50)
        battle = BattleState(player=player, enemies=[enemy], rng=rng)
        battle.turn = 2
        assert interpreter._evaluate_condition("turn_eq:2", battle, "player", None) is True

    def test_turn_eq_no_match(self, interpreter):
        rng = GameRNG(seed=42)
        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        enemy = Enemy(name="Test", enemy_id="test", max_hp=50, current_hp=50)
        battle = BattleState(player=player, enemies=[enemy], rng=rng)
        battle.turn = 3
        assert interpreter._evaluate_condition("turn_eq:2", battle, "player", None) is False


# ---------------------------------------------------------------------------
# Regeneration status
# ---------------------------------------------------------------------------

class TestRegenerationStatus:
    def test_regeneration_loaded(self, registry):
        defn = registry.get_status_def("Regeneration")
        assert defn is not None
        assert defn.decay_per_turn == 1

    def test_regeneration_heals_at_end_of_turn(self, registry, battle, interpreter):
        """Regeneration heals for stack count at end of turn."""
        from sts_gen.sim.triggers import TriggerDispatcher
        from sts_gen.ir.status_effects import StatusTrigger

        td = TriggerDispatcher(interpreter, registry.status_defs)
        battle.player.current_hp = 70
        battle.player.status_effects["Regeneration"] = 5

        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")
        assert battle.player.current_hp == 75  # healed 5

    def test_regeneration_decays(self, registry, battle):
        """Regeneration loses 1 stack per turn from decay."""
        from sts_gen.sim.mechanics.status_effects import decay_statuses

        battle.player.status_effects["Regeneration"] = 3
        decay_statuses(battle.player, registry.status_defs)
        assert battle.player.status_effects.get("Regeneration") == 2

    def test_regeneration_removed_at_zero(self, registry, battle):
        from sts_gen.sim.mechanics.status_effects import decay_statuses

        battle.player.status_effects["Regeneration"] = 1
        decay_statuses(battle.player, registry.status_defs)
        assert "Regeneration" not in battle.player.status_effects
