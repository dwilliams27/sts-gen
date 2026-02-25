"""Run manager -- drives a full Act 1 run through 16 floors.

Manages persistent state (HP, gold, deck, relics, potions) between combat
encounters, handles card/gold/relic/potion rewards, rest sites, treasure
rooms, and loosely-emulated events and shops.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from sts_gen.ir.cards import CardRarity
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles, GameState
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.dungeon.map_gen import MapGenerator, MapNode
from sts_gen.sim.dungeon.rewards import (
    generate_card_reward,
    generate_gold_reward,
    generate_relic_reward,
    maybe_drop_potion,
)
from sts_gen.sim.interpreter import ActionInterpreter
from sts_gen.sim.runner import CombatSimulator
from sts_gen.sim.telemetry import RunTelemetry

if TYPE_CHECKING:
    from sts_gen.sim.content.registry import ContentRegistry
    from sts_gen.sim.play_agents.base import PlayAgent

logger = logging.getLogger(__name__)


class RunManager:
    """Drives a full Act 1 run.

    Parameters
    ----------
    registry:
        The content registry with all game data loaded.
    agent:
        The play agent making decisions.
    rng:
        Master RNG for the run. Forked for sub-systems.
    """

    def __init__(
        self,
        registry: ContentRegistry,
        agent: PlayAgent,
        rng: GameRNG,
    ) -> None:
        self.registry = registry
        self.agent = agent
        self.rng = rng

    def run_act_1(self) -> RunTelemetry:
        """Run a full Act 1 (16 floors) and return telemetry."""
        # Fork RNGs for sub-systems
        map_rng = self.rng.fork("map")
        combat_rng = self.rng.fork("combat")
        reward_rng = self.rng.fork("rewards")
        event_rng = self.rng.fork("events")

        # Init game state: Ironclad starter
        game_state = self._init_game_state()

        # Generate map
        map_gen = MapGenerator()
        nodes = map_gen.generate_act_1(map_rng)

        # Telemetry
        telemetry = RunTelemetry(seed=self.rng.seed)

        # Process each floor
        for node in nodes:
            game_state.floor = node.floor
            telemetry.hp_at_each_floor.append(game_state.player.current_hp)

            if node.node_type == "monster":
                won = self._handle_combat(
                    game_state, combat_rng, reward_rng, telemetry, pool="normal",
                )
                if not won:
                    telemetry.floors_reached = node.floor
                    telemetry.final_result = "loss"
                    break

            elif node.node_type == "elite":
                won = self._handle_combat(
                    game_state, combat_rng, reward_rng, telemetry, pool="elite",
                )
                if not won:
                    telemetry.floors_reached = node.floor
                    telemetry.final_result = "loss"
                    break
                # Elite relic reward
                relic_id = generate_relic_reward(
                    self.registry, reward_rng, game_state.relics,
                )
                if relic_id is not None:
                    game_state.relics.append(relic_id)
                    telemetry.relics_collected.append(relic_id)

            elif node.node_type == "boss":
                won = self._handle_combat(
                    game_state, combat_rng, reward_rng, telemetry, pool="boss",
                )
                telemetry.floors_reached = node.floor
                telemetry.final_result = "win" if won else "loss"
                break

            elif node.node_type == "rest":
                self._handle_rest(game_state, telemetry)
                telemetry.rest_sites_visited += 1

            elif node.node_type == "treasure":
                self._handle_treasure(game_state, reward_rng, telemetry)

            elif node.node_type == "event":
                self._handle_event(game_state, event_rng, telemetry)

            elif node.node_type == "shop":
                self._handle_shop(game_state, reward_rng, telemetry)

            # Check for death from events/shops
            if game_state.player.is_dead:
                telemetry.floors_reached = node.floor
                telemetry.final_result = "loss"
                break

            telemetry.floors_reached = node.floor
        else:
            # Completed all floors without break (shouldn't happen — boss always breaks)
            telemetry.final_result = "loss"

        telemetry.cards_in_deck = [ci.card_id for ci in game_state.deck]
        return telemetry

    # ------------------------------------------------------------------
    # Game state initialization
    # ------------------------------------------------------------------

    def _init_game_state(self) -> GameState:
        """Create the starting game state for an Ironclad Act 1 run."""
        player = Player(
            name="Ironclad", max_hp=80, current_hp=80, max_energy=3, gold=99,
        )
        deck_ids = self.registry.get_starter_deck("ironclad")
        deck = [CardInstance(card_id=cid) for cid in deck_ids]

        return GameState(
            player=player,
            deck=deck,
            relics=["burning_blood"],
            potions=[None, None, None],
            rng=self.rng,
        )

    # ------------------------------------------------------------------
    # Combat handling
    # ------------------------------------------------------------------

    def _handle_combat(
        self,
        game_state: GameState,
        combat_rng: GameRNG,
        reward_rng: GameRNG,
        telemetry: RunTelemetry,
        pool: str,
    ) -> bool:
        """Run a combat encounter. Returns True if player won."""
        # Pick encounter
        encounter = self._pick_encounter(combat_rng, pool)
        if encounter is None:
            return True  # No encounter data, skip

        # Build enemies
        enemies = self._build_enemies(encounter, combat_rng)

        # Build battle state from persistent game state
        deck_copy = [
            CardInstance(card_id=ci.card_id, upgraded=ci.upgraded)
            for ci in game_state.deck
        ]
        battle = BattleState(
            player=Player(
                name=game_state.player.name,
                max_hp=game_state.player.max_hp,
                current_hp=game_state.player.current_hp,
                max_energy=game_state.player.max_energy,
                gold=game_state.player.gold,
            ),
            enemies=enemies,
            card_piles=CardPiles(draw=deck_copy),
            rng=combat_rng,
            relics=list(game_state.relics),
            potions=list(game_state.potions),
        )

        # Run combat
        interpreter = ActionInterpreter(card_registry=self.registry.cards)
        simulator = CombatSimulator(self.registry, interpreter, self.agent)
        battle_telemetry = simulator.run_combat(battle)
        telemetry.battles.append(battle_telemetry)

        # Update persistent state from combat result
        game_state.player.current_hp = max(0, battle.player.current_hp)
        game_state.player.gold = battle.player.gold
        game_state.potions = list(battle.potions)

        if battle_telemetry.result == "win":
            # Card reward
            reward_cards = generate_card_reward(
                self.registry, reward_rng, pool=pool,
            )
            chosen = self.agent.choose_card_reward(
                reward_cards,
                [ci.card_id for ci in game_state.deck],
            )
            if chosen is not None:
                game_state.deck.append(CardInstance(card_id=chosen.id))
                telemetry.cards_added.append(chosen.id)

            # Gold reward
            gold = generate_gold_reward(reward_rng, pool=pool)
            game_state.player.gold += gold
            telemetry.gold_earned += gold

            # Maybe drop potion
            potion_id = maybe_drop_potion(
                self.registry, reward_rng, game_state.potions,
            )
            if potion_id is not None:
                # Add to first empty slot
                for i, slot in enumerate(game_state.potions):
                    if slot is None:
                        game_state.potions[i] = potion_id
                        break

            return True
        else:
            return False

    def _pick_encounter(
        self, rng: GameRNG, pool: str,
    ) -> dict[str, Any] | None:
        """Pick a random encounter from the appropriate pool."""
        if pool == "normal":
            # Mix easy and normal pools for variety
            easy = self.registry.get_encounter_pool("act_1", "easy")
            normal = self.registry.get_encounter_pool("act_1", "normal")
            all_encounters = easy + normal
        elif pool == "elite":
            all_encounters = self.registry.get_encounter_pool("act_1", "elite")
        elif pool == "boss":
            all_encounters = self.registry.get_encounter_pool("act_1", "boss")
        else:
            all_encounters = self.registry.get_encounter_pool("act_1", "easy")

        if not all_encounters:
            return None
        return rng.random_choice(all_encounters)

    def _build_enemies(
        self, encounter: dict[str, Any], rng: GameRNG,
    ) -> list[Enemy]:
        """Build enemy instances from an encounter definition."""
        enemies: list[Enemy] = []
        for eid in encounter.get("enemies", []):
            edata = self.registry.get_enemy_data(eid)
            if edata is not None:
                hp_min = edata.get("hp_min", 50)
                hp_max = edata.get("hp_max", hp_min)
                hp = rng.random_int(hp_min, hp_max)
                enemies.append(Enemy(
                    name=edata.get("name", eid),
                    enemy_id=eid,
                    max_hp=hp,
                    current_hp=hp,
                ))
        return enemies

    # ------------------------------------------------------------------
    # Non-combat floor handlers
    # ------------------------------------------------------------------

    def _handle_rest(
        self, game_state: GameState, telemetry: RunTelemetry,
    ) -> None:
        """Handle rest site: heal 30% or upgrade a card."""
        action = self.agent.choose_rest_action(
            game_state.player, game_state.deck,
        )

        if action == "smith":
            upgradable = [
                ci for ci in game_state.deck
                if not ci.upgraded and self._card_can_upgrade(ci.card_id)
            ]
            if upgradable:
                chosen = self.agent.choose_card_to_upgrade(upgradable)
                if chosen is not None:
                    chosen.upgraded = True
                    return
            # Fall through to rest if nothing to upgrade
            action = "rest"

        # Rest: heal 30% of max HP (rounded down)
        heal_amount = game_state.player.max_hp * 30 // 100
        game_state.player.heal(heal_amount)

    def _card_can_upgrade(self, card_id: str) -> bool:
        """Check if a card has an upgrade definition."""
        card_def = self.registry.get_card(card_id)
        return card_def is not None and card_def.upgrade is not None

    def _handle_treasure(
        self,
        game_state: GameState,
        rng: GameRNG,
        telemetry: RunTelemetry,
    ) -> None:
        """Handle treasure room: always give an Uncommon relic."""
        from sts_gen.ir.relics import RelicTier

        owned_set = set(game_state.relics)
        candidates = [
            r for r in self.registry.relics.values()
            if r.tier == RelicTier.UNCOMMON and r.id not in owned_set
        ]
        if candidates:
            relic = rng.random_choice(candidates)
            game_state.relics.append(relic.id)
            telemetry.relics_collected.append(relic.id)

    def _handle_event(
        self,
        game_state: GameState,
        rng: GameRNG,
        telemetry: RunTelemetry,
    ) -> None:
        """Loosely emulated event: random outcome.

        50% small heal (5-10 HP), 25% gain random card,
        15% lose HP (3-7), 10% gain gold (20-50).
        """
        roll = rng.random_float() * 100

        if roll < 50:
            # Small heal
            heal = rng.random_int(5, 10)
            game_state.player.heal(heal)
        elif roll < 75:
            # Gain random card
            reward = generate_card_reward(self.registry, rng, pool="normal")
            if reward:
                chosen = self.agent.choose_card_reward(
                    reward,
                    [ci.card_id for ci in game_state.deck],
                )
                if chosen is not None:
                    game_state.deck.append(CardInstance(card_id=chosen.id))
                    telemetry.cards_added.append(chosen.id)
        elif roll < 90:
            # Lose HP
            hp_loss = rng.random_int(3, 7)
            game_state.player.current_hp = max(
                0, game_state.player.current_hp - hp_loss,
            )
        else:
            # Gain gold
            gold = rng.random_int(20, 50)
            game_state.player.gold += gold
            telemetry.gold_earned += gold

    def _handle_shop(
        self,
        game_state: GameState,
        rng: GameRNG,
        telemetry: RunTelemetry,
    ) -> None:
        """Loosely emulated shop: maybe buy a random uncommon card.

        If gold > 75: 50% chance buy random uncommon card (deduct 75 gold).
        """
        if game_state.player.gold > 75 and rng.random_float() < 0.5:
            candidates = self.registry.get_reward_pool(
                rarity=CardRarity.UNCOMMON,
            )
            if candidates:
                card = rng.random_choice(candidates)
                game_state.deck.append(CardInstance(card_id=card.id))
                game_state.player.gold -= 75
                telemetry.cards_added.append(card.id)
                telemetry.gold_earned -= 75  # Net gold change
