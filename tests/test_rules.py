"""Rule tests for the Hadudu engine (brief §3 and §8)."""
import random

import pytest

from game.rules import ACTIONS, PLAYER, RESULT, TERMINAL, UTILITY
from game.state import CLASSIC_START_A, TEAM_A, TEAM_B, initial_state, mirror
from reference import reference_rules as ref


def raid_state(raider_cell, defenders, *, attacker_team=TEAM_A, breath=6, crossed=None,
               tagged=(), dod=False, phase="raider", **extra):
    """Build a mid-raid state: raider #0 of the attacking team at ``raider_cell``.

    ``defenders`` is a list of 5 cells/None for the defending team.
    The other 4 attackers stay on their (A) start cells, minus #0.
    """
    s = initial_state(first=attacker_team)
    att = list(s.start[attacker_team])
    att[0] = raider_cell
    pos = [None, None]
    pos[attacker_team] = tuple(att)
    pos[1 - attacker_team] = tuple(defenders)
    if crossed is None:
        crossed = (raider_cell[1] >= 4) if attacker_team == TEAM_A else (raider_cell[1] < 4)
    return s._replace(pos=tuple(pos), phase=phase, raider=0, breath=breath,
                      crossed=crossed, tagged=tuple(tagged), dod=dod, **extra)


FAR_B = [(0, 7), (5, 7), (2, 7), (3, 7), (4, 7)]   # B defenders far from the action


# ---------------------------------------------------------------- start
def test_start_layout_and_mirror():
    s = initial_state()
    assert s.pos[0] == CLASSIC_START_A
    assert s.pos[1] == ((0, 5), (1, 4), (3, 6), (4, 4), (5, 5))
    assert s.pos[1] == mirror(s.pos[0])
    assert PLAYER(s) == TEAM_A


def test_five_start_actions():
    assert len(ACTIONS(initial_state())) == 5


def test_raider_at_1_3_has_seven_actions():
    s = RESULT(initial_state(), ("pick", 1))   # player #2 starts at (1, 3)
    acts = ACTIONS(s)
    assert len(acts) == 7
    assert ("stop",) in acts
    assert ("step", (0, 2)) not in acts and ("step", (1, 4)) not in acts
    assert s.breath == 6 and PLAYER(s) == TEAM_A


def test_first_raider_configurable():
    s = initial_state(first=TEAM_B)
    assert PLAYER(s) == TEAM_B and s.attacker == TEAM_B


# ---------------------------------------------------------------- touch / stop
def test_touch_only_in_defenders_half():
    d = list(FAR_B)
    d[0] = (2, 4)
    s = raid_state((2, 3), d)   # raider in own half next to a defender
    assert ("touch",) not in ACTIONS(s)


def test_touch_only_untagged_defenders():
    d = list(FAR_B)
    d[0] = (2, 5)
    s = raid_state((2, 4), d)
    assert ("touch",) in ACTIONS(s)
    s2 = RESULT(s, ("touch",))
    assert s2.tagged == (0,) and s2.breath == 5
    s3 = RESULT(s2, ("hold",))
    assert ("touch",) not in ACTIONS(s3)          # nobody new to tag
    assert s2.pos[1][0] == (2, 5)                 # tagged defender stays on court


def test_stop_rules():
    s = raid_state((2, 3), FAR_B, crossed=False)
    assert ("stop",) in ACTIONS(s)
    after = RESULT(s, ("stop",))
    assert after.phase == "pick" and after.empty == (1, 0)
    # in the defenders' half: no stop
    assert ("stop",) not in ACTIONS(raid_state((2, 4), FAR_B))
    # do-or-die: no stop
    assert ("stop",) not in ACTIONS(raid_state((2, 3), FAR_B, crossed=False, dod=True))


# ---------------------------------------------------------------- tackle / caught
def test_tackle_with_three_defenders_cancels_tags():
    d = [(1, 5), (2, 5), (4, 6), (0, 7), (5, 7)]
    s = raid_state((2, 4), d, tagged=(0, 1), phase="defender", breath=4)
    s2 = RESULT(s, ("move", 2, (3, 5)))       # third defender closes the tackle
    assert s2.score == (0, 1)
    assert s2.pos[0][0] is None and s2.outq[0] == (0,)
    assert all(p is not None for p in s2.pos[1])   # tags cancelled: nobody out
    assert s2.last_outcome == ("caught", "tackle")
    assert s2.phase == "pick" and s2.raid == 1


def test_raider_tackled_after_own_step():
    d = [(1, 5), (2, 5), (3, 5), (0, 7), (5, 7)]
    s = raid_state((2, 3), d, crossed=False)
    s2 = RESULT(s, ("step", (2, 4)))
    assert s2.score == (0, 1) and s2.last_outcome == ("caught", "tackle")


# ---------------------------------------------------------------- success
def test_success_removes_tagged_and_scores():
    d = [(1, 5), (3, 5), (0, 7), (5, 7), (2, 7)]
    s = raid_state((2, 4), d, tagged=(0, 1), breath=3)
    s2 = RESULT(s, ("step", (2, 3)))
    assert s2.score == (2, 0)
    assert s2.pos[1][0] is None and s2.pos[1][1] is None
    assert s2.outq[1] == (0, 1)
    assert s2.last_outcome == ("success", 2)


def test_return_without_tags_is_empty_raid():
    s = raid_state((2, 4), FAR_B, breath=3)
    s2 = RESULT(s, ("step", (2, 3)))
    assert s2.score == (0, 0) and s2.empty == (1, 0)


# ---------------------------------------------------------------- revival
def test_revival_order_and_nearest_free_cell():
    d = [(1, 5), (3, 5), (0, 7), (5, 7), (2, 7)]
    s = raid_state((2, 4), d, tagged=(0,), breath=3)
    a = list(s.pos[0])
    a[3] = None                 # #4 (start (4,3)) went out first
    a[2] = None                 # then #3 (start (3,1))
    a[1] = (4, 3)               # #2 now stands on #4's start cell
    a[4] = (4, 2)
    s = s._replace(pos=(tuple(a), s.pos[1]), outq=((3, 2), ()))
    s2 = RESULT(s, ("step", (2, 3)))     # +1 -> revive one player, oldest first (#4)
    assert s2.score == (1, 0)
    assert s2.outq[0] == (2,)
    # start (4,3) is occupied -> nearest free cell; distance 1 candidates are
    # (3,3) and (5,3) [(4,2) occupied]; lowest row wins -> (3,3)
    assert s2.pos[0][3] == (3, 3)


def test_all_out_bonus_and_reset():
    d = [(2, 5), None, None, None, None]
    s = raid_state((2, 4), d, tagged=(0,), breath=3)
    s = s._replace(outq=((), (1, 2, 3, 4)))
    s2 = RESULT(s, ("step", (2, 3)))
    assert s2.score == (1 + 2, 0)
    assert s2.pos[1] == s2.start[1] and s2.outq[1] == ()
    assert "all_out" in s2.last_outcome


# ---------------------------------------------------------------- empty raids / do-or-die
def test_do_or_die_after_two_empty_raids_and_reset():
    s = initial_state()
    for _ in range(4):    # A empty, B empty, A empty, B empty
        s = RESULT(s, ("pick", 0))
        s = RESULT(s, ("stop",))
    assert s.empty == (2, 2)
    s = RESULT(s, ("pick", 0))
    assert s.dod and ("stop",) not in ACTIONS(s)
    # do-or-die raid that ends empty: breath runs out in own half
    while not s.phase == "pick":
        acts = ACTIONS(s)
        if PLAYER(s) == TEAM_A:   # raider shuffles inside own half
            own = [x for x in acts if x[0] == "step" and x[1][1] < 4]
            s = RESULT(s, own[0])
        else:
            s = RESULT(s, ("hold",))
    assert s.last_outcome == ("dod_fail",)
    assert s.score == (0, 1)
    assert s.empty == (0, 0)          # any point resets both counters
    assert s.pos[0][0] is None


def test_point_resets_both_counters():
    d = [(1, 5), (3, 5), (0, 7), (5, 7), (2, 7)]
    s = raid_state((2, 4), d, tagged=(0,), breath=3, empty=(1, 1))
    s2 = RESULT(s, ("step", (2, 3)))
    assert s2.empty == (0, 0)


# ---------------------------------------------------------------- breath
def test_breath_expiry_in_defenders_half_is_caught():
    s = raid_state((2, 4), FAR_B, breath=1)
    s2 = RESULT(s, ("step", (2, 5)))
    assert s2.last_outcome == ("caught", "breath") and s2.score == (0, 1)


def test_breath_expiry_in_own_half_is_empty():
    s = raid_state((2, 2), FAR_B, breath=1, crossed=False)
    s2 = RESULT(s, ("step", (2, 1)))
    assert s2.last_outcome == ("empty",) and s2.score == (0, 0) and s2.empty == (1, 0)


def test_success_beats_breath_expiry():
    d = [(1, 5), (3, 5), (0, 7), (5, 7), (2, 7)]
    s = raid_state((2, 4), d, tagged=(0,), breath=1)
    s2 = RESULT(s, ("step", (2, 3)))
    assert s2.last_outcome == ("success", 1)


# ---------------------------------------------------------------- match
def test_sixteen_raids_end_the_match():
    s = initial_state()
    for k in range(16):
        assert not TERMINAL(s)
        s = RESULT(s, ACTIONS(s)[0])
        if s.phase == "raider" and ("stop",) in ACTIONS(s):
            s = RESULT(s, ("stop",))
        else:      # do-or-die: run the raid down with holds / own-half steps
            while s.phase != "pick":
                acts = ACTIONS(s)
                own = [x for x in acts if x[0] == "step" and (x[1][1] < 4) == (s.attacker == 0)]
                s = RESULT(s, own[0] if PLAYER(s) == s.attacker and own else
                           (("hold",) if ("hold",) in acts else acts[0]))
    assert TERMINAL(s) and s.raid == 16 and ACTIONS(s) == []


def test_komi_in_utility():
    s = initial_state(first=TEAM_B, komi=1)._replace(over=True)
    assert UTILITY(s) == -1


def test_result_does_not_change_input():
    rng = random.Random(3)
    s = initial_state()
    for _ in range(300):
        if TERMINAL(s):
            break
        snapshot = tuple(s)
        acts = ACTIONS(s)
        s2 = RESULT(s, rng.choice(acts))
        assert tuple(s) == snapshot
        s = s2


def test_random_games_terminate():
    rng = random.Random(7)
    longest = 0
    for _ in range(300):
        s, n = initial_state(), 0
        while not TERMINAL(s):
            s = RESULT(s, rng.choice(ACTIONS(s)))
            n += 1
            assert n < 2000
        longest = max(longest, n)
    assert longest < 400


# ---------------------------------------------------------------- reference prototype
def _to_ref(action):
    return ("raid", action[1]) if action[0] == "pick" else action


def _from_ref(action):
    return ("pick", action[1]) if action[0] == "raid" else action


@pytest.mark.parametrize("seed", range(200))
def test_matches_reference_prototype(seed):
    """Play the same random action sequence in both engines and compare."""
    rng = random.Random(seed)
    first = seed % 2
    mine = initial_state(first=first)
    theirs = ref.new()
    theirs["first"] = first
    while not ref.terminal(theirs):
        assert not TERMINAL(mine)
        ref_acts = sorted(_from_ref(a) for a in ref.actions(theirs))
        my_acts = sorted(ACTIONS(mine))
        assert my_acts == ref_acts
        assert PLAYER(mine) == ref.player(theirs)
        act = rng.choice(my_acts)
        mine = RESULT(mine, act)
        theirs = ref.result(theirs, _to_ref(act))
        assert list(mine.pos[0]) == theirs["pos"][0] and list(mine.pos[1]) == theirs["pos"][1]
        assert list(mine.score) == theirs["score"]
    assert TERMINAL(mine)
    assert list(mine.score) == theirs["score"]
