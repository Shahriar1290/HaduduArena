"""Tests for pathing (A*/BFS), evaluation, Minimax and Alpha-Beta."""
import math
import random

import pytest

from ai.evaluation import evaluate
from ai.minimax import MINIMAX, SearchStats, alpha_beta
from ai.pathing import bfs_return_path, intercept_distance, path_cost, safe_return_cost
from game.rules import ACTIONS, RESULT, TERMINAL
from game.state import NEIGHBOURS, initial_state, in_half


def random_mid_raid_states(n, seed):
    """Collect states in the middle of a raid by playing random actions."""
    rng = random.Random(seed)
    states = []
    while len(states) < n:
        s = initial_state(first=rng.randrange(2))
        stop_at = rng.randrange(5, 120)
        k = 0
        while not TERMINAL(s) and k < stop_at:
            s = RESULT(s, rng.choice(ACTIONS(s)))
            k += 1
        if not TERMINAL(s) and s.phase != "pick":
            states.append(s)
    return states


# ---------------------------------------------------------------- A* / BFS
def test_astar_not_worse_than_penalised_bfs_path():
    for s in random_mid_raid_states(60, seed=11):
        cost, path = safe_return_cost(s)
        bfs = bfs_return_path(s)
        if not bfs:
            assert math.isinf(cost)
            continue
        assert cost <= path_cost(s, bfs)
        assert cost == path_cost(s, path)


def test_astar_path_is_valid():
    for s in random_mid_raid_states(60, seed=12):
        cost, path = safe_return_cost(s)
        if math.isinf(cost):
            continue
        occupied = s.occupied() - {s.raider_cell()}
        assert path[0] == s.raider_cell()
        assert in_half(s.attacker, path[-1])
        for a, b in zip(path, path[1:]):
            assert b in NEIGHBOURS[a]          # legal king move
            assert b not in occupied           # never through an occupied cell


def test_astar_zero_when_home():
    s = RESULT(initial_state(), ("pick", 1))
    assert safe_return_cost(s) == (0, [(1, 3)])


def test_intercept_distance():
    s = RESULT(initial_state(), ("pick", 1))      # raider (1,3); B has (1,4) next to him
    dist = intercept_distance(s)
    assert dist[1] == 0                             # B#2 at (1,4) is adjacent
    assert all(d >= 0 for d in dist.values())


# ---------------------------------------------------------------- evaluation
def test_evaluation_symmetry_at_start():
    assert evaluate(initial_state()) == 0


def test_evaluation_rewards_tags():
    s = RESULT(initial_state(), ("pick", 1))
    s_tag = s._replace(pos=(s.pos[0][:1] + ((1, 5),) + s.pos[0][2:], s.pos[1]), crossed=True)
    v0 = evaluate(s_tag)
    v1 = evaluate(s_tag._replace(tagged=(1,)))
    assert v1 > v0


# ---------------------------------------------------------------- Minimax / Alpha-Beta
@pytest.mark.parametrize("ordering", [True, False])
def test_alpha_beta_equals_minimax(ordering):
    for s in random_mid_raid_states(20, seed=21):
        v_mm, _ = MINIMAX(s, 2)
        v_ab, _ = alpha_beta(s, 2, ordering=ordering)
        assert v_mm == pytest.approx(v_ab)


def test_alpha_beta_depth3_equals_minimax_and_prunes():
    for s in random_mid_raid_states(5, seed=22):
        st_mm, st_ab = SearchStats(), SearchStats()
        v_mm, _ = MINIMAX(s, 3, stats=st_mm)
        v_ab, _ = alpha_beta(s, 3, stats=st_ab)
        assert v_mm == pytest.approx(v_ab)
        assert st_ab.nodes <= st_mm.nodes


def test_alpha_beta_returns_legal_action():
    for s in random_mid_raid_states(10, seed=23):
        _, a = alpha_beta(s, 3)
        assert a in ACTIONS(s)


def test_raider_takes_the_tackle_free_success():
    """Raider with a tag, one step from home and no danger should go home."""
    s = RESULT(initial_state(), ("pick", 1))
    pos_a = s.pos[0][:1] + ((2, 4),) + s.pos[0][2:]
    s = s._replace(pos=(pos_a, ((0, 7), (5, 7), (3, 7), (4, 7), (2, 5))),
                   crossed=True, tagged=(4,), breath=2)
    _, a = alpha_beta(s, 3)
    assert a[0] == "step" and in_half(0, a[1])
