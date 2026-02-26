"""Tests for PowerTranspiler → Java template context."""

import pytest
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)
from sts_gen.mod_builder.transpiler.powers import PowerTranspiler


TEMPLATE_DIR = Path(__file__).parent.parent.parent / "src" / "sts_gen" / "mod_builder" / "templates"


@pytest.fixture
def transpiler():
    return PowerTranspiler(mod_id="testmod")


@pytest.fixture
def jinja_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )


def _make_demon_form():
    return StatusEffectDefinition(
        id="DemonForm",
        name="Demon Form",
        description="At the start of your turn, gain {stacks} Strength.",
        is_debuff=False,
        stack_behavior=StackBehavior.INTENSITY,
        decay_per_turn=0,
        triggers={
            StatusTrigger.ON_TURN_START: [
                ActionNode(
                    action_type=ActionType.GAIN_STRENGTH,
                    value=1,
                    target="self",
                    condition="per_stack",
                ),
            ],
        },
    )


def _make_rage():
    return StatusEffectDefinition(
        id="Rage",
        name="Rage",
        description="Gain block on attack this turn.",
        is_debuff=False,
        stack_behavior=StackBehavior.INTENSITY,
        decay_per_turn=-1,
        triggers={
            StatusTrigger.ON_ATTACK_PLAYED: [
                ActionNode(
                    action_type=ActionType.GAIN_BLOCK,
                    value=1,
                    target="self",
                    condition="per_stack_raw",
                ),
            ],
        },
    )


def _make_vulnerable():
    return StatusEffectDefinition(
        id="Vulnerable",
        name="Vulnerable",
        description="Takes 25% increased damage.",
        is_debuff=True,
        stack_behavior=StackBehavior.INTENSITY,
        decay_per_turn=1,
        triggers={},
    )


class TestPowerTranspiler:
    def test_demon_form_context(self, transpiler):
        ctx = transpiler.transpile(_make_demon_form())
        assert ctx["class_name"] == "DemonFormPower"
        assert ctx["is_debuff"] is False
        assert len(ctx["triggers"]) == 1
        assert ctx["triggers"][0]["method_name"] == "atStartOfTurn"

    def test_rage_temporary_decay(self, transpiler):
        ctx = transpiler.transpile(_make_rage())
        assert ctx["decay_method"]["amount"] == -1

    def test_vulnerable_debuff(self, transpiler):
        ctx = transpiler.transpile(_make_vulnerable())
        assert ctx["is_debuff"] is True
        assert ctx["decay_method"]["amount"] == 1

    def test_attack_played_guard(self, transpiler):
        ctx = transpiler.transpile(_make_rage())
        body = ctx["triggers"][0]["body"]
        assert "CardType.ATTACK" in body


class TestPowerTemplate:
    def test_demon_form_renders(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_demon_form())
        template = jinja_env.get_template("Power.java.j2")
        java = template.render(**ctx)

        assert "public class DemonFormPower extends AbstractPower" in java
        assert "POWER_ID" in java
        assert "atStartOfTurn" in java
        assert "StrengthPower" in java

    def test_rage_renders_with_decay(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_rage())
        template = jinja_env.get_template("Power.java.j2")
        java = template.render(**ctx)

        assert "RemoveSpecificPowerAction" in java
        assert "atEndOfTurn" in java

    def test_vulnerable_renders(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_vulnerable())
        template = jinja_env.get_template("Power.java.j2")
        java = template.render(**ctx)

        assert "PowerType.DEBUFF" in java
        assert "reducePower" in java
