"""Heuristic evaluation function (imperfect real-time decisions).

Search cannot reach the end of a 16-raid match, so at the depth cutoff we
estimate how good the position is for Team A (positive = good for A).
"""
from __future__ import annotations

import math

from ai.pathing import safe_return_cost
from game.rules import TERMINAL, UTILITY, score_diff
from game.state import BREATH, TEAM_A, GameState

# Weights. The brief's starting values were W_GAIN = 4, W_RISK = 2. Self-play
# tuning (experiments/tune_weights.py) showed that a bolder raider wins more:
# gain 8 / risk 1 beat 4 / 2 in 90% of 48 games at depth 3 and 69% at depth 4
# (depth 2: no difference). See README "Weight tuning".
W_SCORE = 10        # one point on the scoreboard
W_PLAYERS = 3       # one extra player on the court
W_GAIN = 8          # one defender tagged in the current raid
W_RISK = 1          # one defender next to the raider / one move short of breath
NO_PATH_COST = 20   # return cost when the raider is walled in


def evaluate(s: GameState, gain_weight: float = W_GAIN, risk_weight: float = W_RISK) -> float:
    """EVAL(s) from Team A's point of view.

    v = 10 * (scoreA - scoreB) + 3 * (in-players A - in-players B)
    during a raid (sign = +1 if A attacks, -1 if B attacks):
        gain = W_GAIN * tagged
        risk = W_RISK * (adjacent defenders + 2 * max(0, A*-return-cost - breath)
                         + (6 - breath) on a do-or-die raid with no tag yet)
        v   += sign * (gain - risk)
    """
    if TERMINAL(s):
        return W_SCORE * UTILITY(s)
    v = W_SCORE * score_diff(s) + W_PLAYERS * (s.in_count(0) - s.in_count(1))
    if s.phase != "pick":
        sign = 1 if s.attacker == TEAM_A else -1
        cost, _ = safe_return_cost(s)
        if math.isinf(cost):
            cost = NO_PATH_COST
        adjacent = len(s.adjacent_defenders(s.raider_cell()))
        gain = gain_weight * len(s.tagged)
        risk = risk_weight * adjacent + 2 * risk_weight * max(0, cost - s.breath)
        if s.dod and not s.tagged:
            # do-or-die without a tag ends in a lost point: pressure grows as breath runs out
            risk += risk_weight * (BREATH - s.breath)
        v += sign * (gain - risk)
    return v
