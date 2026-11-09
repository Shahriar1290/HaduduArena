"""Minimax and depth-limited Alpha-Beta search.

Team A is MAX, Team B is MIN. Values are always from Team A's point of view.

In Tic-Tac-Toe MAX and MIN take turns, so MAX_VALUE calls MIN_VALUE directly.
In Hadudu the same team can act twice in a row (pick, then the first raider
step), so after every action we ask PLAYER(s') whose turn it is and call
MAX_VALUE or MIN_VALUE accordingly (the helper VALUE does this).

A ply = one single action. At the depth cutoff we call EVAL(s): this is the
"imperfect real-time decision" from the lecture (cutoff test + evaluation).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from ai.evaluation import evaluate
from game.rules import ACTIONS, PLAYER, RESULT, TERMINAL, Action
from game.state import TEAM_A, GameState, chebyshev, in_half

EvalFn = Callable[[GameState], float]


@dataclass
class SearchStats:
    nodes: int = 0     # states visited
    prunes: int = 0    # alpha/beta cut-offs
    # root moves as (action, value, exact). With pruning only a move that becomes
    # the new best gets an exact value; the others are bounds ("no better than").
    root: list = field(default_factory=list)


# ======================================================================
# Plain MINIMAX (exactly like the lab, plus a depth limit)
# ======================================================================
def MINIMAX(state: GameState, depth: int, eval_fn: EvalFn = evaluate,
            stats: Optional[SearchStats] = None) -> tuple[float, Optional[Action]]:
    """Return (value, best action) for the player to move, searching ``depth`` plies."""
    stats = stats if stats is not None else SearchStats()
    best_action = None
    if PLAYER(state) == TEAM_A:                      # MAX picks the largest value
        best = -math.inf
        for a in ACTIONS(state):
            v = VALUE(RESULT(state, a), depth - 1, eval_fn, stats)
            if v > best:
                best, best_action = v, a
    else:                                            # MIN picks the smallest value
        best = math.inf
        for a in ACTIONS(state):
            v = VALUE(RESULT(state, a), depth - 1, eval_fn, stats)
            if v < best:
                best, best_action = v, a
    return best, best_action


def VALUE(state, depth, eval_fn, stats) -> float:
    """Dispatch to MAX_VALUE or MIN_VALUE depending on PLAYER(state)."""
    if PLAYER(state) == TEAM_A:
        return MAX_VALUE(state, depth, eval_fn, stats)
    return MIN_VALUE(state, depth, eval_fn, stats)


def MAX_VALUE(state, depth, eval_fn, stats) -> float:
    stats.nodes += 1
    if TERMINAL(state) or depth == 0:                # cutoff test
        return eval_fn(state)
    v = -math.inf
    for a in ACTIONS(state):
        v = max(v, VALUE(RESULT(state, a), depth - 1, eval_fn, stats))
    return v


def MIN_VALUE(state, depth, eval_fn, stats) -> float:
    stats.nodes += 1
    if TERMINAL(state) or depth == 0:
        return eval_fn(state)
    v = math.inf
    for a in ACTIONS(state):
        v = min(v, VALUE(RESULT(state, a), depth - 1, eval_fn, stats))
    return v


# ======================================================================
# Alpha-Beta pruning
# ======================================================================
def alpha_beta(state: GameState, depth: int, eval_fn: EvalFn = evaluate,
               ordering: bool = True, stats: Optional[SearchStats] = None,
               rng: Optional[random.Random] = None) -> tuple[float, Optional[Action]]:
    """Depth-limited Alpha-Beta search. Returns (value, best action).

    alpha = best value MAX can already guarantee on this path
    beta  = best value MIN can already guarantee on this path
    A branch is pruned as soon as alpha >= beta.
    ``rng`` shuffles the root moves first so equal moves are broken randomly.
    """
    stats = stats if stats is not None else SearchStats()
    stats.nodes += 1
    actions = ACTIONS(state)
    if rng is not None:
        rng.shuffle(actions)
    if ordering:
        actions = order_actions(state, actions)
    maximizing = PLAYER(state) == TEAM_A
    alpha, beta = -math.inf, math.inf
    best_value = -math.inf if maximizing else math.inf
    best_action = actions[0] if actions else None
    for a in actions:
        v = _ab_value(RESULT(state, a), depth - 1, alpha, beta, eval_fn, ordering, stats)
        improves = v > best_value if maximizing else v < best_value
        stats.root.append((a, v, improves))
        if maximizing and v > best_value:
            best_value, best_action = v, a
            alpha = max(alpha, v)
        elif not maximizing and v < best_value:
            best_value, best_action = v, a
            beta = min(beta, v)
    return best_value, best_action


def _ab_value(state, depth, alpha, beta, eval_fn, ordering, stats) -> float:
    if PLAYER(state) == TEAM_A:
        return AB_MAX_VALUE(state, depth, alpha, beta, eval_fn, ordering, stats)
    return AB_MIN_VALUE(state, depth, alpha, beta, eval_fn, ordering, stats)


def AB_MAX_VALUE(state, depth, alpha, beta, eval_fn, ordering, stats) -> float:
    stats.nodes += 1
    if TERMINAL(state) or depth == 0:
        return eval_fn(state)                 # evaluation at the depth cutoff
    v = -math.inf
    actions = ACTIONS(state)
    for a in (order_actions(state, actions) if ordering else actions):
        v = max(v, _ab_value(RESULT(state, a), depth - 1, alpha, beta, eval_fn, ordering, stats))
        if v >= beta:                         # MIN will never allow this branch
            stats.prunes += 1
            return v
        alpha = max(alpha, v)
    return v


def AB_MIN_VALUE(state, depth, alpha, beta, eval_fn, ordering, stats) -> float:
    stats.nodes += 1
    if TERMINAL(state) or depth == 0:
        return eval_fn(state)
    v = math.inf
    actions = ACTIONS(state)
    for a in (order_actions(state, actions) if ordering else actions):
        v = min(v, _ab_value(RESULT(state, a), depth - 1, alpha, beta, eval_fn, ordering, stats))
        if v <= alpha:                        # MAX will never allow this branch
            stats.prunes += 1
            return v
        beta = min(beta, v)
    return v


# ======================================================================
# Move ordering: good moves first -> more cut-offs
# ======================================================================
def order_actions(s: GameState, actions: list[Action]) -> list[Action]:
    """Raider: touch first, then (low breath) steps toward home, then the rest.
    Defender: moves that complete a tackle first, then moves toward the raider."""
    if s.phase == "pick":
        return actions
    raider = s.raider_cell()
    if s.phase == "raider":
        a = s.attacker
        low_breath = s.breath <= 3
        targets = [p for i, p in enumerate(s.pos[s.defender]) if p is not None and i not in s.tagged]

        def raider_key(act):
            if act[0] == "touch":
                return (0, 0)
            if act[0] == "stop":
                return (3, 0)
            cell = act[1]
            if low_breath:      # head for the centre line
                return (1, abs(cell[1] - (3 if a == 0 else 4)) if not in_half(a, cell) else -1)
            near = min((chebyshev(cell, p) for p in targets), default=9)
            return (2, near)    # otherwise: get close to an untagged defender
        return sorted(actions, key=raider_key)

    attackers_half = s.attacker

    def defender_key(act):
        if act[0] == "hold":
            return (2, 0)
        cell = act[2]
        dist = chebyshev(cell, raider)
        if dist == 1 and not in_half(attackers_half, raider):
            others = sum(1 for j, p in enumerate(s.pos[s.defender])
                         if p is not None and j != act[1] and chebyshev(p, raider) == 1)
            if others + 1 >= 3:
                return (0, 0)   # this move completes a tackle
        return (1, dist)
    return sorted(actions, key=defender_key)
