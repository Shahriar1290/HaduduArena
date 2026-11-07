"""Path search on the court: A* for the raider's safe return, BFS for defenders.

The court is an 8-connected grid (king moves). Occupied cells cannot be entered.
"""
from __future__ import annotations

import heapq
import math
from collections import deque
from functools import lru_cache

from game.state import NEIGHBOURS, Cell, GameState, chebyshev, in_half

DEFENDER_PENALTY = 2   # extra cost for each in-defender next to a cell


def columns_to_home(team: int, cell: Cell) -> int:
    """Heuristic h(n): columns the raider still has to cross to reach his half.

    Every move changes the column by at most 1 and costs at least 1, so h(n)
    never overestimates the true cost -> it is ADMISSIBLE, and A* is optimal.
    """
    return max(0, cell[1] - 3) if team == 0 else max(0, 4 - cell[1])


def safe_return_cost(s: GameState) -> tuple[float, list[Cell]]:
    """A* search for the cheapest way home for the current raider.

    Step cost of entering a cell = 1 + 2 * (in-defenders adjacent to that cell).
    Returns (cost, path) where path starts at the raider's cell.
    Returns (inf, []) if the raider is walled in.
    """
    start = s.raider_cell()
    if start is None:
        return 0, []
    team = s.attacker
    blocked = frozenset(s.occupied() - {start})
    defenders = tuple(p for p in s.pos[s.defender] if p is not None)
    return _astar(start, team, blocked, defenders)


@lru_cache(maxsize=200_000)
def _astar(start: Cell, team: int, blocked: frozenset, defenders: tuple) -> tuple[float, list[Cell]]:
    if in_half(team, start):
        return 0, [start]

    def step_cost(cell: Cell) -> int:
        return 1 + DEFENDER_PENALTY * sum(chebyshev(cell, d) == 1 for d in defenders)

    # frontier is a priority queue ordered by f(n) = g(n) + h(n)
    frontier = [(columns_to_home(team, start), 0, start)]
    came_from: dict[Cell, Cell | None] = {start: None}
    g_cost = {start: 0}
    while frontier:
        _, g, cell = heapq.heappop(frontier)
        if g > g_cost[cell]:
            continue                       # stale queue entry
        if in_half(team, cell):            # goal test: back in own half
            path = [cell]
            while came_from[path[-1]] is not None:
                path.append(came_from[path[-1]])
            return g, path[::-1]
        for n in NEIGHBOURS[cell]:
            if n in blocked:
                continue
            new_g = g + step_cost(n)
            if new_g < g_cost.get(n, math.inf):
                g_cost[n] = new_g
                came_from[n] = cell
                heapq.heappush(frontier, (new_g + columns_to_home(team, n), new_g, n))
    return math.inf, []


def path_cost(s: GameState, path: list[Cell]) -> float:
    """Cost of a given path under the same penalties A* uses."""
    defenders = [p for p in s.pos[s.defender] if p is not None]
    return sum(1 + DEFENDER_PENALTY * sum(chebyshev(c, d) == 1 for d in defenders)
               for c in path[1:])


def bfs_return_path(s: GameState) -> list[Cell]:
    """Plain BFS (uninformed, all steps cost 1) from the raider to his own half."""
    start = s.raider_cell()
    team = s.attacker
    blocked = s.occupied() - {start}
    parent: dict[Cell, Cell | None] = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if in_half(team, cell):
            path = [cell]
            while parent[path[-1]] is not None:
                path.append(parent[path[-1]])
            return path[::-1]
        for n in NEIGHBOURS[cell]:
            if n not in blocked and n not in parent:
                parent[n] = cell
                queue.append(n)
    return []


def intercept_distance(s: GameState) -> dict[int, float]:
    """BFS distance (in moves) for each in-defender to a cell next to the raider.

    Defenders may only walk through empty cells of their own half.
    0 means already adjacent; inf means he cannot get there.
    """
    raider = s.raider_cell()
    result: dict[int, float] = {}
    if raider is None:
        return result
    d = s.defender
    occupied = s.occupied()
    for i, start in enumerate(s.pos[d]):
        if start is None:
            continue
        blocked = occupied - {start}
        seen = {start}
        queue = deque([(start, 0)])
        result[i] = math.inf
        while queue:
            cell, dist = queue.popleft()
            if chebyshev(cell, raider) == 1:      # goal: next to the raider
                result[i] = dist
                break
            for n in NEIGHBOURS[cell]:
                if n not in seen and n not in blocked and in_half(d, n):
                    seen.add(n)
                    queue.append((n, dist + 1))
    return result
