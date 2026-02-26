"""Tests for tool handlers -- real registry, no API calls."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sts_gen.agents.tools import (
    ToolContext,
    register_all_tools,
    _handle_get_vanilla_card_detail,
    _handle_list_vanilla_cards,
    _handle_query_baseline,
    _handle_run_quick_sim,
    _handle_validate_content_set,
)
from sts_gen.sim.content.registry import ContentRegistry


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture()
def registry() -> ContentRegistry:
    """Fully loaded vanilla registry."""
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_encounters()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    return reg


@pytest.fixture()
def baseline_path(tmp_path: Path, registry: ContentRegistry) -> Path:
    """Generate and save a tiny baseline for testing."""
    from sts_gen.balance.baselines import generate_baseline, save_baseline

    baseline = generate_baseline(registry, num_runs=50, min_co_occurrence=5)
    path = tmp_path / "test_baseline.json"
    save_baseline(baseline, path)
    return path


@pytest.fixture()
def ctx(registry: ContentRegistry, baseline_path: Path) -> ToolContext:
    """ToolContext with registry and baseline."""
    return ToolContext(registry=registry, baseline_path=baseline_path)


@pytest.fixture()
def ctx_no_baseline(registry: ContentRegistry) -> ToolContext:
    """ToolContext without baseline path."""
    return ToolContext(registry=registry)


# A minimal valid ContentSet JSON
_VALID_CONTENT_SET = json.dumps({
    "mod_id": "test:TestMod",
    "mod_name": "Test Mod",
    "cards": [
        {
            "id": "test_slash",
            "name": "Test Slash",
            "type": "ATTACK",
            "rarity": "COMMON",
            "cost": 1,
            "target": "ENEMY",
            "description": "Deal 8 damage.",
            "actions": [
                {"action_type": "deal_damage", "target": "enemy", "value": 8}
            ],
        }
    ],
})


# =====================================================================
# query_baseline tests
# =====================================================================

class TestQueryBaseline:
    def test_returns_llm_context(self, ctx: ToolContext) -> None:
        """Should return a non-empty LLM context string."""
        result = _handle_query_baseline(ctx, {})
        assert "<vanilla_baseline>" in result
        assert "global:" in result
        assert "card_id" in result

    def test_raises_when_no_baseline(self, ctx_no_baseline: ToolContext) -> None:
        """Should raise ValueError when no baseline path is configured."""
        with pytest.raises(ValueError, match="No baseline path"):
            _handle_query_baseline(ctx_no_baseline, {})


# =====================================================================
# validate_content_set tests
# =====================================================================

class TestValidateContentSet:
    def test_valid_json_passes(self, ctx: ToolContext) -> None:
        """Valid ContentSet JSON should pass validation."""
        result = json.loads(
            _handle_validate_content_set(ctx, {"content_set_json": _VALID_CONTENT_SET})
        )
        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_json_returns_errors(self, ctx: ToolContext) -> None:
        """Malformed JSON should return validation errors."""
        result = json.loads(
            _handle_validate_content_set(ctx, {"content_set_json": "{not valid json"})
        )
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert any("Invalid JSON" in e for e in result["errors"])

    def test_invalid_schema_returns_errors(self, ctx: ToolContext) -> None:
        """Valid JSON but invalid schema should return errors."""
        bad_schema = json.dumps({"mod_id": "test:Bad"})  # Missing mod_name
        result = json.loads(
            _handle_validate_content_set(ctx, {"content_set_json": bad_schema})
        )
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_unknown_status_ref_caught(self, ctx: ToolContext) -> None:
        """Unknown status effect reference in actions should be caught."""
        bad_content = json.dumps({
            "mod_id": "test:BadStatus",
            "mod_name": "Bad Status Mod",
            "cards": [
                {
                    "id": "bad_card",
                    "name": "Bad Card",
                    "type": "SKILL",
                    "rarity": "COMMON",
                    "cost": 1,
                    "target": "SELF",
                    "description": "Apply NonexistentBuff.",
                    "actions": [
                        {
                            "action_type": "apply_status",
                            "target": "self",
                            "status_name": "NonexistentBuff",
                            "value": 1,
                        }
                    ],
                }
            ],
        })
        result = json.loads(
            _handle_validate_content_set(ctx, {"content_set_json": bad_content})
        )
        assert result["valid"] is False
        assert any("NonexistentBuff" in e for e in result["errors"])


# =====================================================================
# run_quick_sim tests
# =====================================================================

class TestRunQuickSim:
    def test_runs_and_returns_metrics(self, ctx: ToolContext) -> None:
        """Should run sims and return global + custom card metrics."""
        result = json.loads(
            _handle_run_quick_sim(ctx, {
                "content_set_json": _VALID_CONTENT_SET,
                "num_runs": 20,
            })
        )
        assert "global" in result
        assert "custom_cards" in result
        assert result["num_runs"] == 20
        assert result["global"]["total_runs"] == 20

    def test_invalid_content_returns_error(self, ctx: ToolContext) -> None:
        """Invalid content set should return error, not crash."""
        result = json.loads(
            _handle_run_quick_sim(ctx, {
                "content_set_json": "{bad json}",
                "num_runs": 10,
            })
        )
        assert "error" in result


# =====================================================================
# list_vanilla_cards tests
# =====================================================================

class TestListVanillaCards:
    def test_returns_all_cards(self, ctx: ToolContext) -> None:
        """Should return all 80 vanilla cards."""
        result = json.loads(_handle_list_vanilla_cards(ctx, {}))
        assert len(result) == 80

    def test_card_format(self, ctx: ToolContext) -> None:
        """Each card should have id, name, type, rarity, cost."""
        result = json.loads(_handle_list_vanilla_cards(ctx, {}))
        for card in result:
            assert "id" in card
            assert "name" in card
            assert "type" in card
            assert "rarity" in card
            assert "cost" in card


# =====================================================================
# get_vanilla_card_detail tests
# =====================================================================

class TestGetVanillaCardDetail:
    def test_returns_card_data(self, ctx: ToolContext) -> None:
        """Should return full card definition for known card."""
        result = json.loads(
            _handle_get_vanilla_card_detail(ctx, {"card_id": "strike"})
        )
        assert result["id"] == "strike"
        assert result["name"] == "Strike"
        assert "actions" in result

    def test_unknown_card_raises(self, ctx: ToolContext) -> None:
        """Should raise KeyError for unknown card_id."""
        with pytest.raises(KeyError, match="nonexistent_card"):
            _handle_get_vanilla_card_detail(ctx, {"card_id": "nonexistent_card"})


# =====================================================================
# Registry extension tests
# =====================================================================

class TestRegistryExtension:
    def test_load_content_set_loads_relics(self) -> None:
        """load_content_set should load relics from ContentSet."""
        from sts_gen.ir.content_set import ContentSet
        from sts_gen.ir.relics import RelicDefinition, RelicTier

        registry = ContentRegistry()
        cs = ContentSet(
            mod_id="test:Relics",
            mod_name="Relic Test",
            relics=[
                RelicDefinition(
                    id="test_relic",
                    name="Test Relic",
                    tier=RelicTier.COMMON,
                    description="A test relic.",
                    trigger="on_combat_start",
                    actions=[],
                )
            ],
        )
        registry.load_content_set(cs)
        assert "test_relic" in registry.relics
        assert registry.relics["test_relic"].name == "Test Relic"

    def test_load_content_set_loads_potions(self) -> None:
        """load_content_set should load potions from ContentSet."""
        from sts_gen.ir.cards import CardTarget
        from sts_gen.ir.content_set import ContentSet
        from sts_gen.ir.potions import PotionDefinition, PotionRarity

        registry = ContentRegistry()
        cs = ContentSet(
            mod_id="test:Potions",
            mod_name="Potion Test",
            potions=[
                PotionDefinition(
                    id="test_potion",
                    name="Test Potion",
                    rarity=PotionRarity.COMMON,
                    description="A test potion.",
                    target=CardTarget.SELF,
                    actions=[],
                )
            ],
        )
        registry.load_content_set(cs)
        assert "test_potion" in registry.potions
        assert registry.potions["test_potion"].name == "Test Potion"

    def test_load_content_set_loads_status_effects(self) -> None:
        """load_content_set should load status effects from ContentSet."""
        from sts_gen.ir.content_set import ContentSet
        from sts_gen.ir.status_effects import (
            StackBehavior,
            StatusEffectDefinition,
        )

        registry = ContentRegistry()
        cs = ContentSet(
            mod_id="test:Statuses",
            mod_name="Status Test",
            status_effects=[
                StatusEffectDefinition(
                    id="test_buff",
                    name="Test Buff",
                    description="A test buff.",
                    is_debuff=False,
                    stack_behavior=StackBehavior.INTENSITY,
                    triggers={},
                )
            ],
        )
        registry.load_content_set(cs)
        assert "test_buff" in registry.status_defs
        assert registry.status_defs["test_buff"].name == "Test Buff"

    def test_custom_overrides_vanilla(self, registry: ContentRegistry) -> None:
        """Custom content should override vanilla content with same id."""
        from sts_gen.ir.content_set import ContentSet
        from sts_gen.ir.cards import CardDefinition, CardType, CardRarity, CardTarget

        original = registry.get_card("strike")
        assert original is not None
        assert original.description == "Deal 6 damage."

        cs = ContentSet(
            mod_id="test:Override",
            mod_name="Override Test",
            cards=[
                CardDefinition(
                    id="strike",
                    name="Strike",
                    type=CardType.ATTACK,
                    rarity=CardRarity.BASIC,
                    cost=1,
                    target=CardTarget.ENEMY,
                    description="Deal 99 damage.",
                    actions=[],
                )
            ],
        )
        registry.load_content_set(cs)
        modified = registry.get_card("strike")
        assert modified is not None
        assert modified.description == "Deal 99 damage."


# =====================================================================
# register_all_tools integration tests
# =====================================================================

class TestRegisterAllTools:
    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_registers_all_five_tools(
        self, mock_cls: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """register_all_tools should wire all 5 tools onto the client."""
        from sts_gen.agents.client import ClaudeClient

        client = ClaudeClient(api_key="sk-test")
        ctx = ToolContext(registry=registry, baseline_path=baseline_path)
        register_all_tools(client, ctx)

        expected = {
            "query_baseline",
            "validate_content_set",
            "run_quick_sim",
            "list_vanilla_cards",
            "get_vanilla_card_detail",
        }
        assert set(client._tools.keys()) == expected

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_bound_handlers_work(
        self, mock_cls: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """Bound handlers should execute correctly through the client's tool registry."""
        from sts_gen.agents.client import ClaudeClient

        client = ClaudeClient(api_key="sk-test")
        ctx = ToolContext(registry=registry, baseline_path=baseline_path)
        register_all_tools(client, ctx)

        # Call list_vanilla_cards handler directly through the binding
        result = json.loads(client._tools["list_vanilla_cards"].handler({}))
        assert len(result) == 80

        # Call query_baseline handler — should return LLM context
        result_str = client._tools["query_baseline"].handler({})
        assert "<vanilla_baseline>" in result_str

        # Call get_vanilla_card_detail — should return card data
        result = json.loads(
            client._tools["get_vanilla_card_detail"].handler({"card_id": "bash"})
        )
        assert result["id"] == "bash"

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_schemas_are_valid_json_schema(
        self, mock_cls: MagicMock, registry: ContentRegistry
    ) -> None:
        """All tool schemas should be valid JSON schema dicts with 'properties'."""
        from sts_gen.agents.client import ClaudeClient

        client = ClaudeClient(api_key="sk-test")
        ctx = ToolContext(registry=registry)
        register_all_tools(client, ctx)

        for name, tool_def in client._tools.items():
            schema = tool_def.input_schema
            assert isinstance(schema, dict), f"{name} schema is not a dict"
            assert "type" in schema or "properties" in schema, (
                f"{name} schema missing 'type' or 'properties'"
            )


# =====================================================================
# run_quick_sim with playable custom card
# =====================================================================

class TestRunQuickSimCustomCardMetrics:
    def test_custom_card_appears_in_metrics(self, ctx: ToolContext) -> None:
        """A common custom card should appear in metrics when offered/picked over enough runs."""
        # Use enough runs that a COMMON card is very likely to be offered at least once
        content = json.dumps({
            "mod_id": "test:Playable",
            "mod_name": "Playable Test",
            "cards": [
                {
                    "id": "custom_blade",
                    "name": "Custom Blade",
                    "type": "ATTACK",
                    "rarity": "COMMON",
                    "cost": 1,
                    "target": "ENEMY",
                    "description": "Deal 9 damage.",
                    "actions": [
                        {"action_type": "deal_damage", "target": "enemy", "value": 9}
                    ],
                }
            ],
        })
        result = json.loads(
            _handle_run_quick_sim(ctx, {
                "content_set_json": content,
                "num_runs": 200,
            })
        )
        assert "error" not in result
        assert result["global"]["total_runs"] == 200

        # The custom card should appear in custom_cards metrics if it was ever
        # offered and picked (COMMON cards are offered frequently). With 200
        # runs this is near-certain.
        custom_ids = {m["card_id"] for m in result["custom_cards"]}
        assert "custom_blade" in custom_ids, (
            f"custom_blade not found in metrics; got {custom_ids}"
        )

        # Verify the metrics structure is complete
        blade_metrics = [
            m for m in result["custom_cards"] if m["card_id"] == "custom_blade"
        ][0]
        assert blade_metrics["times_in_deck"] > 0
        assert blade_metrics["times_offered"] > 0
