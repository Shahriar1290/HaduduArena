# Hadudu Arena

**A Kabaddi Raid-and-Tackle Game Using Adversarial Search and MCTS**
CSE 3210 Artificial Intelligence Laboratory project

Hadudu (Kabaddi) is the national game of Bangladesh. A raider "holds his breath" and chants
*ha-du-du-du* while he runs into the other team's half, touches defenders and tries to get
home before they tackle him. Hadudu Arena turns this into a two-team, turn-based strategy game
on a small grid, with Human vs AI and AI vs AI modes. Every player is a hand-drawn character with
his own name and look. The AIs use
Minimax/Alpha-Beta, Monte Carlo Tree Search, a Mamdani fuzzy system and a CSP.

> The rules are a **simplified version of real Kabaddi** (5 players, a grid court, no bonus
> line, no super tackle). Everything is drawn in code: no logos, photos or sounds.

---

## Install and run

```bash
pip install -r requirements.txt
python main.py
```

Python 3.10+ is required. All commands are run from the `hadudu_arena` folder.

| What | Command |
|---|---|
| Pygame game (menu) | `python main.py` |
| Console game vs an AI | `python main.py --text` (you are Team A vs Minimax depth 3) |
| Console game as Team B | `python main.py --text --a mcts:800 --b human` |
| Tests | `python -m pytest -q` |
| AI tournament | `python -m experiments.tournament --games 50 --a minimax:3 --b mcts:800 --seed 1` |
| Komi experiment | `python -m experiments.tournament --games 40 --a minimax:3 --b minimax:3 --komi-sweep 0,1,2` |
| Preset matchups | `python -m experiments.tournament --preset depth --games 20` (`--list-presets` lists them) |
| Weight tuning | `python -m experiments.tune_weights --depth 3 --games 24` |

Agent specs: `human`, `random`, `minimax:<depth or easy|medium|hard>`, `minimax-noorder:<depth>`,
`fuzzy:<depth or level>`, `mcts:<iterations or level>`, `mcts-random:<iterations>` (MCTS with
pure random playouts).

---

## Rules

```
 col:  0   1   2   3 | 4   5   6   7
 r0    .   .   A1  . | .   B1  .   .        Team A (green) owns columns 0-3
 r1    .   .   .   A2| B2  .   .   .        Team B (red)   owns columns 4-7
 r2    .   .   .   . | .   .   .   .
 r3    .   A3  .   . | .   .   B3  .        Moves: 1 cell in any of 8 directions
 r4    .   .   .   A4| B4  .   .   .
 r5    .   .   A5  . | .   B5  .   .
                     ^ centre line
```

- **Match:** 16 raids, 8 per team, alternating. The first raider can be set (A, B or coin toss).
  Highest score wins; a tie is a draw. *Komi* gives extra points to the team that raids first.
- **Raid:** the attackers pick a raider, who gets **6 breath**. He then alternates with the defenders:
  - raider: **step** to an empty neighbouring cell (1 breath), **touch** = tag every untagged defender
    next to him, only in the defenders' half (1 breath), or **stop** (free; only before crossing and
    not on a do-or-die raid; ends the raid as an empty raid);
  - defenders: **move** one defender one cell inside their half, or **hold**.
- **Raid end** (checked after every raider action, in this order):
  1. **Success:** back in his own half after crossing. Each tagged defender is out, +1 point each.
  2. **Out of breath:** in the defenders' half he is caught; in his own half it is an empty raid.
  3. **Tackle:** 3 or more defenders around him in their half, so he is caught. This is also checked after every defender move.
  A raider with no legal action is caught.
- **Caught:** the raider is out, his tags are cancelled, and the defenders get +1.
- **Empty raid / do-or-die:** after 2 empty raids by a team, its next raid is do-or-die: no stop,
  and an empty raid costs the raider and gives the defenders +1. Any point resets both counters.
- **Revival:** each point scored brings back one of your out players (oldest first) to his start
  cell, or the nearest free cell if it is taken.
- **All out (lona):** if a whole team is out, the other team gets +2 and all 5 come back.

## Controls

| Situation | Control |
|---|---|
| Pick a raider | click one of your players |
| Raider turn | click a highlighted cell to step · `T` / Touch · `S` / Stop (only shown when legal) |
| Defender turn | click a defender, then a highlighted cell · `H` / Hold |
| Any time | `U` undo (Human vs AI) · `R` restart · `Esc` menu · mouse wheel scrolls the log |
| AI vs AI | `A` auto on/off · `N` single step · speed slider · run an N-match series |

## Game modes

- **Human vs AI:** pick your team, the AI type (Minimax α-β, MCTS, Fuzzy Minimax) and the difficulty
  (Easy / Medium / Hard = 2 / 3 / 4 plies or 300 / 800 / 2000 MCTS iterations).
- **AI vs AI:** pick an agent for each team. Watch it play with Auto or Step and set the speed, or run an
  N-match series (colours and the first raider swap every match) with a live scoreboard.

Menu settings: first raider (A, B, coin toss), komi, formation (Classic / Random CSP), seed.

## The players

Every player is a character drawn in code (`ui/characters.py`), with his own name, skin tone, hairstyle
and face. Each body is built from a skeleton of joints with realistic proportions: tapered, outlined
and shaded limbs, a sleeveless kabaddi vest with his number, striped shorts and bare feet with
team-colour anklets. Frames are drawn 3× larger and scaled down for smooth edges, then cached.
Characters are a little taller than a court cell, so they stand on the court like real players. The raider runs with a reaching arm and chants "ha-du-du-du" in a speech bubble.
Defenders drop into a low tackling crouch during a raid, and everyone else stands and breathes.
The names also appear in the raid log.

| # | Team A (green) | Team B (red) |
|---|---|---|
| 1 | Rafiq | Jewel |
| 2 | Sumon | Kamal |
| 3 | Babul | Rubel |
| 4 | Hasan | Shahin |
| 5 | Milon | Tipu |

The screen shows the court with chalk lines, a breath bar, a DO-OR-DIE banner, team panels
(in/out, empty-raid counters), the **A\* safe-return path** (dashed blue line with its cost),
tagged defenders (orange rings), a flashing **tackle zone** when one more defender move would
complete a tackle, the **fuzzy aggression meter**, a scrollable raid log and the "ha-du-du-du" ticker.
AI moves run in a background thread, so the window never freezes.

**Making the action easy to follow**
- **Raid-result banners:** SUCCESSFUL RAID / SUPER RAID (3+ tags), TACKLE!, OUT OF BREATH!, BOXED IN!,
  DO-OR-DIE FAILED, EMPTY RAID and ALL OUT! appear over the half of the court away from the action.
  The AI waits until you have seen them.
- **AI move preview:** the AI's chosen move is shown for a moment before it is played. Steps and
  defender moves get an arrow; picks, touches, stops and holds get a label.
- **Step safety colours (your raider):** each legal step is green *safe*, yellow *risky*, red
  *danger* (a tackle, or not enough breath left to get home by the A* path) or blue *home*.
- **Touch preview:** the defenders a Touch would tag get a pulsing ring and a "TAG?" label.

**Players that react**
- A successful raider jumps and celebrates. A tackled raider falls, the defenders around him pile in,
  and then he walks off.
- Players who go out walk to the side line and sit on their team's **bench** in the side panel, in
  revival order. The one marked *next* comes back first.
- Defenders near the raider crouch and turn to watch him, while those far away stay relaxed.

**Side panel**
- A turn banner at the top says whose turn it is and what to do (it pulses on your turn).
- The breath bar shows "3 / 6" and pulses red with "get home!" when 2 or fewer breaths are left.
- **AI thinking:** the last AI decision's top 3 moves.
  - Alpha-Beta shows its values. Only the chosen move has an exact value; "≤ v" means the branch was
    pruned and can be no better than v.
  - MCTS shows visit counts and win rates.
  - Fuzzy Minimax also shows its aggression.
- **Score by raid:** a small timeline chart of both teams' scores.

---

## How the AI works (mapped to the syllabus)

| Syllabus topic | Where | What it does |
|---|---|---|
| Problem formulation | `game/rules.py`, `game/state.py` | `PLAYER`, `ACTIONS`, `RESULT`, `TERMINAL`, `UTILITY`, the same names as the Minimax lab. Immutable `GameState` (NamedTuple of tuples), so `RESULT` never changes its input. **One ply = one single action.** |
| Uninformed search (BFS) | `ai/pathing.py` | `intercept_distance`: BFS distance of each defender to a cell next to the raider. `bfs_return_path`: the unweighted path home. |
| Informed search (A*) | `ai/pathing.py` | `safe_return_cost`: A* home for the raider. Step cost = 1 + 2 × adjacent defenders; heuristic = columns left to the centre line (admissible). Drawn on screen. |
| Evaluation / imperfect real-time decisions | `ai/evaluation.py` | `10·(score diff) + 3·(players in diff) ± (W_GAIN·tags − W_RISK·(adjacent defenders + 2·max(0, A* cost − breath) + do-or-die pressure))`, with tuned W_GAIN = 8 and W_RISK = 1. |
| Minimax | `ai/minimax.py` | `MINIMAX`, `MAX_VALUE`, `MIN_VALUE`, plus a `VALUE` dispatcher because the same team can act twice in a row (pick, then step). |
| Alpha-Beta | `ai/minimax.py` | `alpha_beta` with node/prune counters and move ordering (touch first, homeward steps on low breath, tackle-completing defender moves first). |
| Monte Carlo Tree Search | `ai/mcts.py` | Selection with UCB1 (c = 1.4), expansion, simulation, backpropagation. Playouts stop after the current raid + 2 raids and score `sigmoid((A−B)/2)`. |
| Fuzzy logic (Mamdani) | `ai/fuzzy.py` | Inputs breath / defenders near / score gap / do-or-die → *aggression*. Triangular/trapezoid MFs, 12 rules, min-AND, max aggregation, centroid. `FuzzyMinimaxAgent` scales the gain and risk weights with it. |
| CSP | `ai/formation_csp.py` | Backtracking + MRV + forward checking to place 5 players with hard constraints (all different, row coverage, ≤ 2 per column) and soft penalties. Used for the "Random CSP" formation. |

### Design notes

- **Minimax vs Alpha-Beta:** both give the same value (tested on random mid-raid states), but Alpha-Beta
  visits far fewer nodes. Plain Minimax only finishes at shallow depth.
- **MCTS playouts:** with purely random playouts MCTS was weak, because random defenders almost never
  tackle. The default is a light *heuristic playout* policy: defenders always complete a tackle if they
  can and often move toward the raider; raiders with tags usually head home. `mcts-random:N` keeps
  the pure random version for comparison.
- **Do-or-die pressure:** shallow searches used to let a do-or-die raid run out of breath at home.
  The evaluation now adds a penalty that grows each turn the raider spends without a tag on a do-or-die raid.

### Weight tuning

The brief started with gain weight 4 and risk weight 2. `experiments/tune_weights.py` played a 4×4 grid
of (gain, risk) values against that baseline at depth 3 (24 games each), then re-checked the best
candidates with 48 games on a new seed:

| gain / risk | 4 / 2 (baseline mirror) | 6 / 1 | 8 / 1 | 8 / 2 | 10 / 1 | 12 / 1 |
|---|---|---|---|---|---|---|
| win % vs 4 / 2 (depth 3, 48 games) | 40 (8 % draws) | 90 | 90 | 73 | 92 | 92 |

So a bolder raider (a high gain:risk ratio) wins clearly, and the curve flattens above 8:1.
We chose **gain 8 / risk 1**. At depth 4 it beat 4 / 2 in 69 % of 16 games. At depth 2 it made no
difference (50 %), because a 2-ply search sees too little of a raid for the weights to matter. The
baseline-vs-itself row (40 % / 52 %) shows the sampling noise is about ±10 % at 48 games.
The fuzzy agent multiplies these tuned weights: `W_GAIN·(0.5 + aggression)` and `W_RISK·(1.5 − aggression)`.

## Project layout

```
hadudu_arena/
  main.py                    entry point (GUI or --text)
  game/state.py              GameState (immutable), initial state, geometry helpers
  game/rules.py              PLAYER, ACTIONS, RESULT, TERMINAL, UTILITY
  ai/pathing.py              A* safe return, BFS interception
  ai/evaluation.py           heuristic evaluation
  ai/minimax.py              MINIMAX / MAX_VALUE / MIN_VALUE, Alpha-Beta, move ordering
  ai/mcts.py                 MCTS with UCB1
  ai/fuzzy.py                Mamdani fuzzy system (hand-written)
  ai/formation_csp.py        CSP formation generator
  ai/agents.py               Human / Random / Minimax / MCTS / FuzzyMinimax agents
  ui/theme.py, ui/renderer.py, ui/screens.py     Pygame front end
  ui/characters.py           the 10 player characters (names, looks, poses)
  experiments/tournament.py  headless AI-vs-AI series -> results/*.csv
  experiments/tune_weights.py  evaluation-weight tuning
  reference/reference_rules.py the original rules prototype (used only by the tests)
  tests/                     pytest tests
  docs/report_outline.md     lab report outline
```

## Tests

`python -m pytest -q` runs:
- the rules: start layout, legal-move counts, touch/stop legality, tackle, success, revival, all out,
  do-or-die, breath expiry, 16-raid end, immutability, random games terminating;
- a comparison with the reference prototype on 200 random action sequences (same legal actions,
  positions and scores after every action);
- A*/BFS, evaluation, Alpha-Beta = Minimax, MCTS, agents, fuzzy, CSP;
- headless UI smoke tests (SDL dummy driver).

## Results summary

Machine: Windows 11, Python 3.13, single thread. Seed 1. Colours and the first raider rotate in a
4-game cycle. The raw CSVs are in `results/`, and `results/experiment_log.txt` has the full console output.
Samples are small (8–40 games), so differences under about 15 % are within noise.

### Matchups (no komi)

| X vs Y | Games | X win | Draw | Y win | Avg score X–Y | Avg time/decision X / Y | Avg nodes X / Y |
|---|---|---|---|---|---|---|---|
| Minimax d3 vs MCTS 800 | 20 | **75 %** | 0 % | 25 % | 5.05 – 3.15 | 3.8 ms / 225 ms | 223 / 800 |
| Minimax d2 vs Minimax d3 | 20 | 5 % | 15 % | **80 %** | 1.80 – 4.65 | 0.8 / 6.6 ms | 46 / 354 |
| Minimax d3 vs Minimax d4 | 20 | 10 % | 10 % | **80 %** | 1.05 – 3.65 | 5.9 / 19.9 ms | 290 / 907 |
| Minimax d2 vs Minimax d4 | 20 | 15 % | 0 % | **85 %** | 0.85 – 4.60 | 1.0 / 21.8 ms | 49 / 1029 |
| Fuzzy d3 vs Minimax d3 | 20 | 45 % | 5 % | 50 % | 2.90 – 2.95 | 6.2 / 6.4 ms | 309 / 323 |
| Minimax d4 vs d4 without ordering | 8 | 50 % | 12 % | 38 % | 1.75 – 1.38 | 19.5 / 23.1 ms | **877 / 1031** |
| MCTS 800 (guided) vs MCTS 800 (random playouts) | 20 | **90 %** | 10 % | 0 % | 3.95 – 1.15 | 299 / 198 ms | 800 / 800 |
| MCTS 300 vs MCTS 2000 | 12 | 42 % | 25 % | 33 % | 3.25 – 3.25 | 88 / 607 ms | 300 / 2000 |

Takeaways:
- Each extra ply of Alpha-Beta wins about 80 % of games.
- Minimax d3 beats MCTS 800 while being about 60× faster per move.
- Move ordering saves about 15 % of the nodes (the score-based evaluation has many ties, which limits pruning).
- Guided playouts are essential for MCTS.
- More MCTS iterations did not help measurably with these short playouts.
- The fuzzy agent is level with plain Minimax at the same depth.

### First-raider advantage and komi

| Agents (self-play) | Komi | First raider win | Second raider win | Draw | First raider expected score |
|---|---|---|---|---|---|
| Minimax d2 (40 games) | 0 | 0 % | 100 % | 0 % | 0 % |
| | **1** | 0 % | 0 % | 100 % | **50 %** |
| | 2 | 100 % | 0 % | 0 % | 100 % |
| Minimax d3 (40 games) | 0 | 38 % | 58 % | 5 % | 40 % |
| | **1** | 42 % | 32 % | 25 % | **55 %** |
| | 2 | 68 % | 18 % | 15 % | 75 % |
| MCTS 800 (20 games) | **0** | 45 % | 35 % | 20 % | **55 %** |
| | 1 | 65 % | 35 % | 0 % | 65 % |
| | 2 | 95 % | 5 % | 0 % | 95 % |

Expected score counts a win as 1 and a draw as ½, so 50 % means fair.
- **Depth-2 search strongly favours the second raider.** Depth-2 self-play is deterministic: every
  game ends 2–1 to the team that raids second.
- **Depth 3 is much closer to even** (40 %). This confirms the brief's hypothesis.
- **Komi 1** is fairest for Minimax at depth 2 and 3. **Komi 0** is fairest for MCTS.
- The fair komi depends on the agents' strength, so we keep komi 0 as the default and offer komi as a setting.
