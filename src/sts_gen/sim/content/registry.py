"""Content registry -- loads and serves card definitions, enemy definitions,
and custom content for the STS combat simulator.

Vanilla content is loaded from JSON files in ``data/vanilla/``.
Custom content is loaded from :class:`ContentSet` IR objects produced
by the generation agents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sts_gen.ir.actions import ActionNode
from sts_gen.ir.cards import (
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    UpgradeDefinition,
)
from sts_gen.ir.content_set import ContentSet
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)

# Default paths relative to the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # src/sts_gen/sim/content -> root
_DEFAULT_CARDS_PATH = _PROJECT_ROOT / "data" / "vanilla" / "ironclad_cards.json"
_DEFAULT_ENEMIES_PATH = _PROJECT_ROOT / "data" / "vanilla" / "enemies.json"
_DEFAULT_ENCOUNTERS_PATH = _PROJECT_ROOT / "data" / "vanilla" / "encounters.json"
_DEFAULT_STATUS_EFFECTS_PATH = _PROJECT_ROOT / "data" / "vanilla" / "status_effects.json"


def _parse_action_node(raw: dict[str, Any]) -> ActionNode:
    """Parse a raw JSON dict into an ActionNode, recursively handling children."""
    children = raw.get("children")
    if children is not None:
        raw = dict(raw)
        raw["children"] = [_parse_action_node(c) for c in children]
    return ActionNode(**raw)


def _parse_status_effect_definition(raw: dict[str, Any]) -> StatusEffectDefinition:
    """Parse a raw JSON dict into a StatusEffectDefinition."""
    triggers: dict[StatusTrigger, list[ActionNode]] = {}
    for trigger_key, actions_raw in raw.get("triggers", {}).items():
        trigger = StatusTrigger(trigger_key)
        actions = [_parse_action_node(a) for a in actions_raw]
        triggers[trigger] = actions

    return StatusEffectDefinition(
        id=raw["id"],
        name=raw["name"],
        description=raw["description"],
        is_debuff=raw["is_debuff"],
        stack_behavior=StackBehavior(raw["stack_behavior"]),
        triggers=triggers,
        decay_per_turn=raw.get("decay_per_turn", 0),
        min_stacks=raw.get("min_stacks", 0),
    )


def _parse_card_definition(raw: dict[str, Any]) -> CardDefinition:
    """Parse a raw JSON dict into a CardDefinition with nested Pydantic models."""
    # Parse actions
    actions = [_parse_action_node(a) for a in raw.get("actions", [])]

    # Parse on_exhaust actions if present
    on_exhaust = [_parse_action_node(a) for a in raw.get("on_exhaust", [])]

    # Parse upgrade if present
    upgrade = None
    raw_upgrade = raw.get("upgrade")
    if raw_upgrade is not None:
        upgrade_actions = None
        if raw_upgrade.get("actions") is not None:
            upgrade_actions = [_parse_action_node(a) for a in raw_upgrade["actions"]]
        upgrade_on_exhaust = None
        if raw_upgrade.get("on_exhaust") is not None:
            upgrade_on_exhaust = [_parse_action_node(a) for a in raw_upgrade["on_exhaust"]]
        upgrade = UpgradeDefinition(
            cost=raw_upgrade.get("cost"),
            actions=upgrade_actions,
            description=raw_upgrade.get("description"),
            exhaust=raw_upgrade.get("exhaust"),
            innate=raw_upgrade.get("innate"),
            on_exhaust=upgrade_on_exhaust,
        )

    return CardDefinition(
        id=raw["id"],
        name=raw["name"],
        type=CardType(raw["type"]),
        rarity=CardRarity(raw["rarity"]),
        cost=raw["cost"],
        target=CardTarget(raw["target"]),
        description=raw["description"],
        actions=actions,
        upgrade=upgrade,
        keywords=raw.get("keywords", []),
        exhaust=raw.get("exhaust", False),
        ethereal=raw.get("ethereal", False),
        innate=raw.get("innate", False),
        retain=raw.get("retain", False),
        on_exhaust=on_exhaust,
        play_restriction=raw.get("play_restriction"),
    )


class ContentRegistry:
    """Loads and serves card definitions, enemy definitions, and custom content.

    The registry is the single source of truth for all game content during
    simulation.  It merges vanilla content with any custom content loaded
    from a :class:`ContentSet`.

    Usage::

        registry = ContentRegistry()
        registry.load_vanilla_cards()
        registry.load_vanilla_enemies()

        card = registry.get_card("strike")
        enemy = registry.get_enemy_data("jaw_worm")
        deck = registry.get_starter_deck("ironclad")
    """

    def __init__(self) -> None:
        self.cards: dict[str, CardDefinition] = {}
        self.enemies: dict[str, dict[str, Any]] = {}
        self.encounters: dict[str, dict[str, Any]] = {}
        self.status_defs: dict[str, StatusEffectDefinition] = {}

    # ------------------------------------------------------------------
    # Vanilla content loading
    # ------------------------------------------------------------------

    def load_vanilla_cards(self, path: str | Path | None = None) -> None:
        """Load vanilla cards from a JSON file.

        Parameters
        ----------
        path:
            Path to the JSON file.  Defaults to
            ``data/vanilla/ironclad_cards.json`` relative to the project root.
        """
        if path is None:
            path = _DEFAULT_CARDS_PATH
        path = Path(path)

        with open(path) as f:
            raw_cards: list[dict[str, Any]] = json.load(f)

        for raw in raw_cards:
            if "_section" in raw:
                continue  # Skip organizational section markers
            card = _parse_card_definition(raw)
            self.cards[card.id] = card

    def load_vanilla_enemies(self, path: str | Path | None = None) -> None:
        """Load vanilla enemy definitions from a JSON file.

        Parameters
        ----------
        path:
            Path to the JSON file.  Defaults to
            ``data/vanilla/enemies.json`` relative to the project root.
        """
        if path is None:
            path = _DEFAULT_ENEMIES_PATH
        path = Path(path)

        with open(path) as f:
            raw_enemies: list[dict[str, Any]] = json.load(f)

        for raw in raw_enemies:
            if "_section" in raw:
                continue  # Skip organizational section markers
            self.enemies[raw["id"]] = raw

    def load_vanilla_encounters(self, path: str | Path | None = None) -> None:
        """Load vanilla encounter definitions from a JSON file.

        Parameters
        ----------
        path:
            Path to the JSON file.  Defaults to
            ``data/vanilla/encounters.json`` relative to the project root.
        """
        if path is None:
            path = _DEFAULT_ENCOUNTERS_PATH
        path = Path(path)

        with open(path) as f:
            self.encounters = json.load(f)

    def load_vanilla_status_effects(self, path: str | Path | None = None) -> None:
        """Load vanilla status effect definitions from a JSON file.

        Parameters
        ----------
        path:
            Path to the JSON file.  Defaults to
            ``data/vanilla/status_effects.json`` relative to the project root.
        """
        if path is None:
            path = _DEFAULT_STATUS_EFFECTS_PATH
        path = Path(path)

        with open(path) as f:
            raw_defs: list[dict[str, Any]] = json.load(f)

        for raw in raw_defs:
            if "_section" in raw:
                continue  # Skip organizational section markers
            defn = _parse_status_effect_definition(raw)
            self.status_defs[defn.id] = defn

    def get_status_def(self, status_id: str) -> StatusEffectDefinition | None:
        """Return the :class:`StatusEffectDefinition` for *status_id*, or ``None``."""
        return self.status_defs.get(status_id)

    # ------------------------------------------------------------------
    # Custom content loading
    # ------------------------------------------------------------------

    def load_content_set(self, content_set: ContentSet) -> None:
        """Load custom content from a :class:`ContentSet` IR.

        Cards from the content set are added to the registry alongside
        vanilla cards.  If a custom card has the same ``id`` as a vanilla
        card, the custom version takes precedence.

        Parameters
        ----------
        content_set:
            A validated ContentSet IR object.
        """
        for card in content_set.cards:
            self.cards[card.id] = card

    # ------------------------------------------------------------------
    # Card queries
    # ------------------------------------------------------------------

    def get_card(self, card_id: str) -> CardDefinition | None:
        """Return the :class:`CardDefinition` for *card_id*, or ``None``."""
        return self.cards.get(card_id)

    def get_card_actions(
        self, card_id: str, upgraded: bool = False
    ) -> list[ActionNode]:
        """Return the action list for a card, respecting upgrade state.

        If the card is upgraded and has upgrade actions defined, those
        are returned.  Otherwise the base actions are returned.

        Parameters
        ----------
        card_id:
            The card identifier.
        upgraded:
            Whether to return the upgraded action list.

        Returns
        -------
        list[ActionNode]
            The action tree for the card, or an empty list if the card
            is not found.
        """
        card = self.get_card(card_id)
        if card is None:
            return []

        if upgraded and card.upgrade and card.upgrade.actions is not None:
            return card.upgrade.actions
        return card.actions

    def get_card_cost(self, card_id: str, upgraded: bool = False) -> int:
        """Return the energy cost of a card, respecting upgrade state.

        Parameters
        ----------
        card_id:
            The card identifier.
        upgraded:
            Whether to return the upgraded cost.

        Returns
        -------
        int
            The energy cost, or -2 (unplayable) if the card is not found.
        """
        card = self.get_card(card_id)
        if card is None:
            return -2

        if upgraded and card.upgrade and card.upgrade.cost is not None:
            return card.upgrade.cost
        return card.cost

    # ------------------------------------------------------------------
    # Enemy queries
    # ------------------------------------------------------------------

    def get_enemy_data(self, enemy_id: str) -> dict[str, Any] | None:
        """Return the raw enemy definition dict for *enemy_id*, or ``None``."""
        return self.enemies.get(enemy_id)

    def get_enemy_move(
        self, enemy_id: str, move_id: str
    ) -> dict[str, Any] | None:
        """Return a specific move definition for an enemy.

        Parameters
        ----------
        enemy_id:
            The enemy identifier.
        move_id:
            The move identifier within that enemy's move list.

        Returns
        -------
        dict | None
            The move definition dict, or ``None`` if not found.
        """
        enemy = self.get_enemy_data(enemy_id)
        if enemy is None:
            return None
        for move in enemy.get("moves", []):
            if move["id"] == move_id:
                return move
        return None

    def list_enemy_ids(self) -> list[str]:
        """Return a list of all registered enemy identifiers."""
        return list(self.enemies.keys())

    # ------------------------------------------------------------------
    # Encounter queries
    # ------------------------------------------------------------------

    def get_encounter(
        self, act: str = "act_1", pool: str = "easy", encounter_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return an encounter definition.

        Parameters
        ----------
        act:
            The act key (e.g. ``"act_1"``).
        pool:
            The encounter pool (``"easy"``, ``"normal"``, ``"elite"``, ``"boss"``).
        encounter_id:
            Specific encounter id.  If ``None``, returns the first encounter.

        Returns
        -------
        dict | None
            The encounter definition, or ``None`` if not found.
        """
        act_data = self.encounters.get(act, {})
        pool_data = act_data.get(pool, [])
        if encounter_id:
            for enc in pool_data:
                if enc.get("id") == encounter_id:
                    return enc
            return None
        return pool_data[0] if pool_data else None

    def get_encounter_pool(
        self, act: str = "act_1", pool: str = "easy",
    ) -> list[dict[str, Any]]:
        """Return all encounters in a pool."""
        return self.encounters.get(act, {}).get(pool, [])

    # ------------------------------------------------------------------
    # Starter deck
    # ------------------------------------------------------------------

    def get_starter_deck(self, character: str = "ironclad") -> list[str]:
        """Return the list of card_ids for a character's starting deck.

        Parameters
        ----------
        character:
            Character name (case-insensitive).  Currently only ``"ironclad"``
            is supported.

        Returns
        -------
        list[str]
            Card identifiers for the starting deck.  Includes duplicates
            (e.g. 5 copies of ``"strike"``).

        Raises
        ------
        ValueError
            If the character is not recognised.
        """
        character = character.lower().strip()

        if character == "ironclad":
            return (
                ["strike"] * 5
                + ["defend"] * 4
                + ["bash"]
            )

        raise ValueError(
            f"Unknown character: {character!r}. "
            f"Supported characters: ironclad"
        )

    # ------------------------------------------------------------------
    # Bulk queries
    # ------------------------------------------------------------------

    def list_card_ids(self) -> list[str]:
        """Return a sorted list of all registered card identifiers."""
        return sorted(self.cards.keys())

    def get_cards_by_type(self, card_type: CardType) -> list[CardDefinition]:
        """Return all cards of a given type (ATTACK, SKILL, POWER, etc.)."""
        return [c for c in self.cards.values() if c.type == card_type]

    def get_cards_by_rarity(
        self, rarity: CardRarity
    ) -> list[CardDefinition]:
        """Return all cards of a given rarity."""
        return [c for c in self.cards.values() if c.rarity == rarity]

    def get_reward_pool(
        self,
        card_type: CardType | None = None,
        rarity: CardRarity | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[CardDefinition]:
        """Return cards eligible for card rewards.

        Filters out BASIC and SPECIAL rarity cards, STATUS and CURSE types,
        and any card ids in *exclude_ids*.

        Parameters
        ----------
        card_type:
            If provided, only return cards of this type.
        rarity:
            If provided, only return cards of this rarity.
        exclude_ids:
            Card ids to exclude from the pool.
        """
        exclude = exclude_ids or set()
        pool: list[CardDefinition] = []

        for card in self.cards.values():
            if card.id in exclude:
                continue
            if card.rarity in (CardRarity.BASIC, CardRarity.SPECIAL):
                continue
            if card.type in (CardType.STATUS, CardType.CURSE):
                continue
            if card_type is not None and card.type != card_type:
                continue
            if rarity is not None and card.rarity != rarity:
                continue
            pool.append(card)

        return pool

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        n_encounters = sum(
            len(pool)
            for act in self.encounters.values()
            for pool in act.values()
        ) if self.encounters else 0
        return (
            f"ContentRegistry(cards={len(self.cards)}, "
            f"enemies={len(self.enemies)}, "
            f"encounters={n_encounters})"
        )
