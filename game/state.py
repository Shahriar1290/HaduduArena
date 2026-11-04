"""Game state for Hadudu Arena.

The state is an immutable NamedTuple made only of tuples, ints and bools,
so RESULT(s, a) can build a new state with ``s._replace(...)`` and never
has to copy or change the old one (no deepcopy needed).
"""
from __future__ import annotations

from typing import NamedTuple, Optional

# ----------------------------------------------------------------------
# Court geometry
# ----------------------------------------------------------------------
ROWS, COLS = 6, 8
TEAM_A, TEAM_B = 0, 1
TEAM_NAMES = ("A", "B")
PLAYERS_PER_TEAM = 5
BREATH = 6            # actions a raider gets per raid
TOTAL_RAIDS = 16      # 8 per team
DO_OR_DIE_AFTER = 2   # empty raids in a row before a do-or-die raid
TACKLE_COUNT = 3      # defenders around the raider needed for a tackle
ALL_OUT_BONUS = 2     # "lona" bonus

Cell = tuple[int, int]

# Team A's half is columns 0-3, Team B's half is columns 4-7.
HALF_COLS = (range(0, 4), range(4, 8))

CLASSIC_START_A: tuple[Cell, ...] = ((0, 2), (1, 3), (3, 1), (4, 3), (5, 2))


def mirror(cells: tuple[Cell, ...]) -> tuple[Cell, ...]:
    """Mirror Team A's cells into Team B's half: (r, c) -> (r, 7 - c)."""
    return tuple((r, COLS - 1 - c) for r, c in cells)


def in_half(team: int, cell: Cell) -> bool:
    """True if ``cell`` lies in ``team``'s own half of the court."""
    return (cell[1] < 4) if team == TEAM_A else (cell[1] >= 4)


def on_court(cell: Cell) -> bool:
    return 0 <= cell[0] < ROWS and 0 <= cell[1] < COLS


def chebyshev(a: Cell, b: Cell) -> int:
    """King-move distance: two cells are neighbours when this is 1."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


# NEIGHBOURS[cell] = the on-court cells in the 8 directions, precomputed once.
_DIRS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)]
NEIGHBOURS: dict[Cell, tuple[Cell, ...]] = {
    (r, c): tuple((r + dr, c + dc) for dr, dc in _DIRS if on_court((r + dr, c + dc)))
    for r in range(ROWS) for c in range(COLS)
}


class GameState(NamedTuple):
    """One snapshot of the match.

    pos[t][i]   : cell of player i of team t, or None if he is out
    outq[t]     : indices of team t's out players, oldest first (revival order)
    score       : (score A, score B) without komi
    raid        : raids already finished (0..16)
    first       : team that raids first
    phase       : 'pick' | 'raider' | 'defender'
    raider      : index of the raider in the attacking team (None in 'pick')
    breath      : breath left for the raider
    crossed     : raider has entered the defenders' half this raid
    tagged      : sorted tuple of tagged defender indices
    empty       : (empty-raid counter A, counter B)
    dod         : current raid is do-or-die
    over        : match finished
    start       : start cells per team (classic or CSP formation)
    komi        : extra points for the team that raids first
    last_outcome: how the last raid ended, e.g. ('success', 2), for logs/stats
    """
    pos: tuple[tuple[Optional[Cell], ...], tuple[Optional[Cell], ...]]
    outq: tuple[tuple[int, ...], tuple[int, ...]]
    score: tuple[int, int]
    raid: int
    first: int
    phase: str
    raider: Optional[int]
    breath: int
    crossed: bool
    tagged: tuple[int, ...]
    empty: tuple[int, int]
    dod: bool
    over: bool
    start: tuple[tuple[Cell, ...], tuple[Cell, ...]]
    komi: float = 0
    last_outcome: Optional[tuple] = None

    # ---- small read-only helpers ------------------------------------
    @property
    def attacker(self) -> int:
        """Team raiding in the current raid (raids alternate)."""
        return (self.raid + self.first) % 2

    @property
    def defender(self) -> int:
        return 1 - self.attacker

    def raider_cell(self) -> Optional[Cell]:
        if self.raider is None:
            return None
        return self.pos[self.attacker][self.raider]

    def occupied(self) -> set[Cell]:
        return {p for team in self.pos for p in team if p is not None}

    def in_count(self, team: int) -> int:
        return sum(p is not None for p in self.pos[team])

    def adjacent_defenders(self, cell: Cell) -> list[int]:
        """Indices of *in* defenders in the 8 cells around ``cell``."""
        return [i for i, p in enumerate(self.pos[self.defender])
                if p is not None and chebyshev(p, cell) == 1]


def initial_state(first: int = TEAM_A, komi: float = 0,
                  formation_a: tuple[Cell, ...] = CLASSIC_START_A) -> GameState:
    """Start of the match. Team B always gets the mirror of Team A's formation."""
    start = (tuple(formation_a), mirror(tuple(formation_a)))
    return GameState(
        pos=(start[0], start[1]), outq=((), ()), score=(0, 0), raid=0, first=first,
        phase="pick", raider=None, breath=0, crossed=False, tagged=(), empty=(0, 0),
        dod=False, over=False, start=start, komi=komi, last_outcome=None,
    )
