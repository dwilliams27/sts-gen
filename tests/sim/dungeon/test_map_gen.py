"""Tests for Act 1 map generation."""

import pytest

from sts_gen.sim.core.rng import GameRNG
from sts_gen.sim.dungeon.map_gen import MapGenerator, MapNode


class TestMapGenerator:
    def test_generates_16_floors(self):
        mg = MapGenerator()
        nodes = mg.generate_act_1(GameRNG(seed=42))
        assert len(nodes) == 16

    def test_floor_numbers_sequential(self):
        mg = MapGenerator()
        nodes = mg.generate_act_1(GameRNG(seed=42))
        assert [n.floor for n in nodes] == list(range(1, 17))

    def test_floor_1_always_monster(self):
        mg = MapGenerator()
        for seed in range(100):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            assert nodes[0].node_type == "monster", f"seed={seed}"

    def test_floor_9_always_treasure(self):
        mg = MapGenerator()
        for seed in range(100):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            assert nodes[8].node_type == "treasure", f"seed={seed}"

    def test_floor_15_always_rest(self):
        mg = MapGenerator()
        for seed in range(100):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            assert nodes[14].node_type == "rest", f"seed={seed}"

    def test_floor_16_always_boss(self):
        mg = MapGenerator()
        for seed in range(100):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            assert nodes[15].node_type == "boss", f"seed={seed}"

    def test_no_elites_before_floor_6(self):
        mg = MapGenerator()
        for seed in range(200):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            for node in nodes[:5]:  # floors 1-5
                assert node.node_type != "elite", (
                    f"seed={seed}, floor={node.floor}"
                )

    def test_no_rests_before_floor_6(self):
        mg = MapGenerator()
        for seed in range(200):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            for node in nodes[:5]:  # floors 1-5
                assert node.node_type != "rest", (
                    f"seed={seed}, floor={node.floor}"
                )

    def test_no_consecutive_same_restricted_type(self):
        """No consecutive elite/rest/shop."""
        mg = MapGenerator()
        restricted = {"elite", "rest", "shop"}
        for seed in range(200):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            for i in range(1, len(nodes)):
                if nodes[i].node_type in restricted:
                    assert nodes[i].node_type != nodes[i - 1].node_type, (
                        f"seed={seed}, floor={nodes[i].floor}, "
                        f"consecutive {nodes[i].node_type}"
                    )

    def test_different_seeds_produce_different_maps(self):
        mg = MapGenerator()
        maps = set()
        for seed in range(50):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            key = tuple(n.node_type for n in nodes)
            maps.add(key)
        # With 50 seeds, we should see multiple distinct maps
        assert len(maps) > 5

    def test_valid_node_types(self):
        valid = {"monster", "elite", "rest", "shop", "event", "treasure", "boss"}
        mg = MapGenerator()
        for seed in range(50):
            nodes = mg.generate_act_1(GameRNG(seed=seed))
            for node in nodes:
                assert node.node_type in valid, (
                    f"Invalid type {node.node_type!r} at floor {node.floor}"
                )

    def test_deterministic_with_same_seed(self):
        mg = MapGenerator()
        nodes1 = mg.generate_act_1(GameRNG(seed=123))
        nodes2 = mg.generate_act_1(GameRNG(seed=123))
        types1 = [n.node_type for n in nodes1]
        types2 = [n.node_type for n in nodes2]
        assert types1 == types2
