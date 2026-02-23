"""Tests for the ActionNode interpreter."""

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
)
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.status_effects import get_status_stacks, has_status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(**kwargs) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3, energy=3)
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(**kwargs) -> Enemy:
    defaults = dict(name="Jaw Worm", enemy_id="jaw_worm", max_hp=44, current_hp=44)
    defaults.update(kwargs)
    return Enemy(**defaults)


def _make_battle(
    player: Player | None = None,
    enemies: list[Enemy] | None = None,
    draw_ids: list[str] | None = None,
    hand_ids: list[str] | None = None,
) -> BattleState:
    piles = CardPiles(
        draw=[CardInstance(card_id=cid) for cid in (draw_ids or ["strike"] * 10)],
        hand=[CardInstance(card_id=cid) for cid in (hand_ids or [])],
    )
    return BattleState(
        player=player or _make_player(),
        enemies=enemies or [_make_enemy()],
        card_piles=piles,
        rng=GameRNG(42),
    )


def _make_strike_def() -> CardDefinition:
    return CardDefinition(
        id="strike",
        name="Strike",
        type=CardType.ATTACK,
        rarity=CardRarity.BASIC,
        cost=1,
        target=CardTarget.ENEMY,
        description="Deal 6 damage.",
        actions=[
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
        ],
    )


def _make_defend_def() -> CardDefinition:
    return CardDefinition(
        id="defend",
        name="Defend",
        type=CardType.SKILL,
        rarity=CardRarity.BASIC,
        cost=1,
        target=CardTarget.SELF,
        description="Gain 5 Block.",
        actions=[
            ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
        ],
    )


# ---------------------------------------------------------------------------
# Execute deal_damage node
# ---------------------------------------------------------------------------

class TestExecuteDealDamage:
    def test_deal_damage_to_enemy(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=0)

        assert battle.enemies[0].current_hp == 38  # 44 - 6

    def test_deal_damage_all_enemies(self):
        enemies = [_make_enemy(enemy_id="a"), _make_enemy(enemy_id="b")]
        interp = ActionInterpreter()
        battle = _make_battle(enemies=enemies)
        actions = [
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=5, target="all_enemies"),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert battle.enemies[0].current_hp == 39  # 44 - 5
        assert battle.enemies[1].current_hp == 39


# ---------------------------------------------------------------------------
# Execute gain_block node
# ---------------------------------------------------------------------------

class TestExecuteGainBlock:
    def test_gain_block_on_self(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert battle.player.block == 5


# ---------------------------------------------------------------------------
# Execute apply_status node
# ---------------------------------------------------------------------------

class TestExecuteApplyStatus:
    def test_apply_status_to_enemy(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(
                action_type=ActionType.APPLY_STATUS,
                value=2,
                status_name="vulnerable",
                target="enemy",
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=0)

        assert has_status(battle.enemies[0], "vulnerable")
        assert get_status_stacks(battle.enemies[0], "vulnerable") == 2

    def test_apply_status_to_self(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(
                action_type=ActionType.APPLY_STATUS,
                value=3,
                status_name="vulnerable",
                target="self",
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert has_status(battle.player, "vulnerable")
        assert get_status_stacks(battle.player, "vulnerable") == 3


# ---------------------------------------------------------------------------
# Execute draw_cards node
# ---------------------------------------------------------------------------

class TestExecuteDrawCards:
    def test_draw_cards(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(action_type=ActionType.DRAW_CARDS, value=3),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert battle.card_piles.hand_size == 3


# ---------------------------------------------------------------------------
# Execute repeat node
# ---------------------------------------------------------------------------

class TestExecuteRepeat:
    def test_repeat_deal_damage(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(
                action_type=ActionType.REPEAT,
                times=3,
                children=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=2, target="enemy"),
                ],
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=0)

        # 3 repetitions x 2 damage = 6 total
        assert battle.enemies[0].current_hp == 38  # 44 - 6

    def test_repeat_zero_times(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(
                action_type=ActionType.REPEAT,
                times=0,
                children=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=100, target="enemy"),
                ],
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=0)

        assert battle.enemies[0].current_hp == 44  # no damage


# ---------------------------------------------------------------------------
# Execute conditional node
# ---------------------------------------------------------------------------

class TestExecuteConditional:
    def test_conditional_true(self):
        """Condition: player has no block -> children should execute."""
        interp = ActionInterpreter()
        battle = _make_battle()
        battle.player.block = 0

        actions = [
            ActionNode(
                action_type=ActionType.CONDITIONAL,
                condition="no_block",
                children=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=10, target="enemy"),
                ],
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=0)

        assert battle.enemies[0].current_hp == 34  # 44 - 10

    def test_conditional_false(self):
        """Condition: player has block -> children should NOT execute."""
        interp = ActionInterpreter()
        battle = _make_battle()
        battle.player.block = 5

        actions = [
            ActionNode(
                action_type=ActionType.CONDITIONAL,
                condition="no_block",
                children=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=10, target="enemy"),
                ],
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=0)

        assert battle.enemies[0].current_hp == 44  # unchanged

    def test_conditional_has_status(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        from sts_gen.sim.mechanics.status_effects import apply_status
        apply_status(battle.player, "strength", 2)

        actions = [
            ActionNode(
                action_type=ActionType.CONDITIONAL,
                condition="has_status:strength",
                children=[
                    ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
                ],
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert battle.player.block == 5

    def test_conditional_hp_below(self):
        interp = ActionInterpreter()
        player = _make_player(current_hp=30, max_hp=80)  # 37.5% HP
        battle = _make_battle(player=player)

        actions = [
            ActionNode(
                action_type=ActionType.CONDITIONAL,
                condition="hp_below:50",
                children=[
                    ActionNode(action_type=ActionType.GAIN_BLOCK, value=10, target="self"),
                ],
            ),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert battle.player.block == 10


# ---------------------------------------------------------------------------
# play_card -- spends energy and discards
# ---------------------------------------------------------------------------

class TestPlayCard:
    def test_play_card_spends_energy_and_discards(self):
        interp = ActionInterpreter()
        battle = _make_battle(hand_ids=["strike"])
        card_instance = battle.card_piles.hand[0]
        card_def = _make_strike_def()

        interp.play_card(card_def, battle, card_instance, chosen_target=0)

        assert battle.player.energy == 2  # 3 - 1
        assert battle.enemies[0].current_hp == 38  # 44 - 6
        # Card moved from hand to discard
        assert battle.card_piles.hand_size == 0
        assert len(battle.card_piles.discard) == 1
        assert battle.card_piles.discard[0].card_id == "strike"

    def test_play_card_insufficient_energy(self):
        interp = ActionInterpreter()
        player = _make_player(energy=0)
        battle = _make_battle(player=player, hand_ids=["strike"])
        card_instance = battle.card_piles.hand[0]
        card_def = _make_strike_def()

        interp.play_card(card_def, battle, card_instance, chosen_target=0)

        # Should not play: energy stays 0, enemy HP unchanged, card stays in hand
        assert battle.player.energy == 0
        assert battle.enemies[0].current_hp == 44
        assert battle.card_piles.hand_size == 1

    def test_play_defend(self):
        interp = ActionInterpreter()
        battle = _make_battle(hand_ids=["defend"])
        card_instance = battle.card_piles.hand[0]
        card_def = _make_defend_def()

        interp.play_card(card_def, battle, card_instance, chosen_target=None)

        assert battle.player.energy == 2
        assert battle.player.block == 5
        assert battle.card_piles.hand_size == 0
        assert len(battle.card_piles.discard) == 1


# ---------------------------------------------------------------------------
# play_card -- with exhaust keyword
# ---------------------------------------------------------------------------

class TestPlayCardExhaust:
    def test_exhaust_card_goes_to_exhaust_pile(self):
        exhaust_card_def = CardDefinition(
            id="true_grit",
            name="True Grit",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.SELF,
            description="Gain 7 Block. Exhaust a random card.",
            actions=[
                ActionNode(action_type=ActionType.GAIN_BLOCK, value=7, target="self"),
            ],
            exhaust=True,
        )
        interp = ActionInterpreter()
        battle = _make_battle(hand_ids=["true_grit"])
        card_instance = battle.card_piles.hand[0]

        interp.play_card(exhaust_card_def, battle, card_instance, chosen_target=None)

        assert battle.card_piles.hand_size == 0
        assert len(battle.card_piles.discard) == 0
        assert len(battle.card_piles.exhaust) == 1
        assert battle.player.block == 7

    def test_exhaust_keyword_in_keywords_list(self):
        """Card with 'exhaust' in keywords list (not the exhaust bool field)."""
        card_def = CardDefinition(
            id="warcry",
            name="Warcry",
            type=CardType.SKILL,
            rarity=CardRarity.COMMON,
            cost=0,
            target=CardTarget.SELF,
            description="Draw 1 card. Put a card from your hand on top of your draw pile. Exhaust.",
            actions=[
                ActionNode(action_type=ActionType.DRAW_CARDS, value=1),
            ],
            keywords=["exhaust"],
        )
        interp = ActionInterpreter()
        battle = _make_battle(hand_ids=["warcry"])
        card_instance = battle.card_piles.hand[0]

        interp.play_card(card_def, battle, card_instance, chosen_target=None)

        assert len(battle.card_piles.exhaust) == 1
        assert len(battle.card_piles.discard) == 0


# ---------------------------------------------------------------------------
# Execute gain_strength node
# ---------------------------------------------------------------------------

class TestExecuteGainStrength:
    def test_gain_strength(self):
        interp = ActionInterpreter()
        battle = _make_battle()
        actions = [
            ActionNode(action_type=ActionType.GAIN_STRENGTH, value=2, target="self"),
        ]
        interp.execute_actions(actions, battle, source="player", chosen_target=None)

        assert get_status_stacks(battle.player, "strength") == 2
