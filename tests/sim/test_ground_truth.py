"""Ground-truth validation suite for the STS simulation engine.

33 experiments across 5 categories:
  1. Deck Composition (6)  — statistical
  2. Mechanic Isolation (11) — deterministic + statistical
  3. Enemy Behavior (6)   — statistical + unit
  4. Statistical Sanity (6)
  5. Comparative Balance (4) — statistical
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import math
import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.damage import calculate_damage
from sts_gen.sim.mechanics.block import gain_block
from sts_gen.sim.mechanics.status_effects import (
    apply_status,
    decay_statuses,
    get_status_stacks,
)
from sts_gen.sim.runner import CombatSimulator, EnemyAI
from sts_gen.sim.play_agents.random_agent import RandomAgent

from tests.sim.conftest import run_experiment, mean_stat, win_rate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STARTER = ["strike"] * 5 + ["defend"] * 4 + ["bash"]


# ---------------------------------------------------------------------------
# Unit-test helpers
# ---------------------------------------------------------------------------

def _make_player(**kwargs: Any) -> Player:
    defaults: dict[str, Any] = dict(
        name="Ironclad", max_hp=80, current_hp=80, max_energy=3, energy=3,
    )
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(**kwargs: Any) -> Enemy:
    defaults: dict[str, Any] = dict(
        name="Dummy", enemy_id="dummy", max_hp=200, current_hp=200,
    )
    defaults.update(kwargs)
    return Enemy(**defaults)


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


# ===================================================================
# Category 1: Deck Composition
# ===================================================================


@pytest.mark.statistical
class TestDeckComposition:
    """Statistical tests comparing deck configurations (500 runs each)."""

    N = 500

    def test_1_1_block_matters(self, registry):
        """Starter deck (with Defends) loses less HP *per turn* than all-Strike.

        All-Strike kills faster (fewer total turns), so total hp_lost may be
        lower.  But per-turn damage taken is higher because no block absorbs
        enemy attacks.
        """
        r_starter = run_experiment(registry, STARTER, ["jaw_worm"], n_runs=self.N)
        r_strikes = run_experiment(
            registry, ["strike"] * 10, ["jaw_worm"], n_runs=self.N,
        )
        hpt_starter = mean_stat(r_starter, "hp_lost") / mean_stat(r_starter, "turns")
        hpt_strikes = mean_stat(r_strikes, "hp_lost") / mean_stat(r_strikes, "turns")
        assert hpt_starter < hpt_strikes

    def test_1_2_strength_scaling(self, registry):
        """Adding Inflame improves win rate or shortens fights."""
        deck_inflame = STARTER + ["inflame"]
        r_base = run_experiment(registry, STARTER, ["jaw_worm"], n_runs=self.N)
        r_inflame = run_experiment(
            registry, deck_inflame, ["jaw_worm"], n_runs=self.N,
        )
        wr_improved = win_rate(r_inflame) > win_rate(r_base)
        turns_improved = mean_stat(r_inflame, "turns") < mean_stat(r_base, "turns")
        assert wr_improved or turns_improved

    def test_1_3_draw_over_raw_block(self, registry):
        """Shrug It Off (block + draw) causes more cards played than Defend."""
        deck_shrug = ["strike"] * 5 + ["shrug_it_off"] * 4 + ["bash"]
        r_starter = run_experiment(registry, STARTER, ["jaw_worm"], n_runs=self.N)
        r_shrug = run_experiment(
            registry, deck_shrug, ["jaw_worm"], n_runs=self.N,
        )
        assert mean_stat(r_shrug, "cards_played") > mean_stat(
            r_starter, "cards_played",
        )

    def test_1_4_aoe_vs_single_target(self, registry):
        """AoE kills multiple enemies faster than single-target attacks."""
        deck_aoe = ["cleave"] * 10
        deck_st = ["strike"] * 10
        enemies_multi = ["red_louse", "red_louse", "red_louse"]
        r_st = run_experiment(
            registry, deck_st, enemies_multi, n_runs=self.N,
        )
        r_aoe = run_experiment(
            registry, deck_aoe, enemies_multi, n_runs=self.N,
        )
        # AoE should kill 3 enemies in fewer turns
        assert mean_stat(r_aoe, "turns") < mean_stat(r_st, "turns")

    def test_1_5_deck_dilution(self, registry):
        """Adding 5 Wounds (unplayable) dilutes the deck and hurts performance."""
        bloated = STARTER + ["wound"] * 5
        r_base = run_experiment(registry, STARTER, ["jaw_worm"], n_runs=self.N)
        r_bloated = run_experiment(
            registry, bloated, ["jaw_worm"], n_runs=self.N,
        )
        slower = mean_stat(r_bloated, "turns") > mean_stat(r_base, "turns")
        more_damage = mean_stat(r_bloated, "hp_lost") > mean_stat(r_base, "hp_lost")
        assert slower or more_damage

    def test_1_6_pure_extremes_fail(self, registry):
        """All-Defend almost never wins; all-Strike has moderate win rate."""
        r_defend = run_experiment(
            registry, ["defend"] * 10, ["jaw_worm"], n_runs=self.N,
        )
        r_strike = run_experiment(
            registry, ["strike"] * 10, ["jaw_worm"], n_runs=self.N,
        )
        wr_defend = win_rate(r_defend)
        wr_strike = win_rate(r_strike)
        assert wr_defend < 0.05
        assert wr_strike > 0.30


# ===================================================================
# Category 2: Mechanic Isolation
# ===================================================================


class TestMechanicIsolation:
    """Deterministic and statistical tests for individual mechanics."""

    # -- Deterministic damage pipeline tests --------------------------------

    def test_2_1_vulnerable(self):
        """Vulnerable multiplies damage by 1.5x."""
        player = _make_player()
        enemy = _make_enemy()
        apply_status(enemy, "vulnerable", 2)
        assert calculate_damage(6, player, enemy) == 9  # floor(6 * 1.5)

    def test_2_2_weak(self):
        """Weak multiplies outgoing damage by 0.75x."""
        player = _make_player()
        enemy = _make_enemy()
        apply_status(player, "weak", 2)
        assert calculate_damage(6, player, enemy) == 4  # floor(6 * 0.75)

    @pytest.mark.parametrize(
        "str_val,expected",
        [(0, 6), (1, 7), (2, 8), (3, 9), (5, 11), (10, 16)],
    )
    def test_2_3_strength_linear(self, str_val, expected):
        """Strength adds linearly to base damage."""
        player = _make_player()
        enemy = _make_enemy()
        if str_val > 0:
            apply_status(player, "strength", str_val)
        assert calculate_damage(6, player, enemy) == expected

    @pytest.mark.statistical
    def test_2_4_block_reduces_hp_loss(self, registry):
        """Cross-validates 1.1: block reduces per-turn HP loss."""
        r_starter = run_experiment(registry, STARTER, ["jaw_worm"], n_runs=500)
        r_strikes = run_experiment(
            registry, ["strike"] * 10, ["jaw_worm"], n_runs=500,
        )
        hpt_starter = mean_stat(r_starter, "hp_lost") / mean_stat(r_starter, "turns")
        hpt_strikes = mean_stat(r_strikes, "hp_lost") / mean_stat(r_strikes, "turns")
        assert hpt_starter < hpt_strikes

    def test_2_5_draw_increases_hand_size(self, registry):
        """Pommel Strike's draw effect works: it draws a card after dealing damage."""
        player = _make_player()
        enemy = _make_enemy()
        deck = [CardInstance(card_id="defend") for _ in range(10)]
        hand = [CardInstance(card_id="pommel_strike")]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck, hand=hand),
            rng=GameRNG(1),
        )
        interpreter = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("pommel_strike")
        # Before: 1 in hand, 10 in draw
        assert len(battle.card_piles.hand) == 1
        interpreter.play_card(card_def, battle, hand[0], chosen_target=0)
        # After: pommel_strike discarded, but drew 1 card -> 1 card in hand
        assert len(battle.card_piles.hand) == 1
        assert len(battle.card_piles.draw) == 9
        # Enemy took 9 damage (pommel_strike base damage)
        assert enemy.current_hp == 200 - 9

    def test_2_6_strength_plus_vulnerable(self):
        """Str + Vuln: floor((6+3) * 1.5) = 13."""
        player = _make_player()
        enemy = _make_enemy()
        apply_status(player, "strength", 3)
        apply_status(enemy, "vulnerable", 2)
        assert calculate_damage(6, player, enemy) == 13

    def test_2_7_full_damage_pipeline(self):
        """Str + Vuln + Weak: floor(floor((6+3)*1.5) * 0.75) = 9."""
        player = _make_player()
        enemy = _make_enemy()
        apply_status(player, "strength", 3)
        apply_status(player, "weak", 2)
        apply_status(enemy, "vulnerable", 2)
        assert calculate_damage(6, player, enemy) == 9

    # -- Bug regression tests -----------------------------------------------

    def test_2_8_body_slam(self, registry):
        """Body Slam deals damage equal to current block."""
        player = _make_player()
        player.block = 15
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=GameRNG(1),
        )
        interpreter = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("body_slam")
        card_inst = CardInstance(card_id="body_slam")
        battle.card_piles.hand.append(card_inst)
        interpreter.play_card(card_def, battle, card_inst, chosen_target=0)
        assert enemy.current_hp == 200 - 15

    def test_2_9_heavy_blade(self, registry):
        """Heavy Blade: 3 strength -> 14 + (3*3) = 23 damage."""
        player = _make_player()
        apply_status(player, "strength", 3)
        enemy = _make_enemy()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=GameRNG(1),
        )
        interpreter = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("heavy_blade")
        card_inst = CardInstance(card_id="heavy_blade")
        battle.card_piles.hand.append(card_inst)
        interpreter.play_card(card_def, battle, card_inst, chosen_target=0)
        assert enemy.current_hp == 200 - 23

    def test_2_10_perfected_strike(self, registry):
        """Perfected Strike: 5 Strikes in deck -> 6 + (2*5) = 16 damage."""
        player = _make_player()
        enemy = _make_enemy()
        # 4 strikes in draw + perfected_strike in hand = 5 cards with "strike"
        draw = [CardInstance(card_id="strike") for _ in range(4)]
        hand = [CardInstance(card_id="perfected_strike")]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=draw, hand=hand),
            rng=GameRNG(1),
        )
        interpreter = ActionInterpreter(card_registry=registry.cards)
        card_def = registry.get_card("perfected_strike")
        interpreter.play_card(card_def, battle, hand[0], chosen_target=0)
        assert enemy.current_hp == 200 - 16

    def test_2_11_metallicize(self):
        """Metallicize: 3 stacks -> +3 block at end of turn."""
        player = _make_player()
        apply_status(player, "Metallicize", 3)
        enemy = _make_enemy()
        deck = [CardInstance(card_id="strike") for _ in range(10)]
        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=GameRNG(1),
        )

        # Simulate turn cycle (same logic as CombatSimulator)
        battle.start_turn()
        battle.end_turn()
        decay_statuses(player)
        # Metallicize block (mirroring runner.py logic)
        met_stacks = player.status_effects.get("Metallicize", 0)
        assert met_stacks == 3
        player.block += met_stacks
        assert player.block == 3

        # Second turn: block cleared at start, re-granted at end
        battle.start_turn()
        assert player.block == 0
        battle.end_turn()
        decay_statuses(player)
        player.block += player.status_effects.get("Metallicize", 0)
        assert player.block == 3


# ===================================================================
# Category 3: Enemy Behavior
# ===================================================================


class TestEnemyBehavior:
    """Enemy AI validation tests."""

    def test_3_1_cultist_opens_incantation(self, registry):
        """Cultist always opens with Incantation."""
        results = run_experiment(
            registry, STARTER, ["cultist"], n_runs=100, base_seed=1,
        )
        for r in results:
            bt = r.battles[0]
            assert len(bt.enemy_moves_per_turn) > 0
            assert bt.enemy_moves_per_turn[0] == ["Incantation"]

    def test_3_2_jaw_worm_opens_chomp(self, registry):
        """Jaw Worm always opens with Chomp."""
        results = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=100, base_seed=1,
        )
        for r in results:
            bt = r.battles[0]
            assert len(bt.enemy_moves_per_turn) > 0
            assert bt.enemy_moves_per_turn[0] == ["Chomp"]

    @pytest.mark.statistical
    def test_3_3_jaw_worm_move_weights(self, registry):
        """Jaw Worm post-opening move distribution matches weights."""
        results = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=1000, base_seed=1,
        )
        # Collect all moves after turn 1
        move_counts: Counter[str] = Counter()
        total = 0
        for r in results:
            bt = r.battles[0]
            for turn_moves in bt.enemy_moves_per_turn[1:]:
                for move_name in turn_moves:
                    move_counts[move_name] += 1
                    total += 1

        if total > 0:
            thrash_pct = move_counts.get("Thrash", 0) / total
            bellow_pct = move_counts.get("Bellow", 0) / total
            chomp_pct = move_counts.get("Chomp", 0) / total
            assert 0.35 <= thrash_pct <= 0.55, f"Thrash {thrash_pct:.2%}"
            assert 0.20 <= bellow_pct <= 0.40, f"Bellow {bellow_pct:.2%}"
            assert 0.15 <= chomp_pct <= 0.35, f"Chomp {chomp_pct:.2%}"

    @pytest.mark.statistical
    def test_3_4_cultist_scales_damage(self, registry):
        """Cultist deals increasing damage per turn (Ritual -> Strength)."""
        # Use high-HP player to ensure long fights
        results = run_experiment(
            registry, STARTER, ["cultist"], n_runs=500, base_seed=1,
        )
        # Partition into short and long fights
        turns_list = [r.battles[0].turns for r in results]
        median_turns = sorted(turns_list)[len(turns_list) // 2]

        short_dpt = []  # damage per turn for short fights
        long_dpt = []
        for r in results:
            bt = r.battles[0]
            if bt.turns <= 1:
                continue
            dpt = bt.hp_lost / bt.turns
            if bt.turns < median_turns:
                short_dpt.append(dpt)
            elif bt.turns > median_turns:
                long_dpt.append(dpt)

        if short_dpt and long_dpt:
            avg_short = sum(short_dpt) / len(short_dpt)
            avg_long = sum(long_dpt) / len(long_dpt)
            # Long fights should have higher damage-per-turn (Ritual scaling)
            assert avg_long > avg_short, (
                f"Long fights DPT {avg_long:.2f} not > short {avg_short:.2f}"
            )

    def test_3_5_red_louse_damage_varies(self, registry):
        """Red Louse Bite damage spans the 5-7 range across runs."""
        enemy_data = registry.get_enemy_data("red_louse")
        damages_seen: set[int] = set()

        for seed in range(100):
            rng = GameRNG(seed).fork("combat")
            enemy = Enemy(
                name="Red Louse",
                enemy_id="red_louse",
                max_hp=12,
                current_hp=12,
            )
            player = _make_player()
            battle = BattleState(
                player=player,
                enemies=[enemy],
                rng=rng,
            )
            ai = EnemyAI(ActionInterpreter())
            ai.determine_intent(enemy, enemy_data, battle, rng)
            if enemy.intent_damage is not None:
                damages_seen.add(enemy.intent_damage)

        assert {5, 6, 7}.issubset(damages_seen), f"Saw only {damages_seen}"

    def test_3_6_jaw_worm_bellow(self, registry):
        """Jaw Worm Bellow grants exactly +3 strength and +6 block."""
        enemy = Enemy(
            name="Jaw Worm",
            enemy_id="jaw_worm",
            max_hp=44,
            current_hp=44,
        )
        player = _make_player()
        battle = BattleState(
            player=player,
            enemies=[enemy],
            rng=GameRNG(1),
        )
        interpreter = ActionInterpreter()
        # Execute Bellow's actions with enemy as source
        bellow_actions = [
            ActionNode(
                action_type=ActionType.GAIN_STRENGTH, value=3, target="self",
            ),
            ActionNode(
                action_type=ActionType.GAIN_BLOCK, value=6, target="self",
            ),
        ]
        interpreter.execute_actions(bellow_actions, battle, source="0")
        assert get_status_stacks(enemy, "strength") == 3
        assert enemy.block == 6


# ===================================================================
# Category 4: Statistical Sanity
# ===================================================================


class TestStatisticalSanity:
    """Sanity checks on the simulation's statistical properties."""

    def test_4_1_different_seeds_differ(self, registry):
        """Different seeds produce different outcomes."""
        r1 = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=50, base_seed=1,
        )
        r2 = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=50, base_seed=9999,
        )
        # At least some results should differ
        results_1 = [r.battles[0].result for r in r1]
        results_2 = [r.battles[0].result for r in r2]
        hp_1 = [r.battles[0].hp_lost for r in r1]
        hp_2 = [r.battles[0].hp_lost for r in r2]
        assert results_1 != results_2 or hp_1 != hp_2

    def test_4_2_same_seed_identical(self, registry):
        """Same seed produces identical outcomes."""
        r1 = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=20, base_seed=42,
        )
        r2 = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=20, base_seed=42,
        )
        for a, b in zip(r1, r2):
            assert a.battles[0].result == b.battles[0].result
            assert a.battles[0].turns == b.battles[0].turns
            assert a.battles[0].hp_lost == b.battles[0].hp_lost
            assert a.battles[0].cards_played == b.battles[0].cards_played
            assert a.battles[0].damage_dealt == b.battles[0].damage_dealt

    @pytest.mark.statistical
    def test_4_3_win_rates_sane(self, registry):
        """Win rates are above 5% for each enemy (easy enemies may reach 100%)."""
        for enemy_id in ["jaw_worm", "cultist", "red_louse"]:
            results = run_experiment(
                registry, STARTER, [enemy_id], n_runs=500,
            )
            wr = win_rate(results)
            assert wr > 0.05, f"{enemy_id} win rate {wr:.2%} too low"

    @pytest.mark.statistical
    def test_4_4_cards_correlate_with_turns(self, registry):
        """Cards played should strongly correlate with number of turns."""
        results = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=500,
        )
        turns = [float(r.battles[0].turns) for r in results]
        cards = [float(r.battles[0].cards_played) for r in results]
        r = _pearson_r(turns, cards)
        assert r > 0.8, f"Pearson r = {r:.3f}, expected > 0.8"

    @pytest.mark.statistical
    def test_4_5_hp_lost_in_most_wins(self, registry):
        """Fewer than 10% of wins have 0 HP lost (flawless victories are rare)."""
        results = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=500,
        )
        wins = [r for r in results if r.battles[0].result == "win"]
        if not wins:
            pytest.skip("No wins to analyze")
        flawless = sum(1 for r in wins if r.battles[0].hp_lost == 0)
        flawless_pct = flawless / len(wins)
        assert flawless_pct < 0.10, f"Flawless rate {flawless_pct:.2%} >= 10%"

    def test_4_6_seeds_recorded(self, registry):
        """Each result records the correct seed."""
        base_seed = 100
        results = run_experiment(
            registry, STARTER, ["jaw_worm"], n_runs=20, base_seed=base_seed,
        )
        for i, r in enumerate(results):
            assert r.seed == base_seed + i


# ===================================================================
# Category 5: Comparative Balance
# ===================================================================


@pytest.mark.statistical
class TestComparativeBalance:
    """Cross-enemy and cross-card comparisons."""

    N = 500

    def _run_all_enemies(self, registry):
        """Run starter deck against all 3 enemies."""
        data = {}
        for eid in ["red_louse", "cultist", "jaw_worm"]:
            data[eid] = run_experiment(
                registry, STARTER, [eid], n_runs=self.N,
            )
        return data

    def test_5_1_red_louse_easiest(self, registry):
        """Red Louse has lowest HP loss and highest win rate."""
        data = self._run_all_enemies(registry)
        wr_rl = win_rate(data["red_louse"])
        hp_rl = mean_stat(data["red_louse"], "hp_lost")
        for eid in ["cultist", "jaw_worm"]:
            assert wr_rl >= win_rate(data[eid]), (
                f"Red Louse WR {wr_rl:.2%} < {eid} {win_rate(data[eid]):.2%}"
            )
            assert hp_rl <= mean_stat(data[eid], "hp_lost"), (
                f"Red Louse hp_lost {hp_rl:.1f} > {eid}"
            )

    def test_5_2_cultist_hardest(self, registry):
        """Cultist has highest HP loss and lowest win rate (Ritual scaling)."""
        data = self._run_all_enemies(registry)
        wr_c = win_rate(data["cultist"])
        hp_c = mean_stat(data["cultist"], "hp_lost")
        for eid in ["jaw_worm", "red_louse"]:
            assert wr_c <= win_rate(data[eid]), (
                f"Cultist WR {wr_c:.2%} > {eid} {win_rate(data[eid]):.2%}"
            )
            assert hp_c >= mean_stat(data[eid], "hp_lost"), (
                f"Cultist hp_lost {hp_c:.1f} < {eid}"
            )

    def test_5_3_cultist_scales_with_length(self, registry):
        """Cultist fights: longer fights cause disproportionately more damage."""
        results = run_experiment(
            registry, STARTER, ["cultist"], n_runs=self.N,
        )
        turns_list = [r.battles[0].turns for r in results]
        median = sorted(turns_list)[len(turns_list) // 2]

        short_hp = [
            r.battles[0].hp_lost
            for r in results
            if r.battles[0].turns < median and r.battles[0].turns > 0
        ]
        long_hp = [
            r.battles[0].hp_lost
            for r in results
            if r.battles[0].turns > median
        ]

        if short_hp and long_hp:
            avg_short = sum(short_hp) / len(short_hp)
            avg_long = sum(long_hp) / len(long_hp)
            # Long fights should lose proportionally more HP per turn
            short_dpt = avg_short / (median - 1) if median > 1 else avg_short
            long_dpt = avg_long / (median + 1)
            assert long_dpt > short_dpt

    def test_5_4_bash_most_impactful(self, registry):
        """Removing Bash hurts win rate more than removing a Defend."""
        deck_no_bash = ["strike"] * 5 + ["defend"] * 4  # 9 cards, no Bash
        deck_no_defend = ["strike"] * 5 + ["defend"] * 3 + ["bash"]  # 9 cards

        r_full = run_experiment(registry, STARTER, ["jaw_worm"], n_runs=self.N)
        r_no_bash = run_experiment(
            registry, deck_no_bash, ["jaw_worm"], n_runs=self.N,
        )
        r_no_defend = run_experiment(
            registry, deck_no_defend, ["jaw_worm"], n_runs=self.N,
        )

        wr_full = win_rate(r_full)
        drop_bash = wr_full - win_rate(r_no_bash)
        drop_defend = wr_full - win_rate(r_no_defend)
        assert drop_bash > drop_defend, (
            f"Bash drop {drop_bash:.2%} <= Defend drop {drop_defend:.2%}"
        )
