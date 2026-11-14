"""Tests for MCTS, the agents and a full headless AI-vs-AI match."""
import random

import pytest

from ai.agents import FuzzyMinimaxAgent, MCTSAgent, MinimaxAgent, RandomAgent, make_agent
from ai.mcts import mcts, playout
from experiments.tournament import play_match
from game.rules import ACTIONS, RESULT, TERMINAL
from game.state import initial_state


def test_mcts_returns_legal_action_and_counts_visits():
    s = RESULT(initial_state(), ("pick", 1))
    action, root = mcts(s, iterations=200, rng=random.Random(1))
    assert action in ACTIONS(s)
    assert root.visits == 200
    assert sum(ch.visits for ch in root.children) == 200


def test_mcts_is_reproducible_with_seed():
    s = initial_state()
    a1, _ = mcts(s, 150, rng=random.Random(5))
    a2, _ = mcts(s, 150, rng=random.Random(5))
    assert a1 == a2


@pytest.mark.parametrize("policy", ["random", "heuristic"])
def test_playout_reward_in_range(policy):
    rng = random.Random(2)
    s = initial_state()
    for _ in range(50):
        r = playout(s, rng, horizon=2, policy=policy)
        assert 0.0 <= r <= 1.0


def test_playout_horizon_stops_early():
    """A playout from raid 0 with horizon 2 stops after raid 3 (not at the end)."""
    import ai.mcts as m
    seen = []
    orig = m.RESULT

    def spy(s, a):
        ns = orig(s, a)
        seen.append(ns.raid)
        return ns
    m.RESULT = spy
    try:
        m.playout(initial_state(), random.Random(1), horizon=2)
    finally:
        m.RESULT = orig
    assert max(seen) == 3


def test_make_agent_specs():
    assert isinstance(make_agent("minimax:hard"), MinimaxAgent)
    assert make_agent("minimax:hard").depth == 4
    assert make_agent("mcts:easy").iterations == 300
    assert make_agent("mcts-random:100").policy == "random"
    assert isinstance(make_agent("fuzzy:2"), FuzzyMinimaxAgent)
    assert not make_agent("minimax-noorder:3").ordering
    assert make_agent("human").is_human
    with pytest.raises(ValueError):
        make_agent("chess:9")


def test_agents_choose_legal_actions():
    rng = random.Random(4)
    agents = [RandomAgent(1), MinimaxAgent(2, seed=1), FuzzyMinimaxAgent(2, seed=1), MCTSAgent(60, seed=1)]
    s = initial_state()
    for _ in range(60):
        if TERMINAL(s):
            break
        for ag in agents:
            assert ag.choose_action(s) in ACTIONS(s)
        s = RESULT(s, rng.choice(ACTIONS(s)))


def test_full_ai_vs_ai_match_runs():
    r = play_match({0: MinimaxAgent(2, seed=1), 1: MCTSAgent(60, seed=2)}, first=1, komi=1)
    assert r.plies > 0
    assert r.diff == r.score[0] - r.score[1] - 1
