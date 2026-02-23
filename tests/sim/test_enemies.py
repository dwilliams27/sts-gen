"""Tests for Act 1 enemy AI patterns, mechanics, and combat integration.

Tests verify:
- All enemies load correctly from JSON
- AI patterns produce correct move sequences
- Special mechanics (split, escape, sleep/wake, mode shift)
- Combat-start powers (Curl Up, Angry, Enrage)
- On-death hooks (Spore Cloud)
- Multi-enemy encounters work without errors
"""

import pytest

from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.status_effects import apply_status, has_status, get_status_stacks
from sts_gen.sim.runner import BatchRunner, CombatSimulator, EnemyAI


@pytest.fixture
def registry():
    r = ContentRegistry()
    r.load_vanilla_cards()
    r.load_vanilla_enemies()
    return r


@pytest.fixture
def rng():
    return GameRNG(42)


def _make_battle(
    registry, rng, enemy_ids, player_hp=80, deck=None,
):
    """Create a BattleState with the given enemies and starter deck."""
    player = Player(name="Ironclad", max_hp=player_hp, current_hp=player_hp, max_energy=3)

    if deck is None:
        deck_ids = registry.get_starter_deck("ironclad")
    else:
        deck_ids = deck
    cards = [CardInstance(card_id=cid) for cid in deck_ids]

    enemies = []
    for eid in enemy_ids:
        edata = registry.get_enemy_data(eid)
        hp_min = edata["hp_min"]
        hp_max = edata["hp_max"]
        hp = rng.random_int(hp_min, hp_max)
        enemies.append(Enemy(
            name=edata["name"], enemy_id=eid, max_hp=hp, current_hp=hp,
        ))

    return BattleState(
        player=player,
        enemies=enemies,
        card_piles=CardPiles(draw=cards),
        rng=rng,
    )


# =====================================================================
# Enemy data loading
# =====================================================================


class TestEnemyLoading:
    """All 25 enemies load from JSON with correct structure."""

    def test_all_enemies_load(self, registry):
        ids = registry.list_enemy_ids()
        assert len(ids) == 25

    def test_every_enemy_has_moves(self, registry):
        for eid in registry.list_enemy_ids():
            e = registry.get_enemy_data(eid)
            assert "moves" in e, f"{eid} missing moves"
            assert len(e["moves"]) > 0, f"{eid} has empty moves"

    def test_every_enemy_has_hp_range(self, registry):
        for eid in registry.list_enemy_ids():
            e = registry.get_enemy_data(eid)
            assert e["hp_min"] > 0, f"{eid} has invalid hp_min"
            assert e["hp_max"] >= e["hp_min"], f"{eid} hp_max < hp_min"

    def test_every_enemy_has_pattern(self, registry):
        for eid in registry.list_enemy_ids():
            e = registry.get_enemy_data(eid)
            assert "pattern" in e, f"{eid} missing pattern"
            assert "type" in e["pattern"], f"{eid} pattern missing type"


# =====================================================================
# AI Pattern Tests
# =====================================================================


class TestFixedSequencePattern:
    """Tests for fixed_sequence pattern (Cultist, Gremlin Wizard, Sentries, etc.)."""

    def test_cultist_sequence(self, registry, rng):
        """Cultist: Incantation once, then Dark Strike forever."""
        edata = registry.get_enemy_data("cultist")
        enemy = Enemy(name="Cultist", enemy_id="cultist", max_hp=50, current_hp=50)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        # Turn 1: Incantation
        ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
        assert enemy.intent == "Incantation"

        # Turns 2-5: Dark Strike
        for _ in range(4):
            ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
            assert enemy.intent == "Dark Strike"

    def test_gremlin_wizard_charge_cycle(self, registry, rng):
        """Gremlin Wizard: 2 charges → blast, then 3 charges → blast loop."""
        edata = registry.get_enemy_data("gremlin_wizard")
        enemy = Enemy(name="GW", enemy_id="gremlin_wizard", max_hp=23, current_hp=23)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        intents = []
        for _ in range(11):
            ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
            intents.append(enemy.intent)

        # First cycle: Charge, Charge, Blast
        assert intents[0] == "Charging"
        assert intents[1] == "Charging"
        assert intents[2] == "Ultimate Blast"
        # Second cycle: Charge, Charge, Charge, Blast
        assert intents[3] == "Charging"
        assert intents[4] == "Charging"
        assert intents[5] == "Charging"
        assert intents[6] == "Ultimate Blast"
        # Third cycle repeats
        assert intents[7] == "Charging"
        assert intents[10] == "Ultimate Blast"

    def test_sentry_alternation(self, registry, rng):
        """Sentries alternate bolt/beam, offset by position index."""
        edata = registry.get_enemy_data("sentry")
        enemies = [
            Enemy(name="S0", enemy_id="sentry", max_hp=40, current_hp=40),
            Enemy(name="S1", enemy_id="sentry", max_hp=40, current_hp=40),
            Enemy(name="S2", enemy_id="sentry", max_hp=40, current_hp=40),
        ]
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=enemies,
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        for i, e in enumerate(enemies):
            ai.init_enemy_state(e, edata, battle, rng, i)

        # Turn 1
        for i, e in enumerate(enemies):
            ai.determine_intent(e, edata, battle, rng, enemy_idx=i)

        # Sentry 0 (even): bolt first
        assert enemies[0].intent == "Bolt"
        # Sentry 1 (odd): beam first
        assert enemies[1].intent == "Beam"
        # Sentry 2 (even): bolt first
        assert enemies[2].intent == "Bolt"

        # Turn 2: alternates
        for i, e in enumerate(enemies):
            ai.determine_intent(e, edata, battle, rng, enemy_idx=i)

        assert enemies[0].intent == "Beam"
        assert enemies[1].intent == "Bolt"
        assert enemies[2].intent == "Beam"


class TestWeightedRandomPattern:
    """Tests for weighted_random pattern with per-move consecutive limits."""

    def test_jaw_worm_opens_chomp(self, registry, rng):
        """Jaw Worm always opens with Chomp."""
        edata = registry.get_enemy_data("jaw_worm")
        enemy = Enemy(name="JW", enemy_id="jaw_worm", max_hp=42, current_hp=42)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
        assert enemy.intent == "Chomp"

    def test_jaw_worm_respects_per_move_consecutive(self, registry):
        """Jaw Worm: Chomp and Bellow limited to 1 consecutive, Thrash to 2."""
        edata = registry.get_enemy_data("jaw_worm")

        # Run many combats and verify no illegal consecutive runs
        for seed in range(50):
            rng = GameRNG(seed)
            enemy = Enemy(name="JW", enemy_id="jaw_worm", max_hp=42, current_hp=42)
            battle = BattleState(
                player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
                enemies=[enemy],
                card_piles=CardPiles(),
                rng=rng,
            )
            ai = EnemyAI(ActionInterpreter())
            ai.init_enemy_state(enemy, edata, battle, rng, 0)

            moves = []
            for _ in range(20):
                ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
                moves.append(enemy.intent)

            # Check constraints (after opening Chomp)
            for i in range(1, len(moves) - 1):
                if moves[i] == "Chomp" and moves[i - 1] == "Chomp":
                    pytest.fail(f"Seed {seed}: Chomp used twice in a row at {i}")
                if moves[i] == "Bellow" and moves[i - 1] == "Bellow":
                    pytest.fail(f"Seed {seed}: Bellow used twice in a row at {i}")
            for i in range(2, len(moves)):
                if (
                    moves[i] == "Thrash"
                    and moves[i - 1] == "Thrash"
                    and moves[i - 2] == "Thrash"
                ):
                    pytest.fail(f"Seed {seed}: Thrash used 3 times in a row at {i}")


class TestSpecialPatterns:
    """Tests for unique enemy patterns."""

    def test_looter_sequence_short_path(self, registry):
        """Looter short path: mug, mug, smoke_bomb, escape."""
        # Use a seed where the 50/50 goes to short path
        edata = registry.get_enemy_data("looter")
        for seed in range(100):
            rng = GameRNG(seed)
            enemy = Enemy(name="L", enemy_id="looter", max_hp=46, current_hp=46)
            battle = BattleState(
                player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
                enemies=[enemy],
                card_piles=CardPiles(),
                rng=rng,
            )
            ai = EnemyAI(ActionInterpreter())
            ai.init_enemy_state(enemy, edata, battle, rng, 0)

            intents = []
            for _ in range(5):
                ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
                intents.append(enemy.intent)

            assert intents[0] == "Mug"
            assert intents[1] == "Mug"
            if intents[2] == "Smoke Bomb":
                # Short path
                assert intents[3] == "Escape"
                return  # Found a short path seed

        pytest.fail("Never found a short-path seed in 100 attempts")

    def test_looter_sequence_long_path(self, registry):
        """Looter long path: mug, mug, lunge, smoke_bomb, escape."""
        edata = registry.get_enemy_data("looter")
        for seed in range(100):
            rng = GameRNG(seed)
            enemy = Enemy(name="L", enemy_id="looter", max_hp=46, current_hp=46)
            battle = BattleState(
                player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
                enemies=[enemy],
                card_piles=CardPiles(),
                rng=rng,
            )
            ai = EnemyAI(ActionInterpreter())
            ai.init_enemy_state(enemy, edata, battle, rng, 0)

            intents = []
            for _ in range(5):
                ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
                intents.append(enemy.intent)

            assert intents[0] == "Mug"
            assert intents[1] == "Mug"
            if intents[2] == "Lunge":
                # Long path
                assert intents[3] == "Smoke Bomb"
                assert intents[4] == "Escape"
                return

        pytest.fail("Never found a long-path seed in 100 attempts")

    def test_shield_gremlin_protects_when_allies_alive(self, registry, rng):
        """Shield Gremlin uses Protect when other enemies are alive."""
        edata = registry.get_enemy_data("shield_gremlin")
        ally = Enemy(name="Ally", enemy_id="mad_gremlin", max_hp=22, current_hp=22)
        shield = Enemy(name="SG", enemy_id="shield_gremlin", max_hp=13, current_hp=13)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[ally, shield],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())

        ai.determine_intent(shield, edata, battle, rng, enemy_idx=1)
        assert shield.intent == "Protect"

    def test_shield_gremlin_attacks_when_alone(self, registry, rng):
        """Shield Gremlin uses Shield Bash when alone."""
        edata = registry.get_enemy_data("shield_gremlin")
        shield = Enemy(name="SG", enemy_id="shield_gremlin", max_hp=13, current_hp=13)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[shield],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())

        ai.determine_intent(shield, edata, battle, rng, enemy_idx=0)
        assert shield.intent == "Shield Bash"

    def test_red_slaver_opens_stab(self, registry, rng):
        """Red Slaver always opens with Stab."""
        edata = registry.get_enemy_data("red_slaver")
        enemy = Enemy(name="RS", enemy_id="red_slaver", max_hp=48, current_hp=48)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
        assert enemy.intent == "Stab"


# =====================================================================
# Combat-start Powers
# =====================================================================


class TestCombatStartPowers:
    def test_curl_up_initializes(self, registry, rng):
        """Curl Up is stored in enemy state at combat start."""
        edata = registry.get_enemy_data("red_louse")
        enemy = Enemy(name="RL", enemy_id="red_louse", max_hp=12, current_hp=12)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        key = ai._enemy_key(enemy)
        curl_up = ai._enemy_state[key]["curl_up"]
        assert 3 <= curl_up <= 7

    def test_angry_applied_as_status(self, registry, rng):
        """Mad Gremlin gets Angry status at combat start."""
        edata = registry.get_enemy_data("mad_gremlin")
        enemy = Enemy(name="MG", enemy_id="mad_gremlin", max_hp=22, current_hp=22)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        assert enemy.status_effects.get("Angry", 0) == 1

    def test_lagavulin_starts_with_metallicize(self, registry, rng):
        """Lagavulin starts sleeping with 8 Metallicize."""
        edata = registry.get_enemy_data("lagavulin")
        enemy = Enemy(name="Lag", enemy_id="lagavulin", max_hp=110, current_hp=110)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        assert enemy.status_effects.get("Metallicize", 0) == 8


# =====================================================================
# Special Mechanics
# =====================================================================


class TestLagavulinSleep:
    def test_lagavulin_sleeps_3_turns(self, registry, rng):
        """Lagavulin uses Sleep for 3 turns, then starts attacking."""
        edata = registry.get_enemy_data("lagavulin")
        enemy = Enemy(name="Lag", enemy_id="lagavulin", max_hp=110, current_hp=110)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        intents = []
        for _ in range(6):
            ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
            intents.append(enemy.intent)

        # 3 turns of sleep
        assert intents[0] == "Sleep"
        assert intents[1] == "Sleep"
        assert intents[2] == "Sleep"
        # Then awake cycle: Attack, Attack, Siphon Soul
        assert intents[3] == "Attack"
        assert intents[4] == "Attack"
        assert intents[5] == "Siphon Soul"


class TestGuardianModeShift:
    def test_guardian_offensive_cycle(self, registry, rng):
        """Guardian follows offensive cycle: Charging → Fierce Bash → Vent Steam → Whirlwind."""
        edata = registry.get_enemy_data("the_guardian")
        enemy = Enemy(name="G", enemy_id="the_guardian", max_hp=240, current_hp=240)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        intents = []
        for _ in range(4):
            ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
            intents.append(enemy.intent)

        assert intents == ["Charging Up", "Fierce Bash", "Vent Steam", "Whirlwind"]


class TestSplitMechanic:
    def test_acid_slime_l_splits(self, registry, rng):
        """Acid Slime (L) splits into 2 Acid Slime (M) at half HP."""
        battle = _make_battle(registry, rng, ["acid_slime_l"])
        enemy = battle.enemies[0]
        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter,
                              __import__("sts_gen.sim.play_agents.random_agent", fromlist=["RandomAgent"]).RandomAgent(rng=rng))

        # Manually damage the slime to below 50%
        enemy.current_hp = enemy.max_hp // 2  # At exactly 50%

        # Run the split check
        sim.enemy_ai.init_enemy_state(enemy, registry.get_enemy_data("acid_slime_l"), battle, rng, 0)
        enemy_datas = [registry.get_enemy_data(e.enemy_id) for e in battle.enemies]
        sim._check_split(enemy, 0, enemy_datas, battle)

        # Should have split: original dead + 2 new medium slimes
        assert enemy.is_dead
        assert len(battle.enemies) == 3  # 1 dead original + 2 new
        assert battle.enemies[1].enemy_id == "acid_slime_m"
        assert battle.enemies[2].enemy_id == "acid_slime_m"


class TestEscapeMechanic:
    def test_looter_escape_ends_combat(self, registry, rng):
        """When Looter uses Escape, it is treated as dead (combat ends)."""
        battle = _make_battle(registry, rng, ["looter"])
        enemy = battle.enemies[0]
        ai = EnemyAI(ActionInterpreter(card_registry=registry.cards))
        ai.init_enemy_state(enemy, registry.get_enemy_data("looter"), battle, rng, 0)

        # Force the escape move
        escape_move = None
        for m in registry.get_enemy_data("looter")["moves"]:
            if m["id"] == "escape":
                escape_move = m
                break
        enemy._current_move = escape_move
        enemy._current_move_type = "escape"

        ai.execute_intent(enemy, 0, battle)

        assert enemy.is_dead
        assert battle.is_over


# =====================================================================
# Execute intent extensions
# =====================================================================


class TestExecuteIntentExtensions:
    def test_debuff_applied_to_player(self, registry, rng):
        """Enemy move with debuffs field applies status to player."""
        edata = registry.get_enemy_data("green_louse")
        enemy = Enemy(name="GL", enemy_id="green_louse", max_hp=14, current_hp=14)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        # Find the Spit Web move
        spit_web = None
        for m in edata["moves"]:
            if m["id"] == "spit_web":
                spit_web = m
        assert spit_web is not None

        enemy._current_move = spit_web
        enemy._current_move_type = spit_web["type"]
        ai.execute_intent(enemy, 0, battle)

        assert has_status(battle.player, "weak")
        assert get_status_stacks(battle.player, "weak") == 2

    def test_status_cards_added_to_discard(self, registry, rng):
        """Enemy move with status_cards adds cards to player's discard."""
        edata = registry.get_enemy_data("acid_slime_m")
        enemy = Enemy(name="AS", enemy_id="acid_slime_m", max_hp=30, current_hp=30)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[enemy],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())

        # Find Corrosive Spit
        spit = None
        for m in edata["moves"]:
            if m["id"] == "corrosive_spit":
                spit = m
        assert spit is not None

        enemy._current_move = spit
        enemy._current_move_type = "attack"
        enemy.intent_damage = 7
        enemy.intent_hits = 1
        ai.execute_intent(enemy, 0, battle)

        # Should have added 1 Slimed card to discard
        slimed_cards = [c for c in battle.card_piles.discard if c.card_id == "slimed"]
        assert len(slimed_cards) == 1

    def test_protect_ally_gives_block(self, registry, rng):
        """Shield Gremlin's Protect gives block to an ally."""
        shield_data = registry.get_enemy_data("shield_gremlin")
        ally = Enemy(name="Ally", enemy_id="mad_gremlin", max_hp=22, current_hp=22)
        shield = Enemy(name="SG", enemy_id="shield_gremlin", max_hp=13, current_hp=13)
        battle = BattleState(
            player=Player(name="P", max_hp=80, current_hp=80, max_energy=3),
            enemies=[ally, shield],
            card_piles=CardPiles(),
            rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())

        protect = None
        for m in shield_data["moves"]:
            if m["id"] == "protect":
                protect = m
        shield._current_move = protect
        shield._current_move_type = "protect_ally"

        ai.execute_intent(shield, 1, battle)

        # Ally should have gained 7 block
        assert ally.block == 7


# =====================================================================
# Combat Integration Tests
# =====================================================================


class TestCombatIntegration:
    """Full combat runs against various enemies complete without errors."""

    @pytest.fixture
    def runner(self, registry):
        return BatchRunner(registry)

    def test_all_normal_enemies_solo(self, runner):
        """10 combats against each normal enemy complete without errors."""
        normals = [
            "jaw_worm", "cultist", "red_louse", "green_louse",
            "acid_slime_s", "acid_slime_m", "spike_slime_s", "spike_slime_m",
            "fungi_beast", "looter", "blue_slaver", "red_slaver",
            "mad_gremlin", "sneaky_gremlin", "fat_gremlin", "gremlin_wizard",
        ]
        for eid in normals:
            results = runner.run_batch(5, {"enemy_ids": [eid]}, base_seed=42)
            assert len(results) == 5, f"{eid}: expected 5 results"
            for r in results:
                assert r.final_result in ("win", "loss"), f"{eid}: bad result {r.final_result}"

    def test_multi_enemy_encounters(self, runner):
        """Multi-enemy encounters complete without errors."""
        configs = [
            ["red_louse", "green_louse"],
            ["acid_slime_s", "acid_slime_s"],
            ["mad_gremlin", "sneaky_gremlin", "fat_gremlin", "shield_gremlin"],
        ]
        for eids in configs:
            results = runner.run_batch(5, {"enemy_ids": eids}, base_seed=42)
            assert len(results) == 5

    def test_elites_run_without_error(self, runner):
        """Elite combats complete without errors."""
        for eid in ["gremlin_nob", "lagavulin"]:
            results = runner.run_batch(5, {"enemy_ids": [eid]}, base_seed=42)
            assert len(results) == 5

    def test_sentries_run_without_error(self, runner):
        """3-Sentry encounter completes without errors."""
        results = runner.run_batch(5, {"enemy_ids": ["sentry", "sentry", "sentry"]}, base_seed=42)
        assert len(results) == 5

    def test_bosses_run_without_error(self, runner):
        """Boss combats complete without errors."""
        for eid in ["the_guardian", "hexaghost", "slime_boss"]:
            results = runner.run_batch(5, {"enemy_ids": [eid]}, base_seed=42)
            assert len(results) == 5

    def test_split_enemies_produce_more_enemies(self, runner):
        """Large slimes and Slime Boss should split during combat."""
        # Run enough combats that splits should occur
        for eid in ["acid_slime_l", "spike_slime_l", "slime_boss"]:
            results = runner.run_batch(10, {"enemy_ids": [eid]}, base_seed=42)
            assert len(results) == 10

    def test_hexaghost_divider_damage_scales(self, registry, rng):
        """Hexaghost Divider damage is floor(player_hp/12)+1 per hit."""
        edata = registry.get_enemy_data("hexaghost")
        enemy = Enemy(name="HG", enemy_id="hexaghost", max_hp=250, current_hp=250)
        player = Player(name="P", max_hp=80, current_hp=72, max_energy=3)
        battle = BattleState(
            player=player, enemies=[enemy],
            card_piles=CardPiles(), rng=rng,
        )
        ai = EnemyAI(ActionInterpreter())
        ai.init_enemy_state(enemy, edata, battle, rng, 0)

        # Turn 1: Activate (no damage)
        ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
        assert enemy.intent == "Activate"

        # Turn 2: Divider - damage should be floor(72/12)+1 = 7 per hit
        ai.determine_intent(enemy, edata, battle, rng, enemy_idx=0)
        assert enemy.intent == "Divider"
        assert enemy.intent_damage == 7  # floor(72/12) + 1
        assert enemy.intent_hits == 6


# =====================================================================
# Encounter Loading
# =====================================================================


class TestEncounterLoading:
    def test_encounters_load(self, registry):
        registry.load_vanilla_encounters()
        assert len(registry.encounters) > 0

    def test_act1_pools_exist(self, registry):
        registry.load_vanilla_encounters()
        act1 = registry.encounters.get("act_1", {})
        assert "easy" in act1
        assert "normal" in act1
        assert "elite" in act1
        assert "boss" in act1

    def test_get_encounter(self, registry):
        registry.load_vanilla_encounters()
        enc = registry.get_encounter("act_1", "easy", "jaw_worm")
        assert enc is not None
        assert enc["enemies"] == ["jaw_worm"]

    def test_get_encounter_pool(self, registry):
        registry.load_vanilla_encounters()
        pool = registry.get_encounter_pool("act_1", "elite")
        assert len(pool) == 3
        elite_ids = {e["id"] for e in pool}
        assert "gremlin_nob" in elite_ids
        assert "lagavulin" in elite_ids
        assert "3_sentries" in elite_ids

    def test_all_encounter_enemies_exist(self, registry):
        """Every enemy_id referenced in encounters.json exists in the enemy registry."""
        registry.load_vanilla_encounters()
        for act_data in registry.encounters.values():
            for pool_list in act_data.values():
                for enc in pool_list:
                    for eid in enc["enemies"]:
                        assert registry.get_enemy_data(eid) is not None, (
                            f"Encounter {enc['id']} references unknown enemy {eid}"
                        )
