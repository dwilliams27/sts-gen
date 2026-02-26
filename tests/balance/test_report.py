"""Tests for report generation."""

from __future__ import annotations

import pytest

from sts_gen.balance.models import (
    CardMetrics,
    GlobalMetrics,
    RelicMetrics,
    SynergyPair,
    VanillaBaseline,
)
from sts_gen.balance.report import generate_llm_context, generate_text_report


def _make_baseline() -> VanillaBaseline:
    """Create a baseline with enough data to exercise report formatting."""
    cards = [
        CardMetrics(
            card_id="offering",
            times_in_deck=500,
            wins_with=100,
            losses_with=400,
            win_rate_with=0.2,
            win_rate_delta=0.1,
            times_offered=300,
            times_picked=200,
            pick_rate=0.667,
            times_played=800,
            play_rate=0.25,
        ),
        CardMetrics(
            card_id="strike",
            times_in_deck=1000,
            wins_with=100,
            losses_with=900,
            win_rate_with=0.1,
            win_rate_delta=0.0,
            times_offered=0,
            times_picked=0,
            pick_rate=0.0,
            times_played=5000,
            play_rate=0.5,
        ),
    ]
    synergies = [
        SynergyPair(
            card_a="offering",
            card_b="demon_form",
            co_occurrence_count=100,
            co_win_rate=0.3,
            independent_expected_wr=0.15,
            synergy_score=0.15,
        ),
    ]
    anti_synergies = [
        SynergyPair(
            card_a="clash",
            card_b="defend",
            co_occurrence_count=80,
            co_win_rate=0.05,
            independent_expected_wr=0.1,
            synergy_score=-0.05,
        ),
    ]
    return VanillaBaseline(
        agent="heuristic",
        num_runs=1000,
        generated_at="2026-01-01T00:00:00+00:00",
        global_metrics=GlobalMetrics(
            total_runs=1000,
            wins=100,
            losses=900,
            win_rate=0.1,
            avg_floors_reached=9.5,
            avg_battles_won=5.1,
            avg_deck_size=15.0,
            avg_gold_earned=200.0,
        ),
        card_metrics=cards,
        relic_metrics=[],
        synergies=synergies,
        anti_synergies=anti_synergies,
    )


class TestTextReport:
    def test_contains_global_stats(self) -> None:
        report = generate_text_report(_make_baseline())
        assert "Global Stats" in report
        assert "10.0%" in report
        assert "9.5" in report

    def test_contains_card_sections(self) -> None:
        report = generate_text_report(_make_baseline())
        assert "Highest Win Rate Delta" in report
        assert "Lowest Win Rate Delta" in report
        assert "offering" in report

    def test_contains_synergies(self) -> None:
        report = generate_text_report(_make_baseline())
        assert "Synergy Pairs" in report
        assert "offering" in report
        assert "demon_form" in report

    def test_contains_anti_synergies(self) -> None:
        report = generate_text_report(_make_baseline())
        assert "Anti-Synergy" in report
        assert "clash" in report


class TestLlmContext:
    def test_contains_header(self) -> None:
        ctx = generate_llm_context(_make_baseline())
        assert "<vanilla_baseline>" in ctx
        assert "</vanilla_baseline>" in ctx

    def test_contains_global_line(self) -> None:
        ctx = generate_llm_context(_make_baseline())
        assert "global:" in ctx
        assert "wr=0.100" in ctx

    def test_contains_card_table(self) -> None:
        ctx = generate_llm_context(_make_baseline())
        assert "card_id | wr_delta" in ctx
        assert "offering" in ctx

    def test_contains_synergies(self) -> None:
        ctx = generate_llm_context(_make_baseline())
        assert "synergies:" in ctx
        assert "anti_synergies:" in ctx
