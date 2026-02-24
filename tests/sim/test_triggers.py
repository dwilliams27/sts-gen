"""Unit tests for TriggerDispatcher -- per_stack scaling, multiple statuses, empty triggers."""

from __future__ import annotations

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.triggers import TriggerDispatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(**kw) -> Player:
    defaults = dict(name="P", max_hp=80, current_hp=80, max_energy=3, energy=3)
    defaults.update(kw)
    return Player(**defaults)


def _make_enemy(**kw) -> Enemy:
    defaults = dict(name="E", enemy_id="dummy", max_hp=100, current_hp=100)
    defaults.update(kw)
    return Enemy(**defaults)


def _make_battle(player=None, enemies=None, seed=1) -> BattleState:
    p = player or _make_player()
    e = enemies or [_make_enemy()]
    return BattleState(
        player=p,
        enemies=e,
        card_piles=CardPiles(),
        rng=GameRNG(seed),
    )


def _make_status_def(
    status_id: str,
    trigger: StatusTrigger,
    actions: list[ActionNode],
    **kw,
) -> StatusEffectDefinition:
    defaults = dict(
        id=status_id,
        name=status_id,
        description="test",
        is_debuff=False,
        stack_behavior=StackBehavior.INTENSITY,
        decay_per_turn=0,
        triggers={trigger: actions},
    )
    defaults.update(kw)
    return StatusEffectDefinition(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTriggerDispatcherScaling:
    """Test per_stack scaling of action values."""

    def test_per_stack_scales_value(self):
        """Value is multiplied by stack count for per_stack condition."""
        actions = [ActionNode(
            action_type=ActionType.GAIN_BLOCK, value=1, target="self",
            condition="per_stack",
        )]
        defn = _make_status_def("TestBuff", StatusTrigger.ON_TURN_END, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"TestBuff": defn})

        battle = _make_battle()
        battle.player.status_effects["TestBuff"] = 5
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        # 5 stacks * 1 value = 5 block (via gain_block which adds dex)
        # Player has 0 dex, so should get 5 block
        assert battle.player.block == 5

    def test_per_stack_raw_bypasses_dex(self):
        """per_stack_raw becomes 'raw' condition, bypassing dex/frail."""
        actions = [ActionNode(
            action_type=ActionType.GAIN_BLOCK, value=1, target="self",
            condition="per_stack_raw",
        )]
        defn = _make_status_def("RageBuff", StatusTrigger.ON_ATTACK_PLAYED, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"RageBuff": defn})

        battle = _make_battle()
        # Give player frail to verify raw bypass
        battle.player.status_effects["frail"] = 2
        battle.player.status_effects["RageBuff"] = 3
        td.fire(battle.player, StatusTrigger.ON_ATTACK_PLAYED, battle, "player")

        # 3 stacks * 1 = 3 raw block (not reduced by frail)
        assert battle.player.block == 3

    def test_per_stack_no_strength_deals_flat_damage(self):
        """per_stack_no_strength deals damage ignoring strength."""
        actions = [ActionNode(
            action_type=ActionType.DEAL_DAMAGE, value=5, target="all_enemies",
            condition="per_stack_no_strength",
        )]
        defn = _make_status_def("CombustBuff", StatusTrigger.ON_TURN_END, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"CombustBuff": defn})

        enemy = _make_enemy(current_hp=100, max_hp=100)
        battle = _make_battle(enemies=[enemy])
        battle.player.status_effects["strength"] = 10  # Should be ignored
        battle.player.status_effects["CombustBuff"] = 2
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        # 2 stacks * 5 = 10 damage, strength ignored
        assert enemy.current_hp == 90

    def test_1_stack_produces_base_value(self):
        """With 1 stack, per_stack just uses the base value."""
        actions = [ActionNode(
            action_type=ActionType.GAIN_BLOCK, value=3, target="self",
            condition="per_stack",
        )]
        defn = _make_status_def("MetBuff", StatusTrigger.ON_TURN_END, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"MetBuff": defn})

        battle = _make_battle()
        battle.player.status_effects["MetBuff"] = 1
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        assert battle.player.block == 3


class TestTriggerDispatcherMultiple:
    """Test multiple statuses with the same trigger."""

    def test_multiple_statuses_fire(self):
        """Multiple statuses with ON_TURN_END each fire."""
        actions_a = [ActionNode(
            action_type=ActionType.GAIN_BLOCK, value=1, target="self",
            condition="per_stack",
        )]
        actions_b = [ActionNode(
            action_type=ActionType.DRAW_CARDS, value=1,
            condition="per_stack",
        )]
        defn_a = _make_status_def("BuffA", StatusTrigger.ON_TURN_END, actions_a)
        defn_b = _make_status_def("BuffB", StatusTrigger.ON_TURN_END, actions_b)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"BuffA": defn_a, "BuffB": defn_b})

        battle = _make_battle()
        battle.player.status_effects["BuffA"] = 3
        battle.player.status_effects["BuffB"] = 2
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        # BuffA: 3 block
        assert battle.player.block == 3
        # BuffB: draw cards (no cards in draw pile, but no error)


class TestTriggerDispatcherEdgeCases:
    """Edge cases for TriggerDispatcher."""

    def test_no_matching_trigger_is_noop(self):
        """Firing a trigger with no matching statuses does nothing."""
        actions = [ActionNode(
            action_type=ActionType.GAIN_BLOCK, value=5, target="self",
            condition="per_stack",
        )]
        defn = _make_status_def("OnlyEnd", StatusTrigger.ON_TURN_END, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"OnlyEnd": defn})

        battle = _make_battle()
        battle.player.status_effects["OnlyEnd"] = 3
        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")

        assert battle.player.block == 0  # No block gained

    def test_zero_stacks_is_noop(self):
        """Status with 0 stacks does not fire."""
        actions = [ActionNode(
            action_type=ActionType.GAIN_BLOCK, value=5, target="self",
            condition="per_stack",
        )]
        defn = _make_status_def("TestBuff", StatusTrigger.ON_TURN_END, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"TestBuff": defn})

        battle = _make_battle()
        battle.player.status_effects["TestBuff"] = 0
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        assert battle.player.block == 0

    def test_unknown_status_is_noop(self):
        """Status not in defs dict is silently skipped."""
        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {})

        battle = _make_battle()
        battle.player.status_effects["UnknownBuff"] = 5
        td.fire(battle.player, StatusTrigger.ON_TURN_END, battle, "player")

        assert battle.player.block == 0

    def test_passive_modifiers_skipped(self):
        """Passive modifiers (strength, dex, etc.) are not fired."""
        # Even if somehow in status_defs, they'd be skipped
        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {})

        battle = _make_battle()
        battle.player.status_effects["strength"] = 5
        td.fire(battle.player, StatusTrigger.ON_TURN_START, battle, "player")

        # No error, no change
        assert battle.player.block == 0

    def test_enemy_source(self):
        """Triggers fire correctly with enemy as source."""
        actions = [ActionNode(
            action_type=ActionType.GAIN_STRENGTH, value=1, target="self",
            condition="per_stack",
        )]
        defn = _make_status_def("Ritual", StatusTrigger.ON_TURN_END, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"Ritual": defn})

        enemy = _make_enemy()
        battle = _make_battle(enemies=[enemy])
        enemy.status_effects["Ritual"] = 3
        td.fire(enemy, StatusTrigger.ON_TURN_END, battle, "0")

        assert enemy.status_effects.get("strength", 0) == 3

    def test_attacker_idx_resolution(self):
        """ON_ATTACKED with attacker_idx resolves 'attacker' target."""
        actions = [ActionNode(
            action_type=ActionType.DEAL_DAMAGE, value=1, target="attacker",
            condition="per_stack_no_strength",
        )]
        defn = _make_status_def("FlameBuf", StatusTrigger.ON_ATTACKED, actions)

        interp = ActionInterpreter()
        td = TriggerDispatcher(interp, {"FlameBuf": defn})

        enemy = _make_enemy(current_hp=50, max_hp=50)
        battle = _make_battle(enemies=[enemy])
        battle.player.status_effects["FlameBuf"] = 4
        td.fire(
            battle.player, StatusTrigger.ON_ATTACKED, battle, "player",
            attacker_idx=0,
        )

        # 4 stacks * 1 = 4 damage to enemy (no strength)
        assert enemy.current_hp == 46
