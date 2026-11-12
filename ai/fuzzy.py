"""Hand-written Mamdani fuzzy inference system: the raider's risk appetite.

Same steps as the tipping example from the lab:
    1. FUZZIFICATION   crisp inputs -> membership degrees
    2. RULE EVALUATION AND = min, rule strength clips the output set
    3. AGGREGATION     max of all clipped output sets
    4. DEFUZZIFICATION centroid of the aggregated set (sampled)

Inputs : breath_left (0-6), defenders_near (0-5), score_gap (-8..8), do_or_die (0/1)
Output : aggression (0-1)   cautious / balanced / daring
"""
from __future__ import annotations

from game.state import GameState, chebyshev


# ----------------------------------------------------------------------
# Membership functions
# ----------------------------------------------------------------------
def trimf(x: float, a: float, b: float, c: float) -> float:
    """Triangle with feet a, c and peak b."""
    if x <= a or x >= c:
        return 1.0 if x == b else 0.0
    return (x - a) / (b - a) if x <= b else (c - x) / (c - b)


def trapmf(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoid: rises a->b, flat b->c, falls c->d."""
    if x < a or x > d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if x < b:
        return (x - a) / (b - a)
    return (d - x) / (d - c)


BREATH = {
    "low":    lambda x: trapmf(x, -1, 0, 1, 3),
    "medium": lambda x: trimf(x, 1, 3, 5),
    "high":   lambda x: trapmf(x, 3, 5, 6, 7),
}
NEAR = {
    "few":  lambda x: trapmf(x, -1, 0, 0.5, 2),
    "some": lambda x: trimf(x, 1, 2, 3),
    "many": lambda x: trapmf(x, 2, 3.5, 5, 6),
}
GAP = {
    "behind": lambda x: trapmf(x, -9, -8, -3, 0),
    "even":   lambda x: trimf(x, -2, 0, 2),
    "ahead":  lambda x: trapmf(x, 0, 3, 8, 9),
}
AGGRESSION = {
    "cautious": lambda y: trapmf(y, -0.1, 0.0, 0.15, 0.45),
    "balanced": lambda y: trimf(y, 0.25, 0.5, 0.75),
    "daring":   lambda y: trapmf(y, 0.55, 0.85, 1.0, 1.1),
}

# ----------------------------------------------------------------------
# Rule base: (antecedents, consequent). Antecedents are ANDed (min).
# ----------------------------------------------------------------------
RULES = [
    ({"breath": "low", "near": "many"}, "cautious"),
    ({"breath": "low", "near": "some"}, "cautious"),
    ({"breath": "low", "near": "few"}, "balanced"),
    ({"breath": "medium", "near": "many"}, "cautious"),
    ({"breath": "medium", "near": "some"}, "balanced"),
    ({"breath": "medium", "near": "few"}, "daring"),
    ({"breath": "high", "near": "few"}, "daring"),
    ({"breath": "high", "near": "some"}, "balanced"),
    ({"gap": "behind", "breath": "high"}, "daring"),
    ({"gap": "behind", "breath": "medium"}, "balanced"),
    ({"gap": "ahead"}, "cautious"),
    ({"dod": "yes"}, "daring"),
]


def fuzzify(breath: float, near: float, gap: float, dod: bool) -> dict:
    """Step 1: degree of membership of each crisp input in each fuzzy set."""
    return {
        "breath": {k: f(breath) for k, f in BREATH.items()},
        "near": {k: f(near) for k, f in NEAR.items()},
        "gap": {k: f(max(-8, min(8, gap))) for k, f in GAP.items()},
        "dod": {"yes": 1.0 if dod else 0.0},
    }


def aggression(breath: float, near: float, gap: float, dod: bool = False,
               samples: int = 101) -> float:
    """Run the whole Mamdani pipeline and return a crisp aggression in [0, 1]."""
    memb = fuzzify(breath, near, gap, dod)

    # Step 2: rule strength = min of its antecedents (fuzzy AND)
    strength = {name: 0.0 for name in AGGRESSION}
    for antecedents, consequent in RULES:
        w = min(memb[var][term] for var, term in antecedents.items())
        strength[consequent] = max(strength[consequent], w)   # several rules -> max

    # Step 3 + 4: aggregate clipped output sets with max, then centroid
    num = den = 0.0
    for k in range(samples):
        y = k / (samples - 1)
        mu = max(min(strength[name], f(y)) for name, f in AGGRESSION.items())
        num += y * mu
        den += mu
    return num / den if den > 0 else 0.5


def state_inputs(s: GameState) -> tuple[float, int, float, bool]:
    """Crisp inputs for the attacking team in state ``s``.

    Before a raider is picked we use full breath and no nearby defenders.
    """
    a = s.attacker
    gap = s.score[a] - s.score[1 - a]
    dod = s.dod or (s.phase == "pick" and s.empty[a] >= 2)
    cell = s.raider_cell()
    if cell is None:
        return 6, 0, gap, dod
    near = sum(1 for p in s.pos[s.defender] if p is not None and chebyshev(p, cell) <= 2)
    return s.breath, near, gap, dod


def state_aggression(s: GameState) -> float:
    return aggression(*state_inputs(s))
