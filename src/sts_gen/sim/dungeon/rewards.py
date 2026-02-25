"""Reward generation for card rewards, gold, relics, and potions.

All values are wiki-verified:
- Card rewards: 3 cards. Normal: 60/37/3% C/U/R. Elite: 50/40/10% C/U/R.
- Gold: normal 10-20, elite 25-35, boss 95-105.
- Potion drop: 40% chance after combat win.
- Elite relic: 50/33/17% C/U/R tier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sts_gen.ir.cards import CardRarity
from sts_gen.ir.relics import RelicTier
from sts_gen.sim.core.rng import GameRNG

if TYPE_CHECKING:
    from sts_gen.ir.cards import CardDefinition
    from sts_gen.sim.content.registry import ContentRegistry


def generate_card_reward(
    registry: ContentRegistry,
    rng: GameRNG,
    pool: str = "normal",
) -> list[CardDefinition]:
    """Generate 3 card reward choices with correct rarity distribution.

    Parameters
    ----------
    registry:
        Content registry for looking up cards by rarity.
    rng:
        Seeded RNG for deterministic selection.
    pool:
        ``"normal"`` or ``"elite"`` — controls rarity thresholds.
    """
    cards: list[CardDefinition] = []
    seen_ids: set[str] = set()

    for _ in range(3):
        rarity = _roll_rarity(rng, pool)
        card = _pick_card_of_rarity(registry, rng, rarity, seen_ids)
        if card is not None:
            cards.append(card)
            seen_ids.add(card.id)

    return cards


def _roll_rarity(rng: GameRNG, pool: str) -> CardRarity:
    """Roll a card rarity based on pool type."""
    roll = rng.random_float() * 100

    if pool == "elite":
        if roll < 50:
            return CardRarity.COMMON
        elif roll < 90:
            return CardRarity.UNCOMMON
        else:
            return CardRarity.RARE
    else:
        # Normal pool
        if roll < 60:
            return CardRarity.COMMON
        elif roll < 97:
            return CardRarity.UNCOMMON
        else:
            return CardRarity.RARE


def _pick_card_of_rarity(
    registry: ContentRegistry,
    rng: GameRNG,
    rarity: CardRarity,
    seen_ids: set[str],
) -> CardDefinition | None:
    """Pick a random card of the given rarity, excluding already-seen ids."""
    candidates = registry.get_reward_pool(rarity=rarity, exclude_ids=seen_ids)
    if not candidates:
        # Fall back to any reward-eligible card
        candidates = registry.get_reward_pool(exclude_ids=seen_ids)
    if not candidates:
        return None
    return rng.random_choice(candidates)


def generate_gold_reward(rng: GameRNG, pool: str = "normal") -> int:
    """Random gold in range: normal 10-20, elite 25-35, boss 95-105."""
    if pool == "elite":
        return rng.random_int(25, 35)
    elif pool == "boss":
        return rng.random_int(95, 105)
    else:
        return rng.random_int(10, 20)


def generate_relic_reward(
    registry: ContentRegistry,
    rng: GameRNG,
    owned_relics: list[str],
) -> str | None:
    """Pick a random relic not already owned. Tier: 50/33/17 C/U/R."""
    tier = _roll_relic_tier(rng)
    owned_set = set(owned_relics)

    candidates = [
        r for r in registry.relics.values()
        if r.tier == tier and r.id not in owned_set
    ]
    if not candidates:
        # Fall back to any non-owned, non-starter relic
        candidates = [
            r for r in registry.relics.values()
            if r.id not in owned_set and r.tier != RelicTier.STARTER
        ]
    if not candidates:
        return None
    return rng.random_choice(candidates).id


def _roll_relic_tier(rng: GameRNG) -> RelicTier:
    """Roll relic tier: 50% Common, 33% Uncommon, 17% Rare."""
    roll = rng.random_float() * 100
    if roll < 50:
        return RelicTier.COMMON
    elif roll < 83:
        return RelicTier.UNCOMMON
    else:
        return RelicTier.RARE


def maybe_drop_potion(
    registry: ContentRegistry,
    rng: GameRNG,
    potions: list[str | None],
) -> str | None:
    """40% chance to drop a random potion if belt has space.

    Returns the potion id if dropped, None otherwise.
    """
    # Check if belt has an empty slot
    if all(p is not None for p in potions):
        return None

    # 40% drop chance
    if rng.random_float() >= 0.40:
        return None

    # Pick a random potion
    candidates = list(registry.potions.values())
    if not candidates:
        return None
    return rng.random_choice(candidates).id
