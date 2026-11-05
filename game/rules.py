"""Problem formulation of Hadudu as an adversarial search problem.

These are the same functions we used in the Minimax lab:
    PLAYER(s)    -> which team must act in state s
    ACTIONS(s)   -> list of legal actions in s
    RESULT(s, a) -> the new state after action a (s itself is not changed)
    TERMINAL(s)  -> True when the match is over
    UTILITY(s)   -> final value for Team A (score A - score B, komi included)

One "ply" is ONE single action: a pick, a raider action or a defender action.

Actions are small tuples:
    ('pick', i)            attacker chooses player i as raider
    ('step', (r, c))       raider moves to a neighbouring empty cell   (1 breath)
    ('touch',)             raider tags all untagged adjacent defenders (1 breath)
    ('stop',)              raider gives up before crossing (empty raid, 0 breath)
    ('move', i, (r, c))    defender i moves to a neighbouring cell in his half
    ('hold',)              defenders do nothing
"""
from __future__ import annotations

from typing import Optional

from .state import (ALL_OUT_BONUS, BREATH, COLS, DO_OR_DIE_AFTER, NEIGHBOURS, ROWS,
                    TACKLE_COUNT, TEAM_A, TOTAL_RAIDS, Cell, GameState, in_half)

Action = tuple


# ======================================================================
# The five functions of the problem formulation
# ======================================================================
def PLAYER(s: GameState) -> int:
    """Attacker acts in 'pick' and 'raider' phases, defender in 'defender' phase."""
    return s.attacker if s.phase in ("pick", "raider") else s.defender


def ACTIONS(s: GameState) -> list[Action]:
    if s.over:
        return []
    if s.phase == "pick":
        return [("pick", i) for i, p in enumerate(s.pos[s.attacker]) if p is not None]
    if s.phase == "raider":
        return raider_actions(s)
    return defender_actions(s)


def RESULT(s: GameState, action: Action) -> GameState:
    """Transition model. Returns a NEW state; the input state is never modified."""
    a = s.attacker
    kind = action[0]

    # ---- 1. pick a raider ------------------------------------------
    if s.phase == "pick":
        s = s._replace(phase="raider", raider=action[1], breath=BREATH, crossed=False,
                       tagged=(), dod=s.empty[a] >= DO_OR_DIE_AFTER, last_outcome=None)
        if not raider_actions(s):          # boxed in on a do-or-die raid
            return _caught(s, "boxed")
        return s

    # ---- 2. raider action ------------------------------------------
    if s.phase == "raider":
        if kind == "stop":                 # costs no breath
            return _empty_raid(s)
        breath = s.breath - 1
        if kind == "step":
            cell = action[1]
            s = s._replace(pos=_set_pos(s.pos, a, s.raider, cell), breath=breath)
            if not in_half(a, cell):
                s = s._replace(crossed=True)
            elif s.crossed:                # end rule 1: back home after crossing
                return _success(s)
        else:                              # touch
            new_tags = set(s.tagged) | set(s.adjacent_defenders(s.raider_cell()))
            s = s._replace(tagged=tuple(sorted(new_tags)), breath=breath)

        if breath == 0:                    # end rule 2: out of breath
            if not in_half(a, s.raider_cell()):
                return _caught(s, "breath")
            return _empty_raid(s)
        if is_tackled(s):                  # end rule 3: tackle
            return _caught(s, "tackle")
        return s._replace(phase="defender")

    # ---- 3. defender action ----------------------------------------
    if kind == "move":
        s = s._replace(pos=_set_pos(s.pos, s.defender, action[1], action[2]))
    if is_tackled(s):
        return _caught(s, "tackle")
    s = s._replace(phase="raider")
    if not raider_actions(s):              # raider has nowhere to go
        return _caught(s, "boxed")
    return s


def TERMINAL(s: GameState) -> bool:
    return s.over


def UTILITY(s: GameState) -> float:
    """Team A's score minus Team B's score, with komi for the first raider."""
    return score_diff(s)


# ======================================================================
# Helpers for legal actions
# ======================================================================
def raider_actions(s: GameState) -> list[Action]:
    a = s.attacker
    cell = s.raider_cell()
    occ = s.occupied()
    acts: list[Action] = [("step", n) for n in NEIGHBOURS[cell] if n not in occ]
    if not in_half(a, cell):
        # touch only if at least one NEW defender is adjacent
        if any(i not in s.tagged for i in s.adjacent_defenders(cell)):
            acts.append(("touch",))
    elif not s.crossed and not s.dod:
        acts.append(("stop",))
    return acts


def defender_actions(s: GameState) -> list[Action]:
    d = s.defender
    occ = s.occupied()
    acts: list[Action] = [("hold",)]
    for i, p in enumerate(s.pos[d]):
        if p is None:
            continue
        for n in NEIGHBOURS[p]:
            if n not in occ and in_half(d, n):
                acts.append(("move", i, n))
    return acts


def is_tackled(s: GameState) -> bool:
    """Raider is in the defenders' half with 3+ in-defenders around him."""
    cell = s.raider_cell()
    return (cell is not None and not in_half(s.attacker, cell)
            and len(s.adjacent_defenders(cell)) >= TACKLE_COUNT)


def score_diff(s: GameState) -> float:
    """Score A - score B, including komi for the team that raids first."""
    komi = s.komi if s.first == TEAM_A else -s.komi
    return s.score[0] - s.score[1] + komi


def winner(s: GameState) -> Optional[int]:
    """Team that won (0/1) or None for a draw."""
    d = score_diff(s)
    return None if d == 0 else (TEAM_A if d > 0 else 1 - TEAM_A)


# ======================================================================
# Raid endings (all return a new state)
# ======================================================================
def _set_pos(pos, team: int, i: int, cell: Optional[Cell]):
    row = list(pos[team])
    row[i] = cell
    return (tuple(row), pos[1]) if team == 0 else (pos[0], tuple(row))


def _add_score(score, team: int, pts: int):
    return (score[0] + pts, score[1]) if team == 0 else (score[0], score[1] + pts)


def _caught(s: GameState, reason: str) -> GameState:
    """Raider goes out, his tags are cancelled, defenders score 1."""
    a, d = s.attacker, s.defender
    pos = _set_pos(s.pos, a, s.raider, None)
    outq = list(s.outq)
    outq[a] = outq[a] + (s.raider,)
    s = s._replace(pos=pos, outq=tuple(outq), tagged=(), empty=(0, 0),
                   score=_add_score(s.score, d, 1), last_outcome=("caught", reason))
    s = _revive(s, d, 1)
    return _end_raid(_check_all_out(s))


def _success(s: GameState) -> GameState:
    """Raider returned home: tagged defenders go out, attackers score 1 each."""
    a, d = s.attacker, s.defender
    k = len(s.tagged)
    if k == 0:
        return _empty_raid(s)
    row = list(s.pos[d])
    for i in s.tagged:
        row[i] = None
    pos = list(s.pos)
    pos[d] = tuple(row)
    outq = list(s.outq)
    outq[d] = outq[d] + tuple(s.tagged)
    s = s._replace(pos=tuple(pos), outq=tuple(outq), empty=(0, 0),
                   score=_add_score(s.score, a, k), last_outcome=("success", k))
    s = _revive(s, a, k)
    return _end_raid(_check_all_out(s))


def _empty_raid(s: GameState) -> GameState:
    """No points. On a do-or-die raid the raider goes out and defenders score 1."""
    a, d = s.attacker, s.defender
    empty = list(s.empty)
    empty[a] += 1
    s = s._replace(empty=tuple(empty), last_outcome=("empty",))
    if s.dod:
        pos = _set_pos(s.pos, a, s.raider, None)
        outq = list(s.outq)
        outq[a] = outq[a] + (s.raider,)
        s = s._replace(pos=pos, outq=tuple(outq), score=_add_score(s.score, d, 1),
                       empty=(0, 0), last_outcome=("dod_fail",))
        s = _check_all_out(_revive(s, d, 1))
    return _end_raid(s)


def _revive(s: GameState, team: int, k: int) -> GameState:
    """Bring back up to k out players of ``team``, oldest first."""
    queue = list(s.outq[team])
    row = list(s.pos[team])
    for _ in range(k):
        if not queue:
            break
        i = queue.pop(0)
        occ = {p for t in (0, 1) for p in (row if t == team else s.pos[t]) if p is not None}
        cell = s.start[team][i]
        if cell in occ:
            # nearest free cell in own half; ties -> lowest row, then lowest column
            free = [(r, c) for r in range(ROWS) for c in range(COLS)
                    if in_half(team, (r, c)) and (r, c) not in occ]
            cell = min(free, key=lambda x: (abs(x[0] - cell[0]) + abs(x[1] - cell[1]), x))
        row[i] = cell
    pos = list(s.pos)
    pos[team] = tuple(row)
    outq = list(s.outq)
    outq[team] = tuple(queue)
    return s._replace(pos=tuple(pos), outq=tuple(outq))


def _check_all_out(s: GameState) -> GameState:
    """All out (lona): the other team gets +2 and the whole team comes back."""
    for t in (0, 1):
        if all(p is None for p in s.pos[t]):
            pos = list(s.pos)
            pos[t] = s.start[t]
            outq = list(s.outq)
            outq[t] = ()
            s = s._replace(pos=tuple(pos), outq=tuple(outq),
                           score=_add_score(s.score, 1 - t, ALL_OUT_BONUS),
                           last_outcome=(s.last_outcome or ()) + ("all_out",))
    return s


def _end_raid(s: GameState) -> GameState:
    raid = s.raid + 1
    return s._replace(raid=raid, phase="pick", raider=None, breath=0, crossed=False,
                      tagged=(), dod=False, over=raid >= TOTAL_RAIDS)


# ======================================================================
# Text descriptions (used by the console mode and the UI log)
# ======================================================================
def describe_action(s: GameState, action: Action) -> str:
    kind = action[0]
    if kind == "pick":
        return f"picks raider #{action[1] + 1} at {s.pos[s.attacker][action[1]]}"
    if kind == "step":
        return f"steps to {action[1]}"
    if kind == "move":
        return f"moves defender #{action[1] + 1} to {action[2]}"
    return kind


def describe_outcome(outcome: tuple) -> str:
    if not outcome:
        return ""
    kind = outcome[0]
    if kind == "success":
        text = f"touched {outcome[1]} defender{'s' if outcome[1] > 1 else ''} and returned safely: +{outcome[1]}"
    elif kind == "caught":
        text = {"tackle": "was tackled", "breath": "ran out of breath in enemy half",
                "boxed": "was boxed in"}[outcome[1]] + ": +1 to defenders"
    elif kind == "dod_fail":
        text = "failed the do-or-die raid: +1 to defenders"
    else:
        text = "made an empty raid"
    if "all_out" in outcome:
        text += " | ALL OUT! +2 bonus"
    return text
