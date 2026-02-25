"""Tests for HeuristicAgent — heuristic-based play agent."""

from __future__ import annotations

import pytest

from sts_gen.ir.actions import ActionNode, ActionType
from sts_gen.ir.cards import CardDefinition, CardRarity, CardTarget, CardType
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.mechanics.status_effects import apply_status
from sts_gen.sim.play_agents.heuristic_agent import HeuristicAgent
from sts_gen.sim.play_agents.random_agent import RandomAgent
from sts_gen.sim.runner import BatchRunner, CombatSimulator


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_status_effects()
    reg.load_vanilla_relics()
    reg.load_vanilla_potions()
    return reg


@pytest.fixture
def agent(registry: ContentRegistry) -> HeuristicAgent:
    return HeuristicAgent(registry=registry)


# ======================================================================
# Helpers
# ======================================================================


def _make_player(**kwargs) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(
    enemy_id: str = "jaw_worm",
    hp: int = 44,
    **kwargs,
) -> Enemy:
    defaults = dict(name="Jaw Worm", enemy_id=enemy_id, max_hp=hp, current_hp=hp)
    defaults.update(kwargs)
    return Enemy(**defaults)


def _make_battle(
    player: Player | None = None,
    enemies: list[Enemy] | None = None,
    hand_ids: list[str] | None = None,
    draw_ids: list[str] | None = None,
    energy: int = 3,
) -> BattleState:
    p = player or _make_player()
    p.energy = energy
    hand = [CardInstance(card_id=cid) for cid in (hand_ids or [])]
    draw = [CardInstance(card_id=cid) for cid in (draw_ids or [])]
    return BattleState(
        player=p,
        enemies=enemies or [_make_enemy()],
        card_piles=CardPiles(hand=hand, draw=draw),
        rng=GameRNG(42),
        turn=1,
    )


def _playable(
    registry: ContentRegistry,
    battle: BattleState,
) -> list[tuple[CardInstance, CardDefinition]]:
    """Get playable cards from hand, matching CombatSimulator logic."""
    result = []
    for ci in battle.card_piles.hand:
        cd = registry.get_card(ci.card_id)
        if cd is None:
            continue
        cost = ci.cost_override if ci.cost_override is not None else cd.cost
        if cost == -2:
            continue
        if cost == -1 or cost <= battle.player.energy:
            result.append((ci, cd))
    return result


# ======================================================================
# Helper unit tests
# ======================================================================


class TestEstimateDamage:
    def test_basic_strike(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["strike"])
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("strike")
        target = battle.enemies[0]
        damage = agent._estimate_damage(cd, ci, battle.player, target)
        assert damage == 6

    def test_with_strength(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["strike"])
        apply_status(battle.player, "strength", 3)
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("strike")
        damage = agent._estimate_damage(cd, ci, battle.player, battle.enemies[0])
        assert damage == 9  # 6 + 3

    def test_with_vulnerable(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["strike"])
        apply_status(battle.enemies[0], "vulnerable", 2)
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("strike")
        damage = agent._estimate_damage(cd, ci, battle.player, battle.enemies[0])
        assert damage == 9  # floor(6 * 1.5)

    def test_with_weak(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["strike"])
        apply_status(battle.player, "weak", 2)
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("strike")
        damage = agent._estimate_damage(cd, ci, battle.player, battle.enemies[0])
        assert damage == 4  # floor(6 * 0.75)

    def test_multi_hit_twin_strike(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["twin_strike"])
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("twin_strike")
        damage = agent._estimate_damage(cd, ci, battle.player, battle.enemies[0])
        assert damage == 10  # 5 * 2 via REPEAT


class TestEstimateBlock:
    def test_basic_defend(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["defend"])
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("defend")
        block = agent._estimate_block(cd, ci, battle.player)
        assert block == 5

    def test_with_dexterity(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["defend"])
        apply_status(battle.player, "dexterity", 2)
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("defend")
        block = agent._estimate_block(cd, ci, battle.player)
        assert block == 7  # 5 + 2

    def test_with_frail(self, agent: HeuristicAgent, registry: ContentRegistry):
        battle = _make_battle(hand_ids=["defend"])
        apply_status(battle.player, "frail", 2)
        ci = battle.card_piles.hand[0]
        cd = registry.get_card("defend")
        block = agent._estimate_block(cd, ci, battle.player)
        assert block == 3  # floor(5 * 0.75)


class TestIncomingDamage:
    def test_single_attacker(self, agent: HeuristicAgent):
        enemy = _make_enemy()
        enemy.intent_damage = 10
        enemy.intent_hits = 1
        battle = _make_battle(enemies=[enemy])
        assert agent._incoming_damage(battle) == 10

    def test_multi_hit(self, agent: HeuristicAgent):
        enemy = _make_enemy()
        enemy.intent_damage = 5
        enemy.intent_hits = 3
        battle = _make_battle(enemies=[enemy])
        assert agent._incoming_damage(battle) == 15

    def test_no_attack_intent(self, agent: HeuristicAgent):
        enemy = _make_enemy()
        enemy.intent_damage = None
        battle = _make_battle(enemies=[enemy])
        assert agent._incoming_damage(battle) == 0

    def test_multiple_enemies(self, agent: HeuristicAgent):
        e1 = _make_enemy()
        e1.intent_damage = 8
        e1.intent_hits = 1
        e2 = _make_enemy(enemy_id="cultist", hp=50)
        e2.name = "Cultist"
        e2.intent_damage = 6
        e2.intent_hits = 1
        battle = _make_battle(enemies=[e1, e2])
        assert agent._incoming_damage(battle) == 14


class TestBestTarget:
    def test_prefers_low_hp(self, agent: HeuristicAgent):
        e1 = _make_enemy(hp=40)
        e1.intent_damage = 5
        e1.intent_hits = 1
        e2 = _make_enemy(enemy_id="cultist", hp=10)
        e2.name = "Cultist"
        e2.intent_damage = 5
        e2.intent_hits = 1
        battle = _make_battle(enemies=[e1, e2])
        # e2 has killable bonus (HP<=15) and lower HP
        assert agent._best_target(battle) == 1

    def test_prefers_high_damage_intent(self, agent: HeuristicAgent):
        e1 = _make_enemy(hp=30)
        e1.intent_damage = 3
        e1.intent_hits = 1
        e2 = _make_enemy(enemy_id="cultist", hp=30)
        e2.name = "Cultist"
        e2.intent_damage = 20
        e2.intent_hits = 1
        battle = _make_battle(enemies=[e1, e2])
        # e2 has higher intent damage score
        assert agent._best_target(battle) == 1

    def test_skips_dead(self, agent: HeuristicAgent):
        e1 = _make_enemy(hp=0)
        e2 = _make_enemy(enemy_id="cultist", hp=30)
        e2.name = "Cultist"
        e2.intent_damage = 5
        e2.intent_hits = 1
        battle = _make_battle(enemies=[e1, e2])
        assert agent._best_target(battle) == 1


# ======================================================================
# Card play priority tests
# ======================================================================


class TestCardPlayPriority:
    def test_offering_first(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Offering should be played first when HP > 10."""
        battle = _make_battle(
            hand_ids=["offering", "strike", "defend"],
            player=_make_player(current_hp=50),
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "offering"

    def test_offering_skipped_low_hp(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Offering should not be played when HP <= 10."""
        battle = _make_battle(
            hand_ids=["offering", "strike"],
            player=_make_player(current_hp=10),
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id != "offering"

    def test_lethal_kills(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should play attack to kill enemy when it's lethal."""
        enemy = _make_enemy(hp=6)  # Strike does 6 damage
        battle = _make_battle(
            hand_ids=["strike", "defend"],
            enemies=[enemy],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "strike"

    def test_survive_blocks_lethal(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should block when incoming damage is lethal."""
        enemy = _make_enemy(hp=50)
        enemy.intent_damage = 20
        enemy.intent_hits = 1
        battle = _make_battle(
            hand_ids=["strike", "defend"],
            player=_make_player(current_hp=15),
            enemies=[enemy],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "defend"

    def test_plays_power(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should play power cards when not in lethal/survival situation."""
        enemy = _make_enemy(hp=100)
        enemy.intent_damage = 5
        enemy.intent_hits = 1
        battle = _make_battle(
            hand_ids=["inflame", "strike", "defend"],
            enemies=[enemy],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "inflame"

    def test_demon_form_before_inflame(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Demon Form has higher priority than Inflame."""
        enemy = _make_enemy(hp=100)
        enemy.intent_damage = 5
        enemy.intent_hits = 1
        battle = _make_battle(
            hand_ids=["inflame", "demon_form"],
            enemies=[enemy],
            energy=4,
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "demon_form"

    def test_vulnerable_application(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should apply vulnerable when target isn't vulnerable."""
        enemy = _make_enemy(hp=100)
        enemy.intent_damage = 5
        enemy.intent_hits = 1
        battle = _make_battle(
            hand_ids=["bash", "strike"],
            enemies=[enemy],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "bash"

    def test_skip_vulnerable_if_already_applied(
        self, agent: HeuristicAgent, registry: ContentRegistry,
    ):
        """Should not prioritize Bash when target already vulnerable."""
        enemy = _make_enemy(hp=100)
        enemy.intent_damage = 3
        enemy.intent_hits = 1
        apply_status(enemy, "vulnerable", 2)
        battle = _make_battle(
            hand_ids=["bash", "strike"],
            enemies=[enemy],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        # Should play best attack (bash is still strong, but strike might be picked
        # based on damage/energy ratio — either way, not via vuln priority)
        assert cd.type == CardType.ATTACK

    def test_nob_filter_skills(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should not play skills against Gremlin Nob when not lethal."""
        nob = _make_enemy(enemy_id="gremlin_nob", hp=100)
        nob.name = "Gremlin Nob"
        nob.intent_damage = 14
        nob.intent_hits = 1
        battle = _make_battle(
            hand_ids=["defend", "strike", "shrug_it_off"],
            enemies=[nob],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.type == CardType.ATTACK

    def test_nob_allows_skills_when_lethal(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should allow skills against Nob when incoming is lethal."""
        nob = _make_enemy(enemy_id="gremlin_nob", hp=100)
        nob.name = "Gremlin Nob"
        nob.intent_damage = 30
        nob.intent_hits = 1
        battle = _make_battle(
            hand_ids=["defend", "shrug_it_off"],
            player=_make_player(current_hp=20),
            enemies=[nob],
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        # Should play a block card to survive
        assert cd.type == CardType.SKILL

    def test_zero_cost_plays(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should play zero-cost cards when nothing higher priority."""
        enemy = _make_enemy(hp=100)
        enemy.intent_damage = 3
        enemy.intent_hits = 1
        apply_status(enemy, "vulnerable", 2)  # Skip vuln priority
        battle = _make_battle(
            hand_ids=["anger"],
            enemies=[enemy],
            energy=0,  # No energy for non-zero-cost cards
        )
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        assert cd.id == "anger"

    def test_ends_turn_when_no_good_plays(
        self, agent: HeuristicAgent, registry: ContentRegistry,
    ):
        """Should end turn when no playable cards."""
        result = agent.choose_card_to_play(
            _make_battle(), [],
        )
        assert result is None

    def test_body_slam_deferred(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Body Slam should be deferred (not played in best_attack phase)."""
        enemy = _make_enemy(hp=100)
        enemy.intent_damage = 3
        enemy.intent_hits = 1
        apply_status(enemy, "vulnerable", 2)
        # Give player some block so Body Slam would do damage
        battle = _make_battle(
            hand_ids=["body_slam", "defend"],
            enemies=[enemy],
        )
        battle.player.block = 20
        playable = _playable(registry, battle)
        result = agent.choose_card_to_play(battle, playable)
        assert result is not None
        _, cd, _ = result
        # Should play defend first (block card), then body slam would come later
        # (or block card, since body slam is deferred past attack phase)
        assert cd.id in ("defend", "body_slam")


# ======================================================================
# Card reward tests
# ======================================================================


class TestCardReward:
    def test_picks_highest_tier(self, agent: HeuristicAgent, registry: ContentRegistry):
        cards = [
            registry.get_card("strike"),
            registry.get_card("offering"),
            registry.get_card("anger"),
        ]
        deck = ["strike"] * 5 + ["defend"] * 4 + ["bash"]
        result = agent.choose_card_reward(cards, deck)
        assert result is not None
        assert result.id == "offering"

    def test_penalizes_duplicates(self, agent: HeuristicAgent, registry: ContentRegistry):
        cards = [
            registry.get_card("pommel_strike"),
            registry.get_card("anger"),
        ]
        # Already have 2 pommel_strikes — -20 penalty (77 -> 57 < anger 65)
        deck = ["pommel_strike", "pommel_strike"] + ["strike"] * 5 + ["defend"] * 4
        result = agent.choose_card_reward(cards, deck)
        assert result is not None
        assert result.id == "anger"

    def test_skips_when_bad_options_large_deck(
        self, agent: HeuristicAgent, registry: ContentRegistry,
    ):
        cards = [
            registry.get_card("strike"),
            registry.get_card("defend"),
        ]
        # Large deck (26 cards) with bad options
        deck = ["strike"] * 16 + ["defend"] * 10
        result = agent.choose_card_reward(cards, deck)
        # Strike score 10, defend 8, both penalized by (26-20)*2=12 → negative
        assert result is None

    def test_empty_reward(self, agent: HeuristicAgent):
        assert agent.choose_card_reward([], ["strike"]) is None


# ======================================================================
# Rest site tests
# ======================================================================


class TestRestAction:
    def test_rest_when_low_hp(self, agent: HeuristicAgent):
        player = _make_player(current_hp=40)  # 50% HP
        deck = [CardInstance(card_id="bash")]
        assert agent.choose_rest_action(player, deck) == "rest"

    def test_smith_when_healthy_and_upgrade_target(self, agent: HeuristicAgent):
        player = _make_player(current_hp=72)  # 90% HP, > 75% threshold
        deck = [CardInstance(card_id="bash")]  # High upgrade priority
        assert agent.choose_rest_action(player, deck) == "smith"

    def test_rest_when_healthy_no_upgrade(self, agent: HeuristicAgent):
        player = _make_player(current_hp=72)  # 90% HP
        deck = [CardInstance(card_id="strike")]  # Low upgrade priority
        assert agent.choose_rest_action(player, deck) == "rest"


# ======================================================================
# Upgrade tests
# ======================================================================


class TestUpgradePriority:
    def test_bash_highest_priority(self, agent: HeuristicAgent):
        cards = [
            CardInstance(card_id="bash"),
            CardInstance(card_id="strike"),
            CardInstance(card_id="defend"),
        ]
        result = agent.choose_card_to_upgrade(cards)
        assert result is not None
        assert result.card_id == "bash"

    def test_empty(self, agent: HeuristicAgent):
        assert agent.choose_card_to_upgrade([]) is None


# ======================================================================
# Potion tests
# ======================================================================


class TestPotionUsage:
    def test_block_potion_on_lethal(self, agent: HeuristicAgent, registry: ContentRegistry):
        enemy = _make_enemy(hp=50)
        enemy.intent_damage = 20
        enemy.intent_hits = 1
        battle = _make_battle(
            player=_make_player(current_hp=15),
            enemies=[enemy],
        )
        block_potion = registry.get_potion("block_potion")
        available = [(0, block_potion)]
        result = agent.choose_potion_to_use(battle, available)
        assert result is not None
        slot, pdef, _ = result
        assert pdef.id == "block_potion"

    def test_saves_potions_normally(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Potions saved when full HP, non-hard fight, single enemy."""
        enemy = _make_enemy(hp=50)
        enemy.intent_damage = 5
        enemy.intent_hits = 1
        battle = _make_battle(enemies=[enemy])
        strength_potion = registry.get_potion("strength_potion")
        available = [(0, strength_potion)]
        result = agent.choose_potion_to_use(battle, available)
        assert result is None

    def test_fire_potion_secure_kill(self, agent: HeuristicAgent, registry: ContentRegistry):
        enemy = _make_enemy(hp=15)
        enemy.intent_damage = 10
        enemy.intent_hits = 1
        battle = _make_battle(enemies=[enemy])
        fire_potion = registry.get_potion("fire_potion")
        available = [(0, fire_potion)]
        result = agent.choose_potion_to_use(battle, available)
        assert result is not None
        _, pdef, target = result
        assert pdef.id == "fire_potion"
        assert target == 0

    def test_multi_enemy_offense(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should use offensive potions turn 1 in multi-enemy fights."""
        e1 = _make_enemy(hp=50)
        e1.intent_damage = 10
        e1.intent_hits = 1
        e2 = _make_enemy(enemy_id="cultist", hp=50)
        e2.name = "Cultist"
        e2.intent_damage = 6
        e2.intent_hits = 1
        battle = _make_battle(enemies=[e1, e2])
        battle.turn = 1
        strength_potion = registry.get_potion("strength_potion")
        available = [(0, strength_potion)]
        result = agent.choose_potion_to_use(battle, available)
        assert result is not None
        _, pdef, _ = result
        assert pdef.id == "strength_potion"

    def test_proactive_defense(self, agent: HeuristicAgent, registry: ContentRegistry):
        """Should use defensive potions when HP < 50% and taking damage."""
        enemy = _make_enemy(hp=50)
        enemy.intent_damage = 10
        enemy.intent_hits = 1
        battle = _make_battle(
            player=_make_player(current_hp=35),  # 43.75% HP
            enemies=[enemy],
        )
        block_potion = registry.get_potion("block_potion")
        available = [(0, block_potion)]
        result = agent.choose_potion_to_use(battle, available)
        assert result is not None
        _, pdef, _ = result
        assert pdef.id == "block_potion"


# ======================================================================
# Integration tests
# ======================================================================


class TestIntegration:
    def test_full_combat_completes(self, registry: ContentRegistry):
        """HeuristicAgent can complete a full combat."""
        agent = HeuristicAgent(registry=registry)
        rng = GameRNG(42)
        combat_rng = rng.fork("combat")

        player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
        deck = [CardInstance(card_id=cid) for cid in registry.get_starter_deck("ironclad")]

        edata = registry.get_enemy_data("jaw_worm")
        hp = combat_rng.random_int(edata["hp_min"], edata["hp_max"])
        enemy = Enemy(
            name=edata["name"], enemy_id="jaw_worm", max_hp=hp, current_hp=hp,
        )

        battle = BattleState(
            player=player,
            enemies=[enemy],
            card_piles=CardPiles(draw=deck),
            rng=combat_rng,
        )

        interpreter = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interpreter, agent)
        telemetry = sim.run_combat(battle)

        assert telemetry.result in ("win", "loss")
        assert telemetry.turns > 0
        assert battle.is_over

    def test_deterministic_results(self, registry: ContentRegistry):
        """Same seed produces same result."""
        results = []
        for _ in range(2):
            agent = HeuristicAgent(registry=registry)
            rng = GameRNG(123)
            combat_rng = rng.fork("combat")

            player = Player(name="Ironclad", max_hp=80, current_hp=80, max_energy=3)
            deck = [CardInstance(card_id=cid) for cid in registry.get_starter_deck("ironclad")]

            edata = registry.get_enemy_data("jaw_worm")
            hp = combat_rng.random_int(edata["hp_min"], edata["hp_max"])
            enemy = Enemy(
                name=edata["name"], enemy_id="jaw_worm", max_hp=hp, current_hp=hp,
            )

            battle = BattleState(
                player=player,
                enemies=[enemy],
                card_piles=CardPiles(draw=deck),
                rng=combat_rng,
            )

            interpreter = ActionInterpreter(card_registry=registry.cards)
            sim = CombatSimulator(registry, interpreter, agent)
            telemetry = sim.run_combat(battle)
            results.append((telemetry.result, telemetry.turns, telemetry.player_hp_end))

        assert results[0] == results[1]

    def test_batch_runner_integration(self, registry: ContentRegistry):
        """BatchRunner correctly constructs HeuristicAgent with registry."""
        runner = BatchRunner(registry, agent_class=HeuristicAgent)
        results = runner.run_batch(
            n_runs=3,
            encounter_config={"enemy_ids": ["jaw_worm"]},
            base_seed=42,
        )
        assert len(results) == 3
        for r in results:
            assert r.final_result in ("win", "loss")

    def test_batch_runner_random_still_works(self, registry: ContentRegistry):
        """BatchRunner still works with RandomAgent (backward compat)."""
        runner = BatchRunner(registry, agent_class=RandomAgent)
        results = runner.run_batch(
            n_runs=2,
            encounter_config={"enemy_ids": ["jaw_worm"]},
            base_seed=42,
        )
        assert len(results) == 2

    def test_full_act_run(self, registry: ContentRegistry):
        """HeuristicAgent can complete a full Act 1 run."""
        runner = BatchRunner(registry, agent_class=HeuristicAgent)
        results = runner.run_full_act_batch(n_runs=1, base_seed=42)
        assert len(results) == 1
        assert results[0].floors_reached > 0
