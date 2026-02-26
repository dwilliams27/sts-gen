"""Tool definitions and handlers for LLM agents.

Each tool = Pydantic input schema + handler function.  Handlers operate
on a shared ``ToolContext`` that holds the registry, baseline path, and
simulation config.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from sts_gen.sim.content.registry import ContentRegistry

from .client import ClaudeClient


# =====================================================================
# Tool context
# =====================================================================

@dataclass
class ToolContext:
    """Shared state for tool handlers."""

    registry: ContentRegistry
    baseline_path: Path | None = None
    sim_runs: int = 100


# =====================================================================
# Input schemas (Pydantic models)
# =====================================================================

class QueryBaselineInput(BaseModel):
    """No input required."""
    pass


class ValidateContentSetInput(BaseModel):
    """JSON string of a ContentSet IR to validate."""
    content_set_json: str


class RunQuickSimInput(BaseModel):
    """Run simulations with custom content."""
    content_set_json: str
    num_runs: int = 100


class ListVanillaCardsInput(BaseModel):
    """No input required."""
    pass


class GetVanillaCardDetailInput(BaseModel):
    """Get full details for a vanilla card."""
    card_id: str


# =====================================================================
# Handlers
# =====================================================================

def _handle_query_baseline(ctx: ToolContext, _input: dict[str, Any]) -> str:
    """Return LLM context string from vanilla baseline."""
    if ctx.baseline_path is None:
        raise ValueError(
            "No baseline path configured. Generate a baseline first "
            "with `python -m sts_gen.balance.baselines`."
        )

    from sts_gen.balance.baselines import load_baseline
    from sts_gen.balance.report import generate_llm_context

    baseline = load_baseline(ctx.baseline_path)
    return generate_llm_context(baseline)


def _handle_validate_content_set(
    ctx: ToolContext, input_data: dict[str, Any]
) -> str:
    """Parse and validate a ContentSet JSON string."""
    from sts_gen.ir.content_set import ContentSet

    raw_json = input_data["content_set_json"]

    # Step 1: Parse JSON
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"valid": False, "errors": [f"Invalid JSON: {exc}"]})

    # Step 2: Validate against Pydantic schema
    try:
        content_set = ContentSet.model_validate(data)
    except Exception as exc:
        errors = []
        for line in str(exc).split("\n"):
            line = line.strip()
            if line:
                errors.append(line)
        return json.dumps({"valid": False, "errors": errors})

    # Step 3: Try loading into a fresh registry to catch deeper issues
    try:
        test_registry = ContentRegistry()
        test_registry.load_content_set(content_set)
    except Exception as exc:
        return json.dumps({
            "valid": False,
            "errors": [f"Registry load error: {exc}"],
        })

    return json.dumps({"valid": True, "errors": []})


def _handle_run_quick_sim(
    ctx: ToolContext, input_data: dict[str, Any]
) -> str:
    """Run quick simulations with custom content mixed into vanilla."""
    from sts_gen.balance.metrics import compute_card_metrics, compute_global_metrics
    from sts_gen.ir.content_set import ContentSet
    from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
    from sts_gen.sim.runner import BatchRunner

    raw_json = input_data["content_set_json"]
    num_runs = input_data.get("num_runs", ctx.sim_runs)

    # Parse and validate
    try:
        data = json.loads(raw_json)
        content_set = ContentSet.model_validate(data)
    except Exception as exc:
        return json.dumps({"error": f"Invalid content set: {exc}"})

    # Build a fresh registry with vanilla + custom
    registry = ContentRegistry()
    registry.load_vanilla_cards()
    registry.load_vanilla_enemies()
    registry.load_vanilla_encounters()
    registry.load_vanilla_status_effects()
    registry.load_vanilla_relics()
    registry.load_vanilla_potions()
    registry.load_content_set(content_set)

    # Run simulations
    try:
        runner = BatchRunner(registry, agent_class=HeuristicAgent)
        results = runner.run_full_act_batch(n_runs=num_runs, base_seed=42)
    except Exception as exc:
        return json.dumps({"error": f"Simulation error: {exc}"})

    # Compute metrics
    global_metrics = compute_global_metrics(results)
    all_card_metrics = compute_card_metrics(results, global_metrics.win_rate)

    # Filter to just custom card IDs
    custom_card_ids = {card.id for card in content_set.cards}
    custom_metrics = [
        m for m in all_card_metrics if m.card_id in custom_card_ids
    ]

    return json.dumps({
        "global": global_metrics.model_dump(),
        "custom_cards": [m.model_dump() for m in custom_metrics],
        "num_runs": num_runs,
    })


def _handle_list_vanilla_cards(
    ctx: ToolContext, _input: dict[str, Any]
) -> str:
    """Return summary of all vanilla cards."""
    cards = []
    for card_id in sorted(ctx.registry.cards):
        card = ctx.registry.cards[card_id]
        cards.append({
            "id": card.id,
            "name": card.name,
            "type": card.type.value,
            "rarity": card.rarity.value,
            "cost": card.cost,
        })
    return json.dumps(cards)


def _handle_get_vanilla_card_detail(
    ctx: ToolContext, input_data: dict[str, Any]
) -> str:
    """Return full CardDefinition as JSON."""
    card_id = input_data["card_id"]
    card = ctx.registry.get_card(card_id)
    if card is None:
        raise KeyError(f"Unknown card_id: {card_id!r}")
    return card.model_dump_json()


# =====================================================================
# Registration
# =====================================================================

def register_all_tools(client: ClaudeClient, ctx: ToolContext) -> None:
    """Register all standard tools on a client, binding ctx into handlers."""
    import functools

    def _bind(handler):  # noqa: ANN001, ANN202
        """Bind ctx as first argument to a handler."""
        @functools.wraps(handler)
        def wrapper(input_data: dict[str, Any]) -> str:
            return handler(ctx, input_data)
        return wrapper

    client.register_tool(
        name="query_baseline",
        description=(
            "Query the vanilla baseline metrics. Returns win rates, "
            "card pick rates, synergies, and other balance reference data."
        ),
        input_schema=QueryBaselineInput,
        handler=_bind(_handle_query_baseline),
    )

    client.register_tool(
        name="validate_content_set",
        description=(
            "Validate a ContentSet IR JSON string. Checks JSON syntax, "
            "Pydantic schema compliance, status effect references, and "
            "registry loading. Returns {valid: bool, errors: [...]}."
        ),
        input_schema=ValidateContentSetInput,
        handler=_bind(_handle_validate_content_set),
    )

    client.register_tool(
        name="run_quick_sim",
        description=(
            "Run quick Act 1 simulations with custom content mixed into "
            "the vanilla card pool. Returns global metrics and per-card "
            "metrics for the custom cards."
        ),
        input_schema=RunQuickSimInput,
        handler=_bind(_handle_run_quick_sim),
    )

    client.register_tool(
        name="list_vanilla_cards",
        description=(
            "List all vanilla Ironclad cards with id, name, type, rarity, "
            "and cost. Use to understand the existing card pool."
        ),
        input_schema=ListVanillaCardsInput,
        handler=_bind(_handle_list_vanilla_cards),
    )

    client.register_tool(
        name="get_vanilla_card_detail",
        description=(
            "Get the full IR definition of a vanilla card, including "
            "actions, upgrade, keywords, and all properties."
        ),
        input_schema=GetVanillaCardDetailInput,
        handler=_bind(_handle_get_vanilla_card_detail),
    )
