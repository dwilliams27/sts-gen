"""Tests for the IR schema -- ActionNode, CardDefinition, ContentSet, etc."""

import json

import pytest

from sts_gen.ir import (
    ActionNode,
    ActionType,
    CardDefinition,
    CardRarity,
    CardTarget,
    CardType,
    ContentSet,
    UpgradeDefinition,
)
from sts_gen.ir.status_effects import (
    StackBehavior,
    StatusEffectDefinition,
    StatusTrigger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strike() -> CardDefinition:
    """Minimal Strike card definition used across several tests."""
    return CardDefinition(
        id="strike",
        name="Strike",
        type=CardType.ATTACK,
        rarity=CardRarity.BASIC,
        cost=1,
        target=CardTarget.ENEMY,
        description="Deal 6 damage.",
        actions=[
            ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
        ],
    )


def _make_defend() -> CardDefinition:
    return CardDefinition(
        id="defend",
        name="Defend",
        type=CardType.SKILL,
        rarity=CardRarity.BASIC,
        cost=1,
        target=CardTarget.SELF,
        description="Gain 5 Block.",
        actions=[
            ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self"),
        ],
    )


# ---------------------------------------------------------------------------
# Card serialization round-trip (JSON)
# ---------------------------------------------------------------------------

class TestCardSerializationRoundTrip:
    """Card definitions must survive a JSON round-trip via Pydantic."""

    def test_strike_round_trip(self):
        card = _make_strike()
        json_str = card.model_dump_json()
        restored = CardDefinition.model_validate_json(json_str)

        assert restored.id == card.id
        assert restored.name == card.name
        assert restored.type == card.type
        assert restored.rarity == card.rarity
        assert restored.cost == card.cost
        assert restored.target == card.target
        assert restored.description == card.description
        assert len(restored.actions) == 1
        assert restored.actions[0].action_type == ActionType.DEAL_DAMAGE
        assert restored.actions[0].value == 6
        assert restored.actions[0].target == "enemy"

    def test_card_with_upgrade_round_trip(self):
        card = CardDefinition(
            id="strike",
            name="Strike",
            type=CardType.ATTACK,
            rarity=CardRarity.BASIC,
            cost=1,
            target=CardTarget.ENEMY,
            description="Deal 6 damage.",
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=6, target="enemy"),
            ],
            upgrade=UpgradeDefinition(
                actions=[
                    ActionNode(action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy"),
                ],
                description="Deal 9 damage.",
            ),
        )
        json_str = card.model_dump_json()
        restored = CardDefinition.model_validate_json(json_str)

        assert restored.upgrade is not None
        assert restored.upgrade.cost is None  # not changed
        assert len(restored.upgrade.actions) == 1
        assert restored.upgrade.actions[0].value == 9
        assert restored.upgrade.description == "Deal 9 damage."

    def test_round_trip_through_dict(self):
        card = _make_strike()
        d = card.model_dump()
        restored = CardDefinition.model_validate(d)
        assert restored == card


# ---------------------------------------------------------------------------
# ActionNode with children (recursive structure)
# ---------------------------------------------------------------------------

class TestActionNodeRecursive:
    def test_repeat_with_children(self):
        node = ActionNode(
            action_type=ActionType.REPEAT,
            times=3,
            children=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=3, target="random_enemy"),
            ],
        )
        assert node.times == 3
        assert len(node.children) == 1
        assert node.children[0].action_type == ActionType.DEAL_DAMAGE
        assert node.children[0].value == 3

    def test_conditional_with_children(self):
        node = ActionNode(
            action_type=ActionType.CONDITIONAL,
            condition="hp_below:50",
            children=[
                ActionNode(action_type=ActionType.GAIN_BLOCK, value=10, target="self"),
            ],
        )
        assert node.condition == "hp_below:50"
        assert len(node.children) == 1

    def test_nested_children_serialization(self):
        """A repeat containing a conditional containing a deal_damage."""
        node = ActionNode(
            action_type=ActionType.REPEAT,
            times=2,
            children=[
                ActionNode(
                    action_type=ActionType.CONDITIONAL,
                    condition="has_status:strength",
                    children=[
                        ActionNode(
                            action_type=ActionType.DEAL_DAMAGE,
                            value=5,
                            target="enemy",
                        ),
                    ],
                ),
            ],
        )
        json_str = node.model_dump_json()
        restored = ActionNode.model_validate_json(json_str)
        assert restored.times == 2
        assert len(restored.children) == 1
        inner = restored.children[0]
        assert inner.action_type == ActionType.CONDITIONAL
        assert len(inner.children) == 1
        assert inner.children[0].value == 5


# ---------------------------------------------------------------------------
# ContentSet validation catches bad status references
# ---------------------------------------------------------------------------

class TestContentSetValidation:
    def test_vanilla_status_reference_is_allowed(self):
        """Referencing a known vanilla status like 'Vulnerable' should work."""
        card = CardDefinition(
            id="test_card",
            name="Test Card",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Apply 2 Vulnerable.",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=2,
                    status_name="Vulnerable",
                    target="enemy",
                ),
            ],
        )
        # Should not raise
        cs = ContentSet(mod_id="test", mod_name="Test", cards=[card])
        assert cs.get_card("test_card") is not None

    def test_unknown_status_reference_raises(self):
        """Referencing a status that is neither vanilla nor defined should fail."""
        card = CardDefinition(
            id="bad_card",
            name="Bad Card",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Apply 2 TotallyFakeStatus.",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=2,
                    status_name="TotallyFakeStatus",
                    target="enemy",
                ),
            ],
        )
        with pytest.raises(ValueError, match="Unknown status effect"):
            ContentSet(mod_id="test", mod_name="Test", cards=[card])

    def test_custom_status_defined_is_allowed(self):
        """Defining a custom status and referencing it should work."""
        custom_status = StatusEffectDefinition(
            id="my_mod:Burning",
            name="Burning",
            description="Take damage at end of turn.",
            is_debuff=True,
            stack_behavior=StackBehavior.INTENSITY,
            triggers={
                StatusTrigger.ON_TURN_END: [
                    ActionNode(
                        action_type=ActionType.DEAL_DAMAGE,
                        value=3,
                        target="self",
                    ),
                ],
            },
            decay_per_turn=0,
        )
        card = CardDefinition(
            id="ignite",
            name="Ignite",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Apply 3 Burning.",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=3,
                    status_name="my_mod:Burning",
                    target="enemy",
                ),
            ],
        )
        cs = ContentSet(
            mod_id="test",
            mod_name="Test",
            cards=[card],
            status_effects=[custom_status],
        )
        assert cs.get_status("my_mod:Burning") is not None


# ---------------------------------------------------------------------------
# ContentSet.prune_unused_statuses
# ---------------------------------------------------------------------------

class TestPruneUnusedStatuses:
    """Tests for ContentSet.prune_unused_statuses()."""

    def _make_status(self, id: str, name: str, refs: list[str] | None = None):
        """Helper: create a StatusEffectDefinition, optionally referencing other statuses."""
        triggers = {}
        if refs:
            triggers[StatusTrigger.ON_TURN_START] = [
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=1,
                    status_name=ref,
                    target="self",
                )
                for ref in refs
            ]
        else:
            triggers[StatusTrigger.ON_TURN_START] = [
                ActionNode(action_type=ActionType.GAIN_BLOCK, value=3, target="self"),
            ]
        return StatusEffectDefinition(
            id=id,
            name=name,
            description=f"{name} status",
            is_debuff=False,
            stack_behavior=StackBehavior.INTENSITY,
            triggers=triggers,
        )

    def _make_card_with_status(self, card_id: str, status_name: str):
        return CardDefinition(
            id=card_id,
            name=card_id,
            type=CardType.POWER,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.SELF,
            description="Test",
            actions=[
                ActionNode(
                    action_type=ActionType.APPLY_STATUS,
                    value=1,
                    status_name=status_name,
                    target="self",
                ),
            ],
        )

    def test_no_pruning_when_all_used(self):
        status = self._make_status("mod:A", "A")
        card = self._make_card_with_status("c1", "mod:A")
        cs = ContentSet(mod_id="t", mod_name="T", cards=[card], status_effects=[status])

        pruned = cs.prune_unused_statuses()
        assert len(pruned.status_effects) == 1
        assert pruned is cs  # same object, no copy needed

    def test_dead_status_removed(self):
        used = self._make_status("mod:A", "A")
        dead = self._make_status("mod:B", "B")
        card = self._make_card_with_status("c1", "mod:A")
        cs = ContentSet(
            mod_id="t", mod_name="T",
            cards=[card], status_effects=[used, dead],
        )

        pruned = cs.prune_unused_statuses()
        assert len(pruned.status_effects) == 1
        assert pruned.status_effects[0].id == "mod:A"

    def test_transitive_ref_kept(self):
        """Status A → Status B in triggers; both should survive."""
        a = self._make_status("mod:A", "A", refs=["mod:B"])
        b = self._make_status("mod:B", "B")
        dead = self._make_status("mod:C", "C")
        card = self._make_card_with_status("c1", "mod:A")
        cs = ContentSet(
            mod_id="t", mod_name="T",
            cards=[card], status_effects=[a, b, dead],
        )

        pruned = cs.prune_unused_statuses()
        kept_ids = {s.id for s in pruned.status_effects}
        assert kept_ids == {"mod:A", "mod:B"}

    def test_mutual_dead_chain_pruned(self):
        """Dead D → Dead E: neither is reachable from cards, both pruned."""
        d = self._make_status("mod:D", "D", refs=["mod:E"])
        e = self._make_status("mod:E", "E")
        used = self._make_status("mod:A", "A")
        card = self._make_card_with_status("c1", "mod:A")
        cs = ContentSet(
            mod_id="t", mod_name="T",
            cards=[card], status_effects=[used, d, e],
        )

        pruned = cs.prune_unused_statuses()
        kept_ids = {s.id for s in pruned.status_effects}
        assert kept_ids == {"mod:A"}

    def test_ref_by_name_keeps_status(self):
        """Cards can reference statuses by name (not just id)."""
        status = self._make_status("mod:Fire", "Fire")
        card = self._make_card_with_status("c1", "Fire")  # name, not id
        cs = ContentSet(
            mod_id="t", mod_name="T",
            cards=[card], status_effects=[status],
        )

        pruned = cs.prune_unused_statuses()
        assert len(pruned.status_effects) == 1

    def test_upgrade_actions_count_as_refs(self):
        """Status referenced only in upgrade actions should be kept."""
        status = self._make_status("mod:X", "X")
        card = CardDefinition(
            id="c1", name="c1", type=CardType.POWER, rarity=CardRarity.COMMON,
            cost=1, target=CardTarget.SELF, description="Test",
            actions=[ActionNode(action_type=ActionType.GAIN_BLOCK, value=5, target="self")],
            upgrade=UpgradeDefinition(
                actions=[ActionNode(
                    action_type=ActionType.APPLY_STATUS, value=2,
                    status_name="mod:X", target="self",
                )],
            ),
        )
        cs = ContentSet(
            mod_id="t", mod_name="T",
            cards=[card], status_effects=[status],
        )

        pruned = cs.prune_unused_statuses()
        assert len(pruned.status_effects) == 1

    def test_relic_refs_count(self):
        """Status referenced by a relic should be kept."""
        from sts_gen.ir.relics import RelicDefinition, RelicTier

        status = self._make_status("mod:R", "R")
        relic = RelicDefinition(
            id="mod:relic", name="Test Relic", tier=RelicTier.COMMON,
            description="Test", trigger="on_combat_start",
            actions=[ActionNode(
                action_type=ActionType.APPLY_STATUS, value=1,
                status_name="mod:R", target="self",
            )],
        )
        cs = ContentSet(
            mod_id="t", mod_name="T",
            relics=[relic], status_effects=[status],
        )

        pruned = cs.prune_unused_statuses()
        assert len(pruned.status_effects) == 1

    def test_potion_refs_count(self):
        """Status referenced by a potion should be kept."""
        from sts_gen.ir.potions import PotionDefinition, PotionRarity

        status = self._make_status("mod:P", "P")
        potion = PotionDefinition(
            id="mod:pot", name="Test Potion", rarity=PotionRarity.COMMON,
            description="Test", target=CardTarget.SELF,
            actions=[ActionNode(
                action_type=ActionType.APPLY_STATUS, value=1,
                status_name="mod:P", target="self",
            )],
        )
        cs = ContentSet(
            mod_id="t", mod_name="T",
            potions=[potion], status_effects=[status],
        )

        pruned = cs.prune_unused_statuses()
        assert len(pruned.status_effects) == 1

    def test_empty_statuses_noop(self):
        cs = ContentSet(mod_id="t", mod_name="T")
        pruned = cs.prune_unused_statuses()
        assert pruned is cs


# ---------------------------------------------------------------------------
# CardDefinition with upgrade
# ---------------------------------------------------------------------------

class TestCardWithUpgrade:
    def test_upgrade_with_new_cost(self):
        card = CardDefinition(
            id="body_slam",
            name="Body Slam",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Deal damage equal to your Block.",
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=0, target="enemy"),
            ],
            upgrade=UpgradeDefinition(cost=0),
        )
        assert card.upgrade.cost == 0
        assert card.upgrade.actions is None  # not changed
        assert card.upgrade.description is None

    def test_upgrade_with_new_actions(self):
        card = _make_strike()
        card.upgrade = UpgradeDefinition(
            actions=[
                ActionNode(action_type=ActionType.DEAL_DAMAGE, value=9, target="enemy"),
            ],
        )
        assert card.upgrade.actions[0].value == 9

    def test_no_upgrade(self):
        card = _make_strike()
        assert card.upgrade is None


# ---------------------------------------------------------------------------
# All card types, rarities, targets create successfully
# ---------------------------------------------------------------------------

class TestEnumCoverage:
    @pytest.mark.parametrize(
        "card_type",
        [CardType.ATTACK, CardType.SKILL, CardType.POWER, CardType.STATUS, CardType.CURSE],
    )
    def test_all_card_types(self, card_type):
        card = CardDefinition(
            id=f"test_{card_type.value.lower()}",
            name=f"Test {card_type.value}",
            type=card_type,
            rarity=CardRarity.COMMON,
            cost=1,
            target=CardTarget.ENEMY,
            description="Test card.",
            actions=[],
        )
        assert card.type == card_type

    @pytest.mark.parametrize(
        "rarity",
        [CardRarity.BASIC, CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE, CardRarity.SPECIAL],
    )
    def test_all_card_rarities(self, rarity):
        card = CardDefinition(
            id=f"test_{rarity.value.lower()}",
            name=f"Test {rarity.value}",
            type=CardType.ATTACK,
            rarity=rarity,
            cost=1,
            target=CardTarget.ENEMY,
            description="Test card.",
            actions=[],
        )
        assert card.rarity == rarity

    @pytest.mark.parametrize(
        "target",
        [CardTarget.ENEMY, CardTarget.ALL_ENEMIES, CardTarget.SELF, CardTarget.NONE],
    )
    def test_all_card_targets(self, target):
        card = CardDefinition(
            id=f"test_{target.value.lower()}",
            name=f"Test {target.value}",
            type=CardType.ATTACK,
            rarity=CardRarity.COMMON,
            cost=1,
            target=target,
            description="Test card.",
            actions=[],
        )
        assert card.target == target

    @pytest.mark.parametrize(
        "action_type",
        list(ActionType),
    )
    def test_all_action_types_construct(self, action_type):
        node = ActionNode(action_type=action_type)
        assert node.action_type == action_type
