"""Monte Carlo Tree Search with UCB1.

Each iteration has the four standard steps:
    1. SELECTION       walk down the tree, choosing children with UCB1
    2. EXPANSION       add one new child for an untried action
    3. SIMULATION      play fast (random or lightly guided) actions for a
                       few raids: a "playout"
    4. BACKPROPAGATION add the playout reward to every node on the path

A node's ``wins`` are counted for the team that made the move INTO that node,
so during selection each team picks the child that is best for itself.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from game.rules import ACTIONS, PLAYER, RESULT, TERMINAL, Action, score_diff
from ai.pathing import columns_to_home
from game.state import TEAM_A, GameState, chebyshev, in_half


class Node:
    __slots__ = ("state", "parent", "action", "mover", "children", "untried", "visits", "wins")

    def __init__(self, state: GameState, parent: Optional["Node"] = None,
                 action: Optional[Action] = None, rng: Optional[random.Random] = None):
        self.state = state
        self.parent = parent
        self.action = action
        self.mover = PLAYER(parent.state) if parent else None   # team that chose ``action``
        self.children: list[Node] = []
        self.untried = ACTIONS(state)
        if rng is not None:
            rng.shuffle(self.untried)
        self.visits = 0
        self.wins = 0.0

    def ucb1(self, c: float) -> float:
        """UCB1 = exploitation (average reward) + exploration bonus."""
        return (self.wins / self.visits
                + c * math.sqrt(math.log(self.parent.visits) / self.visits))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def rollout_action(s: GameState, rng: random.Random) -> Action:
    """Fast 'heavy playout' policy: random, but with a little Kabaddi sense.

    Pure random players almost never tackle and rarely bring tags home, so
    playouts would say little about real play. This policy:
      - defenders: always take a move that completes a tackle; otherwise half
        the time move a defender closer to the raider
      - raider: with tags after crossing, usually step toward home;
        otherwise usually touch when possible
    Everything else is a uniform random choice.
    """
    actions = ACTIONS(s)
    if s.phase == "pick":
        return rng.choice(actions)
    raider = s.raider_cell()
    if s.phase == "defender":
        near_now = sum(1 for p in s.pos[s.defender] if p is not None and chebyshev(p, raider) == 1)
        closer = []
        for a in actions:
            if a[0] != "move":
                continue
            old, new = s.pos[s.defender][a[1]], a[2]
            if chebyshev(new, raider) == 1 and chebyshev(old, raider) > 1:
                if near_now + 1 >= 3 and not in_half(s.attacker, raider):
                    return a                                   # completes a tackle
                closer.append(a)
            elif chebyshev(new, raider) < chebyshev(old, raider):
                closer.append(a)
        if closer and rng.random() < 0.5:
            return rng.choice(closer)
        return rng.choice(actions)
    # raider
    if s.tagged and rng.random() < 0.8:
        home = columns_to_home(s.attacker, raider)
        homeward = [a for a in actions if a[0] == "step" and columns_to_home(s.attacker, a[1]) < home]
        if homeward:
            return rng.choice(homeward)
    if ("touch",) in actions and rng.random() < 0.8:
        return ("touch",)
    return rng.choice(actions)


def playout(state: GameState, rng: random.Random, horizon: int = 2,
            policy: str = "heuristic") -> float:
    """SIMULATION step: play until the current raid and ``horizon`` more raids
    are finished (or the match ends), using the random or heuristic policy.

    Returns a reward for Team A in [0, 1]: sigmoid((scoreA - scoreB) / 2).
    """
    stop_raid = state.raid + 1 + horizon
    s = state
    while not TERMINAL(s) and s.raid < stop_raid:
        if policy == "random":
            s = RESULT(s, rng.choice(ACTIONS(s)))
        else:
            s = RESULT(s, rollout_action(s, rng))
    return sigmoid(score_diff(s) / 2)


def mcts(root_state: GameState, iterations: int = 800, c: float = 1.4, horizon: int = 2,
         rng: Optional[random.Random] = None, policy: str = "heuristic") -> tuple[Action, Node]:
    """Run MCTS from ``root_state``; return (most visited action, root node)."""
    rng = rng or random.Random()
    root = Node(root_state, rng=rng)
    for _ in range(iterations):
        node = root
        # 1. SELECTION: fully expanded nodes -> follow the best UCB1 child
        while not node.untried and node.children:
            node = max(node.children, key=lambda ch: ch.ucb1(c))
        # 2. EXPANSION: add one child for an action not tried yet
        if node.untried and not TERMINAL(node.state):
            action = node.untried.pop()
            child = Node(RESULT(node.state, action), parent=node, action=action, rng=rng)
            node.children.append(child)
            node = child
        # 3. SIMULATION
        reward_a = playout(node.state, rng, horizon, policy)
        # 4. BACKPROPAGATION: reward seen from the team that moved into each node
        while node is not None:
            node.visits += 1
            if node.mover is not None:
                node.wins += reward_a if node.mover == TEAM_A else 1.0 - reward_a
            node = node.parent
    best = max(root.children, key=lambda ch: ch.visits)   # robust child
    return best.action, root
