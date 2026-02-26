"""Tests for RelicTranspiler → Java template context."""

import pytest
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.relics import RelicDefinition, RelicTier
from sts_gen.mod_builder.transpiler.relics import RelicTranspiler


TEMPLATE_DIR = Path(__file__).parent.parent.parent / "src" / "sts_gen" / "mod_builder" / "templates"


@pytest.fixture
def transpiler():
    return RelicTranspiler(mod_id="testmod")


@pytest.fixture
def jinja_env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )


def _make_burning_blood():
    return RelicDefinition(
        id="burning_blood",
        name="Burning Blood",
        tier=RelicTier.STARTER,
        description="At the end of combat, heal 6 HP.",
        trigger="on_combat_end",
        actions=[
            ActionNode(action_type=ActionType.HEAL, value=6, target="self"),
        ],
    )


def _make_counter_relic():
    return RelicDefinition(
        id="nunchaku",
        name="Nunchaku",
        tier=RelicTier.UNCOMMON,
        description="Every 10th Attack played gains 1 Energy.",
        trigger="on_card_played",
        actions=[
            ActionNode(action_type=ActionType.GAIN_ENERGY, value=1),
        ],
        counter=10,
        counter_per_turn=False,
    )


class TestRelicTranspiler:
    def test_burning_blood_context(self, transpiler):
        ctx = transpiler.transpile(_make_burning_blood())
        assert ctx["class_name"] == "BurningBlood"
        assert ctx["tier"] == "STARTER"
        assert ctx["trigger_method"] == "onVictory"
        assert ctx["counter_config"] is None
        assert "HealAction" in ctx["action_body"]

    def test_counter_relic_context(self, transpiler):
        ctx = transpiler.transpile(_make_counter_relic())
        assert ctx["counter_config"]["threshold"] == 10
        assert ctx["counter_config"]["per_turn"] is False
        assert ctx["trigger_method"] == "onPlayCard"


class TestRelicTemplate:
    def test_burning_blood_renders(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_burning_blood())
        template = jinja_env.get_template("Relic.java.j2")
        java = template.render(**ctx)

        assert "public class BurningBlood extends AbstractRelic" in java
        assert "RelicTier.STARTER" in java
        assert "HealAction" in java
        assert "onVictory" in java

    def test_counter_relic_renders(self, transpiler, jinja_env):
        ctx = transpiler.transpile(_make_counter_relic())
        template = jinja_env.get_template("Relic.java.j2")
        java = template.render(**ctx)

        assert "this.counter++" in java
        assert "this.counter >= 10" in java
        assert "this.counter = 0" in java
