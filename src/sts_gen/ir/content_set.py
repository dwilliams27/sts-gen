"""Top-level container that bundles all mod content into a single IR document."""

from __future__ import annotations

import re

from pydantic import BaseModel, model_validator

from .actions import ActionNode, ActionType
from .cards import CardDefinition
from .keywords import KeywordDefinition
from .potions import PotionDefinition
from .relics import RelicDefinition
from .status_effects import StatusEffectDefinition

# Status effects that ship with the base game and can be referenced without
# being explicitly defined in a mod's IR.
VANILLA_STATUSES: frozenset[str] = frozenset(
    {
        # Debuffs
        "Vulnerable",
        "Weak",
        "Frail",
        "Poison",
        "Constricted",
        "Entangled",
        "No Draw",
        "Choked",
        "Bias",
        "Hex",
        "Lock-On",
        "Mark",
        "Draw Reduction",
        # Buffs
        "Strength",
        "Dexterity",
        "Artifact",
        "Thorns",
        "Plated Armor",
        "Metallicize",
        "Ritual",
        "Rage",
        "Barricade",
        "Blur",
        "Buffer",
        "Burst",
        "Creative AI",
        "Dark Embrace",
        "Demon Form",
        "Double Tap",
        "Equilibrium",
        "Evolve",
        "Feel No Pain",
        "Fire Breathing",
        "Flame Barrier",
        "Flying",
        "Intangible",
        "Juggernaut",
        "Loop",
        "Magnetism",
        "Mayhem",
        "Nightmare",
        "Noxious Fumes",
        "Panache",
        "Pen Nib",
        "Phantasmal",
        "Regeneration",
        "Retain",
        "Sadistic",
        "After Image",
        "Envenom",
        "Accuracy",
        "Amplify",
        "Battle Hymn",
        "Blasphemer",
        "Brutality",
        "Combust",
        "Corruption",
        "Devotion",
        "Duplication",
        "Echo Form",
        "Electro",
        "Establishment",
        "Fasting",
        "Hello World",
        "Infinite Blades",
        "Mantra",
        "Master Reality",
        "Mental Fortress",
        "Nirvana",
        "Omega",
        "Rushdown",
        "Study",
        "Vigor",
        "Wave of the Hand",
        "Wraith Form",
    }
)


def _collect_status_refs(actions: list[ActionNode]) -> set[str]:
    """Walk an action tree and collect every ``status_name`` reference."""
    refs: set[str] = set()
    for node in actions:
        if node.status_name is not None:
            refs.add(node.status_name)
        if node.children:
            refs.update(_collect_status_refs(node.children))
    return refs


# ---------------------------------------------------------------------------
# Transpilability: known-valid conditions per ActionType
# ---------------------------------------------------------------------------

# Literal conditions (exact match)
_VALID_CONDITIONS: dict[ActionType, set[str]] = {
    ActionType.DEAL_DAMAGE: {
        "no_strength",
        "use_block_as_damage",
        "times_from_x_cost",
        # Power trigger contexts:
        "per_stack",
        "per_stack_no_strength",
    },
    ActionType.GAIN_BLOCK: {
        "raw",
        "per_non_attack_in_hand",
        "per_stack",
        "per_stack_raw",
    },
    ActionType.HEAL: {"heal_from_last_damage", "raise_max_hp"},
    ActionType.EXHAUST_CARDS: {"non_attack", "random"},
    ActionType.FOR_EACH: {"enemy", "card_in_hand"},
    ActionType.REPEAT: {"times_from_x_cost"},
    ActionType.LOSE_HP: {"per_stack"},
    ActionType.GAIN_ENERGY: {"per_stack"},
    ActionType.GAIN_STRENGTH: {"per_stack"},
    ActionType.GAIN_DEXTERITY: {"per_stack"},
    ActionType.DRAW_CARDS: {"per_stack"},
}

# Regex patterns for parameterised conditions (e.g. ``has_status:Foo``)
_VALID_CONDITION_PATTERNS: dict[ActionType, list[re.Pattern[str]]] = {
    ActionType.DEAL_DAMAGE: [
        re.compile(r"^plus_per_exhaust:\d+$"),
        re.compile(r"^strength_multiplier_\d+$"),
        re.compile(r"^plus_per_strike_\d+$"),
        re.compile(r"^plus_rampage_scaling:\d+$"),
        re.compile(r"^searing_blow_scaling$"),
    ],
    ActionType.CONDITIONAL: [
        re.compile(r"^has_status:.+$"),
        re.compile(r"^target_has_status:.+$"),
        re.compile(r"^hp_below:\d+$"),
        re.compile(r"^hp_above:\d+$"),
        re.compile(r"^no_block$"),
        re.compile(r"^hand_empty$"),
        re.compile(r"^hand_size_gte:\d+$"),
        re.compile(r"^only_attacks_in_hand$"),
        re.compile(r"^enemy_intends_attack$"),
        re.compile(r"^target_is_dead$"),
        re.compile(r"^turn_eq:\d+$"),
    ],
}

# ActionTypes that accept conditions (via literals or patterns above).
_CONDITIONED_TYPES = set(_VALID_CONDITIONS.keys()) | set(
    _VALID_CONDITION_PATTERNS.keys()
)

# Ironclad-only trigger_custom patterns — matched with re.match for prefix:N forms
_IRONCLAD_TRIGGER_CUSTOM_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^exhume$"),
    re.compile(r"^armaments$"),
    re.compile(r"^armaments_all$"),
    re.compile(r"^dual_wield(:\d+)?$"),
    re.compile(r"^infernal_blade$"),
    re.compile(r"^increment_rampage(:\d+)?$"),
]

# Required fields per action type
_REQUIRED_FIELDS: dict[ActionType, list[str]] = {
    ActionType.APPLY_STATUS: ["status_name"],
    ActionType.REMOVE_STATUS: ["status_name"],
    ActionType.MULTIPLY_STATUS: ["status_name"],
}


def _is_valid_condition(action_type: ActionType, condition: str) -> bool:
    """Return True if *condition* is known-valid for *action_type*."""
    literals = _VALID_CONDITIONS.get(action_type, set())
    if condition in literals:
        return True
    patterns = _VALID_CONDITION_PATTERNS.get(action_type, [])
    return any(p.match(condition) for p in patterns)


def _walk_action_errors(
    actions: list[ActionNode],
    *,
    source_label: str,
    allow_trigger_custom: bool = False,
) -> list[str]:
    """Recursively validate an action tree for transpilability.

    Returns a list of human-readable error strings (empty = valid).
    """
    errors: list[str] = []
    for node in actions:
        # 1. Reject trigger_custom (unless whitelisted for Ironclad)
        if node.action_type == ActionType.TRIGGER_CUSTOM:
            cond = node.condition or ""
            is_ironclad = any(
                p.match(cond) for p in _IRONCLAD_TRIGGER_CUSTOM_PATTERNS
            )
            if allow_trigger_custom and is_ironclad:
                pass  # Ironclad-specific, allowed
            else:
                errors.append(
                    f"{source_label}: trigger_custom is not allowed "
                    f"(condition={cond!r}). Use existing IR primitives instead."
                )

        # 2. Unknown conditions
        if node.condition is not None and node.action_type != ActionType.TRIGGER_CUSTOM:
            if node.action_type not in _CONDITIONED_TYPES:
                errors.append(
                    f"{source_label}: {node.action_type.value} does not "
                    f"accept conditions (got {node.condition!r})."
                )
            elif not _is_valid_condition(node.action_type, node.condition):
                errors.append(
                    f"{source_label}: unknown condition {node.condition!r} "
                    f"for {node.action_type.value}."
                )

        # 3. Missing required fields
        for field in _REQUIRED_FIELDS.get(node.action_type, []):
            if getattr(node, field, None) is None:
                errors.append(
                    f"{source_label}: {node.action_type.value} requires "
                    f"'{field}' but it is missing."
                )

        # Recurse into children
        if node.children:
            errors.extend(
                _walk_action_errors(
                    node.children,
                    source_label=source_label,
                    allow_trigger_custom=allow_trigger_custom,
                )
            )
    return errors


class ContentSet(BaseModel):
    """Top-level IR document that describes an entire mod's content.

    Serialise to JSON for persistence / transport, deserialise to validate
    and then hand off to the transpiler or simulator.
    """

    mod_id: str
    """Java-style unique mod identifier (e.g. 'myUsername:CoolMod')."""

    mod_name: str
    """Human-readable mod name."""

    author: str = "sts-gen"
    """Author or generator tag."""

    version: str = "0.1.0"
    """Semantic version of the mod content."""

    cards: list[CardDefinition] = []
    relics: list[RelicDefinition] = []
    potions: list[PotionDefinition] = []
    keywords: list[KeywordDefinition] = []
    status_effects: list[StatusEffectDefinition] = []

    # -- convenience lookups ------------------------------------------------

    def get_card(self, card_id: str) -> CardDefinition | None:
        """Return the card with the given id, or ``None``."""
        for card in self.cards:
            if card.id == card_id:
                return card
        return None

    def get_status(self, status_id: str) -> StatusEffectDefinition | None:
        """Return the status effect with the given id, or ``None``."""
        for status in self.status_effects:
            if status.id == status_id:
                return status
        return None

    # -- pruning ------------------------------------------------------------

    def prune_unused_statuses(self) -> "ContentSet":
        """Return a copy with unreferenced status effects removed.

        Collects every ``status_name`` referenced from cards, relics, and
        potions, then transitively follows references inside status-effect
        triggers to find the full reachable set.  Any status whose id *and*
        name are both outside that set is dropped.
        """
        # 1. Direct refs from cards, relics, potions (the "roots").
        root_refs: set[str] = set()
        for card in self.cards:
            root_refs.update(_collect_status_refs(card.actions))
            if card.upgrade and card.upgrade.actions:
                root_refs.update(_collect_status_refs(card.upgrade.actions))
        for relic in self.relics:
            root_refs.update(_collect_status_refs(relic.actions))
        for potion in self.potions:
            root_refs.update(_collect_status_refs(potion.actions))

        # 2. Build lookup: id-or-name → StatusEffectDefinition
        by_key: dict[str, StatusEffectDefinition] = {}
        for s in self.status_effects:
            by_key[s.id] = s
            by_key[s.name] = s

        # 3. Transitive closure: follow trigger refs from reachable statuses.
        reachable: set[str] = set()  # ids of kept statuses
        frontier = set(root_refs)
        while frontier:
            ref = frontier.pop()
            status = by_key.get(ref)
            if status is None or status.id in reachable:
                continue
            reachable.add(status.id)
            # Add refs from this status's triggers
            for trigger_actions in status.triggers.values():
                for child_ref in _collect_status_refs(trigger_actions):
                    if child_ref not in reachable:
                        frontier.add(child_ref)

        kept = [s for s in self.status_effects if s.id in reachable]
        if len(kept) == len(self.status_effects):
            return self

        return self.model_copy(update={"status_effects": kept})

    # -- validation ---------------------------------------------------------

    @model_validator(mode="after")
    def _validate_status_references(self) -> "ContentSet":
        """Ensure every ``status_name`` used in an ActionNode corresponds to
        either a status effect defined in this content set or a known vanilla
        status from the base game.
        """
        known_ids: set[str] = {s.id for s in self.status_effects}
        known_names: set[str] = {s.name for s in self.status_effects}
        allowed = known_ids | known_names | VANILLA_STATUSES

        # Gather every status reference from all action trees across all
        # content types.
        all_refs: set[str] = set()

        for card in self.cards:
            all_refs.update(_collect_status_refs(card.actions))
            if card.upgrade and card.upgrade.actions:
                all_refs.update(_collect_status_refs(card.upgrade.actions))

        for relic in self.relics:
            all_refs.update(_collect_status_refs(relic.actions))

        for potion in self.potions:
            all_refs.update(_collect_status_refs(potion.actions))

        for status in self.status_effects:
            for trigger_actions in status.triggers.values():
                all_refs.update(_collect_status_refs(trigger_actions))

        unknown = all_refs - allowed
        if unknown:
            raise ValueError(
                f"Unknown status effect(s) referenced in actions: "
                f"{', '.join(sorted(unknown))}. "
                f"Define them in status_effects or use a vanilla status name."
            )

        return self

    @model_validator(mode="after")
    def _validate_transpilability(self) -> "ContentSet":
        """Ensure all action trees are transpilable to Java.

        Rejects:
        - ``trigger_custom`` actions (reserved for Ironclad-specific mechanics)
        - Unknown/unsupported conditions for a given action type
        - Missing required fields (e.g. ``status_name`` on ``apply_status``)
        """
        errors: list[str] = []

        for card in self.cards:
            label = f"card '{card.id}'"
            errors.extend(
                _walk_action_errors(card.actions, source_label=label)
            )
            if card.upgrade and card.upgrade.actions:
                errors.extend(
                    _walk_action_errors(
                        card.upgrade.actions,
                        source_label=f"{label} (upgrade)",
                    )
                )
            if card.on_exhaust:
                errors.extend(
                    _walk_action_errors(
                        card.on_exhaust,
                        source_label=f"{label} (on_exhaust)",
                    )
                )

        for relic in self.relics:
            errors.extend(
                _walk_action_errors(
                    relic.actions, source_label=f"relic '{relic.id}'"
                )
            )

        for potion in self.potions:
            errors.extend(
                _walk_action_errors(
                    potion.actions, source_label=f"potion '{potion.id}'"
                )
            )

        for status in self.status_effects:
            for trigger, trigger_actions in status.triggers.items():
                errors.extend(
                    _walk_action_errors(
                        trigger_actions,
                        source_label=f"status '{status.id}' trigger {trigger}",
                    )
                )

        if errors:
            raise ValueError(
                f"Transpilability validation failed with {len(errors)} error(s):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        return self
