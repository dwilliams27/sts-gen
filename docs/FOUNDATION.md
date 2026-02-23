# sts-gen: AI-Powered Slay the Spire Mod Generator

## Context

Slay the Spire (STS) is a roguelike deckbuilder with deep, tightly-balanced mechanics that has spawned a thriving modding ecosystem. Creating a *good* mod -- one that is fun, thematically coherent, and balanced -- is hard. It requires understanding intricate card interactions, energy economics, scaling curves across 3 acts, and synergy patterns that emerge from hundreds of possible deck combinations.

This project builds a system where AI agents design, simulate-test, iteratively refine, and package STS mods. The key differentiator is the **simulation-driven feedback loop**: agents don't just generate content -- they generate hypotheses about what would be fun and balanced, prove or disprove those hypotheses through thousands of simulated games, and refine until convergence. This is a scientific process, not a one-shot generation.

---

## Goals

1. **Generate playable STS mods** -- JAR files that load via ModTheSpire/BaseMod and work in the real game
2. **Ensure balance** -- Generated content should have win rates, pick rates, and power curves comparable to vanilla STS
3. **Maximize fun** -- Cards should create interesting decisions, enable novel archetypes, and have satisfying synergies
4. **Prove properties via simulation** -- Every balance claim is backed by statistical evidence from thousands of simulated runs
5. **Support iteration** -- Agents can plan multi-experiment campaigns, run simulations, interpret results, and refine across multiple rounds

---

## System Architecture Overview

```
                         ┌───────────────────┐
                         │   Orchestrator /   │
                         │       CLI          │
                         └────────┬──────────┘
                                  │
          ┌───────────┬───────────┼───────────┬────────────┐
          │           │           │           │            │
          ▼           ▼           ▼           ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ Content  │ │   Sim    │ │ Balance  │ │ Refine   │ │   Mod    │
   │   Gen    │ │  Engine  │ │ Analysis │ │   Loop   │ │ Builder  │
   │  Agents  │ │          │ │          │ │          │ │          │
   └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
        │             │           │             │            │
        └──────┬──────┴─────┬─────┘             │            │
               ▼            ▼                   │            ▼
        ┌────────────┐ ┌───────────┐            │     ┌────────────┐
        │ Content IR │ │ Experiment│◄───────────┘     │ Java + JAR │
        │  (JSON)    │ │  Store    │                  │   Output   │
        └────────────┘ └───────────┘                  └────────────┘
```

**Data flow**: Design Brief → Designer Agent → Content IR → Critic Agent → Simulator → Balance Analyzer → Experiment Planner → Refiner Agent → (loop until converged) → Mod Builder → Playable JAR

---

## The Six Subsystems

### 1. Intermediate Representation (IR) — `sts_gen/ir/`

The shared data contract everything else depends on. Pydantic models defining:

- **ContentSet** — top-level container: mod id, name, cards, relics, potions, keywords
- **CardDefinition** — type, rarity, cost, target, base stats, description, action tree, upgrade definition
- **ActionNode** — tree of primitive effects (the card's "what it does"). Uses a fixed vocabulary of ~20 primitives: `deal_damage`, `gain_block`, `apply_status`, `draw_cards`, `gain_energy`, `conditional`, `for_each`, etc.
- **RelicDefinition** — tier, trigger events, effect actions
- **PotionDefinition** — rarity, potency, effect actions
- **KeywordDefinition / StatusEffectDefinition** — novel mechanics with triggers and stacking behavior

The primitive action vocabulary was chosen by analyzing all 300+ vanilla STS cards — every one decomposes into these primitives. Novel cards compose them in new ways. A `trigger_custom` escape hatch exists for truly exotic mechanics but should rarely be needed.

### 2. Simulation Engine — `sts_gen/sim/`

A headless Python replica of STS mechanics. This is the linchpin of the whole system.

**Core mechanics to implement:**
- Damage calculation (strength, vulnerable, weak, multi-hit)
- Block (application, decay, dexterity, frail)
- Energy system (gain, spend, conservation)
- Card piles (draw, hand, discard, exhaust — shuffle, draw, manipulation)
- Status effects (full lifecycle: apply, stack, decay, trigger, remove)
- Targeting (single enemy, all enemies, self, random)

**Content registries:**
- Vanilla cards, relics, potions, enemies (loaded from `data/vanilla/` JSON files)
- Custom content (loaded from IR at runtime — the key extensibility mechanism)

**Dungeon simulation:**
- Procedural map generation per act
- Run manager (3-act progression, floor types, boss selection)
- Card rewards, gold, shops, rest sites, events

**The Interpreter** — the critical bridge between IR and simulation. Reads ActionNode trees and dispatches to mechanics at runtime. No pre-compiled card classes needed. Novel cards from the LLM "just work" because they compose the same primitives. Custom status effects register triggers that fire on game events and produce action lists.

**Play-test agents** (AI players that exercise the content):
- **RandomAgent** — random valid actions (baseline, fast)
- **HeuristicAgent** — rule-based scoring (primary workhorse, port logic from Bottled AI's approach: weighted board state evaluation, priority card selection)
- **MCTSAgent** — Monte Carlo Tree Search (higher quality, slower, Phase 6)

**Performance target:** 10,000+ runs per evaluation cycle. Strategy: `multiprocessing.Pool` across cores, combat-only screening mode, optional Cython for hot paths. Estimated ~25s for 10k runs on 8 cores.

### 3. Content Generation Agents — `sts_gen/agents/`

LLM-powered agents (Claude API with structured outputs + tool use). No heavyweight framework — direct API calls with Pydantic response schemas.

**Agent roles:**

| Agent | Input | Output | Purpose |
|-------|-------|--------|---------|
| **Designer** | Design brief (archetype, character, constraints) | ContentSet IR | Generate initial card/relic/potion ideas |
| **Critic** | ContentSet IR | CritiqueReport (scored issues) | Pre-simulation sanity check: cost curves, keyword density, upgrade quality |
| **Experiment Planner** | Balance report + history | ExperimentPlan | Decide what simulations to run next |
| **Refiner** | IR + balance data + history | Revised ContentSet IR | Adjust numbers, redesign cards based on evidence |
| **Red Team** | IR + balance report | RedTeamReport | Find degenerate combos, infinite loops, trivializing strategies |

Agents have **tool access** to the simulator (run batches, query results, get vanilla baselines, analyze synergies). The Experiment Planner and Refiner support **multi-turn conversations** where they request simulations, interpret results, and request more — enabling longer-horizon experimental campaigns.

### 4. Balance Analysis — `sts_gen/balance/`

Statistical framework consuming simulation telemetry:

**Key metrics:**
- Win rate (overall + per-card-in-deck)
- Card pick rate and play rate
- Damage-per-energy and block-per-energy efficiency
- Average turns per combat, HP lost per fight
- Floor reached distribution

**Synergy detection:** For each card pair, compare co-occurrence win rate against independence assumption. Flag positive synergies (good — indicates archetype coherence) and degenerate synergies (pair win rate > 2x baseline).

**Red-team checks:** Infinite loops (net-positive resource cycles within a turn), one-card-army scenarios (single card drafted multiple times → 80%+ win rate), zero-decision decks.

**Vanilla baselines:** Pre-computed from 50k+ vanilla simulation runs. All generated content is measured relative to these.

### 5. Iterative Refinement Loop — `sts_gen/refinement/`

The orchestration of generate → test → refine cycles:

```
content = designer.generate(brief)
content = critic.review(content)

while not converged(content, iteration):
    plan = experimenter.plan(content, history)
    for experiment in plan:
        results = simulator.run(content, experiment)
        analysis = analyzer.analyze(results)
    red_team = red_team_agent.probe(content, analysis)
    content = refiner.refine(content, analysis, red_team, history)
    content = critic.review(content)
    iteration += 1
```

**Convergence criteria** (all must hold for 2 consecutive iterations):
1. Win rate within target band (vanilla baseline ± 5pp)
2. No card pick rate below 5% (dead card) or above 85% (auto-pick)
3. No degenerate strategies detected
4. Power curve variance below threshold
5. Max 10 iterations (hard cap)

History tracking prevents oscillation (buff→nerf→buff cycles). Variance floor prevents convergence to boring flat designs where every card is equally mediocre.

### 6. Mod Builder — `sts_gen/mod_builder/`

Transpiles finalized IR into a playable STS mod:

- **Transpilers** — one per content type. Each IR primitive maps to a known STS Java action class (e.g., `deal_damage` → `DamageAction`, `apply_status` → `ApplyPowerAction`). For `trigger_custom` escape hatches, generates custom `AbstractGameAction` subclasses.
- **Jinja2 templates** — card, relic, potion, power, mod initializer, pom.xml, ModTheSpire.json
- **Localization generator** — card text, relic descriptions, keyword tooltips as JSON
- **Placeholder art** — simple geometric card/relic art (optional AI art generation in later phases)
- **Maven builder** — invokes Maven to compile and package the JAR

---

## Technology Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Core language | Python 3.11+ | LLM ecosystem, data science, matches existing STS AI projects |
| Output language | Java 8 (generated) | Required by ModTheSpire/BaseMod |
| LLM | Claude API (Opus/Sonnet) | Structured outputs, tool use, reasoning quality |
| Schema/validation | Pydantic v2 | IR contract, Claude structured output integration |
| Java build | Maven | Standard STS mod toolchain |
| Python tooling | uv + pyproject.toml | Modern, fast package management |
| Parallelism | multiprocessing | Embarrassingly parallel simulation runs |
| Storage | SQLite (SQLAlchemy) | Zero-config experiment tracking |
| Templating | Jinja2 | Java source generation |
| CLI | Typer | Type-hint-driven CLI |
| Testing | pytest | Standard |

---

## Project Structure

```
sts-gen/
  pyproject.toml
  src/sts_gen/
    ir/                    # Pydantic IR schemas (ContentSet, CardDefinition, ActionNode, ...)
    sim/
      core/                # GameState, BattleState, ActionQueue, RNG
      mechanics/           # damage, block, energy, card_piles, status_effects, targeting
      content/             # Card/relic/enemy/encounter registries (vanilla + custom)
      dungeon/             # Map gen, run manager, rewards, shop
      play_agents/         # RandomAgent, HeuristicAgent, MCTSAgent
      interpreter.py       # ActionNode tree interpreter
      runner.py            # Batch simulation executor
      telemetry.py         # Per-run data collection
    agents/
      designer.py          # Content generation agent
      critic.py            # Pre-simulation review agent
      experimenter.py      # Experiment planning agent
      refiner.py           # Evidence-based refinement agent
      red_team.py          # Degenerate strategy finder
      prompts/             # System prompts as markdown files
      tools.py             # Tool definitions for agent tool-use
    balance/               # Metrics, baselines, synergy detection, power curves, reports
    refinement/            # Loop controller, convergence criteria, history tracking
    mod_builder/
      transpiler/          # IR → Java transpilers (card, relic, potion, action, power)
      templates/           # Jinja2 Java source templates
      localization/        # String/tooltip generators
      art/                 # Placeholder + optional AI art
      builder.py           # Maven build orchestration
    orchestrator/          # Pipeline runner, config, state machine
    cli/                   # Typer CLI entry point + command modules
    store/                 # SQLite experiment/content storage
  tests/                   # Mirrors src/ structure
  data/
    vanilla/               # All vanilla STS content in IR format (cards, relics, enemies, baselines)
    examples/              # Example generated content sets
  output/                  # Git-ignored: experiment DBs, built JARs, reports
```

---

## Phased Build Order

### Phase 1: Foundation — IR + Minimal Combat Simulation
- Define complete IR schema (Pydantic models, validation, tests)
- Implement simulation core: GameState, BattleState, ActionQueue, RNG
- Implement core mechanics: damage, block, energy, card piles, basic status effects
- Implement ActionNode interpreter
- Implement ~20 vanilla Ironclad cards + 2-3 enemy types
- RandomAgent + batch runner + telemetry
- **Exit gate:** 1,000 single-combat simulations with Ironclad starter deck, collecting damage/block/turn telemetry

### Phase 2: Simulation Depth — Full Act 1 Runs
- All Ironclad cards, all Act 1 enemies/encounters
- Map generator, run manager, rewards, shop
- Relics and potions in simulation
- HeuristicAgent (port Bottled AI scoring approach)
- Remaining status effects and complex card patterns (X-cost, exhaust, retain)
- **Exit gate:** 10,000 full Act 1 runs in <5 min, heuristic agent achieves plausible win rates

### Phase 3: Content Generation — LLM Agents Producing Valid IR
- Agent infrastructure (Claude API client, tool execution loop)
- Curate vanilla card data into `data/vanilla/cards.json`
- Designer agent (system prompt + IR schema + examples + design heuristics)
- Critic agent (cost-efficiency bounds, keyword density, upgrade quality)
- **Exit gate:** Designer produces valid IR that loads into simulator without errors; Critic catches obvious balance violations

### Phase 4: Balance Loop — Iterative Refinement with Convergence
- Balance analyzer with full metric suite
- Synergy detection and red-team checks
- Compute vanilla baselines from 50k+ simulation runs
- Experiment Planner, Refiner, and Red Team agents
- Refinement loop with convergence criteria
- **Exit gate:** System runs 3-5 refinement iterations from a design brief and converges to balanced content set

### Phase 5: Mod Builder — Playable JAR Output
- All transpilers (card, relic, potion, action, power, keyword)
- Jinja2 templates tested against actual BaseMod API
- Localization generator, placeholder art
- Maven build orchestration
- **Exit gate:** Generated mod loads in STS via ModTheSpire, cards appear in library, function correctly in combat

### Phase 6: Expansion & Polish
- Full Acts 2-3 simulation with all content
- MCTS play-test agent
- Silent, Defect, Watcher character support
- AI art generation
- Web UI for interactive design sessions
- Custom character generation (new character classes, not just content for existing ones)

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Simulation fidelity** — divergence from real STS behavior | Content tests well in sim but plays wrong in-game | Verify edge cases against decompiled STS source; validation suite comparing sim vs real game via CommunicationMod |
| **LLM hallucination** — syntactically valid but semantically broken IR | Cards reference nonexistent status effects or impossible conditions | Semantic validation pass checking all references resolve; Critic agent catches these; Refiner fixes on retry |
| **Simulation speed** — Python too slow for 10k+ runs/cycle | Refinement loop takes hours per iteration | multiprocessing parallelism; combat-only screening mode; Cython for hot paths if needed |
| **Balance oscillation** — buff/nerf cycles that never converge | System never terminates or produces mediocre flat designs | Full history tracking prevents reverts; variance floor ensures interesting spread; 10-iteration hard cap |
| **Java transpilation** — generated code doesn't compile or behaves differently from sim | Mod doesn't work despite passing simulation | Test suite of known IR→Java mappings; round-trip test via CommunicationMod comparing sim predictions vs actual game |
| **Play-test agent quality** — bot can't use complex cards effectively, skewing metrics | Strong cards appear weak because bot misplays them | Multiple agent types (heuristic + MCTS + random); weight pick-rate metrics over win-rate; flag disagreements for review |
| **Novel mechanic expressiveness** — primitive vocabulary too limited for creative ideas | Boring cards that only use basic effects | Vocabulary covers all 300+ vanilla cards; conditional/for_each provide combinatorial depth; promote recurring escape-hatch patterns to first-class primitives over time |

---

## Verification Plan

After each phase, verify with:
1. **Unit tests** — pytest suite mirroring src/ structure
2. **Integration tests** — end-to-end pipeline segments (IR → sim, IR → Java, brief → IR → sim → report)
3. **Baseline comparison** — simulation metrics for vanilla content should match known STS balance data
4. **Round-trip testing** (Phase 5+) — generated mod loaded in real STS via CommunicationMod, outcomes compared to simulator predictions
5. **Human review** — interactive mode lets a human inspect generated content, balance reports, and final mod before packaging
