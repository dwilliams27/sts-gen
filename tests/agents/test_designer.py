"""Tests for DesignerAgent -- all API calls mocked, no network required."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sts_gen.agents.designer import DesignerAgent, _load_prompt
from sts_gen.agents.schemas import (
    ArchetypeSpec,
    ArchitectureOutput,
    CardPoolOutput,
    CardRole,
    ConceptOutput,
    KeywordsOutput,
)
from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    UpgradeDefinition,
)
from sts_gen.ir.keywords import KeywordDefinition
from sts_gen.ir.potions import PotionDefinition, PotionRarity
from sts_gen.ir.relics import RelicDefinition, RelicTier
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)
from sts_gen.sim.content.registry import ContentRegistry


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture()
def registry() -> ContentRegistry:
    """Minimal vanilla registry."""
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_encounters()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    return reg


@pytest.fixture()
def baseline_path(tmp_path: Path) -> Path:
    """Dummy baseline path (doesn't need to exist for mocked tests)."""
    return tmp_path / "test_baseline.json"


# =====================================================================
# Pre-built stage outputs
# =====================================================================

def _make_concept() -> ConceptOutput:
    return ConceptOutput(
        character_name="Pyromancer",
        fantasy="A fire mage who builds up heat and releases it in bursts.",
        signature_mechanic="Heat stacks convert to Strength at turn start.",
        mechanic_status_effect=StatusEffectDefinition(
            id="pyromancer:Heat",
            name="Heat",
            description="At the start of your turn, gain 1 Strength per stack.",
            is_debuff=False,
            stack_behavior=StackBehavior.INTENSITY,
            triggers={
                StatusTrigger.ON_TURN_START: [
                    ActionNode(
                        action_type=ActionType.GAIN_STRENGTH,
                        value=1,
                        target="self",
                        condition="per_stack",
                    )
                ]
            },
        ),
        archetype_seeds=["Burn", "Eruption", "Ember Control"],
    )


def _make_architecture() -> ArchitectureOutput:
    return ArchitectureOutput(
        archetypes=[
            ArchetypeSpec(
                name="Burn",
                description="Apply persistent fire damage.",
                is_major=True,
                setup_roles=["Igniter"],
                payoff_roles=["Inferno"],
            ),
            ArchetypeSpec(
                name="Eruption",
                description="Build heat then release.",
                is_major=True,
                setup_roles=["Heat Builder"],
                payoff_roles=["Eruption Finisher"],
            ),
        ],
        card_skeleton=[
            CardRole(
                role_name="Fire Strike",
                rarity=CardRarity.BASIC,
                card_type=CardType.ATTACK,
                archetypes=["Burn"],
                brief="Basic fire attack.",
            ),
            CardRole(
                role_name="Fire Guard",
                rarity=CardRarity.BASIC,
                card_type=CardType.SKILL,
                archetypes=["Eruption"],
                brief="Basic fire defense.",
            ),
        ],
    )


def _make_keywords() -> KeywordsOutput:
    return KeywordsOutput(
        status_effects=[
            StatusEffectDefinition(
                id="pyromancer:Heat",
                name="Heat",
                description="At the start of your turn, gain 1 Strength per stack.",
                is_debuff=False,
                stack_behavior=StackBehavior.INTENSITY,
                triggers={
                    StatusTrigger.ON_TURN_START: [
                        ActionNode(
                            action_type=ActionType.GAIN_STRENGTH,
                            value=1,
                            target="self",
                            condition="per_stack",
                        )
                    ]
                },
            ),
        ],
        keywords=[
            KeywordDefinition(
                id="pyromancer:Heat",
                name="Heat",
                description="Stacks that convert to Strength at turn start.",
            ),
        ],
    )


def _make_card_pool() -> CardPoolOutput:
    return CardPoolOutput(
        cards=[
            CardDefinition(
                id="pyromancer:FireStrike",
                name="Fire Strike",
                type=CardType.ATTACK,
                rarity=CardRarity.BASIC,
                cost=1,
                target=CardTarget.ENEMY,
                description="Deal 6 damage.",
                actions=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy")
                ],
                upgrade=UpgradeDefinition(
                    actions=[
                        ActionNode(action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy")
                    ],
                    description="Deal 9 damage.",
                ),
            ),
            CardDefinition(
                id="pyromancer:FireGuard",
                name="Fire Guard",
                type=CardType.SKILL,
                rarity=CardRarity.BASIC,
                cost=1,
                target=CardTarget.SELF,
                description="Gain 5 Block.",
                actions=[
                    ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self")
                ],
                upgrade=UpgradeDefinition(
                    actions=[
                        ActionNode(action_type=ActionType.GAIN_BLOCK, value=8, target="self")
                    ],
                    description="Gain 8 Block.",
                ),
            ),
            CardDefinition(
                id="pyromancer:Ignite",
                name="Ignite",
                type=CardType.POWER,
                rarity=CardRarity.BASIC,
                cost=1,
                target=CardTarget.SELF,
                description="Gain 2 Heat.",
                actions=[
                    ActionNode(
                        action_type=ActionType.APPLY_STATUS,
                        value=2,
                        target="self",
                        status_name="pyromancer:Heat",
                    )
                ],
                upgrade=UpgradeDefinition(
                    actions=[
                        ActionNode(
                            action_type=ActionType.APPLY_STATUS,
                            value=3,
                            target="self",
                            status_name="pyromancer:Heat",
                        )
                    ],
                    description="Gain 3 Heat.",
                ),
            ),
        ],
        relics=[
            RelicDefinition(
                id="pyromancer:EmberStone",
                name="Ember Stone",
                tier=RelicTier.COMMON,
                description="At the start of combat, gain 2 Heat.",
                trigger="on_combat_start",
                actions=[
                    ActionNode(
                        action_type=ActionType.APPLY_STATUS,
                        value=2,
                        target="self",
                        status_name="pyromancer:Heat",
                    )
                ],
            ),
        ],
        potions=[
            PotionDefinition(
                id="pyromancer:FlamePotion",
                name="Flame Potion",
                rarity=PotionRarity.COMMON,
                description="Gain 5 Heat.",
                target=CardTarget.SELF,
                actions=[
                    ActionNode(
                        action_type=ActionType.APPLY_STATUS,
                        value=5,
                        target="self",
                        status_name="pyromancer:Heat",
                    )
                ],
            ),
        ],
    )


# =====================================================================
# Tests
# =====================================================================

class TestDesignerAgent:
    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_generate_calls_all_stages(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path,
        tmp_path: Path,
    ) -> None:
        """generate() should call chat + structured_output for each stage."""
        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()

        # Set up structured_output to return stage outputs in sequence
        mock_client.structured_output.side_effect = [
            _make_concept(),
            _make_architecture(),
            _make_keywords(),
            _make_card_pool(),
        ]
        mock_client.chat.return_value = "OK"

        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test",
            run_dir=tmp_path / "run",
        )
        result = agent.generate("A fire mage character.")

        # 4 stages with chat (stage 5 may not need chat if assembly succeeds)
        assert mock_client.chat.call_count >= 4
        # 4 structured_output calls
        assert mock_client.structured_output.call_count == 4

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_stage_concept_uses_brief(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path,
        tmp_path: Path,
    ) -> None:
        """First chat message should contain the design brief."""
        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()
        mock_client.chat.return_value = "OK"
        mock_client.structured_output.side_effect = [
            _make_concept(),
            _make_architecture(),
            _make_keywords(),
            _make_card_pool(),
        ]

        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test",
            run_dir=tmp_path / "run",
        )
        agent.generate("A necromancer who raises the dead.")

        first_chat_call = mock_client.chat.call_args_list[0]
        message = first_chat_call[0][0]
        assert "necromancer" in message.lower()
        assert "<design_brief>" in message

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_validation_retry(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path,
        tmp_path: Path,
    ) -> None:
        """Should retry on ValidationError, feeding error back via chat."""
        from pydantic import ValidationError

        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()
        mock_client.chat.return_value = "OK"

        # First structured_output fails, second succeeds (for concept stage)
        # Then the rest succeed normally
        call_count = [0]

        def side_effect(prompt, schema, output_tool_name="respond"):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Model did not call the forced tool.")
            if schema == ConceptOutput:
                return _make_concept()
            if schema == ArchitectureOutput:
                return _make_architecture()
            if schema == KeywordsOutput:
                return _make_keywords()
            if schema == CardPoolOutput:
                return _make_card_pool()
            raise ValueError(f"Unexpected schema: {schema}")

        mock_client.structured_output.side_effect = side_effect

        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test",
            run_dir=tmp_path / "run",
        )
        result = agent.generate("A fire mage.")

        # Extra chat call for the error feedback
        assert mock_client.chat.call_count >= 5
        assert result.mod_name == "Pyromancer"

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_max_retries_exceeded(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path,
        tmp_path: Path,
    ) -> None:
        """Should raise after max_retries when structured_output always fails."""
        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()
        mock_client.chat.return_value = "OK"
        mock_client.structured_output.side_effect = RuntimeError(
            "Model did not call the forced tool."
        )

        agent = DesignerAgent(
            registry=registry,
            baseline_path=baseline_path,
            api_key="sk-test",
            max_retries=2,
            run_dir=tmp_path / "run",
        )

        with pytest.raises(RuntimeError, match="forced tool"):
            agent.generate("A fire mage.")

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_assembly_produces_valid_content_set(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path,
        tmp_path: Path,
    ) -> None:
        """Final ContentSet should have correct mod_id and all content."""
        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()
        mock_client.chat.return_value = "OK"
        mock_client.structured_output.side_effect = [
            _make_concept(),
            _make_architecture(),
            _make_keywords(),
            _make_card_pool(),
        ]

        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test",
            run_dir=tmp_path / "run",
        )
        result = agent.generate("A fire mage.")

        assert result.mod_id == "pyromancer"
        assert result.mod_name == "Pyromancer"
        assert len(result.cards) == 3
        assert len(result.relics) == 1
        assert len(result.potions) == 1
        assert len(result.keywords) == 1
        assert len(result.status_effects) == 1

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_system_prompt_loaded(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """ClaudeClient should be created with non-empty system_prompt."""
        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test"
        )

        init_kwargs = MockClient.call_args
        system_prompt = init_kwargs.kwargs.get("system_prompt", "")
        assert len(system_prompt) > 100
        assert "Slay the Spire" in system_prompt

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_tools_registered(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """All 5 tools should be registered on the client."""
        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()

        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test"
        )

        # register_tool should have been called 5 times
        assert mock_client.register_tool.call_count == 5
        tool_names = {
            call.kwargs.get("name", call.args[0] if call.args else None)
            for call in mock_client.register_tool.call_args_list
        }
        assert tool_names == {
            "query_baseline",
            "validate_content_set",
            "run_quick_sim",
            "list_vanilla_cards",
            "get_vanilla_card_detail",
        }

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_usage_accessible(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """usage property should return client's TokenUsage."""
        from sts_gen.agents.client import TokenUsage

        mock_usage = TokenUsage(input_tokens=100, output_tokens=50)
        mock_client = MockClient.return_value
        mock_client.usage = mock_usage

        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test"
        )
        assert agent.usage is mock_usage
        assert agent.usage.input_tokens == 100

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_max_tokens(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """Client should be created with max_tokens=65536."""
        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test"
        )

        init_kwargs = MockClient.call_args
        assert init_kwargs.kwargs.get("max_tokens") == 64000

    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_artifacts_saved(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path,
        tmp_path: Path,
    ) -> None:
        """generate() should save stage artifacts as JSON files."""
        mock_client = MockClient.return_value
        mock_client.usage = MagicMock()
        mock_client.chat.return_value = "OK"
        mock_client.structured_output.side_effect = [
            _make_concept(),
            _make_architecture(),
            _make_keywords(),
            _make_card_pool(),
        ]

        run_dir = tmp_path / "test_run"
        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test",
            run_dir=run_dir,
        )
        agent.generate("A fire mage.")

        assert agent.run_dir == run_dir
        assert (run_dir / "brief.txt").read_text() == "A fire mage."
        assert (run_dir / "1_concept.json").exists()
        assert (run_dir / "2_architecture.json").exists()
        assert (run_dir / "3_keywords.json").exists()
        assert (run_dir / "4_card_pool.json").exists()
        assert (run_dir / "5_content_set.json").exists()

        # Verify the final content set is valid JSON we can reload
        import json
        data = json.loads((run_dir / "5_content_set.json").read_text())
        assert data["mod_id"] == "pyromancer"
        assert len(data["cards"]) == 3

    def test_prompt_file_exists(self) -> None:
        """The designer system prompt file should exist and be non-empty."""
        prompt = _load_prompt()
        assert len(prompt) > 500
        assert "ActionType" in prompt
        assert "CardDefinition" in prompt


class TestDesignerAgentDefaultTemperature:
    @patch("sts_gen.agents.designer.ClaudeClient")
    def test_no_temperature_kwarg(
        self, MockClient: MagicMock, registry: ContentRegistry, baseline_path: Path
    ) -> None:
        """DesignerAgent should not pass temperature, relying on client default (1.0)."""
        agent = DesignerAgent(
            registry=registry, baseline_path=baseline_path, api_key="sk-test"
        )

        init_kwargs = MockClient.call_args
        # Temperature should not be explicitly passed — uses client default
        assert "temperature" not in init_kwargs.kwargs
