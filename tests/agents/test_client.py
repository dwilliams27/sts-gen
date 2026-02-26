"""Tests for ClaudeClient -- all API calls are mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from sts_gen.agents.client import ClaudeClient, TokenUsage


# =====================================================================
# Helpers
# =====================================================================

def _make_usage(
    *,
    input_tokens: int = 10,
    output_tokens: int = 20,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
) -> MagicMock:
    """Build a mock Usage object with all billing-relevant fields."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_creation_input_tokens = cache_creation_input_tokens
    usage.cache_read_input_tokens = cache_read_input_tokens
    return usage


def _make_text_response(
    text: str,
    *,
    input_tokens: int = 10,
    output_tokens: int = 20,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
):
    """Build a mock Message with a single TextBlock and end_turn."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    msg = MagicMock()
    msg.content = [text_block]
    msg.stop_reason = "end_turn"
    msg.usage = _make_usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    return msg


def _make_tool_use_response(
    tool_name: str,
    tool_input: dict,
    tool_use_id: str = "toolu_123",
    *,
    input_tokens: int = 10,
    output_tokens: int = 20,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
):
    """Build a mock Message with a ToolUseBlock and tool_use stop."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input
    tool_block.id = tool_use_id

    msg = MagicMock()
    msg.content = [tool_block]
    msg.stop_reason = "tool_use"
    msg.usage = _make_usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    return msg


# =====================================================================
# Init tests
# =====================================================================

class TestInit:
    def test_raises_without_api_key(self) -> None:
        """Should raise ValueError when no API key is available."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY if set
            import os
            env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                with pytest.raises(ValueError, match="No API key"):
                    ClaudeClient()
            finally:
                if env_backup is not None:
                    os.environ["ANTHROPIC_API_KEY"] = env_backup

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_accepts_explicit_key(self, mock_cls: MagicMock) -> None:
        """Should accept an explicit api_key."""
        client = ClaudeClient(api_key="sk-test-123")
        mock_cls.assert_called_once_with(api_key="sk-test-123")
        assert client._model == "claude-sonnet-4-20250514"

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_accepts_env_key(self, mock_cls: MagicMock) -> None:
        """Should accept API key from environment."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-env-456"}):
            client = ClaudeClient()
            mock_cls.assert_called_once_with(api_key="sk-env-456")


# =====================================================================
# Chat tests
# =====================================================================

class TestChat:
    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_simple_text_response(self, mock_cls: MagicMock) -> None:
        """Chat should return text from a simple end_turn response."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_text_response("Hello!")

        client = ClaudeClient(api_key="sk-test")
        result = client.chat("Hi")

        assert result == "Hello!"
        assert len(client.messages) == 2  # user + assistant

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_message_accumulation(self, mock_cls: MagicMock) -> None:
        """Messages should accumulate across multiple chat calls."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _make_text_response("First"),
            _make_text_response("Second"),
        ]

        client = ClaudeClient(api_key="sk-test")
        client.chat("msg1")
        client.chat("msg2")

        # user1 + assistant1 + user2 + assistant2
        assert len(client.messages) == 4

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_tool_dispatch_loop(self, mock_cls: MagicMock) -> None:
        """Should dispatch tool, feed result back, then return final text."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # First call: model wants to use a tool
        # Second call: model gives final answer
        mock_client.messages.create.side_effect = [
            _make_tool_use_response("my_tool", {"x": 1}),
            _make_text_response("Done!"),
        ]

        client = ClaudeClient(api_key="sk-test")
        client.register_tool(
            name="my_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=lambda data: f"result: {data['x']}",
        )

        result = client.chat("Do something")
        assert result == "Done!"
        assert mock_client.messages.create.call_count == 2

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_multiple_tool_calls_in_one_response(self, mock_cls: MagicMock) -> None:
        """Should handle multiple tool_use blocks in a single response."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Build response with 2 tool use blocks
        tool1 = MagicMock()
        tool1.type = "tool_use"
        tool1.name = "tool_a"
        tool1.input = {"q": "hello"}
        tool1.id = "toolu_a"

        tool2 = MagicMock()
        tool2.type = "tool_use"
        tool2.name = "tool_b"
        tool2.input = {"q": "world"}
        tool2.id = "toolu_b"

        multi_tool_msg = MagicMock()
        multi_tool_msg.content = [tool1, tool2]
        multi_tool_msg.stop_reason = "tool_use"
        multi_tool_msg.usage = _make_usage(input_tokens=10, output_tokens=20)

        mock_client.messages.create.side_effect = [
            multi_tool_msg,
            _make_text_response("All done"),
        ]

        client = ClaudeClient(api_key="sk-test")
        client.register_tool("tool_a", "A", {"type": "object"}, lambda d: "a_result")
        client.register_tool("tool_b", "B", {"type": "object"}, lambda d: "b_result")

        result = client.chat("Use both tools")
        assert result == "All done"

        # Check that tool results were sent back
        last_user_msg = None
        for msg in client.messages:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                last_user_msg = msg
        assert last_user_msg is not None
        tool_results = [
            b for b in last_user_msg["content"] if b.get("type") == "tool_result"
        ]
        assert len(tool_results) == 2

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_unknown_tool_raises(self, mock_cls: MagicMock) -> None:
        """Should raise KeyError when model calls an unregistered tool."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_tool_use_response(
            "nonexistent", {}
        )

        client = ClaudeClient(api_key="sk-test")
        with pytest.raises(KeyError, match="nonexistent"):
            client.chat("Call a ghost tool")

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_handler_error_returns_error_result(self, mock_cls: MagicMock) -> None:
        """Handler exceptions should be returned as is_error tool results."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.side_effect = [
            _make_tool_use_response("bad_tool", {}),
            _make_text_response("Handled error"),
        ]

        def failing_handler(data):
            raise ValueError("Something broke")

        client = ClaudeClient(api_key="sk-test")
        client.register_tool("bad_tool", "Fails", {"type": "object"}, failing_handler)

        result = client.chat("Try the bad tool")
        assert result == "Handled error"

        # Verify error was sent back
        tool_result_msg = client.messages[2]  # user -> assistant -> tool_result -> ...
        assert tool_result_msg["role"] == "user"
        tool_result = tool_result_msg["content"][0]
        assert tool_result["is_error"] is True
        assert "Something broke" in tool_result["content"]

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_max_tool_rounds_raises(self, mock_cls: MagicMock) -> None:
        """Should raise RuntimeError when max_tool_rounds is exceeded."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Always return tool_use — never end_turn
        mock_client.messages.create.return_value = _make_tool_use_response(
            "loop_tool", {}
        )

        client = ClaudeClient(api_key="sk-test", max_tool_rounds=3)
        client.register_tool(
            "loop_tool", "Loops", {"type": "object"}, lambda d: "ok"
        )

        with pytest.raises(RuntimeError, match="max_tool_rounds"):
            client.chat("Loop forever")


# =====================================================================
# Structured output tests
# =====================================================================

class TestStructuredOutput:
    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_returns_validated_pydantic_model(self, mock_cls: MagicMock) -> None:
        """Should return a validated Pydantic instance."""

        class MyOutput(BaseModel):
            name: str
            score: int

        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.return_value = _make_tool_use_response(
            "respond", {"name": "TestCard", "score": 42}
        )

        client = ClaudeClient(api_key="sk-test")
        result = client.structured_output("Give me output", MyOutput)

        assert isinstance(result, MyOutput)
        assert result.name == "TestCard"
        assert result.score == 42

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_forces_tool_choice(self, mock_cls: MagicMock) -> None:
        """Should pass tool_choice forcing the output tool."""

        class Simple(BaseModel):
            value: str

        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.return_value = _make_tool_use_response(
            "respond", {"value": "hello"}
        )

        client = ClaudeClient(api_key="sk-test")
        client.structured_output("Test", Simple)

        # Check the create call used tool_choice
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("tool_choice") == {
            "type": "tool",
            "name": "respond",
        }

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_conversation_continues_after(self, mock_cls: MagicMock) -> None:
        """Message history should include structured output interaction."""

        class Simple(BaseModel):
            value: str

        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.return_value = _make_tool_use_response(
            "respond", {"value": "hello"}
        )

        client = ClaudeClient(api_key="sk-test")
        client.structured_output("Test", Simple)

        # Should have: user, assistant (tool_use), user (tool_result)
        assert len(client.messages) == 3
        assert client.messages[0]["role"] == "user"
        assert client.messages[1]["role"] == "assistant"
        assert client.messages[2]["role"] == "user"


# =====================================================================
# Token usage tests
# =====================================================================

class TestTokenUsage:
    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_cumulative_tracking(self, mock_cls: MagicMock) -> None:
        """Token usage should accumulate across calls."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.side_effect = [
            _make_text_response("A", input_tokens=100, output_tokens=50),
            _make_text_response("B", input_tokens=200, output_tokens=75),
        ]

        client = ClaudeClient(api_key="sk-test")
        client.chat("msg1")
        client.chat("msg2")

        assert client.usage.input_tokens == 300
        assert client.usage.output_tokens == 125
        assert client.usage.api_calls == 2

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_cache_token_tracking(self, mock_cls: MagicMock) -> None:
        """Cache creation and read tokens should accumulate separately."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.side_effect = [
            # First call: cache miss → cache write
            _make_text_response(
                "A",
                input_tokens=50,
                output_tokens=20,
                cache_creation_input_tokens=1000,
                cache_read_input_tokens=None,
            ),
            # Second call: cache hit
            _make_text_response(
                "B",
                input_tokens=50,
                output_tokens=30,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=1000,
            ),
        ]

        client = ClaudeClient(api_key="sk-test")
        client.chat("msg1")
        client.chat("msg2")

        assert client.usage.input_tokens == 100
        assert client.usage.output_tokens == 50
        assert client.usage.cache_creation_input_tokens == 1000
        assert client.usage.cache_read_input_tokens == 1000
        assert client.usage.api_calls == 2
        assert client.usage.total_input_tokens == 100 + 1000 + 1000

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_api_calls_count_tool_loops(self, mock_cls: MagicMock) -> None:
        """api_calls should count each round-trip, including tool loops."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.side_effect = [
            _make_tool_use_response("my_tool", {}),   # round-trip 1
            _make_tool_use_response("my_tool", {}),   # round-trip 2
            _make_text_response("Done"),               # round-trip 3
        ]

        client = ClaudeClient(api_key="sk-test")
        client.register_tool("my_tool", "t", {"type": "object"}, lambda d: "ok")
        client.chat("Go")

        assert client.usage.api_calls == 3

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_reset_clears_all_fields(self, mock_cls: MagicMock) -> None:
        """Reset should clear all usage fields including cache tokens."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.messages.create.return_value = _make_text_response(
            "Hi",
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=500,
            cache_read_input_tokens=200,
        )

        client = ClaudeClient(api_key="sk-test")
        client.chat("msg")

        assert client.usage.input_tokens == 100
        assert client.usage.cache_creation_input_tokens == 500
        assert client.usage.cache_read_input_tokens == 200
        assert client.usage.api_calls == 1

        client.reset()

        assert client.usage.input_tokens == 0
        assert client.usage.output_tokens == 0
        assert client.usage.cache_creation_input_tokens == 0
        assert client.usage.cache_read_input_tokens == 0
        assert client.usage.api_calls == 0
        assert len(client.messages) == 0

    def test_cost_usd_sonnet(self) -> None:
        """Cost calculation for Sonnet model."""
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=500_000,
            cache_creation_input_tokens=200_000,
            cache_read_input_tokens=800_000,
        )
        # Sonnet: $3/MTok input, $15/MTok output, $3.75/MTok cache write, $0.30/MTok cache read
        cost = usage.cost_usd("claude-sonnet-4-20250514")
        expected = (
            1_000_000 * 3.0       # input
            + 500_000 * 15.0      # output
            + 200_000 * 3.75      # cache write
            + 800_000 * 0.30      # cache read
        ) / 1_000_000
        assert cost == pytest.approx(expected)
        assert cost == pytest.approx(11.49)

    def test_cost_usd_opus(self) -> None:
        """Cost calculation for Opus model."""
        usage = TokenUsage(input_tokens=100_000, output_tokens=50_000)
        # Opus: $5/MTok input, $25/MTok output
        cost = usage.cost_usd("claude-opus-4-6-20250219")
        expected = (100_000 * 5.0 + 50_000 * 25.0) / 1_000_000
        assert cost == pytest.approx(expected)
        assert cost == pytest.approx(1.75)

    def test_cost_usd_haiku(self) -> None:
        """Cost calculation for Haiku model."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
        # Haiku 4.5: $1/MTok input, $5/MTok output
        cost = usage.cost_usd("claude-haiku-4-5-20251001")
        assert cost == pytest.approx(6.0)

    def test_cost_usd_unknown_model_raises(self) -> None:
        """Unknown model should raise ValueError."""
        usage = TokenUsage(input_tokens=100)
        with pytest.raises(ValueError, match="Unknown model"):
            usage.cost_usd("gpt-4-turbo")

    def test_total_input_tokens(self) -> None:
        """total_input_tokens should sum all three input categories."""
        usage = TokenUsage(
            input_tokens=100,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=300,
        )
        assert usage.total_input_tokens == 600

    def test_cost_usd_zero_tokens(self) -> None:
        """Zero usage should produce zero cost."""
        usage = TokenUsage()
        assert usage.cost_usd("claude-sonnet-4-20250514") == 0.0
        assert usage.total_input_tokens == 0

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_structured_output_tracks_usage(self, mock_cls: MagicMock) -> None:
        """structured_output() should accumulate tokens and api_calls."""

        class Simple(BaseModel):
            value: str

        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_tool_use_response(
            "respond", {"value": "hi"},
            input_tokens=500, output_tokens=100,
            cache_read_input_tokens=2000,
        )

        client = ClaudeClient(api_key="sk-test")
        client.structured_output("Test", Simple)

        assert client.usage.input_tokens == 500
        assert client.usage.output_tokens == 100
        assert client.usage.cache_read_input_tokens == 2000
        assert client.usage.api_calls == 1


# =====================================================================
# Tool registration tests
# =====================================================================

class TestRegisterTool:
    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_pydantic_model_auto_converts(self, mock_cls: MagicMock) -> None:
        """Pydantic model input_schema should be converted to JSON schema."""

        class MyInput(BaseModel):
            name: str
            count: int

        client = ClaudeClient(api_key="sk-test")
        client.register_tool("test", "desc", MyInput, lambda d: "ok")

        tool_def = client._tools["test"]
        assert "properties" in tool_def.input_schema
        assert "name" in tool_def.input_schema["properties"]
        assert "count" in tool_def.input_schema["properties"]

    @patch("sts_gen.agents.client.anthropic.Anthropic")
    def test_dict_passthrough(self, mock_cls: MagicMock) -> None:
        """Dict input_schema should be passed through as-is."""
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}

        client = ClaudeClient(api_key="sk-test")
        client.register_tool("test", "desc", schema, lambda d: "ok")

        tool_def = client._tools["test"]
        assert tool_def.input_schema is schema
