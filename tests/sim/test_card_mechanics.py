"""Tests for card keyword mechanics: exhaust, ethereal, innate, retain.

These test the combat loop integration in CombatSimulator, not the
interpreter directly.
"""

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
)
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.runner import CombatSimulator
from sts_gen.sim.play_agents.base import PlayAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(**kwargs) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3, energy=3)
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(**kwargs) -> Enemy:
    defaults = dict(name="Dummy", enemy_id="dummy", max_hp=100, current_hp=100)
    defaults.update(kwargs)
    return Enemy(**defaults)


class _SingleCardAgent(PlayAgent):
    """Agent that plays the first playable card each turn, then ends turn."""

    def __init__(self):
        self._played_this_turn = False

    def choose_card_to_play(self, battle, playable_cards):
        if self._played_this_turn:
            self._played_this_turn = False
            return None
        if not playable_cards:
            return None
        card_inst, card_def = playable_cards[0]
        self._played_this_turn = True
        target = 0 if card_def.target == CardTarget.ENEMY else None
        return (card_inst, card_def, target)

    def choose_card_reward(self, cards, deck):
        return None

    def choose_potion_to_use(self, battle, available_potions):
        return None

    def choose_rest_action(self, player, deck):
        return "rest"

    def choose_card_to_upgrade(self, upgradable):
        return None


class _NoPlayAgent(PlayAgent):
    """Agent that never plays cards — just ends turn immediately."""

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


def _make_registry_with_cards(cards: list[CardDefinition]) -> ContentRegistry:
    """Create a minimal registry with the given card definitions."""
    registry = ContentRegistry()
    for card in cards:
        registry.cards[card.id] = card
    # Add a dummy enemy so combats don't fail
    registry.enemies["dummy"] = {
        "id": "dummy",
        "name": "Dummy",
        "hp_min": 100,
        "hp_max": 100,
        "moves": [{"id": "wait", "name": "Wait", "type": "buff", "actions": []}],
        "pattern": {"type": "sequential"},
    }
    return registry


# ---------------------------------------------------------------------------
# Exhaust
# ---------------------------------------------------------------------------

class TestExhaust:
    def test_exhaust_card_goes_to_exhaust_not_discard(self):
        """Cards with exhaust=True go to exhaust pile after play."""
        card = CardDefinition(
            id="test_exhaust",
            name="Test Exhaust",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=0,
            target=CardTarget.SELF,
            description="Gain 1 Block. Exhaust.",
            actions=[ActionNode(action_type=ActionType.GAIN_BLOCK, value=1, target="self")],
            exhaust=True,
        )
        registry = _make_registry_with_cards([card])
        interp = ActionInterpreter(card_registry=registry.cards)
        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                draw=[],
                hand=[CardInstance(card_id="test_exhaust")],
            ),
            rng=GameRNG(42),
        )
        card_inst = battle.card_piles.hand[0]
        interp.play_card(card, battle, card_inst, chosen_target=None)

        assert len(battle.card_piles.exhaust) == 1
        assert len(battle.card_piles.discard) == 0
        assert battle.card_piles.hand_size == 0


# ---------------------------------------------------------------------------
# Ethereal
# ---------------------------------------------------------------------------

class TestEthereal:
    def test_ethereal_card_exhausted_at_end_of_turn(self):
        """Ethereal cards still in hand at end of turn get exhausted."""
        ethereal_card = CardDefinition(
            id="test_ethereal",
            name="Test Ethereal",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=99,  # Too expensive to play
            target=CardTarget.SELF,
            description="Ethereal.",
            actions=[],
            ethereal=True,
        )
        normal_card = CardDefinition(
            id="test_normal",
            name="Test Normal",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=99,
            target=CardTarget.SELF,
            description="Normal.",
            actions=[],
        )
        registry = _make_registry_with_cards([ethereal_card, normal_card])
        interp = ActionInterpreter(card_registry=registry.cards)
        agent = _NoPlayAgent()
        sim = CombatSimulator(registry, interp, agent)

        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                draw=[],
                hand=[
                    CardInstance(card_id="test_ethereal"),
                    CardInstance(card_id="test_normal"),
                ],
            ),
            rng=GameRNG(42),
        )

        # Simulate one turn manually: start_turn already happened
        battle.turn = 1
        # Agent plays nothing, end turn triggers card handling
        sim._end_turn_card_handling(battle)

        # Ethereal card should be exhausted
        assert len(battle.card_piles.exhaust) == 1
        assert battle.card_piles.exhaust[0].card_id == "test_ethereal"
        # Normal card should be discarded
        assert len(battle.card_piles.discard) == 1
        assert battle.card_piles.discard[0].card_id == "test_normal"
        # Hand should be empty
        assert battle.card_piles.hand_size == 0


# ---------------------------------------------------------------------------
# Innate
# ---------------------------------------------------------------------------

class TestInnate:
    def test_innate_cards_drawn_first(self):
        """Innate cards should be moved to top of draw pile before first draw."""
        innate_card = CardDefinition(
            id="test_innate",
            name="Test Innate",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.SELF,
            description="Innate.",
            actions=[ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self")],
            innate=True,
        )
        normal_card = CardDefinition(
            id="test_normal",
            name="Test Normal",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.SELF,
            description="Normal.",
            actions=[ActionNode(action_type=ActionType.GAIN_BLOCK, value=3, target="self")],
        )
        registry = _make_registry_with_cards([innate_card, normal_card])
        interp = ActionInterpreter(card_registry=registry.cards)

        # Put innate card at the BOTTOM (last position)
        draw = [CardInstance(card_id="test_normal") for _ in range(9)]
        draw.append(CardInstance(card_id="test_innate"))

        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(draw=draw),
            rng=GameRNG(42),
        )

        agent = _NoPlayAgent()
        sim = CombatSimulator(registry, interp, agent)

        # _move_innate_to_top should put the innate card first
        sim._move_innate_to_top(battle)

        assert battle.card_piles.draw[0].card_id == "test_innate"


# ---------------------------------------------------------------------------
# Retain
# ---------------------------------------------------------------------------

class TestRetain:
    def test_retain_card_stays_in_hand(self):
        """Cards with retain=True stay in hand at end of turn."""
        retain_card = CardDefinition(
            id="test_retain",
            name="Test Retain",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=99,  # Too expensive to play
            target=CardTarget.SELF,
            description="Retain.",
            actions=[],
            retain=True,
        )
        normal_card = CardDefinition(
            id="test_normal",
            name="Test Normal",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=99,
            target=CardTarget.SELF,
            description="Normal.",
            actions=[],
        )
        registry = _make_registry_with_cards([retain_card, normal_card])
        interp = ActionInterpreter(card_registry=registry.cards)
        agent = _NoPlayAgent()
        sim = CombatSimulator(registry, interp, agent)

        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                draw=[],
                hand=[
                    CardInstance(card_id="test_retain"),
                    CardInstance(card_id="test_normal"),
                ],
            ),
            rng=GameRNG(42),
        )
        battle.turn = 1
        sim._end_turn_card_handling(battle)

        # Retain card stays in hand
        assert battle.card_piles.hand_size == 1
        assert battle.card_piles.hand[0].card_id == "test_retain"
        # Normal card discarded
        assert len(battle.card_piles.discard) == 1
        assert battle.card_piles.discard[0].card_id == "test_normal"

    def test_ethereal_takes_priority_over_retain(self):
        """If a card is both ethereal and retain, ethereal wins (card gets exhausted)."""
        both_card = CardDefinition(
            id="test_both",
            name="Test Both",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=99,
            target=CardTarget.SELF,
            description="Ethereal. Retain.",
            actions=[],
            ethereal=True,
            retain=True,
        )
        registry = _make_registry_with_cards([both_card])
        interp = ActionInterpreter(card_registry=registry.cards)
        agent = _NoPlayAgent()
        sim = CombatSimulator(registry, interp, agent)

        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                draw=[],
                hand=[CardInstance(card_id="test_both")],
            ),
            rng=GameRNG(42),
        )
        battle.turn = 1
        sim._end_turn_card_handling(battle)

        # Ethereal takes priority — card is exhausted, not retained
        assert battle.card_piles.hand_size == 0
        assert len(battle.card_piles.exhaust) == 1
        assert len(battle.card_piles.discard) == 0


# ---------------------------------------------------------------------------
# Play Restriction
# ---------------------------------------------------------------------------

class TestPlayRestriction:
    def test_play_restriction_blocks_non_attack_hand(self):
        """Card with only_attacks_in_hand restriction is unplayable when hand has skills."""
        clash = CardDefinition(
            id="clash",
            name="Clash",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=0,
            target=CardTarget.ENEMY,
            description="Can only be played if every card in your hand is an Attack. Deal 14 damage.",
            actions=[ActionNode(action_type=ActionType.DEAL_DAMAGE, value=14, target="enemy")],
            play_restriction="only_attacks_in_hand",
        )
        defend = CardDefinition(
            id="defend",
            name="Defend",
            type=CardType.SKILL,
            rarity=CardRarity.BASIC,
            cost=1,
            target=CardTarget.SELF,
            description="Gain 5 Block.",
            actions=[ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self")],
        )
        registry = _make_registry_with_cards([clash, defend])
        interp = ActionInterpreter(card_registry=registry.cards)
        agent = _NoPlayAgent()
        sim = CombatSimulator(registry, interp, agent)

        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                draw=[],
                hand=[
                    CardInstance(card_id="clash"),
                    CardInstance(card_id="defend"),
                ],
            ),
            rng=GameRNG(42),
        )

        playable = sim._get_playable_cards(battle)
        playable_ids = [card_def.id for _, card_def in playable]

        # Clash should NOT be playable (hand has a skill)
        assert "clash" not in playable_ids
        # Defend should be playable
        assert "defend" in playable_ids

    def test_play_restriction_allows_all_attack_hand(self):
        """Card with only_attacks_in_hand restriction is playable when hand is all attacks."""
        clash = CardDefinition(
            id="clash",
            name="Clash",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=0,
            target=CardTarget.ENEMY,
            description="Can only be played if every card in your hand is an Attack. Deal 14 damage.",
            actions=[ActionNode(action_type=ActionType.DEAL_DAMAGE, value=14, target="enemy")],
            play_restriction="only_attacks_in_hand",
        )
        strike = CardDefinition(
            id="strike",
            name="Strike",
            type=CardType.ATTACK,
            rarity=CardRarity.BASIC,
            cost=1,
            target=CardTarget.ENEMY,
            description="Deal 6 damage.",
            actions=[ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy")],
        )
        registry = _make_registry_with_cards([clash, strike])
        interp = ActionInterpreter(card_registry=registry.cards)
        agent = _NoPlayAgent()
        sim = CombatSimulator(registry, interp, agent)

        battle = BattleState(
            player=_make_player(),
            enemies=[_make_enemy()],
            card_piles=CardPiles(
                draw=[],
                hand=[
                    CardInstance(card_id="clash"),
                    CardInstance(card_id="strike"),
                ],
            ),
            rng=GameRNG(42),
        )

        playable = sim._get_playable_cards(battle)
        playable_ids = [card_def.id for _, card_def in playable]

        # Both should be playable
        assert "clash" in playable_ids
        assert "strike" in playable_ids
