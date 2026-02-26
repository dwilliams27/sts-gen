"""Designer agent -- multi-stage LLM pipeline that generates a complete ContentSet.

Takes a design brief and produces cards, relics, potions, keywords, and status
effects through 5 enforced stages, using tools for reference and structured
outputs for gate validation at each stage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from sts_gen.ir.content_set import ContentSet
from sts_gen.sim.content.registry import ContentRegistry

from .client import ClaudeClient, TokenUsage
from .schemas import (
    ArchitectureOutput,
    CardPoolOutput,
    ConceptOutput,
    KeywordsOutput,
)
from .tools import ToolContext, register_all_tools

# Default directory for run artifacts
_DEFAULT_RUNS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "runs"


def _load_prompt() -> str:
    """Load designer system prompt from prompts/designer_system.md."""
    prompt_path = Path(__file__).parent / "prompts" / "designer_system.md"
    return prompt_path.read_text()


class DesignerAgent:
    """Multi-stage content generation agent.

    Parameters
    ----------
    registry:
        Loaded ContentRegistry for tool handlers to query vanilla content.
    baseline_path:
        Path to a saved VanillaBaseline JSON file.
    model:
        Anthropic model ID.
    api_key:
        Anthropic API key (falls back to ANTHROPIC_API_KEY env var).
    max_retries:
        Maximum retries per stage on validation failure.
    """

    def __init__(
        self,
        *,
        registry: ContentRegistry,
        baseline_path: Path,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        max_retries: int = 3,
        run_dir: Path | None = None,
    ) -> None:
        prompt_text = _load_prompt()
        self._client = ClaudeClient(
            model=model,
            system_prompt=prompt_text,
            max_tokens=64000,
            api_key=api_key,
        )
        self._ctx = ToolContext(registry=registry, baseline_path=baseline_path)
        register_all_tools(self._client, self._ctx)
        self._max_retries = max_retries

        # Set up artifact directory for this run
        if run_dir is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            run_dir = _DEFAULT_RUNS_DIR / ts
        self._run_dir = run_dir

    def generate(self, brief: str) -> ContentSet:
        """Run all 5 stages and return a complete ContentSet.

        Parameters
        ----------
        brief:
            Free-text design brief describing the desired character.

        Returns
        -------
        ContentSet
            Validated content set ready for simulation or transpilation.
        """
        # Save brief for reference
        self._run_dir.mkdir(parents=True, exist_ok=True)
        (self._run_dir / "brief.txt").write_text(brief)

        concept = self._stage_concept(brief)
        self._save_artifact("1_concept", concept)

        architecture = self._stage_architecture(concept)
        self._save_artifact("2_architecture", architecture)

        keywords = self._stage_keywords(concept, architecture)
        self._save_artifact("3_keywords", keywords)

        card_pool = self._stage_card_pool(concept, architecture, keywords)
        self._save_artifact("4_card_pool", card_pool)

        content_set = self._stage_assemble(concept, keywords, card_pool)
        self._save_artifact("5_content_set", content_set)

        return content_set

    @property
    def usage(self) -> TokenUsage:
        """Cumulative token usage across all API calls."""
        return self._client.usage

    @property
    def run_dir(self) -> Path:
        """Directory where this run's artifacts are saved."""
        return self._run_dir

    def _save_artifact(self, name: str, data: BaseModel | ContentSet) -> Path:
        """Save a Pydantic model as JSON to the run directory."""
        self._run_dir.mkdir(parents=True, exist_ok=True)
        path = self._run_dir / f"{name}.json"
        path.write_text(data.model_dump_json(indent=2))
        return path

    # ------------------------------------------------------------------
    # Stage 1: Concept
    # ------------------------------------------------------------------

    def _stage_concept(self, brief: str) -> ConceptOutput:
        self._client.chat(
            f"<design_brief>\n{brief}\n</design_brief>\n\n"
            "Stage 1: Develop a character concept. Use query_baseline and "
            "list_vanilla_cards to understand the design space. Think about:\n"
            "- What fantasy does the player inhabit?\n"
            "- What is the signature mechanic (a custom status effect)?\n"
            "- What 2-3 archetypes will the character support?\n\n"
            "Explore freely, then I'll ask for your structured concept."
        )

        return self._extract_with_retry(
            "Provide your concept using the required schema. "
            "The mechanic_status_effect must be a complete, valid "
            "StatusEffectDefinition with proper triggers and actions.",
            ConceptOutput,
            "submit_concept",
        )

    # ------------------------------------------------------------------
    # Stage 2: Architecture
    # ------------------------------------------------------------------

    def _stage_architecture(self, concept: ConceptOutput) -> ArchitectureOutput:
        self._client.chat(
            f"Stage 2: Design the architecture for {concept.character_name}.\n\n"
            f"Character fantasy: {concept.fantasy}\n"
            f"Signature mechanic: {concept.signature_mechanic}\n"
            f"Archetype seeds: {', '.join(concept.archetype_seeds)}\n\n"
            "Design 2-4 archetypes with setup/payoff roles, then create a "
            "card skeleton of ~70 role slots matching the vanilla distribution "
            "(3 basic, ~20 common, ~35 uncommon, ~16 rare, ~5 status/curse). "
            "Use get_vanilla_card_detail to see how vanilla archetypes work.\n\n"
            "Think through the design, then I'll ask for structured output."
        )

        return self._extract_with_retry(
            "Provide your architecture using the required schema.",
            ArchitectureOutput,
            "submit_architecture",
        )

    # ------------------------------------------------------------------
    # Stage 3: Keywords & Status Effects
    # ------------------------------------------------------------------

    def _stage_keywords(
        self, concept: ConceptOutput, architecture: ArchitectureOutput
    ) -> KeywordsOutput:
        archetype_names = [a.name for a in architecture.archetypes]
        self._client.chat(
            f"Stage 3: Define keywords and status effects for "
            f"{concept.character_name}.\n\n"
            f"Archetypes: {', '.join(archetype_names)}\n\n"
            "Create ALL custom StatusEffectDefinitions needed for the "
            "character's mechanics. This includes:\n"
            "- The signature mechanic status\n"
            "- Supporting statuses for archetypes\n"
            "- **Every status that any Power card will apply_status with** — "
            "in STS, Power cards work by applying a status to the player. "
            "That status must have a StatusEffectDefinition with triggers "
            "that implement the Power's ongoing effect. For example, Demon Form "
            "applies the 'Demon Form' status which has an ON_TURN_START trigger.\n\n"
            "Also create KeywordDefinitions for player-facing tooltip terms.\n\n"
            "Each StatusEffectDefinition must have proper triggers with "
            "valid ActionNode trees. Use the IR cookbook in the system "
            "prompt for reference patterns.\n\n"
            "Think through the design, then I'll ask for structured output."
        )

        return self._extract_with_retry(
            "Provide your keywords and status effects using the required schema.",
            KeywordsOutput,
            "submit_keywords",
        )

    # ------------------------------------------------------------------
    # Stage 4: Card Pool
    # ------------------------------------------------------------------

    def _stage_card_pool(
        self,
        concept: ConceptOutput,
        architecture: ArchitectureOutput,
        keywords: KeywordsOutput,
    ) -> CardPoolOutput:
        status_ids = [s.id for s in keywords.status_effects]
        status_names = [s.name for s in keywords.status_effects]
        self._client.chat(
            f"Stage 4: Generate the full card pool for "
            f"{concept.character_name}.\n\n"
            f"Available custom status IDs: {', '.join(status_ids)}\n"
            f"Available custom status names: {', '.join(status_names)}\n\n"
            "CRITICAL: Every status_name used in apply_status actions MUST "
            "be either a vanilla status (Strength, Vulnerable, Weak, etc.) "
            "or one of the custom statuses listed above. Do NOT invent new "
            "status names in card actions — use ONLY statuses defined in "
            "Stage 3. Power cards should apply_status using one of the "
            "custom status IDs or names above.\n\n"
            "Generate ALL cards matching the card skeleton from Stage 2, "
            "plus 3-5 relics and 2-3 potions. Every card must have:\n"
            "- Valid ActionNode actions using only supported conditions\n"
            "- Proper upgrade definitions\n"
            "- Correct type/rarity/cost/target\n"
            "- ID format: mod_id:CardName\n\n"
            "Use query_baseline to check balance reference points. "
            "Think through the design, then I'll ask for structured output."
        )

        return self._extract_with_retry(
            "Provide your card pool using the required schema.",
            CardPoolOutput,
            "submit_card_pool",
        )

    # ------------------------------------------------------------------
    # Stage 5: Assembly & Validation
    # ------------------------------------------------------------------

    def _stage_assemble(
        self,
        concept: ConceptOutput,
        keywords: KeywordsOutput,
        card_pool: CardPoolOutput,
    ) -> ContentSet:
        # Derive mod_id from character name
        mod_id = concept.character_name.lower().replace(" ", "_")
        status_ids = [s.id for s in keywords.status_effects]
        status_names = [s.name for s in keywords.status_effects]

        for attempt in range(self._max_retries):
            try:
                content_set = ContentSet(
                    mod_id=mod_id,
                    mod_name=concept.character_name,
                    cards=card_pool.cards,
                    relics=card_pool.relics,
                    potions=card_pool.potions,
                    keywords=keywords.keywords,
                    status_effects=keywords.status_effects,
                )
                return content_set.prune_unused_statuses()
            except (ValidationError, ValueError) as exc:
                if attempt == self._max_retries - 1:
                    raise
                # Re-extract card pool with error feedback embedded in the
                # structured_output prompt (avoids chat() where the model
                # might try to call previous forced tools).
                card_pool = self._extract_with_retry(
                    f"Stage 5: ContentSet assembly failed with errors:\n\n"
                    f"{exc}\n\n"
                    f"Available custom status IDs: {', '.join(status_ids)}\n"
                    f"Available custom status names: {', '.join(status_names)}\n\n"
                    "Fix the card pool so every status_name in apply_status "
                    "actions is either a vanilla status or one of the custom "
                    "statuses listed above. Provide the corrected card pool.",
                    CardPoolOutput,
                    "submit_card_pool",
                )

        # Unreachable, but satisfies type checker
        raise RuntimeError("Assembly failed after max retries")  # pragma: no cover

    # ------------------------------------------------------------------
    # Shared retry logic
    # ------------------------------------------------------------------

    def _extract_with_retry(
        self,
        prompt: str,
        schema: type,
        tool_name: str,
    ) -> object:
        """Extract structured output with retry on validation failure."""
        for attempt in range(self._max_retries):
            try:
                return self._client.structured_output(
                    prompt, schema, output_tool_name=tool_name
                )
            except (ValidationError, RuntimeError) as exc:
                if attempt == self._max_retries - 1:
                    raise
                self._client.chat(
                    f"Validation error: {exc}\nPlease fix and try again."
                )
        raise RuntimeError("Unreachable")  # pragma: no cover
