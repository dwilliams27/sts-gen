# Quick Commands

## Run tests

```bash
uv run pytest tests/ -v
```

## Run 100-combat simulation with stats

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
from sts_gen.ir import *
from sts_gen.sim.content.registry import ContentRegistry
r = ContentRegistry()
r.load_vanilla_cards()
r.load_vanilla_enemies()
print(f'{len(r.cards)} cards, {len(r.enemies)} enemies loaded')
print(f'Starter deck: {r.get_starter_deck(\"ironclad\")}')
print(f'Strike actions: {r.get_card(\"strike\").actions}')
"
```
