"""Constraint Satisfaction Problem: generate a defensive formation.

VARIABLES   D1..D5 = the cells of the 5 players (generated for Team A,
            then mirrored for Team B so the match stays fair)
DOMAINS     the 24 cells of Team A's half (columns 0-3)
HARD CONSTRAINTS
    1. all cells different                     (AllDiff)
    2. all cells in the team's own half        (built into the domain)
    3. every court row has a defender within 1 row of it   (row coverage)
    4. at most 2 defenders per column
SOFT CONSTRAINTS (each violation = 1 penalty point)
    a. all 5 players in the back two columns
    b. two players side by side in the same row (wasted coverage)
    c. no player within 2 columns of the centre line

Solved with BACKTRACKING SEARCH + MRV (minimum remaining values) variable
ordering + FORWARD CHECKING. Values are tried in a seeded random order, so
different seeds give different formations. We run the search a few times
and keep the solution with the fewest soft-constraint penalties.
"""
from __future__ import annotations

import random
from typing import Optional

from game.state import ROWS, Cell

N_PLAYERS = 5
HALF = [(r, c) for r in range(ROWS) for c in range(4)]   # Team A's half
BACK_COLS = (0, 1)
FRONT_COLS = (2, 3)        # within 2 columns of the centre line
MAX_PER_COLUMN = 2


# ----------------------------------------------------------------------
# Constraint checks
# ----------------------------------------------------------------------
def uncovered_rows(cells) -> list[int]:
    """Rows that have no defender within 1 row."""
    return [r for r in range(ROWS) if not any(abs(c[0] - r) <= 1 for c in cells)]


def min_players_to_cover(rows: list[int]) -> int:
    """Fewest players needed to cover these rows (each covers 3 consecutive
    rows). Greedy interval covering is optimal here."""
    count, covered_until = 0, -10
    for r in sorted(rows):
        if r > covered_until:
            count += 1
            covered_until = r + 2     # a player at row r+1 covers r, r+1, r+2
    return count


def satisfies_hard_constraints(cells) -> bool:
    cells = list(cells)
    return (len(cells) == N_PLAYERS
            and len(set(cells)) == N_PLAYERS                                   # 1
            and all(0 <= r < ROWS and 0 <= c < 4 for r, c in cells)           # 2
            and not uncovered_rows(cells)                                      # 3
            and all(sum(c[1] == col for c in cells) <= MAX_PER_COLUMN for col in range(4)))  # 4


def soft_penalty(cells) -> int:
    cells = list(cells)
    penalty = 0
    if all(c[1] in BACK_COLS for c in cells):                         # a
        penalty += 1
    for i in range(len(cells)):                                       # b
        for j in range(i + 1, len(cells)):
            if cells[i][0] == cells[j][0] and abs(cells[i][1] - cells[j][1]) == 1:
                penalty += 1
    if not any(c[1] in FRONT_COLS for c in cells):                    # c
        penalty += 1
    return penalty


# ----------------------------------------------------------------------
# Backtracking with MRV + forward checking
# ----------------------------------------------------------------------
def forward_check(assignment: dict[int, Cell], domains: dict[int, list[Cell]]):
    """Prune the domains of unassigned variables after the latest assignment.
    Returns the new domains, or None if some variable can no longer be filled
    (a dead end found early: that is the point of forward checking)."""
    used = set(assignment.values())
    full_cols = {col for col in range(4)
                 if sum(c[1] == col for c in assignment.values()) >= MAX_PER_COLUMN}
    new_domains = {}
    for var, dom in domains.items():
        if var in assignment:
            continue
        pruned = [c for c in dom if c not in used and c[1] not in full_cols]
        if not pruned:
            return None
        new_domains[var] = pruned
    # row coverage: the remaining players must still be able to cover all rows
    rows_left = uncovered_rows(assignment.values())
    if min_players_to_cover(rows_left) > len(new_domains):
        return None
    for r in rows_left:
        if not any(abs(c[0] - r) <= 1 for dom in new_domains.values() for c in dom):
            return None
    return new_domains


def backtrack(assignment: dict[int, Cell], domains: dict[int, list[Cell]],
              rng: random.Random, stats: dict) -> Optional[dict[int, Cell]]:
    if len(assignment) == N_PLAYERS:
        return assignment if satisfies_hard_constraints(assignment.values()) else None
    # MRV: choose the unassigned variable with the fewest legal values left
    var = min((v for v in domains if v not in assignment), key=lambda v: (len(domains[v]), v))
    values = domains[var][:]
    rng.shuffle(values)
    for value in values:
        stats["nodes"] += 1
        assignment[var] = value
        new_domains = forward_check(assignment, domains)
        if new_domains is not None:
            new_domains.update({v: [assignment[v]] for v in assignment})
            result = backtrack(assignment, new_domains, rng, stats)
            if result is not None:
                return result
        del assignment[var]
        stats["backtracks"] += 1
    return None


def solve(seed: Optional[int] = None, stats: Optional[dict] = None) -> tuple[Cell, ...]:
    """One run of the backtracking search: any formation meeting the hard constraints."""
    rng = random.Random(seed)
    stats = stats if stats is not None else {"nodes": 0, "backtracks": 0}
    domains = {v: HALF[:] for v in range(N_PLAYERS)}
    result = backtrack({}, domains, rng, stats)
    if result is None:
        raise RuntimeError("no formation satisfies the constraints")
    return tuple(sorted(result.values()))      # number players top to bottom


def generate_formation(seed: Optional[int] = None, tries: int = 12) -> tuple[Cell, ...]:
    """Run the CSP ``tries`` times and keep the formation with the lowest
    soft-constraint penalty (stop early at 0)."""
    rng = random.Random(seed)
    best, best_pen = None, None
    for _ in range(tries):
        cells = solve(rng.randrange(10**9))
        pen = soft_penalty(cells)
        if best is None or pen < best_pen:
            best, best_pen = cells, pen
        if pen == 0:
            break
    return best
