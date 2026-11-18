"""Headless AI-vs-AI series for the report.

Examples (run from the hadudu_arena folder):
    python -m experiments.tournament --games 50 --a minimax:3 --b mcts:800 --seed 1
    python -m experiments.tournament --games 20 --a minimax:3 --b minimax:3 --komi-sweep 0,1,2
    python -m experiments.tournament --preset depth --games 20
    python -m experiments.tournament --list-presets

Agent X (--a) and agent Y (--b) swap colours and the first raider in a
4-game cycle, so each agent plays every (team, first raider) combination
equally often:
    game 0: X=A, A first   game 1: X=B, A first
    game 2: X=A, B first   game 3: X=B, B first
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import time
from dataclasses import dataclass, field

from ai.agents import Agent, make_agent
from game.rules import ACTIONS, PLAYER, RESULT, TERMINAL, score_diff
from game.state import CLASSIC_START_A, TEAM_NAMES, initial_state

PRESETS = {
    "depth": [("minimax:2", "minimax:3"), ("minimax:3", "minimax:4"), ("minimax:2", "minimax:4")],
    "mm-vs-mcts": [("minimax:3", "mcts:800")],
    "fuzzy": [("fuzzy:3", "minimax:3")],
    "mcts-iters": [("mcts:300", "mcts:2000")],
    "ordering": [("minimax:4", "minimax-noorder:4")],
}


@dataclass
class MatchResult:
    first: int
    score: tuple[int, int]
    diff: float                       # score A - score B incl. komi
    tackles: int = 0                  # raiders caught (tackle, breath or boxed)
    all_outs: int = 0
    plies: int = 0
    time: list = field(default_factory=lambda: [0.0, 0.0])    # per team
    nodes: list = field(default_factory=lambda: [0, 0])
    decisions: list = field(default_factory=lambda: [0, 0])


def play_match(agents: dict[int, Agent], first: int = 0, komi: float = 0,
               formation=CLASSIC_START_A, max_plies: int = 5000,
               should_stop=None) -> MatchResult:
    """Play one full match between two agents (team 0 = A, team 1 = B).

    ``should_stop`` is an optional callable; the UI uses it to cancel a series.
    """
    s = initial_state(first=first, komi=komi, formation_a=formation)
    res = MatchResult(first=first, score=(0, 0), diff=0)
    while not TERMINAL(s) and res.plies < max_plies:
        if should_stop is not None and should_stop():
            break
        team = PLAYER(s)
        agent = agents[team]
        action = agent.choose_action(s)
        if len(ACTIONS(s)) > 1:              # only count real decisions
            res.time[team] += agent.last_time
            res.nodes[team] += agent.last_nodes
            res.decisions[team] += 1
        raid = s.raid
        s = RESULT(s, action)
        res.plies += 1
        if s.raid != raid and s.last_outcome:
            res.tackles += s.last_outcome[0] == "caught"
            res.all_outs += "all_out" in s.last_outcome
    res.score, res.diff = s.score, score_diff(s)
    return res


def run_series(spec_x: str, spec_y: str, games: int, seed: int = 1, komi: float = 0,
               formation: str = "classic", out_dir: str = "results", quiet: bool = False,
               tag: str = "") -> dict:
    """Play ``games`` matches X vs Y, write a CSV and return the summary dict."""
    rng = random.Random(seed)
    rows = []
    win = {"X": 0, "Y": 0, "draw": 0}
    first_wins = second_wins = 0
    points = {"X": 0.0, "Y": 0.0}
    t_used = {"X": 0.0, "Y": 0.0}
    n_used = {"X": 0, "Y": 0}
    dec = {"X": 0, "Y": 0}
    tackles = 0
    t_start = time.time()
    for g in range(games):
        x_team = g % 2
        first = (g // 2) % 2
        formation_a = CLASSIC_START_A
        if formation == "csp":
            from ai.formation_csp import generate_formation
            formation_a = generate_formation(seed=rng.randrange(10**9))
        agent_x = make_agent(spec_x, seed=rng.randrange(10**9))
        agent_y = make_agent(spec_y, seed=rng.randrange(10**9))
        agents = {x_team: agent_x, 1 - x_team: agent_y}
        r = play_match(agents, first, komi, formation_a)

        diff_x = r.diff if x_team == 0 else -r.diff
        result = "X" if diff_x > 0 else "Y" if diff_x < 0 else "draw"
        win[result] += 1
        if r.diff != 0:
            winner_team = 0 if r.diff > 0 else 1
            first_wins += winner_team == first
            second_wins += winner_team != first
        y_team = 1 - x_team
        points["X"] += r.score[x_team]
        points["Y"] += r.score[y_team]
        for key, team in (("X", x_team), ("Y", y_team)):
            t_used[key] += r.time[team]
            n_used[key] += r.nodes[team]
            dec[key] += r.decisions[team]
        tackles += r.tackles
        winner_name = "draw" if result == "draw" else (agent_x.name if result == "X" else agent_y.name)
        rows.append({
            "game": g + 1, "agent_A": agents[0].name, "agent_B": agents[1].name,
            "first_raider": TEAM_NAMES[first], "komi": komi,
            "score_A": r.score[0], "score_B": r.score[1], "final_diff_A": r.diff,
            "winner": winner_name, "winner_team": "draw" if r.diff == 0 else ("A" if r.diff > 0 else "B"),
            "tackles": r.tackles, "all_outs": r.all_outs, "plies": r.plies,
            "avg_time_A": round(r.time[0] / max(1, r.decisions[0]), 5),
            "avg_time_B": round(r.time[1] / max(1, r.decisions[1]), 5),
            "avg_nodes_A": round(r.nodes[0] / max(1, r.decisions[0]), 1),
            "avg_nodes_B": round(r.nodes[1] / max(1, r.decisions[1]), 1),
            "formation": "-".join(f"{a}{b}" for a, b in formation_a),
        })
        if not quiet:
            print(f"  game {g + 1:>3}/{games}: A={agents[0].name:<22} B={agents[1].name:<22} "
                  f"first={TEAM_NAMES[first]}  {r.score[0]:>2}-{r.score[1]:<2} -> {winner_name}")

    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = f"{spec_x}_vs_{spec_y}_komi{komi}{tag}".replace(":", "")
    path = os.path.join(out_dir, f"{stamp}_{safe}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    decided = first_wins + second_wins
    summary = {
        "X": spec_x, "Y": spec_y, "games": games, "komi": komi, "csv": path,
        "x_win%": 100 * win["X"] / games, "draw%": 100 * win["draw"] / games,
        "y_win%": 100 * win["Y"] / games,
        "x_avg_score": points["X"] / games, "y_avg_score": points["Y"] / games,
        "x_avg_time": t_used["X"] / max(1, dec["X"]), "y_avg_time": t_used["Y"] / max(1, dec["Y"]),
        "x_avg_nodes": n_used["X"] / max(1, dec["X"]), "y_avg_nodes": n_used["Y"] / max(1, dec["Y"]),
        "first_raider_win%": 100 * first_wins / games,
        "second_raider_win%": 100 * second_wins / games,
        # expected score of the first raider (win = 1, draw = 0.5): 50% = fair
        "first_score%": 100 * (first_wins + 0.5 * (games - decided)) / games,
        "tackles_per_game": tackles / games,
        "seconds": time.time() - t_start,
    }
    print_summary(summary)
    return summary


def print_summary(s: dict) -> None:
    print(f"\n=== {s['X']} (X) vs {s['Y']} (Y), {s['games']} games, komi {s['komi']} ===")
    print(f"  X wins {s['x_win%']:.0f}%  draws {s['draw%']:.0f}%  Y wins {s['y_win%']:.0f}%")
    print(f"  average score  X {s['x_avg_score']:.2f}  Y {s['y_avg_score']:.2f}")
    print(f"  avg decision time  X {s['x_avg_time'] * 1000:.1f} ms  Y {s['y_avg_time'] * 1000:.1f} ms")
    print(f"  avg nodes/decision X {s['x_avg_nodes']:.0f}  Y {s['y_avg_nodes']:.0f}")
    print(f"  first raider wins {s['first_raider_win%']:.0f}%  second raider wins "
          f"{s['second_raider_win%']:.0f}%  (first raider's expected score "
          f"{s['first_score%']:.0f}%, 50% = fair)")
    print(f"  tackles per game {s['tackles_per_game']:.1f}   wall time {s['seconds']:.0f} s")
    print(f"  CSV: {s['csv']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Hadudu Arena AI tournament")
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--a", default="minimax:3", help="agent X")
    p.add_argument("--b", default="mcts:800", help="agent Y")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--komi", type=float, default=0)
    p.add_argument("--komi-sweep", default=None, help="comma list, e.g. 0,1,2")
    p.add_argument("--formation", choices=["classic", "csp"], default="classic")
    p.add_argument("--preset", choices=sorted(PRESETS), default=None)
    p.add_argument("--list-presets", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    if args.list_presets:
        for name, pairs in PRESETS.items():
            print(f"{name:12} " + ", ".join(f"{a} vs {b}" for a, b in pairs))
        return
    pairs = PRESETS[args.preset] if args.preset else [(args.a, args.b)]
    komis = [float(k) for k in args.komi_sweep.split(",")] if args.komi_sweep else [args.komi]
    summaries = []
    for a, b in pairs:
        for k in komis:
            summaries.append(run_series(a, b, args.games, args.seed, k, args.formation,
                                        quiet=args.quiet))
    if len(komis) > 1:
        print("\n=== komi sweep: first raider's expected score (win 1, draw 0.5) ===")
        for s in summaries:
            print(f"  komi {s['komi']:>4}: first {s['first_raider_win%']:.0f}%  "
                  f"second {s['second_raider_win%']:.0f}%  draws {s['draw%']:.0f}%  "
                  f"expected score {s['first_score%']:.0f}%")
        best = min(summaries, key=lambda s: abs(s["first_score%"] - 50))
        print(f"  closest to 50%: komi {best['komi']}")


if __name__ == "__main__":
    main()
