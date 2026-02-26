"""Tests for balance data models."""

from __future__ import annotations

import json

import pytest

from sts_gen.balance.models import (
    CardMetrics,
    GlobalMetrics,
    RelicMetrics,
    SynergyPair,
    VanillaBaseline,
)


def _make_card_metrics(**overrides: object) -> CardMetrics:
    defaults = dict(
        card_id="test_card",
        times_in_deck=100,
        wins_with=20,
        losses_with=80,
        win_rate_with=0.2,
        win_rate_delta=0.1,
        times_offered=50,
        times_picked=25,
        pick_rate=0.5,
        times_played=200,
        play_rate=0.3,
    )
    defaults.update(overrides)
    return CardMetrics(**defaults)


def _make_global_metrics(**overrides: object) -> GlobalMetrics:
    defaults = dict(
        total_runs=1000,
        wins=100,
        losses=900,
        win_rate=0.1,
        avg_floors_reached=9.0,
        avg_battles_won=5.0,
        avg_deck_size=15.0,
        avg_gold_earned=200.0,
    )
    defaults.update(overrides)
    return GlobalMetrics(**defaults)


def _make_baseline(**overrides: object) -> VanillaBaseline:
    defaults = dict(
        agent="heuristic",
        num_runs=1000,
        generated_at="2026-01-01T00:00:00+00:00",
        global_metrics=_make_global_metrics(),
        card_metrics=[_make_card_metrics()],
        relic_metrics=[],
        synergies=[],
        anti_synergies=[],
    )
    defaults.update(overrides)
    return VanillaBaseline(**defaults)


class TestCardMetrics:
    def test_creation(self) -> None:
        cm = _make_card_metrics(card_id="offering")
        assert cm.card_id == "offering"
        assert cm.win_rate_with == 0.2

    def test_optional_efficiency_fields(self) -> None:
        cm = _make_card_metrics()
        assert cm.avg_damage_per_play is None
        assert cm.avg_block_per_play is None

        cm2 = _make_card_metrics(avg_damage_per_play=15.0, avg_block_per_play=8.0)
        assert cm2.avg_damage_per_play == 15.0
        assert cm2.avg_block_per_play == 8.0


class TestGlobalMetrics:
    def test_creation(self) -> None:
        gm = _make_global_metrics()
        assert gm.total_runs == 1000
        assert gm.win_rate == 0.1


class TestRelicMetrics:
    def test_creation(self) -> None:
        rm = RelicMetrics(
            relic_id="vajra",
            times_held=50,
            wins_with=10,
            win_rate_with=0.2,
            win_rate_delta=0.1,
        )
        assert rm.relic_id == "vajra"


class TestSynergyPair:
    def test_creation(self) -> None:
        sp = SynergyPair(
            card_a="offering",
            card_b="demon_form",
            co_occurrence_count=100,
            co_win_rate=0.3,
            independent_expected_wr=0.15,
            synergy_score=0.15,
        )
        assert sp.synergy_score == 0.15


class TestVanillaBaseline:
    def test_serialization_roundtrip(self) -> None:
        baseline = _make_baseline()
        data = baseline.model_dump()
        restored = VanillaBaseline.model_validate(data)
        assert restored.agent == baseline.agent
        assert restored.num_runs == baseline.num_runs
        assert restored.global_metrics.win_rate == baseline.global_metrics.win_rate
        assert len(restored.card_metrics) == 1

    def test_json_roundtrip(self) -> None:
        baseline = _make_baseline()
        json_str = json.dumps(baseline.model_dump())
        data = json.loads(json_str)
        restored = VanillaBaseline.model_validate(data)
        assert restored == baseline
