"""Quick validation that all vanilla content loads correctly."""

from collections import Counter

from sts_gen.sim.content.registry import ContentRegistry


def test_load_all():
    registry = ContentRegistry()
    registry.load_vanilla_cards()
    registry.load_vanilla_enemies()

    print(f"Registry: {registry}")
    print()

    # --- Cards ---
    print("=== CARDS ===")
    card_ids = registry.list_card_ids()
    assert len(card_ids) == 22, f"Expected 22 cards, got {len(card_ids)}"

    for card_id in card_ids:
        card = registry.get_card(card_id)
        assert card is not None
        print(f"  {card.id:20s} | {card.type.value:6s} | {card.rarity.value:9s} | cost={card.cost:2d} | {card.name}")
        for i, action in enumerate(card.actions):
            parts = [f"action[{i}]: {action.action_type.value}"]
            if action.value is not None:
                parts.append(f"value={action.value}")
            if action.target and action.target != "default":
                parts.append(f"target={action.target}")
            if action.status_name:
                parts.append(f"status={action.status_name}")
            if action.card_id:
                parts.append(f"card_id={action.card_id}")
            if action.pile:
                parts.append(f"pile={action.pile}")
            if action.times:
                parts.append(f"times={action.times}")
            if action.condition:
                parts.append(f"condition={action.condition}")
            if action.children:
                parts.append(f"children=[{len(action.children)} nodes]")
            print(f"    {' '.join(parts)}")
        if card.upgrade:
            print(f"    upgrade: cost={card.upgrade.cost}, has_actions={card.upgrade.actions is not None}")

    print()

    # --- Enemies ---
    print("=== ENEMIES ===")
    enemy_ids = registry.list_enemy_ids()
    assert len(enemy_ids) == 3, f"Expected 3 enemies, got {len(enemy_ids)}"

    for eid in enemy_ids:
        e = registry.get_enemy_data(eid)
        assert e is not None
        print(f"  {e['id']:15s} | HP {e['hp_min']}-{e['hp_max']} | {e['name']}")
        for move in e["moves"]:
            parts = [f"move: {move['id']:15s} type={move['type']}"]
            if "damage" in move:
                parts.append(f"dmg={move['damage']}")
            if "damage_min" in move:
                parts.append(f"dmg={move['damage_min']}-{move['damage_max']}")
            if "block" in move:
                parts.append(f"block={move['block']}")
            if "actions" in move:
                parts.append(f"actions=[{len(move['actions'])}]")
            print(f"    {' '.join(parts)}")
        pat = e["pattern"]
        print(f"    pattern: type={pat['type']}, opening={pat.get('opening_move')}")

    print()

    # --- Starter deck ---
    deck = registry.get_starter_deck("ironclad")
    assert len(deck) == 10, f"Expected 10 cards in deck, got {len(deck)}"
    print(f"=== STARTER DECK ({len(deck)} cards) ===")
    for card_id, count in Counter(deck).items():
        print(f"  {count}x {card_id}")

    # Verify starter deck composition
    counts = Counter(deck)
    assert counts["strike"] == 5
    assert counts["defend"] == 4
    assert counts["bash"] == 1

    print()

    # --- Upgrade tests ---
    print("=== UPGRADE TESTS ===")

    # Strike: base 6 dmg, upgrade 9 dmg, cost stays 1
    assert registry.get_card_cost("strike", upgraded=False) == 1
    assert registry.get_card_cost("strike", upgraded=True) == 1
    base = registry.get_card_actions("strike", upgraded=False)
    upg = registry.get_card_actions("strike", upgraded=True)
    assert base[0].value == 6
    assert upg[0].value == 9
    print("  strike: OK")

    # Body Slam: base cost 1, upgraded cost 0
    assert registry.get_card_cost("body_slam", upgraded=False) == 1
    assert registry.get_card_cost("body_slam", upgraded=True) == 0
    print("  body_slam: OK")

    # Sword Boomerang: base 3 times, upgraded 4 times
    base = registry.get_card_actions("sword_boomerang", upgraded=False)
    upg = registry.get_card_actions("sword_boomerang", upgraded=True)
    assert base[0].times == 3
    assert upg[0].times == 4
    print("  sword_boomerang: OK")

    # Inflame: base gain 2 str, upgraded gain 3 str
    base = registry.get_card_actions("inflame", upgraded=False)
    upg = registry.get_card_actions("inflame", upgraded=True)
    assert base[0].value == 2
    assert upg[0].value == 3
    print("  inflame: OK")

    print()

    # --- Reward pool ---
    pool = registry.get_reward_pool()
    print(f"=== REWARD POOL ({len(pool)} cards) ===")
    for card in pool:
        print(f"  {card.id} ({card.rarity.value})")
        # No BASIC, SPECIAL, STATUS, or CURSE cards in pool
        assert card.rarity.value not in ("BASIC", "SPECIAL")
        assert card.type.value not in ("STATUS", "CURSE")

    print()

    # --- Special card checks ---
    # Wound is a STATUS card and should not be in the reward pool
    wound = registry.get_card("wound")
    assert wound is not None
    assert wound.type.value == "STATUS"
    assert wound.cost == -2
    assert wound not in pool

    # Wild Strike references wound
    ws = registry.get_card("wild_strike")
    assert ws is not None
    assert ws.actions[1].card_id == "wound"

    # Exhaust flag
    warcry = registry.get_card("warcry")
    assert warcry is not None
    assert warcry.exhaust is True

    # Power cards
    inflame = registry.get_card("inflame")
    assert inflame.type.value == "POWER"
    metallicize = registry.get_card("metallicize")
    assert metallicize.type.value == "POWER"

    print("ALL VALIDATION PASSED")


if __name__ == "__main__":
    test_load_all()
