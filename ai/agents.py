"""Agents: anything that can choose an action for a state.

    HumanAgent         - the UI / console asks the person instead
    RandomAgent        - uniform random legal action (baseline)
    MinimaxAgent       - depth-limited Alpha-Beta with the heuristic evaluation
    MCTSAgent          - Monte Carlo Tree Search with UCB1
    FuzzyMinimaxAgent  - Alpha-Beta whose evaluation weights come from fuzzy logic
"""
from __future__ import annotations

import random
import time
from typing import Optional

from ai.evaluation import W_GAIN, W_RISK, evaluate
from ai.minimax import SearchStats, alpha_beta
from game.rules import ACTIONS, PLAYER, Action, describe_action
from game.state import TEAM_A, GameState

DIFFICULTY = {
    "minimax": {"easy": 2, "medium": 3, "hard": 4},
    "fuzzy": {"easy": 2, "medium": 3, "hard": 4},
    "mcts": {"easy": 300, "medium": 800, "hard": 2000},
}


class Agent:
    name = "agent"
    is_human = False

    def __init__(self) -> None:
        self.last_nodes = 0       # nodes searched for the last decision
        self.last_time = 0.0      # seconds used for the last decision
        # what the agent "thought" about its last decision, for the UI:
        # {"title", "detail", "moves": [(text, value text, chosen?) ...]}
        self.last_analysis = None

    def choose_action(self, state: GameState) -> Action:
        raise NotImplementedError


class HumanAgent(Agent):
    name = "Human"
    is_human = True


class RandomAgent(Agent):
    def __init__(self, seed: Optional[int] = None):
        super().__init__()
        self.rng = random.Random(seed)
        self.name = "Random"

    def choose_action(self, state):
        action = self.rng.choice(ACTIONS(state))
        self.last_analysis = {"title": self.name, "detail": "picks a uniformly random legal action",
                              "moves": [(describe_action(state, action), "random", True)]}
        return action


class MinimaxAgent(Agent):
    def __init__(self, depth: int = 3, ordering: bool = True, seed: Optional[int] = None,
                 gain_weight: float = W_GAIN, risk_weight: float = W_RISK):
        super().__init__()
        self.depth = depth
        self.ordering = ordering
        self.gain_weight, self.risk_weight = gain_weight, risk_weight
        self.rng = random.Random(seed)
        self.name = f"Minimax d{depth}" + ("" if ordering else " (no ordering)")

    def eval_fn(self, state: GameState):
        """Evaluation used at the depth cutoff (weights can be changed for tuning)."""
        if (self.gain_weight, self.risk_weight) == (W_GAIN, W_RISK):
            return evaluate
        g, r = self.gain_weight, self.risk_weight
        return lambda s: evaluate(s, g, r)

    def choose_action(self, state):
        t0 = time.perf_counter()
        actions = ACTIONS(state)
        if len(actions) == 1:                   # forced move: no search needed
            self.last_nodes, self.last_time = 0, time.perf_counter() - t0
            self.last_analysis = _forced(self.name, state, actions[0])
            return actions[0]
        stats = SearchStats()
        _, action = alpha_beta(state, self.depth, self.eval_fn(state), self.ordering,
                               stats, rng=self.rng)
        self.last_nodes, self.last_time = stats.nodes, time.perf_counter() - t0
        self.last_analysis = self._analysis(state, action, stats)
        return action

    def _analysis(self, state, action, stats):
        """Top root moves, with values shown from the mover's point of view."""
        sign = 1 if PLAYER(state) == TEAM_A else -1
        rows = []
        for a, v, exact in stats.root:
            v = v * sign
            rows.append((a == action, exact, v, a))
        rows.sort(key=lambda r: (not r[0], -r[2]))          # chosen move first
        moves = [(describe_action(state, a), f"{v:+.1f}" if exact else f"≤ {v:+.1f}", chosen)
                 for chosen, exact, v, a in rows[:3]]
        fuzzy = f" · aggression {self.last_aggression:.2f}" if hasattr(self, "last_aggression") else ""
        return {"title": f"{self.name} · Alpha-Beta{fuzzy}",
                "detail": f"{stats.nodes:,} nodes · {stats.prunes:,} prunes · {self.last_time * 1000:.0f} ms",
                "moves": moves}


class FuzzyMinimaxAgent(MinimaxAgent):
    """Alpha-Beta + a Mamdani fuzzy system that sets the raider's risk appetite.

    gain_weight = W_GAIN * (0.5 + aggression), risk_weight = W_RISK * (1.5 - aggression)
    (the brief's 4 and 2 are the untuned W_GAIN / W_RISK). With aggression 0.5
    this is exactly the normal evaluation. When this agent
    is defending it uses the neutral 0.5.
    """

    def __init__(self, depth: int = 3, seed: Optional[int] = None):
        super().__init__(depth, True, seed)
        self.name = f"Fuzzy Minimax d{depth}"
        self.last_aggression = 0.5

    def eval_fn(self, state):
        from ai.fuzzy import state_aggression
        agg = state_aggression(state) if PLAYER(state) == state.attacker else 0.5
        self.last_aggression = agg
        gain_w = W_GAIN * (0.5 + agg)
        risk_w = W_RISK * (1.5 - agg)
        return lambda s: evaluate(s, gain_w, risk_w)


class MCTSAgent(Agent):
    def __init__(self, iterations: int = 800, seed: Optional[int] = None,
                 horizon: int = 2, c: float = 1.4, policy: str = "heuristic"):
        super().__init__()
        self.policy = policy
        self.iterations = iterations
        self.horizon = horizon
        self.c = c
        self.rng = random.Random(seed)
        self.name = f"MCTS {iterations}" + (" (random playouts)" if policy == "random" else "")

    def choose_action(self, state):
        from ai.mcts import mcts
        t0 = time.perf_counter()
        actions = ACTIONS(state)
        if len(actions) == 1:
            self.last_nodes, self.last_time = 0, time.perf_counter() - t0
            self.last_analysis = _forced(self.name, state, actions[0])
            return actions[0]
        action, root = mcts(state, self.iterations, self.c, self.horizon, self.rng, self.policy)
        self.last_nodes, self.last_time = self.iterations, time.perf_counter() - t0
        kids = sorted(root.children, key=lambda ch: ch.visits, reverse=True)[:3]
        self.last_analysis = {
            "title": f"{self.name} · UCB1 tree search",
            "detail": f"{self.iterations:,} playouts · {self.last_time * 1000:.0f} ms · most-visited move wins",
            "moves": [(describe_action(state, ch.action),
                       f"{ch.visits} visits · {100 * ch.wins / max(1, ch.visits):.0f}%", ch.action == action)
                      for ch in kids]}
        return action


def _forced(name, state, action):
    return {"title": name, "detail": "only one legal action (no search needed)",
            "moves": [(describe_action(state, action), "forced", True)]}


def make_agent(spec: str, seed: Optional[int] = None) -> Agent:
    """Build an agent from a short spec.

    Examples: 'random', 'minimax:3', 'minimax:hard', 'minimax-noorder:3',
              'mcts:800', 'mcts:easy', 'mcts-random:800', 'fuzzy:3', 'human'.
    """
    kind, _, arg = spec.lower().partition(":")
    if kind == "human":
        return HumanAgent()
    if kind == "random":
        return RandomAgent(seed)
    base = kind.replace("-noorder", "").replace("-random", "")
    if base in DIFFICULTY and arg in DIFFICULTY[base]:
        arg = str(DIFFICULTY[base][arg])
    if kind == "minimax":
        return MinimaxAgent(int(arg or 3), True, seed)
    if kind == "minimax-noorder":
        return MinimaxAgent(int(arg or 3), False, seed)
    if kind == "fuzzy":
        return FuzzyMinimaxAgent(int(arg or 3), seed)
    if kind == "mcts":
        return MCTSAgent(int(arg or 800), seed)
    if kind == "mcts-random":
        return MCTSAgent(int(arg or 800), seed, policy="random")
    raise ValueError(f"unknown agent spec: {spec!r}")
