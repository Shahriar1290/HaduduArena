"""Tune the evaluation weights W_GAIN / W_RISK by self-play.

Each candidate (gain, risk) Minimax plays the baseline Minimax (4, 2) at the
same depth; colours and the first raider swap in the usual 4-game cycle.

    python -m experiments.tune_weights --depth 3 --games 20
"""
from __future__ import annotations

import argparse
import random

from ai.agents import MinimaxAgent
from experiments.tournament import play_match

GRID = [(g, r) for g in (2, 4, 6, 8) for r in (1, 2, 3, 4)]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--games", type=int, default=20)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--grid", default=None, help="e.g. 4:2,8:1,8:2 (default: 4x4 grid)")
    p.add_argument("--base", default="4:2", help="baseline weights gain:risk")
    args = p.parse_args()
    grid = GRID if not args.grid else [tuple(float(v) for v in x.split(":")) for x in args.grid.split(",")]
    base_g, base_r = (float(v) for v in args.base.split(":"))
    print(f"candidate vs baseline (gain {base_g:g}, risk {base_r:g}), depth {args.depth}, {args.games} games each", flush=True)
    print(f"{'gain':>5} {'risk':>5} {'win%':>6} {'draw%':>6} {'loss%':>6} {'pts for':>8} {'pts vs':>7}")
    for gain, risk in grid:
        rng = random.Random(args.seed)
        w = d = l = pf = pa = 0
        for g in range(args.games):
            x_team, first = g % 2, (g // 2) % 2
            cand = MinimaxAgent(args.depth, seed=rng.randrange(10**9), gain_weight=gain, risk_weight=risk)
            base = MinimaxAgent(args.depth, seed=rng.randrange(10**9), gain_weight=base_g, risk_weight=base_r)
            r = play_match({x_team: cand, 1 - x_team: base}, first)
            diff = r.diff if x_team == 0 else -r.diff
            w, d, l = w + (diff > 0), d + (diff == 0), l + (diff < 0)
            pf += r.score[x_team]
            pa += r.score[1 - x_team]
        n = args.games
        print(f"{gain:>5g} {risk:>5g} {100*w/n:>6.0f} {100*d/n:>6.0f} {100*l/n:>6.0f} "
              f"{pf/n:>8.2f} {pa/n:>7.2f}", flush=True)


if __name__ == "__main__":
    main()
