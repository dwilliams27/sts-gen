"""Tests for reward generation: cards, gold, relics, potions."""

import pytest

from sts_gen.ir.cards import CardRarity
from sts_gen.ir.relics import RelicTier
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.dungeon.rewards import (
    generate_card_reward,
    generate_gold_reward,
    generate_relic_reward,
    maybe_drop_potion,
)


@pytest.fixture
def registry():
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_encounters()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    return reg


class TestCardReward:
    def test_returns_3_cards(self, registry):
        rng = GameRNG(seed=42)
        cards = generate_card_reward(registry, rng)
        assert len(cards) == 3

    def test_no_duplicate_cards_in_reward(self, registry):
        rng = GameRNG(seed=42)
        for seed in range(50):
            cards = generate_card_reward(registry, GameRNG(seed=seed))
            ids = [c.id for c in cards]
            assert len(ids) == len(set(ids)), f"Duplicates in seed={seed}: {ids}"

    def test_no_basic_or_special_cards(self, registry):
        for seed in range(100):
            cards = generate_card_reward(registry, GameRNG(seed=seed))
            for card in cards:
                assert card.rarity not in (CardRarity.BASIC, CardRarity.SPECIAL), (
                    f"Got {card.rarity} card {card.id} in seed={seed}"
                )

    def test_normal_pool_rarity_distribution(self, registry):
        """Normal pool: ~60% Common, ~37% Uncommon, ~3% Rare."""
        counts = {CardRarity.COMMON: 0, CardRarity.UNCOMMON: 0, CardRarity.RARE: 0}
        n_runs = 1000
        for seed in range(n_runs):
            cards = generate_card_reward(registry, GameRNG(seed=seed), pool="normal")
            for card in cards:
                counts[card.rarity] += 1

        total = sum(counts.values())
        common_pct = counts[CardRarity.COMMON] / total * 100
        uncommon_pct = counts[CardRarity.UNCOMMON] / total * 100
        rare_pct = counts[CardRarity.RARE] / total * 100

        # Allow generous margins for randomness
        assert 45 < common_pct < 75, f"Common: {common_pct:.1f}%"
        assert 25 < uncommon_pct < 50, f"Uncommon: {uncommon_pct:.1f}%"
        assert 0.5 < rare_pct < 10, f"Rare: {rare_pct:.1f}%"

    def test_elite_pool_has_more_rares(self, registry):
        """Elite pool should have higher rare rate than normal."""
        rare_normal = 0
        rare_elite = 0
        n_runs = 500
        for seed in range(n_runs):
            normal_cards = generate_card_reward(registry, GameRNG(seed=seed), pool="normal")
            elite_cards = generate_card_reward(registry, GameRNG(seed=seed + 10000), pool="elite")
            rare_normal += sum(1 for c in normal_cards if c.rarity == CardRarity.RARE)
            rare_elite += sum(1 for c in elite_cards if c.rarity == CardRarity.RARE)

        assert rare_elite > rare_normal


class TestGoldReward:
    def test_normal_gold_range(self):
        for seed in range(100):
            gold = generate_gold_reward(GameRNG(seed=seed), pool="normal")
            assert 10 <= gold <= 20, f"seed={seed}: gold={gold}"

    def test_elite_gold_range(self):
        for seed in range(100):
            gold = generate_gold_reward(GameRNG(seed=seed), pool="elite")
            assert 25 <= gold <= 35, f"seed={seed}: gold={gold}"

    def test_boss_gold_range(self):
        for seed in range(100):
            gold = generate_gold_reward(GameRNG(seed=seed), pool="boss")
            assert 95 <= gold <= 105, f"seed={seed}: gold={gold}"


class TestRelicReward:
    def test_returns_relic_id(self, registry):
        rng = GameRNG(seed=42)
        relic_id = generate_relic_reward(registry, rng, owned_relics=["burning_blood"])
        assert relic_id is not None
        assert relic_id in registry.relics

    def test_skips_owned_relics(self, registry):
        rng = GameRNG(seed=42)
        owned = ["burning_blood", "vajra", "anchor"]
        relic_id = generate_relic_reward(registry, rng, owned_relics=owned)
        if relic_id is not None:
            assert relic_id not in owned

    def test_no_starter_relics_from_reward(self, registry):
        for seed in range(100):
            rng = GameRNG(seed=seed)
            relic_id = generate_relic_reward(registry, rng, owned_relics=[])
            if relic_id is not None:
                relic_def = registry.relics[relic_id]
                assert relic_def.tier != RelicTier.STARTER, (
                    f"Got starter relic {relic_id}"
                )


class TestPotionDrop:
    def test_potion_drop_rate_approximately_40_pct(self, registry):
        drops = 0
        n_runs = 1000
        for seed in range(n_runs):
            result = maybe_drop_potion(
                registry, GameRNG(seed=seed), [None, None, None],
            )
            if result is not None:
                drops += 1

        drop_rate = drops / n_runs
        assert 0.30 < drop_rate < 0.50, f"Drop rate: {drop_rate:.2f}"

    def test_no_drop_when_belt_full(self, registry):
        for seed in range(100):
            result = maybe_drop_potion(
                registry,
                GameRNG(seed=seed),
                ["fire_potion", "block_potion", "strength_potion"],
            )
            assert result is None

    def test_dropped_potion_is_valid(self, registry):
        for seed in range(100):
            result = maybe_drop_potion(
                registry, GameRNG(seed=seed), [None, None, None],
            )
            if result is not None:
                assert result in registry.potions
