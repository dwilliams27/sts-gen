"""Claude API client -- multi-turn conversation manager with tool dispatch.

Wraps the Anthropic SDK to provide:
- Multi-turn conversation management
- Automatic tool call dispatch
- Structured output via forced tool_choice
- Cumulative token usage tracking
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic
from pydantic import BaseModel


@dataclass
class TokenUsage:
    """Cumulative token usage across all API calls.

    Tracks all five billing-relevant token buckets from the Anthropic API:

    - ``input_tokens``: Base input tokens (non-cached).
    - ``output_tokens``: Generated output tokens.
    - ``cache_creation_input_tokens``: Tokens written to prompt cache
      (billed at 1.25x base input rate for 5-min cache).
    - ``cache_read_input_tokens``: Tokens read from prompt cache
      (billed at 0.1x base input rate).
    - ``api_calls``: Number of raw API round-trips (including tool
      dispatch loops within a single ``chat()`` call).
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    api_calls: int = 0

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens across all categories.

        Equal to ``input_tokens + cache_creation_input_tokens +
        cache_read_input_tokens``.  This is the sum the API docs
        describe as the "total input tokens" for a request.
        """
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def cost_usd(self, model: str) -> float:
        """Estimate total USD cost based on model pricing.

        Uses official Anthropic per-MTok rates (as of 2025-02).
        Cache writes assume 5-minute TTL pricing.

        Parameters
        ----------
        model:
            Model ID string (e.g. ``"claude-sonnet-4-20250514"``).
            Matched by prefix to handle dated model IDs.

        Returns
        -------
        float
            Estimated cost in USD.

        Raises
        ------
        ValueError
            If the model is not recognized.
        """
        rates = _get_model_rates(model)
        return (
            self.input_tokens * rates["input"]
            + self.output_tokens * rates["output"]
            + self.cache_creation_input_tokens * rates["cache_write"]
            + self.cache_read_input_tokens * rates["cache_read"]
        ) / 1_000_000


# Per-MTok pricing (USD).  Cache writes use 5-minute TTL rates.
# Source: https://platform.claude.com/docs/en/about-claude/pricing
_MODEL_RATES: dict[str, dict[str, float]] = {
    "opus-4": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "sonnet-4": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "haiku-4": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.10},
    "haiku-3": {"input": 0.25, "output": 1.25, "cache_write": 0.30, "cache_read": 0.03},
}


def _get_model_rates(model: str) -> dict[str, float]:
    """Look up pricing rates for a model ID.

    Matches by searching for known model family prefixes within the
    model string to handle dated IDs like ``"claude-sonnet-4-20250514"``.
    """
    model_lower = model.lower()
    # Check from most specific to least specific
    for key, rates in _MODEL_RATES.items():
        if key in model_lower:
            return rates
    raise ValueError(
        f"Unknown model for cost estimation: {model!r}. "
        f"Known families: {list(_MODEL_RATES.keys())}"
    )


@dataclass
class _ToolDef:
    """Internal tool registration record."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]


class ClaudeClient:
    """Multi-turn conversation manager wrapping the Anthropic SDK.

    Handles tool dispatch automatically: when the model calls a registered
    tool, the handler runs and results are fed back until the model produces
    a final text response.

    Parameters
    ----------
    model:
        Anthropic model ID.
    system_prompt:
        System prompt prepended to every API call.
    max_tokens:
        Maximum tokens per API response.
    temperature:
        Sampling temperature (0.0 = deterministic).
    api_key:
        Anthropic API key.  Falls back to ``ANTHROPIC_API_KEY`` env var.
    max_tool_rounds:
        Safety limit on consecutive tool dispatch loops.
    """

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        api_key: str | None = None,
        max_tool_rounds: int = 20,
    ) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No API key provided. Pass api_key= or set ANTHROPIC_API_KEY."
            )

        self._client = anthropic.Anthropic(api_key=resolved_key)
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_tool_rounds = max_tool_rounds

        self._messages: list[dict[str, Any]] = []
        self._tools: dict[str, _ToolDef] = {}
        self._usage = TokenUsage()

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: type[BaseModel] | dict,
        handler: Callable[[dict[str, Any]], str],
    ) -> None:
        """Register a tool the model can call.

        Parameters
        ----------
        name:
            Tool name (must be unique).
        description:
            Description shown to the model.
        input_schema:
            Pydantic model (auto-converted via ``model_json_schema()``)
            or raw JSON schema dict.
        handler:
            Function that takes the tool input dict and returns a string result.
        """
        if isinstance(input_schema, type) and issubclass(input_schema, BaseModel):
            schema = input_schema.model_json_schema()
        else:
            schema = input_schema

        self._tools[name] = _ToolDef(
            name=name,
            description=description,
            input_schema=schema,
            handler=handler,
        )

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def chat(self, user_message: str) -> str:
        """Send a user message, handle tool calls automatically, return final text.

        The method loops: if the model responds with tool_use blocks,
        handlers are dispatched and results fed back until the model
        produces an end_turn with text.

        Raises
        ------
        RuntimeError
            If ``max_tool_rounds`` is exceeded.
        KeyError
            If the model calls an unregistered tool.
        """
        self._messages.append({"role": "user", "content": user_message})
        return self._run_loop()

    def structured_output(
        self,
        user_message: str,
        output_schema: type[BaseModel],
        output_tool_name: str = "respond",
    ) -> BaseModel:
        """Force a structured response matching a Pydantic schema.

        Registers a temporary tool with the given schema and forces the
        model to call it via ``tool_choice``.  The tool input is validated
        against the Pydantic model and returned.

        Parameters
        ----------
        user_message:
            The user message to send.
        output_schema:
            Pydantic model class defining the expected output.
        output_tool_name:
            Name for the forced tool.
        """
        schema = output_schema.model_json_schema()

        # Build the forced tool definition
        forced_tool = {
            "name": output_tool_name,
            "description": f"Return a structured response matching the {output_schema.__name__} schema.",
            "input_schema": schema,
        }

        self._messages.append({"role": "user", "content": user_message})

        # Make API call with forced tool_choice
        api_tools = self._build_tool_params() + [forced_tool]
        response = self._call_api(
            tools=api_tools,
            tool_choice={"type": "tool", "name": output_tool_name},
        )

        # Extract the tool use block
        tool_input = None
        for block in response.content:
            if block.type == "tool_use" and block.name == output_tool_name:
                tool_input = block.input
                break

        if tool_input is None:
            raise RuntimeError(
                f"Model did not call the forced tool '{output_tool_name}'."
            )

        # Validate via Pydantic
        result = output_schema.model_validate(tool_input)

        # Append assistant message to history so conversation can continue
        self._messages.append({"role": "assistant", "content": response.content})

        # Append a synthetic tool_result so the API stays happy
        for block in response.content:
            if block.type == "tool_use" and block.name == output_tool_name:
                self._messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "OK",
                    }],
                })
                break

        return result

    def reset(self) -> None:
        """Clear conversation history and token usage."""
        self._messages.clear()
        self._usage = TokenUsage()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def usage(self) -> TokenUsage:
        """Cumulative token usage across all API calls."""
        return self._usage

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Current conversation history (read-only view)."""
        return list(self._messages)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_tool_params(self) -> list[dict[str, Any]]:
        """Convert registered tools to API tool parameter format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    def _call_api(
        self,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
    ) -> anthropic.types.Message:
        """Make a single API call and track token usage."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": self._messages,
        }

        if self._system_prompt:
            kwargs["system"] = self._system_prompt

        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = self._client.messages.create(**kwargs)

        # Track usage — all five billing-relevant token buckets
        self._usage.input_tokens += response.usage.input_tokens
        self._usage.output_tokens += response.usage.output_tokens
        self._usage.cache_creation_input_tokens += (
            response.usage.cache_creation_input_tokens or 0
        )
        self._usage.cache_read_input_tokens += (
            response.usage.cache_read_input_tokens or 0
        )
        self._usage.api_calls += 1

        return response

    def _run_loop(self) -> str:
        """Run the chat loop: call API, dispatch tools, repeat until end_turn."""
        tools = self._build_tool_params() or None

        for _ in range(self._max_tool_rounds):
            response = self._call_api(tools=tools)

            if response.stop_reason == "end_turn":
                # Extract text from content blocks
                text_parts = [
                    block.text
                    for block in response.content
                    if block.type == "text"
                ]
                text = "\n".join(text_parts)

                # Append assistant message to history
                self._messages.append(
                    {"role": "assistant", "content": response.content}
                )
                return text

            if response.stop_reason == "tool_use":
                # Append the full assistant message (may contain text + tool_use)
                self._messages.append(
                    {"role": "assistant", "content": response.content}
                )

                # Dispatch each tool call
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    if block.name not in self._tools:
                        raise KeyError(
                            f"Model called unknown tool: {block.name!r}. "
                            f"Registered tools: {list(self._tools.keys())}"
                        )

                    tool_def = self._tools[block.name]
                    try:
                        result_str = tool_def.handler(block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        })
                    except Exception as exc:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {exc}",
                            "is_error": True,
                        })

                # Append tool results as a user message
                self._messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason — return whatever text we have
                text_parts = [
                    block.text
                    for block in response.content
                    if block.type == "text"
                ]
                self._messages.append(
                    {"role": "assistant", "content": response.content}
                )
                return "\n".join(text_parts)

        raise RuntimeError(
            f"Exceeded max_tool_rounds ({self._max_tool_rounds}). "
            f"The model may be stuck in a tool call loop."
        )
