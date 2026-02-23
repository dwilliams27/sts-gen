"""Top-level container that bundles all mod content into a single IR document."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from .actions import ActionNode
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
