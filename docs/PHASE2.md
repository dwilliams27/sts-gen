# Phase 2: Simulation Depth — Full Act 1 Runs

## Context

Phase 1 built a working combat simulator with 22 Ironclad cards, 3 enemies, and a RandomAgent. Phase 1.5 added a ground-truth validation suite (38 tests) and fixed 5 simulation bugs. Now we need to scale from "basic combat works" to "full Act 1 runs with realistic content."

**The exit gate**: 10,000 full Act 1 runs in <5 min, heuristic agent achieves plausible win rates (50-70%).

**Critical data accuracy concern**: The current 22 cards were authored from Claude's training data. Scaling to ~75 cards amplifies hallucination risk — Gemini already caught wrong stats on Armaments, wrong mechanics on Clash, and missing exhaust on Havoc. **Every card, enemy, relic, and potion must be wiki-verified before entering the JSON.** No stats from memory — all values must come from the STS wiki.

### Wiki-First Verification Protocol

This protocol applies to ALL game data (cards, enemies, relics, potions, status effects):

1. **LOOK UP**: Before implementing any game entity, fetch its STS wiki page via `WebFetch` from `slay-the-spire.fandom.com/wiki/<EntityName>`. Extract exact stats.
2. **IMPLEMENT**: Write the IR JSON definition using only wiki-sourced values.
3. **VERIFY**: After implementation, fetch the wiki page AGAIN and cross-check every number in the JSON against the wiki. Fix any discrepancies.
4. **TEST**: Write a deterministic test that verifies the exact behavior matches wiki-sourced expectations.

**This protocol is a hard gate.** No card/enemy/relic/potion enters `data/vanilla/` without completing all 4 steps. The plan below deliberately avoids listing specific stats — those come from the wiki at implementation time.

**Re-verify existing data**: The 22 cards and 3 enemies already in `data/vanilla/` were authored from memory. Before adding new content in 2B/2C, first wiki-verify all existing entries and fix any discrepancies.

---

## Sub-Phase Order

```
2A: Interpreter Extensions (new ActionTypes, conditions, card mechanics)
 ↓
2B: Full Ironclad Card Pool (~75 cards, wiki-verified)
 ↓ (can overlap with 2C)
2C: Full Act 1 Enemy Pool (~20 enemies + encounters)
 ↓
2D: Status Trigger System (wire StatusTrigger into combat loop)
 ↓
2E: Relics + Potions (starter relic, ~15 relics, ~11 potions)
 ↓
2F: Map Generator + Run Manager (linear Act 1 map, card rewards, rest sites)
 ↓
2G: HeuristicAgent (scoring-based card play + deck building)
 ↓
2H: Integration + Exit Gate (10k runs, performance, verification)
```

---

## Sub-Phase 2A: Interpreter Extensions

**Goal**: Extend ActionNode system to support all Ironclad card patterns before adding the cards.

### 2A.1: New ActionTypes

Add to `ActionType` enum in `src/sts_gen/ir/actions.py`:

| ActionType | Purpose | Cards |
|---|---|---|
| `DOUBLE_BLOCK` | Set block = block × 2 | Entrench |
| `MULTIPLY_STATUS` | Multiply a status's stacks (e.g. ×2) | Limit Break |
| `PLAY_TOP_CARD` | Play top card of a pile, optionally exhaust it | Havoc |

Add handlers in `src/sts_gen/sim/interpreter.py` dispatch table.

### 2A.2: New Conditions

Add to `_evaluate_condition` in interpreter.py:

| Condition | Purpose | Cards |
|---|---|---|
| `only_attacks_in_hand` | True if every card in hand is Attack type | Clash |
| `enemy_intends_attack` | True if chosen target enemy's intent is attack | Spot Weakness |

### 2A.3: New Damage Conditions

Add to `_handle_deal_damage` in interpreter.py:

| Condition | Formula | Cards |
|---|---|---|
| `plus_per_exhaust_N` | base + N × exhaust_pile_size | — |
| `times_from_x_cost` | Use X-cost value as `times` for multi-hit | Whirlwind |

### 2A.4: Play Restriction Field

Add `play_restriction: str | None = None` to `CardDefinition` in `src/sts_gen/ir/cards.py`.

Modify `_get_playable_cards` in `src/sts_gen/sim/runner.py` to check `play_restriction` via the interpreter's `_evaluate_condition`.

### 2A.5: Card Keyword Mechanics in Combat Loop

The `CardDefinition` already has `exhaust`, `ethereal`, `innate`, `retain` boolean fields. Wire them into `src/sts_gen/sim/runner.py`:

- **Exhaust**: After card play, if `card_def.exhaust`, exhaust instead of discard. (Check if already implemented.)
- **Ethereal**: At end of turn, exhaust cards in hand with `ethereal=True` instead of discarding.
- **Innate**: Before first draw, move innate cards to top of draw pile.
- **Retain**: At end of turn, skip discarding cards with `retain=True`.

### 2A.6: X-Cost in REPEAT

When `REPEAT` node has `times=0` (or `times=None`), read `self._x_cost_value` as the repeat count. This enables Whirlwind-style "deal damage X times."

### 2A.7: Exhaust All

Support `value=-1` in `EXHAUST_CARDS` handler to mean "exhaust entire hand." Needed for Fiend Fire.

### Files Modified

| File | Changes |
|---|---|
| `src/sts_gen/ir/actions.py` | Add 3 new ActionTypes |
| `src/sts_gen/ir/cards.py` | Add `play_restriction` field |
| `src/sts_gen/sim/interpreter.py` | New handlers, new conditions, REPEAT X-cost, exhaust-all |
| `src/sts_gen/sim/runner.py` | Play restrictions in `_get_playable_cards`, ethereal/innate/retain in end-of-turn |
| `tests/sim/test_interpreter.py` | Tests for every new handler and condition |
| `tests/sim/test_card_mechanics.py` (NEW) | Tests for exhaust/ethereal/innate/retain |

---

## Sub-Phase 2B: Full Ironclad Card Pool

**Goal**: Add all ~75 Ironclad cards to `data/vanilla/ironclad_cards.json` with wiki-verified stats.

### Data Verification Process

For EVERY card:
1. Fetch the card's STS wiki page via `WebFetch` from `slay-the-spire.fandom.com/wiki/<CardName>`
2. Extract: cost, type, rarity, base damage/block/effect values, upgrade values, keywords (exhaust/ethereal/innate/retain)
3. Write the IR JSON definition
4. Write a deterministic unit test verifying exact behavior

### Card Tiers by Implementation Complexity

**Tier 1 — Expressible now** (~30 cards): Only use existing ActionTypes and conditions.
Pattern examples: ethereal + deal damage, lose HP + deal damage, repeat deal damage, gain energy + exhaust, damage all + add status card to discard, apply status to all + exhaust.

**Tier 2 — Needs 2A extensions** (~20 cards): Need new conditions/ActionTypes from sub-phase 2A.
Pattern examples: play restrictions, double block, multiply strength, X-cost repeat, play top card from pile, conditional on enemy intent, temporary status effects.

**Tier 3 — Needs trigger system from 2D** (~15 cards): Power cards with ongoing triggers.
Pattern examples: turn-start scaling (gain strength/energy per turn), on-exhaust triggers (draw/block when card exhausted), on-attacked triggers (reflect damage), passive modifiers (block doesn't decay).

**Tier 3 cards will have the JSON definition written in 2B but their trigger-based effects won't work until 2D is complete.** Each gets a test marked `@pytest.mark.xfail` until 2D.

### Simplified Cards (acceptable for Phase 2)

Some cards have mechanics too complex for Phase 2's scope. When a card's full mechanic would require disproportionate effort (e.g., upgrading other cards mid-combat, infinite upgrade chains, "next card played" tracking), implement a simplified version that captures the card's primary effect. Mark these with a `# SIMPLIFIED` comment in the JSON. Full fidelity deferred to later phases.

### Status/Curse Cards to Add

Status and curse cards (Burn, Dazed, Slimed, Void, etc.) injected by enemies and cards. All stats wiki-verified — these are often unplayable cards with specific end-of-turn or on-draw effects.

### Files Modified

| File | Changes |
|---|---|
| `data/vanilla/ironclad_cards.json` | Expand from 22 → ~75 entries |
| `tests/sim/test_cards_deterministic.py` (NEW) | One test per card, exact behavior verification |

---

## Sub-Phase 2C: Full Act 1 Enemy Pool

**Goal**: Add all Act 1 enemies with wiki-verified stats, movesets, and AI patterns.

### Enemy List

All stats (HP ranges, damage values, status amounts) must be wiki-verified at implementation time. Listed here are only the enemy names and behavioral patterns needed for implementation planning.

**Normal pool** (3 already exist: Jaw Worm, Cultist, Red Louse):
- Green Louse — weighted_random (attack + apply Weak)
- Acid Slime (S) — sequential (attack + apply status)
- Acid Slime (M) — weighted, **splits at half HP** (needs split mechanic)
- Spike Slime (S) — single_move
- Spike Slime (M) — weighted, **splits at half HP**
- Fungi Beast — weighted (attack + grow strength)
- Looter — fixed_sequence, **escapes after N turns** (needs escape mechanic)
- Blue Slaver — weighted (attack + apply Weak)
- Red Slaver — weighted (attack + apply Vulnerable + one-time Entangle)
- Gremlin (5 types: Mad, Sneaky, Fat, Shield, Wizard) — simple patterns, mostly single_move or sequential

**Elites** (3 total):
- Gremlin Nob — weighted; **enrages when player plays Skill** (needs reactive hook)
- Lagavulin — **sleeps 3 turns then wakes** (needs sleep/wake mechanic); alternating attack/debuff
- Sentries (×3) — **alternating pattern between units** (needs multi-enemy coordination); adds Dazed to deck

**Bosses** (3 total):
- The Guardian — **mode shift at damage threshold** (needs state machine pattern)
- Hexaghost — turn-cycle based pattern; adds Burn to deck
- Slime Boss — **splits at half HP into 2 large slimes** (needs split mechanic)

### New Enemy AI Capabilities

The current `EnemyAI` supports `fixed_sequence`, `weighted_random`, `sequential`. Act 1 needs:

| Capability | Enemies | Implementation |
|---|---|---|
| Split (die + spawn 2 enemies) | Slimes, Slime Boss | New `on_hp_threshold` hook in enemy definition |
| Escape (remove from combat) | Looter | New `on_turn_N` action |
| Reactive (respond to player actions) | Gremlin Nob (enrage on Skill) | New `on_player_card_type` hook |
| Mode switch | The Guardian | State machine in enemy pattern |
| Sleep/wake | Lagavulin | `initial_state: "sleeping"` + wake conditions |

**Implementation**: Add an `event_hooks` field to enemy definitions in JSON. The combat loop fires events at the right times, and enemy hooks respond. Hook types needed: `on_player_skill_played` (reactive buffs), `on_hp_below_half` (split into specific enemy types), `on_turn_N` (escape/wake). All hook values wiki-verified.

### Encounter Definitions

New file: `data/vanilla/encounters.json` with Act 1 encounter compositions:
- Easy pool (floors 1-3): solo Jaw Worm, solo Cultist, 2× Louse, etc.
- Normal pool: mixed slime groups, Gremlin gang, Fungi Beast, Looter
- Elite pool: Gremlin Nob, Lagavulin, Sentries
- Boss pool: Guardian, Hexaghost, Slime Boss

### Boss Simplification (Phase 2)

Full boss fidelity is complex. Acceptable simplifications for Phase 2:
- Guardian: Simplified mode alternation (skip precise damage-threshold tracking)
- Hexaghost: Fixed turn cycle (skip HP-dependent scaling)
- Slime Boss: Split at half HP is the core mechanic — implement this fully

All boss stats and move values must still be wiki-verified even for simplified patterns.

### Files Modified

| File | Changes |
|---|---|
| `data/vanilla/enemies.json` | Expand from 3 → ~20 enemies |
| `data/vanilla/encounters.json` (NEW) | Act 1 encounter compositions |
| `src/sts_gen/sim/runner.py` | Extend EnemyAI: event hooks, split, escape, mode switch, sleep/wake |
| `src/sts_gen/sim/content/registry.py` | Add encounter loading, `get_encounter()` |
| `tests/sim/test_enemies.py` (NEW) | Per-enemy AI pattern tests |

---

## Sub-Phase 2D: Status Trigger System

**Goal**: Wire `StatusTrigger` from the IR into the combat loop so power cards work.

### Current Gap

The IR has `StatusEffectDefinition.triggers: dict[StatusTrigger, list[ActionNode]]` and the mechanics module has `trigger_status()` which looks up definitions and returns action nodes. But **nothing in the combat loop calls `trigger_status()`**. Metallicize and Ritual are hardcoded.

### TriggerDispatcher

New file: `src/sts_gen/sim/mechanics/triggers.py`

```python
class TriggerDispatcher:
    def __init__(self, interpreter, status_defs: dict[str, StatusEffectDefinition]):
        ...

    def fire(self, entity, trigger: StatusTrigger, battle, source, **context):
        """For each status on entity that has this trigger, execute its actions."""
        # Scale action values by stack count for "per_stack" conditions
```

### Integration Points in `CombatSimulator.run_combat`

| Event | Where | Replaces |
|---|---|---|
| `ON_TURN_START` | Start of player turn, start of each enemy turn | Hardcoded Ritual |
| `ON_TURN_END` | End of player turn | Hardcoded Metallicize |
| `ON_CARD_PLAYED` | After interpreter executes card actions | (new) |
| `ON_ATTACKED` | After damage is dealt | (new) |
| `ON_CARD_DRAWN` | After draw_cards | (new) |

### Vanilla Status Effect Definitions

New file: `data/vanilla/status_effects.json`. All stat values must be wiki-verified. Definitions needed for all statuses referenced by Ironclad power cards and enemy abilities. Key trigger categories:

| Trigger | Statuses Using It | Behavior |
|---|---|---|
| ON_TURN_START | Ritual, Demon Form, Brutality, etc. | Gain strength, draw, etc. per stack |
| ON_TURN_END | Metallicize, Combust, etc. | Gain block, deal damage, etc. per stack |
| ON_CARD_EXHAUSTED | Dark Embrace, Feel No Pain | Draw/gain block when any card is exhausted |
| ON_STATUS_DRAWN | Evolve | Draw when a Status card is drawn |
| ON_ATTACKED | Flame Barrier | Deal damage back to attacker |
| ON_ATTACK_PLAYED | Rage | Gain block when Attack card is played |
| ON_BLOCK_GAINED | Juggernaut | Deal damage to random enemy |
| PASSIVE | Barricade | Block doesn't decay at turn start |

Note: `ON_CARD_EXHAUSTED`, `ON_STATUS_DRAWN`, `ON_ATTACK_PLAYED`, `ON_BLOCK_GAINED` are new trigger types needed beyond the current `StatusTrigger` enum. Add them.

### Temporary Effects (Flex, Flame Barrier, Rage)

For effects that last "this turn only," use `decay_per_turn: 1` on the status definition. The status decays to 0 and is removed at end of turn after its ON_TURN_END actions fire.

### Per-Stack Scaling

When triggers fire, the action value needs to scale with stacks. For example, a status with N stacks that grants block per stack should grant N block, not 1. Implementation: the TriggerDispatcher multiplies `node.value` by `stack_count` for nodes with `condition: "per_stack"`.

### Files Modified

| File | Changes |
|---|---|
| `src/sts_gen/ir/status_effects.py` | Add new StatusTrigger values |
| `data/vanilla/status_effects.json` (NEW) | Vanilla status effect definitions |
| `src/sts_gen/sim/mechanics/triggers.py` (NEW) | TriggerDispatcher |
| `src/sts_gen/sim/runner.py` | Replace hardcoded Metallicize/Ritual with TriggerDispatcher calls |
| `src/sts_gen/sim/content/registry.py` | Add `status_defs` loading |
| `tests/sim/test_triggers.py` (NEW) | Trigger dispatch unit tests |
| `tests/sim/test_powers.py` (NEW) | Integration tests for power cards |

---

## Sub-Phase 2E: Relics + Potions

**Goal**: Add starter relic + ~15 combat-relevant relics + ~11 potions. Focus is on correct in-combat behavior; acquisition is loosely emulated (elite/treasure drops, shop purchases are just random picks from a pool).

### Relics

All relic stats must be wiki-verified at implementation time. Target ~15 combat-relevant relics covering these trigger categories:

| Trigger Type | Example Relics | Capability Needed |
|---|---|---|
| on_combat_start | Vajra, Oddly Smooth Stone, Anchor, Bag of Preparation | Apply status/block at battle init |
| on_combat_end | Burning Blood (STARTER) | Heal after combat |
| on_turn_start/end | Lantern (first turn), Orichalcum | Conditional energy/block |
| on_attacked | Bronze Scales | Reflect damage |
| counter-based | Pen Nib, Nunchaku, Shuriken, Kunai | Track attack counts |
| passive modifier | Paper Phrog | Modify damage formula constants |

Implementation uses `RelicDefinition` from `src/sts_gen/ir/relics.py` (already defined) + TriggerDispatcher from 2D.

Add `relic_counters: dict[str, int]` to `GameState` for counter-based relics.

### Potions

All potion stats must be wiki-verified at implementation time. Target ~11 potions covering the core effect types:

| Effect Type | Example Potions |
|---|---|
| Direct damage | Fire Potion, Explosive Potion |
| Gain block | Block Potion |
| Buff self | Strength Potion, Dexterity Potion |
| Debuff enemy | Fear Potion (Vulnerable), Weak Potion |
| Card advantage | Swift Potion (draw) |
| Energy | Energy Potion |
| Healing | Regen Potion, Fruit Juice |

Implementation: `use_potion(battle, potion_def, target)` function that runs the potion's action list through the interpreter.

### Agent Interface Extensions

Add to `PlayAgent` ABC in `src/sts_gen/sim/play_agents/base.py`:
- `choose_potion(battle, potions) -> (slot, target) | None`
- `choose_card_reward(offered, deck) -> CardDefinition | None`
- `choose_rest_action(game_state, options) -> str`

### Files Modified

| File | Changes |
|---|---|
| `data/vanilla/relics.json` (NEW) | ~15 relic definitions |
| `data/vanilla/potions.json` (NEW) | ~11 potion definitions |
| `src/sts_gen/sim/content/registry.py` | Add relic/potion loading |
| `src/sts_gen/sim/core/game_state.py` | Add `relic_counters` |
| `src/sts_gen/sim/runner.py` | Relic triggers + potion usage in combat loop |
| `src/sts_gen/sim/mechanics/potions.py` (NEW) | `use_potion()` |
| `src/sts_gen/sim/play_agents/base.py` | New abstract methods |
| `src/sts_gen/sim/play_agents/random_agent.py` | Implement new methods |
| `tests/sim/test_relics.py` (NEW) | Per-relic tests |
| `tests/sim/test_potions.py` (NEW) | Per-potion tests |

---

## Sub-Phase 2F: Map Generator + Run Manager

**Goal**: Run multi-floor Act 1 with map, card rewards, rest sites, HP persistence.

### Simplified Linear Map

Full STS map is a 7×15 grid with branching paths. For Phase 2, use a **linear sequence** — one node per floor with type determined by weighted random for that floor position. This avoids graph generation/pathfinding complexity while providing correct encounter distribution.

New file: `src/sts_gen/sim/dungeon/map_gen.py`

Floor layout (15 floors): Wiki-verify the rough floor distribution. General structure is monsters early, elites mid-late, boss at floor 15, with rest/event/shop/treasure interspersed.

### Run Manager

New file: `src/sts_gen/sim/dungeon/run_manager.py`

```python
class RunManager:
    def run_act_1(self) -> RunTelemetry:
        map_nodes = MapGenerator().generate_act_1(rng)
        for node in map_nodes:
            if player.is_dead: break
            if node.type == "monster": run_combat() + card_reward()
            elif node.type == "elite": run_combat() + card_reward() + relic_reward()
            elif node.type == "rest": rest_or_smith()
            elif node.type == "boss": run_combat()
            elif node.type == "treasure": relic_reward()
            elif node.type == "event": random_minor_event()
            elif node.type == "shop": maybe_buy_something()
        return telemetry
```

### Card Reward System

After combat win, offer 3 cards from the card pool:
- Rarity distribution: wiki-verify the exact Common/Uncommon/Rare percentages
- `ContentRegistry.get_reward_pool()` already exists and correctly filters
- Agent picks one card (or skips)

### Rest Sites

Two options: Rest (heal % of max HP — wiki-verify exact amount) or Smith (upgrade a card). Agent decides.

### HP Persistence

The `GameState` already has `current_hp` / `max_hp`. The `RunManager` passes the Player (with carried-over HP) into each new `BattleState`. This is the critical difference from Phase 1's single-combat model.

### Events (Loosely Emulated)

**No real event system.** Events are just a random minor good or bad outcome to approximate their impact on run statistics:
- ~50% chance: small heal (5-10 HP)
- ~25% chance: gain a random card
- ~15% chance: lose some HP (3-7)
- ~10% chance: gain some gold

### Shops (Loosely Emulated)

**No real shop system.** When the agent hits a shop node:
- If gold > threshold, ~50% chance to buy a random card from the reward pool (deduct gold)
- Small chance to buy a random relic if gold is high
- Otherwise, skip

### Telemetry Extensions

Add to `RunTelemetry`:
```python
cards_added: list[str]          # cards picked as rewards
relics_collected: list[str]
potions_used: int
gold_earned: int
rest_sites_visited: int
hp_at_each_floor: list[int]
```

### BatchRunner Integration

Add `BatchRunner.run_full_act_batch(n_runs, base_seed)` alongside existing `run_batch()`. Existing single-combat mode is preserved for backward compatibility.

### Files Modified

| File | Changes |
|---|---|
| `src/sts_gen/sim/dungeon/__init__.py` | Exports |
| `src/sts_gen/sim/dungeon/map_gen.py` (NEW) | MapNode, MapGenerator |
| `src/sts_gen/sim/dungeon/run_manager.py` (NEW) | RunManager |
| `src/sts_gen/sim/runner.py` | Add `run_full_act_batch` to BatchRunner |
| `src/sts_gen/sim/telemetry.py` | Extend RunTelemetry |
| `src/sts_gen/sim/play_agents/base.py` | Card reward + rest + path choice methods |
| `src/sts_gen/sim/play_agents/random_agent.py` | Implement new methods |
| `tests/sim/dungeon/test_map_gen.py` (NEW) | Map structure tests |
| `tests/sim/dungeon/test_run_manager.py` (NEW) | Full run integration tests |

---

## Sub-Phase 2G: HeuristicAgent

**Goal**: Scoring-based agent that plays reasonably, achieving 50-70% Act 1 win rate.

### Combat Decision Scoring

New file: `src/sts_gen/sim/play_agents/heuristic_agent.py`

For each possible card play, score based on:
1. **Damage value**: Higher for killing blows (removes future incoming damage). Multi-hit cards score higher with Strength.
2. **Block vs incoming**: Block up to incoming attack damage. Diminishing returns beyond that.
3. **Vulnerable priority**: Applying Vulnerable early multiplies all future damage.
4. **Scaling value**: Powers (Inflame, Demon Form) scored higher early in combat.
5. **Energy efficiency**: Slight penalty for high-cost cards when cheap alternatives exist.

### Card Reward Scoring

Pick cards that complement deck:
- Track attack/block ratio (target ~55/35/10)
- Avoid deck bloat (skip if >22 cards)
- Value Uncommon/Rare over Common
- Synergy: if deck has Strength sources, prefer multi-hit attacks

### Rest Site Decision

- HP < 60%: Rest (heal)
- HP >= 60%: Smith (upgrade)
- Upgrade priority: Bash > key damage cards > Strikes

### Potion Usage

- Use damage potions when they'd secure a kill
- Use defensive potions when incoming damage would be lethal
- Use Strength/Dexterity potions on turn 1 of long fights

### Files Modified

| File | Changes |
|---|---|
| `src/sts_gen/sim/play_agents/heuristic_agent.py` (NEW) | Full agent implementation |
| `tests/sim/play_agents/test_heuristic_agent.py` (NEW) | Scoring function unit tests |

---

## Sub-Phase 2H: Integration + Exit Gate

### Exit Gate Criteria

1. **10,000 full Act 1 runs complete without errors** in <5 minutes
2. **HeuristicAgent win rate**: 50-70% (vs RandomAgent ~10-25%)
3. **All existing 204 tests still pass**
4. **New test suite**: ~150+ new tests across all sub-phases

### Performance Estimate

10,000 runs x ~11 combats = ~110,000 combats. Phase 1: 1000 combats in <1s. With full-run overhead (map, rewards, deck management) estimate 2x -> ~220s sequential, ~28s with 8-core parallel. Well within 5-minute target.

### Integration Tests

New file: `tests/sim/test_full_act1.py`:
- 1000 runs complete without errors
- HeuristicAgent win rate is 2x+ RandomAgent
- HeuristicAgent win rate is 50-75%
- Average deck size at boss is 15-25 cards
- HP trends downward across floors
- Card rewards are taken in ~60-80% of offerings

### Files Modified

| File | Changes |
|---|---|
| `tests/sim/test_full_act1.py` (NEW) | Full Act 1 integration tests |
| `COMMAND.md` | Add full-run commands |
| `CLAUDE.md` | Update architecture section |

---

## Verification

```bash
# Run all tests (should be ~350+)
uv run pytest tests/ -v

# Run just new Phase 2 tests
uv run pytest tests/sim/test_cards_deterministic.py tests/sim/test_enemies.py tests/sim/test_triggers.py tests/sim/test_relics.py tests/sim/test_potions.py tests/sim/dungeon/ tests/sim/test_full_act1.py -v

# Run exit gate benchmark
uv run pytest tests/sim/test_full_act1.py -v -m statistical

# Quick smoke test (100 full runs)
uv run python -c "from sts_gen.sim.runner import BatchRunner; ..."
```
