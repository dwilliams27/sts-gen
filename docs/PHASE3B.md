# Phase 3B: Content Generation — LLM Agents Producing Valid IR

## Goal

LLM agents generate novel card/relic/potion content as valid IR that loads into the simulator, runs without errors, and — critically — represents a *coherent, fun character* with a clear identity, overlapping archetypes, and a signature mechanic.

**Depends on**: Phase 3A (baselines for context and validation) ✅

**Exit gate**: Designer produces valid IR from a design brief; content loads into sim and runs 1,000 combats without errors; Critic identifies structural design problems; at least one generated character feels like a real STS mod when you read its card pool.

---

## Design Philosophy

### Why hierarchical generation matters

Every great STS character mod shares a structure:

1. **One signature mechanic** that creates a new decision axis (not a reskin of existing ones)
2. **2-3 overlapping archetypes** where 30%+ of cards bridge multiple builds
3. **Setup/payoff structure** at every rarity tier
4. **Early-game viability** before synergies come online

Bad mods skip this hierarchy and jump to "generate 75 cards." The result: bimodal power curves, keyword dilution, derivative design, no identity. The agent architecture must make it structurally impossible to skip from "theme" to "cards" without going through "mechanic → archetypes → skeleton → cards."

### IR expressibility as a hard constraint

The IR can express all 80 vanilla Ironclad cards via 23 action types, 12 status triggers, conditionals, for-each loops, and custom status effects. But it cannot express:

- Selective card manipulation ("choose a card to exhaust")
- Complex scaling ("damage = hand size × 3 + strength")
- Multi-turn queuing ("next turn, replay your hand")
- Arbitrary condition expressions ("if 2+ Strength AND played Attack this turn")

The Designer must be scoped to the expressible space. Novel mechanics should be implemented as **compositions of existing primitives** — primarily custom status effects with triggers and actions. If a mechanic can't be expressed, we note it for future IR extension rather than hacking around it.

### What makes cards fun (design principles for the prompt)

- **Novel verbs over bigger numbers.** "Exhaust a curse to gain X" is a new verb. "Deal 14 instead of 12" is not.
- **Partial solutions.** Every card should solve *some* problems, not all. Cards must create tradeoffs.
- **Context-dependent value.** No card should be correct in >80% of situations. Value should depend on build/board state.
- **Risk/reward.** 15-20% of cards should involve meaningful risk (self-damage, self-debuff, curse generation).
- **Discovery moments.** Synergies between cards that aren't explicitly labeled — they emerge from mechanical interaction.

---

## Architecture

### Agent Roles

| Agent | Type | Purpose |
|-------|------|---------|
| **Designer** | Multi-turn, tool-using | Generates content through enforced stages |
| **Critic** | Single-turn review | Structural design quality analysis |
| **Validation Pipeline** | Code (not LLM) | IR + semantic + sim load + balance screen |

### Designer Agent (multi-stage)

The Designer is a multi-turn agent that goes through enforced stages. Each stage produces structured output that becomes input to the next.

**Stage 1: Concept**
- Input: Design brief (theme, fantasy, constraints)
- Output: Character name, fantasy, signature mechanic (1 sentence), proof it maps to IR primitives (status effect + trigger sketch)
- Gate: Mechanic must be expressible as a StatusEffectDefinition with existing trigger types and action primitives

**Stage 2: Architecture**
- Input: Concept + IR capabilities + vanilla baselines
- Output: 2-3 major archetypes, 2-4 minor archetypes, overlap map (which cards bridge which archetypes), card skeleton (roles per archetype per rarity)
- Gate: Each archetype has ≥3 setup + ≥3 payoff roles. ≥30% of card roles serve 2+ archetypes.

**Stage 3: Keywords & Status Definitions**
- Input: Architecture
- Output: StatusEffectDefinitions for signature mechanic + sub-mechanics, KeywordDefinitions for player-facing terms
- Gate: Each keyword has 8-15 card roles referencing it. Status defs validate against IR schema.

**Stage 4: Card Pool**
- Input: Architecture + keywords + status defs + vanilla baselines
- Output: Full CardDefinition IR for each card (~20 common, ~35 uncommon, ~16 rare, + basics/status), RelicDefinitions (3-5), PotionDefinitions (2-3)
- Gate: All IR validates. Card count per rarity matches vanilla distribution.

**Stage 5: Self-Review**
- Input: Complete ContentSet
- Output: Revised ContentSet with Designer's own corrections before Critic handoff

### Critic Agent (structural review)

Receives the complete ContentSet + baselines. Returns a scored critique covering:

| Check | Target | Why |
|-------|--------|-----|
| Archetype overlap | ≥30% bridge cards | Prevents parallel-track builds with no interesting draft decisions |
| Setup/payoff ratio | ≥3 each per archetype at C/U | Prevents feast-or-famine builds |
| Keyword density | 8-15 cards per keyword | Prevents dilution (too few) or monotony (too many) |
| Power curve shape | Bell curve, not bimodal | Prevents god-cards + trash, ensures contextual value |
| Early-game plan | Starter + 2-3 commons survive Act 1 | Prevents "only works in Act 3" frustration |
| Novel verb count | ≥30% cards with non-trivial effects | Prevents "deal N / gain N" filler |
| Derivative detection | Compare effects to vanilla pool | Flags reskins with different numbers |
| Thematic coherence | Names + mechanics align | Prevents wallpaper theming |
| Block access | Adequate common block cards | Prevents "no defense" characters |
| Cost curve | Energy costs match effect power | Prevents over/under-costed cards |

Returns actionable feedback: "Archetype B has no common-rarity payoff cards — add a common Attack that scales with [keyword] stacks."

### Validation Pipeline (code)

1. **IR schema validation** — Pydantic model_validate on all definitions
2. **Semantic validation** — all status/card/keyword refs resolve, no undefined references
3. **IR expressibility check** — no TRIGGER_CUSTOM with unknown conditions, all condition strings in supported set
4. **Sim load test** — content loads into ContentRegistry without errors
5. **Quick balance screen** — 100-1000 runs with HeuristicAgent, flag cards with 0 plays or 100% play rate

### The Loop

```
Designer (stages 1-5) → Validation → Critic → Designer revises → Validation → Critic
(max 3 Designer-Critic iterations)
```

---

## Implementation Plan

### Files to Create

| File | Purpose |
|------|---------|
| `src/sts_gen/agents/__init__.py` | Agent package |
| `src/sts_gen/agents/client.py` | Claude API client with structured outputs |
| `src/sts_gen/agents/tools.py` | Tool definitions (query baselines, validate IR, run sims) |
| `src/sts_gen/agents/designer.py` | Designer agent (multi-stage generation) |
| `src/sts_gen/agents/critic.py` | Critic agent (structural review) |
| `src/sts_gen/agents/prompts/` | System prompts as markdown/text files |
| `src/sts_gen/agents/prompts/designer_system.md` | Designer system prompt (IR schema, examples, principles) |
| `src/sts_gen/agents/prompts/critic_system.md` | Critic system prompt (quality checks, baselines) |
| `src/sts_gen/agents/validation.py` | Semantic validation + expressibility checking |
| `src/sts_gen/agents/pipeline.py` | End-to-end pipeline: Designer → Validate → Critic → loop |
| `tests/agents/` | Test suite |
| `scripts/generate_content.py` | CLI: design brief → ContentSet IR |

### Files to Modify

| File | Change |
|------|--------|
| `src/sts_gen/ir/content_set.py` | May need validation helpers for semantic checking |
| `CLAUDE.md` | Add agents module to architecture |
| `COMMAND.md` | Add content generation commands |

### Sub-phases

**3B-1: Agent Infrastructure** (~day 1)
- Claude API client with structured outputs (Pydantic response schemas)
- Tool definitions (query baselines, validate IR snippet, run quick sim)
- Conversation management for multi-turn Designer sessions

**3B-2: Designer Agent** (~days 2-3)
- System prompt with IR schema, vanilla examples, design principles, expressibility guide
- Multi-stage generation flow (concept → architecture → keywords → cards → self-review)
- Structured output schemas for each stage
- Tool use: query baselines, check vanilla similarity

**3B-3: Validation Pipeline** (~day 2, parallel with Designer)
- Semantic validation (ref resolution, condition checking)
- Sim load test (register content, run combat)
- Quick balance screen

**3B-4: Critic Agent** (~day 3)
- System prompt with quality checks, baselines, vanilla distribution targets
- Structural analysis logic (some checks are code, some are LLM judgment)
- Actionable feedback format

**3B-5: Pipeline + CLI** (~day 4)
- End-to-end: brief → Designer → Validate → Critic → revise loop
- CLI script for running generation
- Test suite

---

## Key Design Decisions

### Structured outputs vs. free-form

Use Pydantic response schemas with Claude's structured output mode for each Designer stage. This ensures the LLM produces valid JSON that we can programmatically process. Free-form text is only used for descriptions and flavor.

### How much IR schema goes in the prompt?

The full ActionType enum + CardDefinition schema + StatusEffectDefinition schema + 5-10 vanilla card examples showing diverse compositions. The prompt should also include a "cookbook" of common patterns:
- "To make a scaling buff: create a StatusEffectDefinition with ON_TURN_START trigger"
- "To make a card that rewards exhaust: use FOR_EACH exhaust_count"
- "To make a conditional effect: CONDITIONAL with has_status:YourKeyword"

### How to handle the HeuristicAgent's limitations?

The HeuristicAgent was built for vanilla Ironclad. It won't know how to play novel mechanics well. For Phase 3B, this is acceptable — we're checking that content is *valid and loadable*, not perfectly balanced. The quick balance screen will show whether cards are played at all, not whether they're optimally valued. Phase 5 addresses play quality.

### What if the LLM proposes an inexpressible mechanic?

Stage 1 includes an IR expressibility gate. If the mechanic can't map to existing primitives, the Designer must revise the concept. The prompt includes explicit examples of expressible vs. inexpressible patterns. We don't extend the IR during 3B — we note the demand for future work.

---

## Out of Scope

- **Balance refinement loop** (Phase 5) — no Experiment Planner, Refiner, or Red Team
- **IR extensions** — if Designer hits expressibility walls, note for later
- **Mod building** (Phase 4) — validate via simulation only
- **Custom play agents** — HeuristicAgent is sufficient for validation
- **Multi-character support** — generate for Ironclad's card pool slot initially
