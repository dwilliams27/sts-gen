# CLAUDE.md

## Project

sts-gen: AI-powered Slay the Spire mod generator. Python simulation engine + LLM agents that design, simulate-test, iteratively refine, and package balanced STS mods as playable JAR files.

Full architecture and phased plan: `docs/FOUNDATION.md`

## Quick Reference

```bash
uv run pytest tests/ -v          # Run all tests (323 tests, ~5s)
uv run pytest tests/ -x          # Stop on first failure
```

See `COMMAND.md` for simulation commands.

## Design Principles

**No unnecessary fallbacks.** Fallbacks should only be implemented when explicitly asked for or where they clearly serve a purpose. The system must maintain coherence and simplicity. Having many fallback cases complicates behavior significantly — if something is missing or wrong, it should fail loudly rather than silently degrade into a "default attack for 6 damage" or "generic 50 HP enemy." A clear error is more useful than hidden incorrect behavior.

**Fail fast, fail loud.** Prefer raising exceptions over returning defaults when data is missing. If a card_id isn't in the registry, that's a bug — don't silently skip it. If an enemy definition is missing, crash — don't fabricate one.

**Single source of truth.** Strength, dexterity, and all status effects live in the `entity.status_effects` dict. The direct `Player.strength` / `Player.dexterity` fields exist on the model but are not used by the simulation — all reads go through `get_status_stacks()`.

**IR is the contract.** Everything — vanilla cards, custom cards, enemies — is defined through the same IR primitives. No special-case code for vanilla content. If a card can't be expressed in the IR, extend the IR rather than adding a hack.

**Simulation fidelity matters.** Every mechanic should match real STS behavior. When in doubt, check against the decompiled game source. Wrong simulation results produce wrong balance conclusions.

**Wiki-verify all game data.** Whenever creating anything that references data from the base game (status effects, cards, enemies, relics, potions, encounters, etc.), the exact values and behaviors MUST be looked up on the Slay the Spire wiki (`slay-the-spire.fandom.com`). Never rely on memory for game-specific numbers, trigger timing, or scaling behavior — always fetch and verify from the wiki first.

**Refactor when needed.** Don't be afraid to rearchitect systems, files, or components when they won't work well with new features. A bit of tech debt is fine, but when a system is clearly fighting the new requirements, take the time to refactor rather than piling hacks on top. This should be a considered decision, not the first resort — but also not avoided out of inertia.

## Architecture

```
src/sts_gen/
  ir/                          # Pydantic v2 IR schema
    actions.py                 #   ActionNode + ActionType (23 primitives)
    cards.py                   #   CardDefinition, CardType, CardRarity, CardTarget, UpgradeDefinition
    relics.py                  #   RelicDefinition, RelicTier
    potions.py                 #   PotionDefinition, PotionRarity
    keywords.py                #   KeywordDefinition
    status_effects.py          #   StatusEffectDefinition, StatusTrigger, StackBehavior
    content_set.py             #   ContentSet (top-level container with validation)

  sim/
    core/                      # Simulation state
      rng.py                   #   GameRNG (seeded, forkable via SHA-256)
      entities.py              #   Entity, Player, Enemy, EnemyIntent
      game_state.py            #   CardInstance, CardPiles, BattleState, GameState
      action_queue.py          #   QueuedAction, ActionQueue

    mechanics/                 # Combat math (stateless functions operating on state objects)
      damage.py                #   calculate_damage (str+vuln+weak pipeline), deal_damage
      block.py                 #   gain_block (dex+frail), clear_block, decay_block
      energy.py                #   reset_energy, spend_energy, gain_energy
      card_piles.py            #   draw_cards, discard_card, exhaust_card, etc.
      status_effects.py        #   apply_status, decay_statuses, trigger_status, has_status
      targeting.py             #   resolve_targets

    interpreter.py             # ActionNode tree -> mechanics dispatch (dispatch table pattern)
    triggers.py                # TriggerDispatcher — fires status triggers generically
    runner.py                  # EnemyAI, CombatSimulator, BatchRunner
    telemetry.py               # BattleTelemetry, RunTelemetry dataclasses

    content/
      registry.py              # ContentRegistry — loads and serves cards, enemies, status defs

    play_agents/
      base.py                  # PlayAgent ABC
      random_agent.py          # RandomAgent (random valid actions, 10% end-turn chance)

data/vanilla/
  ironclad_cards.json          # 80 Ironclad cards in IR format (all wiki-verified)
  enemies.json                 # 25 Act 1 enemies (wiki-verified)
  encounters.json              # Act 1 encounter compositions (easy/normal/elite/boss pools)
  status_effects.json          # 16 status effect definitions (all wiki-verified)

tests/                         # Mirrors src/ structure, 323 tests
```

## Phase 2 Plan

Full plan: `docs/PHASE2.md`

## Key Naming Conventions

- Entity HP: `current_hp`, `max_hp` (not `hp`)
- Entity alive/dead: `is_dead` property (not `is_alive`)
- Card piles: `.draw`, `.hand`, `.discard`, `.exhaust` (not `.draw_pile` etc.)
- Status queries: `get_status_stacks(entity, "strength")` from mechanics module
- Source indexing: `"player"` or integer enemy index
- Target specs: `"enemy"`, `"all_enemies"`, `"self"`, `"random"`, `"none"`

## Phase 2 Progress

- [x] 2A: Interpreter extensions (3 new ActionTypes, 2 new conditions, 2 new damage conditions, play restrictions, exhaust-all, X-cost REPEAT, ethereal/innate/retain)
- [x] 2B: Full Ironclad card pool (80 cards, wiki-verified: 3 basic + 20 common + 36 uncommon + 16 rare + 5 status)
- [x] 2C: Full Act 1 enemy pool (25 enemies + encounters, wiki-verified)
- [x] 2D: Status trigger system
- [ ] 2E: Relics + potions
- [ ] 2F: Map generator + run manager
- [ ] 2G: HeuristicAgent
- [ ] 2H: Integration + exit gate

## What Doesn't Exist Yet

- HeuristicAgent (only RandomAgent exists)
- Map generation, run manager, rewards, shops, relics, potions in sim
- ~~Status trigger system~~ (DONE: TriggerDispatcher + 16 wiki-verified status definitions fire generically)
- UpgradeDefinition now supports exhaust/innate overrides (Limit Break+, Brutality+)
- Some cards are simplified (marked [SIMPLIFIED] in description): Armaments, Dual Wield, Rampage, Blood for Blood, Searing Blow, Feed, Fiend Fire, Reaper, Exhume, Second Wind, etc.
- Enemy reactive hooks (Enrage, Sharp Hide, Curl Up, Angry, split, escape, mode shift, sleep/wake) are implemented directly in runner.py — not yet generalized through the trigger system
- LLM agents, balance analysis, mod builder
