"""Tests for the fuzzy risk-appetite system and the CSP formation generator."""
import itertools

from ai.formation_csp import (generate_formation, satisfies_hard_constraints, soft_penalty,
                              solve, uncovered_rows)
from ai.fuzzy import aggression, state_aggression
from game.rules import ACTIONS, RESULT, TERMINAL
from game.state import CLASSIC_START_A, initial_state, mirror


# ---------------------------------------------------------------- fuzzy
def test_fuzzy_output_in_unit_interval():
    for b, n, g, d in itertools.product(range(7), range(6), range(-8, 9, 2), (False, True)):
        assert 0.0 <= aggression(b, n, g, d) <= 1.0


def test_fuzzy_daring_when_breath_high_and_behind():
    daring = aggression(breath=6, near=1, gap=-5)
    cautious = aggression(breath=1, near=4, gap=0)
    assert daring > 0.6
    assert cautious < 0.4
    assert daring > cautious


def test_fuzzy_higher_with_more_breath_and_when_behind():
    assert aggression(6, 2, -4) > aggression(2, 2, -4)
    assert aggression(4, 2, -6) > aggression(4, 2, 6)


def test_fuzzy_do_or_die_is_daring():
    assert aggression(3, 3, 0, dod=True) > aggression(3, 3, 0, dod=False)


def test_state_aggression_runs_on_states():
    s = initial_state()
    for a in [("pick", 1), ("step", (1, 4))]:
        if a in ACTIONS(s):
            s = RESULT(s, a)
        assert 0 <= state_aggression(s) <= 1


# ---------------------------------------------------------------- CSP
def test_classic_formation_is_valid():
    assert satisfies_hard_constraints(CLASSIC_START_A)


def test_hard_constraint_checker_catches_violations():
    assert not satisfies_hard_constraints([(0, 0), (1, 0), (2, 0), (3, 1), (5, 1)])  # 3 in col 0
    assert not satisfies_hard_constraints([(0, 0), (0, 1), (1, 2), (2, 3), (1, 0)])  # rows 4,5 uncovered
    assert not satisfies_hard_constraints([(0, 0), (0, 0), (2, 1), (4, 2), (5, 3)])  # duplicate
    assert not satisfies_hard_constraints([(0, 4), (1, 0), (2, 1), (4, 2), (5, 3)])  # wrong half


def test_every_generated_formation_satisfies_hard_constraints():
    for seed in range(150):
        cells = solve(seed)
        assert satisfies_hard_constraints(cells), cells
        assert not uncovered_rows(cells)


def test_generate_formation_low_penalty_and_seeded():
    for seed in range(40):
        f = generate_formation(seed)
        assert satisfies_hard_constraints(f)
        assert soft_penalty(f) == 0
    assert generate_formation(7) == generate_formation(7)
    assert len({generate_formation(s) for s in range(20)}) > 5     # real variety


def test_soft_penalty_counts():
    assert soft_penalty([(0, 0), (1, 1), (2, 0), (4, 1), (5, 0)]) == 2   # all back + none near centre
    assert soft_penalty([(0, 2), (0, 3), (2, 1), (4, 2), (5, 0)]) == 1   # one side-by-side pair


def test_csp_formation_plays_a_full_game():
    import random
    f = generate_formation(3)
    s = initial_state(formation_a=f)
    assert s.pos[1] == mirror(f)
    rng = random.Random(1)
    while not TERMINAL(s):
        s = RESULT(s, rng.choice(ACTIONS(s)))
