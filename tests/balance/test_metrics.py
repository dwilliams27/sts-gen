"""Tests for metric computation functions."""

from __future__ import annotations

import pytest

from sts_gen.balance.metrics import (
    compute_card_metrics,
    compute_global_metrics,
    compute_relic_metrics,
    compute_synergies,
)
from sts_gen.sim.telemetry import BattleTelemetry, RunTelemetry


def _make_battle(
    result: str = "win",
    turns: int = 5,
    cards_played_by_id: dict[str, int] | None = None,
) -> BattleTelemetry:
    return BattleTelemetry(
        enemy_ids=["cultist"],
        result=result,
        turns=turns,
        player_hp_start=80,
        player_hp_end=60 if result == "win" else 0,
        hp_lost=20 if result == "win" else 80,
        damage_dealt=50,
        block_gained=30,
        cards_played=10,
        cards_played_by_id=cards_played_by_id or {},
    )


def _make_run(
    seed: int = 0,
    result: str = "loss",
    cards_in_deck: list[str] | None = None,
    relics_collected: list[str] | None = None,
    battles: list[BattleTelemetry] | None = None,
    floors: int = 5,
    gold: int = 100,
    card_offers: list[list[str]] | None = None,
    card_picks: list[str | None] | None = None,
) -> RunTelemetry:
    return RunTelemetry(
        seed=seed,
        battles=battles or [_make_battle()],
        final_result=result,
        floors_reached=floors,
        cards_in_deck=cards_in_deck or ["strike", "defend", "bash"],
        relics_collected=relics_collected or [],
        gold_earned=gold,
        card_offers=card_offers or [],
        card_picks=card_picks or [],
    )


# ---- Global metrics ----

class TestComputeGlobalMetrics:
    def test_basic(self) -> None:
        runs = [
            _make_run(result="win", floors=16, gold=200),
            _make_run(result="loss", floors=8, gold=100),
            _make_run(result="loss", floors=4, gold=50),
        ]
        gm = compute_global_metrics(runs)
        assert gm.total_runs == 3
        assert gm.wins == 1
        assert gm.losses == 2
        assert gm.win_rate == pytest.approx(1 / 3)
        assert gm.avg_floors_reached == pytest.approx((16 + 8 + 4) / 3)
        assert gm.avg_gold_earned == pytest.approx((200 + 100 + 50) / 3)

    def test_empty_runs(self) -> None:
        gm = compute_global_metrics([])
        assert gm.total_runs == 0
        assert gm.win_rate == 0.0

    def test_all_wins(self) -> None:
        runs = [_make_run(result="win") for _ in range(5)]
        gm = compute_global_metrics(runs)
        assert gm.win_rate == 1.0

    def test_avg_battles_won(self) -> None:
        runs = [
            _make_run(battles=[_make_battle("win"), _make_battle("loss")]),
            _make_run(battles=[_make_battle("win"), _make_battle("win")]),
        ]
        gm = compute_global_metrics(runs)
        assert gm.avg_battles_won == pytest.approx(1.5)

    def test_avg_deck_size(self) -> None:
        runs = [
            _make_run(cards_in_deck=["a", "b", "c"]),
            _make_run(cards_in_deck=["a"]),
        ]
        gm = compute_global_metrics(runs)
        assert gm.avg_deck_size == pytest.approx(2.0)


# ---- Card metrics ----

class TestComputeCardMetrics:
    def test_win_rate_delta(self) -> None:
        runs = [
            # 2 wins with offering in deck
            _make_run(result="win", cards_in_deck=["strike", "offering"]),
            _make_run(result="win", cards_in_deck=["strike", "offering"]),
            # 1 loss with offering
            _make_run(result="loss", cards_in_deck=["strike", "offering"]),
            # 2 losses without offering
            _make_run(result="loss", cards_in_deck=["strike"]),
            _make_run(result="loss", cards_in_deck=["strike"]),
        ]
        global_wr = 2 / 5  # 0.4
        metrics = compute_card_metrics(runs, global_wr)
        by_id = {m.card_id: m for m in metrics}

        # Offering: 2/3 wins = 0.667, delta = 0.667 - 0.4 = 0.267
        offering = by_id["offering"]
        assert offering.times_in_deck == 3
        assert offering.wins_with == 2
        assert offering.losses_with == 1
        assert offering.win_rate_with == pytest.approx(2 / 3)
        assert offering.win_rate_delta == pytest.approx(2 / 3 - 0.4)

        # Strike: all 5 runs, 2 wins = 0.4, delta = 0.0
        strike = by_id["strike"]
        assert strike.times_in_deck == 5
        assert strike.win_rate_delta == pytest.approx(0.0)

    def test_pick_rate(self) -> None:
        runs = [
            _make_run(
                cards_in_deck=["strike", "offering"],
                card_offers=[["offering", "strike", "defend"], ["pommel_strike", "shrug_it_off"]],
                card_picks=["offering", None],
            ),
            _make_run(
                cards_in_deck=["strike"],
                card_offers=[["offering", "bash"]],
                card_picks=[None],
            ),
        ]
        metrics = compute_card_metrics(runs, 0.1)
        by_id = {m.card_id: m for m in metrics}

        offering = by_id["offering"]
        assert offering.times_offered == 2
        assert offering.times_picked == 1
        assert offering.pick_rate == pytest.approx(0.5)

    def test_play_rate(self) -> None:
        runs = [
            _make_run(
                cards_in_deck=["strike", "offering"],
                battles=[_make_battle(turns=10, cards_played_by_id={"offering": 3, "strike": 5})],
            ),
        ]
        metrics = compute_card_metrics(runs, 0.1)
        by_id = {m.card_id: m for m in metrics}

        offering = by_id["offering"]
        assert offering.times_played == 3
        assert offering.play_rate == pytest.approx(3 / 10)

    def test_empty_runs(self) -> None:
        assert compute_card_metrics([], 0.1) == []

    def test_div_by_zero_no_offers(self) -> None:
        """Card never offered → pick_rate = 0.0."""
        runs = [_make_run(cards_in_deck=["strike"])]
        metrics = compute_card_metrics(runs, 0.1)
        by_id = {m.card_id: m for m in metrics}
        assert by_id["strike"].pick_rate == 0.0

    def test_div_by_zero_no_battles(self) -> None:
        """No battles → play_rate = 0.0."""
        runs = [_make_run(cards_in_deck=["strike"], battles=[])]
        metrics = compute_card_metrics(runs, 0.1)
        by_id = {m.card_id: m for m in metrics}
        assert by_id["strike"].play_rate == 0.0


# ---- Relic metrics ----

class TestComputeRelicMetrics:
    def test_basic(self) -> None:
        runs = [
            _make_run(result="win", relics_collected=["vajra"]),
            _make_run(result="loss", relics_collected=["vajra"]),
            _make_run(result="loss", relics_collected=[]),
        ]
        global_wr = 1 / 3
        metrics = compute_relic_metrics(runs, global_wr)
        assert len(metrics) == 1
        vajra = metrics[0]
        assert vajra.relic_id == "vajra"
        assert vajra.times_held == 2
        assert vajra.wins_with == 1
        assert vajra.win_rate_with == pytest.approx(0.5)
        assert vajra.win_rate_delta == pytest.approx(0.5 - 1 / 3)

    def test_empty_runs(self) -> None:
        assert compute_relic_metrics([], 0.1) == []


# ---- Synergy detection ----

class TestComputeSynergies:
    def test_basic_synergy(self) -> None:
        """Two cards that always win together should have positive synergy."""
        runs: list[RunTelemetry] = []
        # 60 runs: both A and B in deck → 40 wins
        for i in range(60):
            runs.append(_make_run(
                seed=i,
                result="win" if i < 40 else "loss",
                cards_in_deck=["card_a", "card_b", "strike"],
            ))
        # 40 runs: only A → 5 wins
        for i in range(40):
            runs.append(_make_run(
                seed=100 + i,
                result="win" if i < 5 else "loss",
                cards_in_deck=["card_a", "strike"],
            ))
        # 40 runs: only B → 5 wins
        for i in range(40):
            runs.append(_make_run(
                seed=200 + i,
                result="win" if i < 5 else "loss",
                cards_in_deck=["card_b", "strike"],
            ))

        global_wr = 50 / 140
        synergies, anti = compute_synergies(
            runs, global_wr, min_co_occurrence=10, top_n=5,
        )
        assert len(synergies) >= 1
        pair = synergies[0]
        assert {pair.card_a, pair.card_b} == {"card_a", "card_b"}
        assert pair.synergy_score > 0
        assert pair.co_occurrence_count == 60

    def test_min_co_occurrence_filter(self) -> None:
        """Pairs below min_co_occurrence are excluded."""
        runs = [
            _make_run(cards_in_deck=["card_a", "card_b"])
            for _ in range(5)
        ]
        synergies, anti = compute_synergies(runs, 0.1, min_co_occurrence=10)
        assert len(synergies) == 0
        assert len(anti) == 0

    def test_starters_excluded(self) -> None:
        """Starter cards should not appear in synergy pairs."""
        runs: list[RunTelemetry] = []
        for i in range(100):
            runs.append(_make_run(
                seed=i,
                result="win" if i < 50 else "loss",
                cards_in_deck=["strike", "defend", "bash"],
            ))
        synergies, anti = compute_synergies(runs, 0.5, min_co_occurrence=10)
        assert len(synergies) == 0
        assert len(anti) == 0

    def test_empty_runs(self) -> None:
        synergies, anti = compute_synergies([], 0.1)
        assert synergies == []
        assert anti == []

    def test_zero_global_wr(self) -> None:
        """Zero global win rate → no synergies (guard against div-by-zero)."""
        runs = [_make_run(cards_in_deck=["a", "b"]) for _ in range(100)]
        synergies, anti = compute_synergies(runs, 0.0, min_co_occurrence=10)
        assert synergies == []
        assert anti == []
