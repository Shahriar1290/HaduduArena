# Hadudu Arena: A Kabaddi Raid-and-Tackle Game Using Adversarial Search and MCTS

*Lab report outline: CSE 3210 Artificial Intelligence Laboratory (with CSE 3209)*

---

## 1. Introduction
- Hadudu / Kabaddi: the national game of Bangladesh. A raider "holds his breath" (chanting *ha-du-du-du*), crosses into the opponents' half, touches defenders and has to get home before he is tackled.
- Why it suits adversarial search:
  - two teams with opposite goals (zero-sum score difference)
  - fully observable and deterministic (no dice, no hidden cards)
  - a natural tension between risk and reward (go deeper and touch more, or come home safely)
  - turn-based once a raid is split into single actions
- How our project differs from typical lab games (Checkers, Connect Four, Quoridor, …): it models a real sport, players act in an uneven order, and there is a scoring/revival system.
- Objectives: formulate the game, build Minimax/Alpha-Beta and MCTS agents, add fuzzy logic and a CSP, compare them experimentally.

## 2. Game Description
- Court (6 × 8 grid, halves, centre line), teams, start formation (figure: screenshot of the court).
- Raid sequence: pick → raider action → defender action → … ; breath = 6.
- How a raid ends: success, out of breath, tackle (3 adjacent defenders), no legal action.
- Scoring: touch points, tackle point, all out (+2), revival order.
- Empty raids and do-or-die (and why the rule was needed: AIs drew 0–0 without it).
- Match length: 16 raids, komi option.
- Simplifications compared with real Kabaddi (7 players, bonus line, super tackle, lobbies, timed raids).

## 3. Problem Formulation
- **State**: positions, in/out status + revival queue, scores, raid number, first raider, phase, raider, breath, crossed flag, tagged set, empty-raid counters, do-or-die flag (show the `GameState` NamedTuple).
- **Initial state**: classic or CSP-generated formation, mirrored.
- **PLAYER(s)**: attacker in pick/raider phases, defender in defender phase. Note that turns do *not* strictly alternate.
- **ACTIONS(s)**: pick / step / touch / stop / move / hold (with legality conditions).
- **RESULT(s, a)**: transition model, immutable state (no deepcopy).
- **TERMINAL(s)**: 16 raids played.
- **UTILITY(s)**: score A − score B (+ komi for the first raider).
- Size of the problem: branching factor (5 picks, ≈ 7–9 raider actions, ≈ 20–30 defender actions), about 130 plies per match. Why full Minimax is impossible.

## 4. Algorithms
### 4.1 Uninformed and informed path search (BFS, A*)
- `safe_return_cost`: A* on the 8-connected grid, step cost 1 + 2 × adjacent defenders, heuristic = columns left to the centre line (admissible, consistent).
- `intercept_distance`: BFS distance from each defender to the raider.
- Test: A* is never worse than the penalised BFS path; paths are valid.

### 4.2 Evaluation function (imperfect real-time decisions)
- Formula and meaning of each term (score, players in, gain, risk, A* return cost vs breath, do-or-die pressure).
- Weight tuning (`experiments/tune_weights.py`): a 4×4 grid against the brief's 4 / 2, then a 48-game check. Gain 8 / risk 1 won 90 % at depth 3 and 69 % at depth 4, with no difference at depth 2. Discuss why a bolder raider is better and why the do-or-die pressure term was added.

### 4.3 Minimax
- `MINIMAX`, `MAX_VALUE`, `MIN_VALUE` (same as the Tic-Tac-Toe lab) with the `VALUE` dispatcher, needed because turns do not strictly alternate.
- Depth limit and cutoff test.

### 4.4 Alpha-Beta pruning
- α/β meaning, pruning condition, node/prune counters.
- Move ordering (touch first, homeward steps when breath is low, tackle-completing defender moves first).
- Test: same values as Minimax on 20 random mid-raid states.
- Table: nodes with/without ordering, speed at depth 2/3/4 (for example, 12 opening moves at depth 4 took 0.13 s and about 12k nodes).

### 4.5 Monte Carlo Tree Search
- Selection (UCB1, c = 1.4), expansion, simulation, backpropagation (reward from the mover's point of view).
- Playout horizon (current raid + 2 raids) and reward `sigmoid((A − B)/2)`.
- Random vs heuristic (guided) playouts: pure random playouts were weak because random defenders almost never tackle. Guided MCTS beat random-playout MCTS 90 % – 0 %.
- Iterations per difficulty (300 / 800 / 2000).

### 4.6 Fuzzy logic: raider risk appetite (Mamdani)
- Inputs, membership functions (figure), rule base (table), min/max inference, centroid defuzzification.
- How aggression changes the evaluation weights; the aggression meter in the UI.

### 4.7 CSP: defensive formations
- Variables, domains, hard constraints, soft constraints.
- Backtracking + MRV + forward checking (including the row-coverage look-ahead).
- Use in the game (random but fair start formations).

## 5. Implementation
- Module structure (`game/`, `ai/`, `ui/`, `experiments/`, `tests/`), rules separated from the UI.
- Pygame UI: Human vs AI and AI vs AI modes, hand-drawn player characters, threaded AI, overlays (A* path, tackle zone, breath bar, aggression meter, log, ticker).
- Testing: list of the test groups and the comparison against the reference prototype (200 random action sequences, identical after every action).

## 6. Experimental Setup
- Hardware / Python version.
- Tournament script, the 4-game colour/first-raider rotation, seeds.
- Matchups: Minimax 2/3/4 against each other; Minimax vs MCTS; Fuzzy Minimax vs Minimax; MCTS 300 vs 2000; Alpha-Beta with and without move ordering; random vs heuristic playouts.

## 7. Results
*(numbers from the first run are in README → "Results summary"; raw data in `results/*.csv`)*

| Matchup | Games | X win % | Draw % | Y win % | Avg score X–Y | Avg time X / Y (ms) | Avg nodes X / Y |
|---|---|---|---|---|---|---|---|
| Minimax d2 vs d3 | 20 | 5 | 15 | 80 | 1.80–4.65 | 0.8 / 6.6 | 46 / 354 |
| Minimax d3 vs d4 | 20 | 10 | 10 | 80 | 1.05–3.65 | 5.9 / 19.9 | 290 / 907 |
| Minimax d3 vs MCTS 800 | 20 | 75 | 0 | 25 | 5.05–3.15 | 3.8 / 225 | 223 / 800 |
| Fuzzy d3 vs Minimax d3 | 20 | 45 | 5 | 50 | 2.90–2.95 | 6.2 / 6.4 | 309 / 323 |
| MCTS 300 vs MCTS 2000 | 12 | 42 | 25 | 33 | 3.25–3.25 | 88 / 607 | 300 / 2000 |
| Minimax d4 vs d4 (no ordering) | 8 | 50 | 12 | 38 | 1.75–1.38 | 19.5 / 23.1 | 877 / 1031 |

- Alpha-Beta node counts with and without ordering.
- Decision time vs depth / iterations (chart).

## 8. The First-Raider Advantage and Komi
- Observation: under random play the second raider wins far more often (about 48 % vs 27 % in 3000 games).
- Hypothesis: shallow search favours the second raider, deeper search is closer to even.
- Komi sweep (first raider's expected score, win = 1, draw = ½):

| Agents | Komi 0 | Komi 1 | Komi 2 |
|---|---|---|---|
| Minimax d2 self-play (40 games, deterministic) | 0 % | **50 %** | 100 % |
| Minimax d3 self-play (40 games) | 40 % | **55 %** | 75 % |
| MCTS 800 self-play (20 games) | **55 %** | 65 % | 95 % |

- The fair komi depends on the agents' strength: 1 for Minimax, 0 for MCTS. Discuss sample size.

## 9. Discussion
- Why depth matters (a raid is many plies long: the horizon effect).
- Minimax vs MCTS in a game with uneven turns and long raids.
- Effect of the fuzzy risk appetite.
- What the evaluation function misses.

## 10. Limitations & Future Work
- 7 players per side, bonus line, super tackle (tackle with ≤ 3 defenders = 2 points), simultaneous revival rules, lobby areas.
- Real-time (non-turn-based) movement; several defenders moving at once.
- Transposition tables, iterative deepening with time limits, learned evaluation functions.
- Smarter MCTS playouts, RAVE, parallel MCTS.

## 11. Conclusion
- Summary of what was built and the main experimental findings.

## References
- Russell & Norvig, *Artificial Intelligence: A Modern Approach* (adversarial search, MCTS, CSP).
- Kocsis & Szepesvári (2006), *Bandit based Monte-Carlo planning* (UCT).
- Mamdani & Assilian (1975), fuzzy logic controller.
- Course lab sheets, CSE 3210.
