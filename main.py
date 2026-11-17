"""Hadudu Arena entry point.

    python main.py                      # Pygame window (menu)
    python main.py --text               # console game: you (Team A) vs Minimax depth 3
    python main.py --text --a minimax:3 --b human   # you play Team B
    python main.py --text --a mcts:800 --b minimax:3 # watch AI vs AI
"""
from __future__ import annotations

import argparse
import random

from game.rules import ACTIONS, PLAYER, RESULT, TERMINAL, describe_action, describe_outcome, score_diff
from game.state import COLS, ROWS, TEAM_NAMES, GameState, initial_state


def draw_text_board(s: GameState) -> str:
    grid = [["." for _ in range(COLS)] for _ in range(ROWS)]
    for t, letter in ((0, "a"), (1, "b")):
        for i, p in enumerate(s.pos[t]):
            if p is not None:
                ch = str(i + 1)
                if s.raider == i and t == s.attacker and s.phase != "pick":
                    ch = "R"
                elif t == s.defender and i in s.tagged:
                    ch = "x"
                grid[p[0]][p[1]] = (letter.upper() if t == 0 else letter) + ch
    lines = ["     " + "  ".join(f"{c:>2}" for c in range(COLS))]
    for r in range(ROWS):
        cells = [f"{grid[r][c]:>2}" for c in range(COLS)]
        lines.append(f"  {r}  " + "  ".join(cells[:4]) + "  |" + "  ".join(cells[4:]))
    return "\n".join(lines)


def status_line(s: GameState) -> str:
    text = (f"Score A {s.score[0]} - {s.score[1]} B | raid {min(s.raid + 1, 16)}/16 | "
            f"{TEAM_NAMES[s.attacker]} raiding | phase {s.phase}")
    if s.phase != "pick":
        text += f" | breath {s.breath}"
    if s.dod:
        text += " | DO-OR-DIE"
    return text


def run_text(agents: dict) -> None:
    s = initial_state(first=agents.get("first", 0), komi=agents.get("komi", 0))
    while not TERMINAL(s):
        print()
        print(draw_text_board(s))
        print(status_line(s))
        team = PLAYER(s)
        acts = ACTIONS(s)
        agent = agents.get(team)
        if agent is None:
            for k, a in enumerate(acts):
                print(f"  [{k}] {describe_action(s, a)}")
            while True:
                choice = input(f"Team {TEAM_NAMES[team]}, choose action (q quits): ").strip()
                if choice == "q":
                    return
                if choice.isdigit() and int(choice) < len(acts):
                    action = acts[int(choice)]
                    break
        else:
            action = agent.choose_action(s)
            print(f"Team {TEAM_NAMES[team]} ({agent.name}) {describe_action(s, action)}")
        raid = s.raid
        s = RESULT(s, action)
        if s.raid != raid:
            print(f">>> Raid {raid + 1}: {describe_outcome(s.last_outcome)}")
    print(draw_text_board(s))
    d = score_diff(s)
    print(f"Final: A {s.score[0]} - {s.score[1]} B (komi {s.komi}) -> "
          + ("draw" if d == 0 else f"Team {'A' if d > 0 else 'B'} wins"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Hadudu Arena")
    parser.add_argument("--text", action="store_true", help="play in the console")
    parser.add_argument("--a", default="human", help="agent for Team A, e.g. human, minimax:3, mcts:800")
    parser.add_argument("--b", default="minimax:3", help="agent for Team B")
    parser.add_argument("--first", default="A", choices=["A", "B"])
    parser.add_argument("--komi", type=float, default=0)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.text:
        if args.a == "human" and args.b == "human":
            parser.error("one side must be an AI agent")
        from ai.agents import make_agent
        rng = random.Random(args.seed)
        agents = {"first": 0 if args.first == "A" else 1, "komi": args.komi}
        for team, spec in ((0, args.a), (1, args.b)):
            agents[team] = None if spec == "human" else make_agent(spec, seed=rng.randrange(10**9))
        run_text(agents)
    else:
        from ui.screens import run_app
        run_app()


if __name__ == "__main__":
    main()
