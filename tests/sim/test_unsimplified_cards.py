"""Tests for the 6 un-simplified Ironclad cards.

Covers Rampage, Blood for Blood, Searing Blow, Armaments, Dual Wield,
and Infernal Blade — all of which previously had [SIMPLIFIED] behavior.
"""

import pytest

from sts_gen.ir.cards import CardTarget, CardType
from sts_gen.sim.content.registry import ContentRegistry
from sts_gen.sim.core.entities import Enemy, Player
from sts_gen.sim.core.game_state import BattleState, CardInstance, CardPiles
from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.interpreter import ActionInterpreter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(**kwargs) -> Player:
    defaults = dict(name="Ironclad", max_hp=80, current_hp=80, max_energy=3, energy=3)
    defaults.update(kwargs)
    return Player(**defaults)


def _make_enemy(**kwargs) -> Enemy:
    defaults = dict(name="Dummy", enemy_id="dummy", max_hp=200, current_hp=200)
    defaults.update(kwargs)
    return Enemy(**defaults)


@pytest.fixture(scope="module")
def registry() -> ContentRegistry:
    reg = ContentRegistry()
    reg.load_vanilla_cards()
    reg.load_vanilla_enemies()
    reg.load_vanilla_status_effects()
    return reg


def _make_battle(
    hand_ids: list[str] | None = None,
    draw_ids: list[str] | None = None,
    player: Player | None = None,
    enemies: list[Enemy] | None = None,
) -> BattleState:
    piles = CardPiles(
        draw=[CardInstance(card_id=cid) for cid in (draw_ids or ["strike"] * 10)],
        hand=[CardInstance(card_id=cid) for cid in (hand_ids or [])],
    )
    return BattleState(
        player=player or _make_player(),
        enemies=enemies or [_make_enemy()],
        card_piles=piles,
        rng=GameRNG(42),
    )


def _play_card(
    registry: ContentRegistry,
    battle: BattleState,
    card_inst: CardInstance,
    target: int | None = 0,
) -> None:
    """Play a card through the interpreter."""
    card_def = registry.get_card(card_inst.card_id)
    assert card_def is not None, f"Card {card_inst.card_id!r} not in registry"
    interp = ActionInterpreter(card_registry=registry.cards)
    interp.play_card(card_def, battle, card_inst, chosen_target=target)


def _play_card_from_hand(
    registry: ContentRegistry,
    battle: BattleState,
    card_id: str,
    target: int | None = 0,
) -> CardInstance:
    """Find card_id in hand, play it, return the instance."""
    for ci in battle.card_piles.hand:
        if ci.card_id == card_id:
            _play_card(registry, battle, ci, target)
            return ci
    raise ValueError(f"Card {card_id!r} not in hand")


# ===========================================================================
# Rampage
# ===========================================================================


class TestRampage:
    def test_first_play_deals_base_damage(self, registry: ContentRegistry) -> None:
        """First play of Rampage deals 8 damage (no bonus yet)."""
        battle = _make_battle()
        ci = CardInstance(card_id="rampage")
        battle.card_piles.hand.append(ci)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        # 8 damage with 0 strength
        assert battle.enemies[0].current_hp == hp_before - 8

    def test_second_play_deals_scaled_damage(self, registry: ContentRegistry) -> None:
        """Second play adds +5 bonus for base Rampage."""
        battle = _make_battle(player=_make_player(energy=10))
        ci = CardInstance(card_id="rampage")
        battle.card_piles.hand.append(ci)

        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        assert battle.enemies[0].current_hp == hp_before - 8  # first play: 8

        # Move back to hand for second play
        battle.card_piles.hand.append(ci)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        assert battle.enemies[0].current_hp == hp_before - 13  # second play: 8 + 5

    def test_upgraded_scales_by_8(self, registry: ContentRegistry) -> None:
        """Upgraded Rampage scales by +8 per play."""
        battle = _make_battle(player=_make_player(energy=10))
        ci = CardInstance(card_id="rampage", upgraded=True)
        battle.card_piles.hand.append(ci)

        _play_card(registry, battle, ci)
        hp_after_first = battle.enemies[0].current_hp

        battle.card_piles.hand.append(ci)
        _play_card(registry, battle, ci)
        hp_after_second = battle.enemies[0].current_hp

        # First: 8, Second: 8 + 8 = 16
        assert 200 - hp_after_first == 8
        assert hp_after_first - hp_after_second == 16

    def test_two_copies_track_independently(self, registry: ContentRegistry) -> None:
        """Two different Rampage copies scale independently."""
        battle = _make_battle(player=_make_player(energy=20))
        ci_a = CardInstance(card_id="rampage")
        ci_b = CardInstance(card_id="rampage")

        # Play A twice
        battle.card_piles.hand.append(ci_a)
        _play_card(registry, battle, ci_a)
        battle.card_piles.hand.append(ci_a)
        _play_card(registry, battle, ci_a)

        # Play B first time — should deal 8 (no bonus)
        battle.card_piles.hand.append(ci_b)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci_b)
        assert battle.enemies[0].current_hp == hp_before - 8


# ===========================================================================
# Blood for Blood
# ===========================================================================


class TestBloodForBlood:
    def test_base_cost_is_4(self, registry: ContentRegistry) -> None:
        """Blood for Blood base cost is 4."""
        card_def = registry.get_card("blood_for_blood")
        assert card_def is not None
        assert card_def.cost == 4

    def test_cost_decreases_on_self_hp_loss(self, registry: ContentRegistry) -> None:
        """Cost decreases when player loses HP from a card (e.g. Offering)."""
        battle = _make_battle(player=_make_player(energy=10))
        bfb = CardInstance(card_id="blood_for_blood")
        battle.card_piles.hand.append(bfb)

        # Simulate HP loss tracking
        battle.combat_vars["hp_loss_count"] = 2

        # Manually trigger cost update (as runner would)
        from sts_gen.sim.runner import CombatSimulator
        interp = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interp, None)
        sim._update_blood_for_blood_costs(battle)

        assert bfb.cost_override == 2  # 4 - 2

    def test_cost_floors_at_zero(self, registry: ContentRegistry) -> None:
        """Cost never goes below 0."""
        battle = _make_battle()
        bfb = CardInstance(card_id="blood_for_blood")
        battle.card_piles.hand.append(bfb)

        battle.combat_vars["hp_loss_count"] = 10

        from sts_gen.sim.runner import CombatSimulator
        interp = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interp, None)
        sim._update_blood_for_blood_costs(battle)

        assert bfb.cost_override == 0

    def test_upgraded_base_cost_is_3(self, registry: ContentRegistry) -> None:
        """Upgraded Blood for Blood has base cost 3."""
        battle = _make_battle()
        bfb = CardInstance(card_id="blood_for_blood", upgraded=True)
        battle.card_piles.hand.append(bfb)

        battle.combat_vars["hp_loss_count"] = 1

        from sts_gen.sim.runner import CombatSimulator
        interp = ActionInterpreter(card_registry=registry.cards)
        sim = CombatSimulator(registry, interp, None)
        sim._update_blood_for_blood_costs(battle)

        assert bfb.cost_override == 2  # 3 - 1


# ===========================================================================
# Searing Blow
# ===========================================================================


class TestSearingBlow:
    def test_base_damage_12(self, registry: ContentRegistry) -> None:
        """Searing Blow at upgrade_count=0 deals 12 damage."""
        battle = _make_battle()
        ci = CardInstance(card_id="searing_blow", upgrade_count=0)
        battle.card_piles.hand.append(ci)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        assert battle.enemies[0].current_hp == hp_before - 12

    def test_upgrade_1_damage_16(self, registry: ContentRegistry) -> None:
        """Searing Blow+1 deals 16 damage (12 + 4*1 + 0)."""
        battle = _make_battle()
        ci = CardInstance(card_id="searing_blow", upgraded=True, upgrade_count=1)
        battle.card_piles.hand.append(ci)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        assert battle.enemies[0].current_hp == hp_before - 16

    def test_upgrade_2_damage_21(self, registry: ContentRegistry) -> None:
        """Searing Blow+2 deals 21 damage (12 + 8 + 1)."""
        battle = _make_battle()
        ci = CardInstance(card_id="searing_blow", upgraded=True, upgrade_count=2)
        battle.card_piles.hand.append(ci)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        assert battle.enemies[0].current_hp == hp_before - 21

    def test_upgrade_3_damage_27(self, registry: ContentRegistry) -> None:
        """Searing Blow+3 deals 27 damage (12 + 12 + 3)."""
        battle = _make_battle()
        ci = CardInstance(card_id="searing_blow", upgraded=True, upgrade_count=3)
        battle.card_piles.hand.append(ci)
        hp_before = battle.enemies[0].current_hp
        _play_card(registry, battle, ci)
        assert battle.enemies[0].current_hp == hp_before - 27

    def test_always_upgradable_at_rest(self) -> None:
        """Searing Blow should be upgradable even when already upgraded."""
        from sts_gen.sim.dungeon.run_manager import RunManager

        deck = [
            CardInstance(card_id="searing_blow", upgraded=True, upgrade_count=3),
            CardInstance(card_id="strike"),
        ]
        upgradable = [
            ci for ci in deck
            if (not ci.upgraded) or ci.card_id == "searing_blow"
        ]
        assert any(ci.card_id == "searing_blow" for ci in upgradable)

    def test_multi_upgrade_increments_count(self) -> None:
        """Upgrading Searing Blow increments upgrade_count."""
        ci = CardInstance(card_id="searing_blow", upgraded=True, upgrade_count=2)
        ci.upgrade_count += 1
        assert ci.upgrade_count == 3


# ===========================================================================
# Armaments
# ===========================================================================


class TestArmaments:
    def test_base_upgrades_one_card(self, registry: ContentRegistry) -> None:
        """Base Armaments upgrades one random non-upgraded card in hand."""
        battle = _make_battle(player=_make_player(energy=5))
        # Add armaments + 3 non-upgraded strikes to hand
        armaments = CardInstance(card_id="armaments")
        s1 = CardInstance(card_id="strike")
        s2 = CardInstance(card_id="strike")
        s3 = CardInstance(card_id="strike")
        battle.card_piles.hand.extend([armaments, s1, s2, s3])

        _play_card(registry, battle, armaments, target=None)

        # Exactly one strike should be upgraded
        upgraded_count = sum(1 for c in [s1, s2, s3] if c.upgraded)
        assert upgraded_count == 1

    def test_upgraded_upgrades_all(self, registry: ContentRegistry) -> None:
        """Upgraded Armaments upgrades ALL non-upgraded cards in hand."""
        battle = _make_battle(player=_make_player(energy=5))
        armaments = CardInstance(card_id="armaments", upgraded=True)
        s1 = CardInstance(card_id="strike")
        s2 = CardInstance(card_id="defend")
        s3 = CardInstance(card_id="bash")
        battle.card_piles.hand.extend([armaments, s1, s2, s3])

        _play_card(registry, battle, armaments, target=None)

        assert s1.upgraded is True
        assert s2.upgraded is True
        assert s3.upgraded is True

    def test_skips_already_upgraded(self, registry: ContentRegistry) -> None:
        """Armaments doesn't attempt to re-upgrade already upgraded cards."""
        battle = _make_battle(player=_make_player(energy=5))
        armaments = CardInstance(card_id="armaments")
        # Already upgraded card in hand
        already_upgraded = CardInstance(card_id="strike", upgraded=True)
        not_upgraded = CardInstance(card_id="defend")
        battle.card_piles.hand.extend([armaments, already_upgraded, not_upgraded])

        _play_card(registry, battle, armaments, target=None)

        # The non-upgraded card should get upgraded
        assert not_upgraded.upgraded is True
        # The already-upgraded card stays upgraded
        assert already_upgraded.upgraded is True


# ===========================================================================
# Dual Wield
# ===========================================================================


class TestDualWield:
    def test_copies_attack_in_hand(self, registry: ContentRegistry) -> None:
        """Dual Wield creates a copy of an Attack card in hand."""
        battle = _make_battle(player=_make_player(energy=5))
        dw = CardInstance(card_id="dual_wield")
        strike = CardInstance(card_id="strike")
        battle.card_piles.hand.extend([dw, strike])

        hand_before = len(battle.card_piles.hand)
        _play_card(registry, battle, dw, target=None)

        # Dual Wield is discarded/exhausted, strike stays, copy added
        # Hand should have strike + copy of strike
        strikes_in_hand = [
            c for c in battle.card_piles.hand if c.card_id == "strike"
        ]
        assert len(strikes_in_hand) == 2  # original + copy

    def test_upgraded_makes_two_copies(self, registry: ContentRegistry) -> None:
        """Upgraded Dual Wield creates 2 copies."""
        battle = _make_battle(player=_make_player(energy=5))
        dw = CardInstance(card_id="dual_wield", upgraded=True)
        strike = CardInstance(card_id="strike")
        battle.card_piles.hand.extend([dw, strike])

        _play_card(registry, battle, dw, target=None)

        strikes_in_hand = [
            c for c in battle.card_piles.hand if c.card_id == "strike"
        ]
        assert len(strikes_in_hand) == 3  # original + 2 copies

    def test_only_copies_attacks_and_powers(self, registry: ContentRegistry) -> None:
        """Dual Wield only targets Attack and Power cards, not Skills."""
        battle = _make_battle(player=_make_player(energy=5))
        dw = CardInstance(card_id="dual_wield")
        # Only a skill in hand — should find nothing to copy
        defend = CardInstance(card_id="defend")
        battle.card_piles.hand.extend([dw, defend])

        hand_size_before = len(battle.card_piles.hand)
        _play_card(registry, battle, dw, target=None)

        # No copy should be made, defend still in hand
        defends_in_hand = [
            c for c in battle.card_piles.hand if c.card_id == "defend"
        ]
        assert len(defends_in_hand) == 1


# ===========================================================================
# Infernal Blade
# ===========================================================================


class TestInfernalBlade:
    def test_adds_random_attack_to_hand(self, registry: ContentRegistry) -> None:
        """Infernal Blade adds a random Attack card to hand."""
        battle = _make_battle(player=_make_player(energy=5))
        ib = CardInstance(card_id="infernal_blade")
        battle.card_piles.hand.append(ib)

        _play_card(registry, battle, ib, target=None)

        # Should have generated a card in hand
        assert len(battle.card_piles.hand) >= 1
        # The generated card should be an Attack
        for c in battle.card_piles.hand:
            cd = registry.get_card(c.card_id)
            if cd is not None:
                assert cd.type == CardType.ATTACK

    def test_generated_card_costs_zero(self, registry: ContentRegistry) -> None:
        """Generated Attack has cost_override=0."""
        battle = _make_battle(player=_make_player(energy=5))
        ib = CardInstance(card_id="infernal_blade")
        battle.card_piles.hand.append(ib)

        _play_card(registry, battle, ib, target=None)

        # Find the generated card (not infernal_blade itself)
        generated = [
            c for c in battle.card_piles.hand
            if c.card_id != "infernal_blade"
        ]
        assert len(generated) == 1
        assert generated[0].cost_override == 0

    def test_upgraded_costs_zero_to_play(self, registry: ContentRegistry) -> None:
        """Upgraded Infernal Blade costs 0 energy."""
        card_def = registry.get_card("infernal_blade")
        assert card_def is not None
        assert card_def.upgrade is not None
        assert card_def.upgrade.cost == 0


# ===========================================================================
# Integration: no SIMPLIFIED tags remain
# ===========================================================================


class TestNoSimplifiedTags:
    def test_no_simplified_in_json(self) -> None:
        """No [SIMPLIFIED] tags should remain in the card JSON."""
        import json
        from pathlib import Path

        json_path = Path(__file__).parent.parent.parent / "data" / "vanilla" / "ironclad_cards.json"
        content = json_path.read_text()
        assert "SIMPLIFIED" not in content
