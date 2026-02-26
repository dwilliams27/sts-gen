# Quick Commands

## Run tests

```bash
uv run pytest tests/ -v              # All tests (~515, ~35s with integration)
uv run pytest tests/ -x              # Stop on first failure
uv run pytest tests/ -x --ignore=tests/sim/test_full_act1.py  # Fast (~6s, skip 10k-run gate)
```

## Generate vanilla baselines

```bash
# Full baseline (50k runs, ~60s) → saves JSON + prints report
uv run python scripts/generate_baselines.py --runs 50000

# Quick baseline (1k runs, ~1s)
uv run python scripts/generate_baselines.py --runs 1000
```

## Full Act 1 simulation

```bash
# Compare RandomAgent vs HeuristicAgent (2000 runs, generates chart)
uv run python scripts/compare_agents.py --runs 2000

# Diagnose where HeuristicAgent dies (2000 runs, per-enemy breakdown)
uv run python scripts/diagnose_agent.py --runs 2000
```

## Quick simulation smoke test

```bash
uv run python -c "
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
from sts_gen.sim.runner import BatchRunner

registry = ContentRegistry()
registry.load_vanilla_cards()
registry.load_vanilla_enemies()
registry.load_vanilla_status_effects()
registry.load_vanilla_relics()
registry.load_vanilla_potions()
registry.load_vanilla_encounters()

runner = BatchRunner(registry, agent_class=HeuristicAgent)
results = runner.run_full_act_batch(n_runs=100, base_seed=42)
wins = sum(1 for r in results if r.final_result == 'win')
avg_floors = sum(r.floors_reached for r in results) / 100
print(f'HeuristicAgent: {wins}% wins, {avg_floors:.1f} avg floors (100 runs)')
"
```

## Single-combat simulation

```bash
uv run python -c "
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.runner import BatchRunner

registry = ContentRegistry()
registry.load_vanilla_cards()
registry.load_vanilla_enemies()

runner = BatchRunner(registry=registry)
for enemy in ['jaw_worm', 'cultist', 'red_louse']:
    results = runner.run_batch(100, {'enemy_ids': [enemy]}, base_seed=42)
    wins = sum(1 for r in results if r.final_result == 'win')
    avg_hp = sum(r.battles[0].hp_lost for r in results) / 100
    print(f'{enemy:12s}  win={wins}%  avg_hp_lost={avg_hp:.0f}')
"
```

## Verify IR schema and content loading

```bash
uv run python -c "
from sts_gen.sim.content.registry import ContentRegistry
r = ContentRegistry()
r.load_vanilla_cards()
r.load_vanilla_enemies()
r.load_vanilla_status_effects()
r.load_vanilla_relics()
r.load_vanilla_potions()
r.load_vanilla_encounters()
print(f'{len(r.cards)} cards, {len(r.enemies)} enemies loaded')
print(f'{len(r.status_defs)} status defs, {len(r.relics)} relics, {len(r.potions)} potions')
print(f'Starter deck: {r.get_starter_deck(\"ironclad\")}')
"
```
