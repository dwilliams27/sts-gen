# Roadmap: Phases 3-6 (Revised Ordering)

> **Context**: Phases 1-2 are complete. We have a working simulation engine with full Act 1 Ironclad content (80 cards, 25 enemies, 14 relics, 11 potions), a HeuristicAgent achieving ~8% Act 1 win rate, and 539 passing tests. See `docs/FOUNDATION.md` for the original architecture and `CLAUDE.md` for current state.

## Why Reorder?

The original plan (FOUNDATION.md) sequenced phases as: Content Gen → Balance Loop → Mod Builder → Expansion. This front-loads all the automation infrastructure before you can see results in-game. The revised ordering closes the feedback loop faster:

**Old**: 3 (LLM) → 4 (Balance) → 5 (Mod Builder) → 6 (Expansion)
**New**: 3A (Baselines) → 3B (Content Gen) → 4 (Mod Builder) → 5 (Balance Loop) → 6 (Expansion)

The key insight: you want to be *playing* generated mods as early as possible. The automated balance loop is most useful after you've manually seen what the LLM gets right and wrong.

---

## Phase 3A: Vanilla Baselines & Balance Metrics

**Goal**: Build the statistical analysis infrastructure and establish ground-truth baselines from vanilla content. No LLM needed — this is mechanical work that validates the sim and produces data the LLM agents will need as context.

**Work**:

1. **Batch baseline runs** — 50k full Act 1 runs with HeuristicAgent, collecting full telemetry
2. **Per-card impact metrics**:
   - Win rate delta when card is in deck vs. not
   - Pick rate (how often the agent takes each card from rewards)
   - Play rate (how often a card is played when drawn)
   - Damage-per-energy and block-per-energy efficiency
3. **Deck archetype analysis**:
   - Cluster winning decks by composition
   - Identify which card combinations over/under-perform
4. **Synergy detection**:
   - For card pairs, compare co-occurrence win rate vs. independence assumption
   - Flag strong positive synergies and degenerate combos
5. **Baseline report format** — structured output (JSON + human-readable summary) that LLM agents can consume as context
6. **Power curve analysis** — how card value changes by floor (early-game vs. late-game picks)

**Output**: `sts_gen/balance/` module with metrics, baselines, and reports. Pre-computed baseline data in `data/vanilla/baselines/`.

**Depends on**: Phase 2 (sim engine, HeuristicAgent) ✅

**Exit gate**: Vanilla baseline report generated; per-card win rate deltas are plausible (e.g., Offering/Demon Form high impact, Strike/Defend low impact); synergy detection finds known combos (Barricade + Entrench, Corruption + Feel No Pain).

---

## Phase 3B: Content Generation — LLM Agents Producing Valid IR

**Goal**: LLM agents generate novel card/relic/potion content as valid IR that loads into the simulator and produces plausible balance metrics.

**Work**:

1. **Agent infrastructure**:
   - Claude API client with structured outputs (Pydantic response schemas)
   - Tool execution loop (agents can request sim runs, query baselines)
   - Conversation management for multi-turn agent sessions
2. **Designer agent**:
   - System prompt with IR schema, vanilla examples, design heuristics
   - Vanilla baselines as context ("here's what balanced looks like")
   - Input: design brief (archetype, theme, constraints)
   - Output: ContentSet IR (cards, relics, potions, keywords)
3. **Critic agent**:
   - Pre-simulation sanity check
   - Cost curve validation (is a 1-cost card doing 3-cost work?)
   - Keyword density check (too many/few keywords)
   - Upgrade quality check (upgrades should be meaningful but not mandatory)
   - Cross-reference against vanilla baselines
4. **Validation pipeline**:
   - IR schema validation (Pydantic)
   - Semantic validation (all status refs resolve, targets valid, costs legal)
   - Sim loading test (content loads and runs without errors)
   - Quick balance screen (100 runs, check for obvious outliers)

**Depends on**: Phase 3A (baselines for context and validation)

**Exit gate**: Designer produces valid IR from a design brief; content loads into sim and runs 1,000 combats without errors; Critic catches intentionally-broken content (overcosted cards, missing upgrade, dead keywords).

---

## Phase 4: Mod Builder — Playable JAR Output

**Goal**: Transpile IR into a playable STS mod (JAR file) that loads via ModTheSpire/BaseMod.

> Moved up from original Phase 5. This is deterministic, low-risk work that's independent of LLM quality. Building it early means you can play-test generated content in the real game as soon as Phase 3B produces it.

**Work**:

1. **IR → Java transpilers** (one per content type):
   - Card transpiler: `CardDefinition` → `CustomCard extends CustomCard`
   - Action transpiler: `ActionNode` tree → sequence of `AbstractGameAction` calls
   - Relic transpiler: `RelicDefinition` → `CustomRelic extends CustomRelic`
   - Potion transpiler: `PotionDefinition` → `CustomPotion extends CustomPotion`
   - Status/Power transpiler: `StatusEffectDefinition` → `AbstractPower` subclass
   - Keyword transpiler: `KeywordDefinition` → tooltip registration
2. **Jinja2 templates**:
   - Card, relic, potion, power Java source templates
   - Mod initializer (`@SpireInitializer` class)
   - `pom.xml` for Maven build
   - `ModTheSpire.json` manifest
3. **Localization generator** — card text, descriptions, tooltips as JSON resource files
4. **Placeholder art** — simple geometric/text-based card and relic images
5. **Maven build orchestration** — invoke Maven to compile and package JAR
6. **Validation**: generated mod for vanilla Ironclad subset loads in STS, cards appear in library

**Depends on**: IR schema ✅ (no sim or LLM dependency)

**Exit gate**: A mod generated from a small IR content set (3-5 cards, 1 relic) loads in STS via ModTheSpire; cards appear in the card library; playing them in combat produces the correct effects.

---

## Phase 5: Balance Loop — Iterative Refinement with Convergence

**Goal**: Close the automated refinement loop: generate → simulate → analyze → refine → repeat until balanced.

> Moved from original Phase 4. Built last because it benefits from manual experience with what the LLM actually gets wrong (from Phases 3B + 4).

**Work**:

1. **Experiment Planner agent**:
   - Input: balance report + iteration history
   - Output: what simulations to run next (deck compositions, encounter types, sample sizes)
   - Multi-turn: can request results, interpret, request more
2. **Refiner agent**:
   - Input: IR + balance data + history
   - Output: revised ContentSet IR with specific adjustments
   - Tracks what was changed and why (prevents oscillation)
3. **Red Team agent**:
   - Probes for degenerate combos, infinite loops, trivializing strategies
   - Tests specific scenarios (e.g., "what if the player gets 3 copies of this card?")
4. **Refinement loop orchestration**:
   ```
   content = designer.generate(brief)
   content = critic.review(content)
   while not converged(content, iteration):
       plan = experimenter.plan(content, history)
       results = simulator.run(content, plan)
       analysis = analyzer.analyze(results)
       red_team = red_team_agent.probe(content, analysis)
       content = refiner.refine(content, analysis, red_team, history)
       iteration += 1
   mod = builder.build(content)
   ```
5. **Convergence criteria** (all must hold for 2 consecutive iterations):
   - Win rate within vanilla baseline +/- 5 percentage points
   - No card pick rate below 5% (dead card) or above 85% (auto-pick)
   - No degenerate strategies detected by Red Team
   - Power curve variance above minimum floor (prevents flat/boring designs)
   - Hard cap: 10 iterations
6. **History tracking** — full audit trail of changes, preventing buff/nerf oscillation

**Depends on**: Phase 3A (baselines), Phase 3B (content gen agents), Phase 4 (mod builder for in-game validation)

**Exit gate**: System runs 3-5 refinement iterations from a design brief, converges to a balanced content set, and outputs a playable mod JAR. Balance metrics are within target bands.

---

## Phase 6: Expansion & Polish

**Goal**: Broaden coverage and improve quality across all dimensions.

**Work** (not strictly ordered — pick based on value):

- **Acts 2-3 simulation**: new enemies, encounters, map generation, boss fights
- **Other characters**: Silent, Defect, Watcher card pools + starter decks
- **MCTS play-test agent**: higher-quality play testing for better balance signal
- **Custom character generation**: entirely new character classes (not just content for existing ones)
- **AI art generation**: card art, relic icons beyond placeholders
- **Web UI**: interactive design sessions, balance visualization dashboards
- **CommunicationMod integration**: round-trip validation comparing sim predictions vs. real game outcomes

**Depends on**: Phases 3-5

---

## Dependency Graph

```
Phase 1 (IR + Core Sim) ─────────────────────────────────────── ✅
    │
Phase 2 (Full Act 1) ────────────────────────────────────────── ✅
    │
    ├── Phase 3A (Vanilla Baselines)
    │       │
    │       ├── Phase 3B (Content Gen Agents)
    │       │       │
    │       │       ├── Phase 5 (Balance Loop)
    │       │       │
    │       │   Phase 4 (Mod Builder) ◄── IR schema ✅
    │       │       │
    │       │       └── [play-test generated mods in real STS]
    │       │
    │       └── Phase 5 (Balance Loop)
    │
    └── Phase 4 (Mod Builder) ◄── can start in parallel with 3A
            │
            Phase 6 (Expansion)
```

Note: Phase 4 (Mod Builder) only depends on the IR schema, not the sim or LLM agents. It *can* start in parallel with Phase 3A if desired, but the value of play-testing mods is highest once content generation is working.

---

## Estimated Scope

| Phase | Key deliverable | Rough size |
|-------|----------------|------------|
| 3A | Vanilla baselines + balance metrics module | Medium — mostly data pipeline |
| 3B | Designer + Critic agents producing valid IR | Large — LLM integration, prompt engineering |
| 4 | IR → JAR mod builder | Medium-Large — Java transpilation, templates |
| 5 | Automated refinement loop with convergence | Medium — orchestration of existing pieces |
| 6 | Acts 2-3, other characters, MCTS, polish | Large — ongoing |
