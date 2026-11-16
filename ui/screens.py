"""Screens: main menu, match setup, rules, game and results.

The App owns the window and the current screen. Each screen has
handle(event), update(now) and draw(surface).
"""
from __future__ import annotations

import math
import random
import threading
import time

import pygame

from ai.agents import FuzzyMinimaxAgent, HumanAgent, make_agent
from ai.fuzzy import state_aggression
from ai.pathing import safe_return_cost
from game.rules import (ACTIONS, PLAYER, RESULT, TERMINAL, describe_action, describe_outcome,
                        score_diff)
from game.state import CLASSIC_START_A, TEAM_NAMES, chebyshev, in_half, initial_state
from ui import theme as T
from ui.characters import clear_cache, draw_character, player_name
from ui.renderer import Renderer, legal_tackle_threat, wrap

AI_TYPES = {"Minimax α-β": "minimax", "MCTS": "mcts", "Fuzzy Minimax": "fuzzy", "Random": "random"}
DIFFICULTIES = ["Easy", "Medium", "Hard"]


# ======================================================================
# Small widgets
# ======================================================================
class Button:
    def __init__(self, rect, label, on_click, key_hint="", visible=lambda: True,
                 enabled=lambda: True, size=18):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.key_hint = key_hint
        self.visible = visible
        self.enabled = enabled
        self.size = size

    def handle(self, event) -> bool:
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.visible()
                and self.enabled() and self.rect.collidepoint(event.pos)):
            self.on_click()
            return True
        return False

    def draw(self, surf):
        if not self.visible():
            return
        label = self.label() if callable(self.label) else self.label
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        on = self.enabled()
        col = T.BUTTON_OFF if not on else T.BUTTON_HOVER if hover else T.BUTTON
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        pygame.draw.rect(surf, T.SAND_DARK if on else T.BUTTON_OFF, self.rect, 2, border_radius=8)
        text = label + (f"  [{self.key_hint}]" if self.key_hint else "")
        img = T.font(self.size, True).render(text, True, T.TEXT if on else T.TEXT_DIM)
        surf.blit(img, img.get_rect(center=self.rect.center))


class Selector:
    """'Label   < value >' - click the arrows (or the value) to cycle options."""

    def __init__(self, x, y, w, label, options, index=0):
        self.label = label
        self.options = list(options)
        self.index = index
        self.rect = pygame.Rect(x, y, w, 40)
        self.left = pygame.Rect(self.rect.right - 230, y + 4, 32, 32)
        self.right = pygame.Rect(self.rect.right - 36, y + 4, 32, 32)
        self.value_rect = pygame.Rect(self.left.right, y, self.right.left - self.left.right, 40)

    @property
    def value(self):
        return self.options[self.index]

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.left.collidepoint(event.pos):
                self.index = (self.index - 1) % len(self.options)
                return True
            if self.right.collidepoint(event.pos) or self.value_rect.collidepoint(event.pos):
                self.index = (self.index + 1) % len(self.options)
                return True
        return False

    def draw(self, surf):
        lbl = T.font(18).render(self.label, True, T.TEXT_DIM)
        surf.blit(lbl, lbl.get_rect(midleft=(self.rect.x, self.rect.centery)))
        for r, ch in ((self.left, "<"), (self.right, ">")):
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surf, T.BUTTON_HOVER if hover else T.BUTTON, r, border_radius=6)
            img = T.font(18, True).render(ch, True, T.TEXT)
            surf.blit(img, img.get_rect(center=r.center))
        val = T.font(18, True).render(str(self.value), True, T.TEXT)
        surf.blit(val, val.get_rect(center=self.value_rect.center))


class Slider:
    def __init__(self, rect, value=0.5, label=""):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.label = label
        self.dragging = False

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and \
                self.rect.inflate(0, 16).collidepoint(event.pos):
            self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        else:
            return False
        if self.dragging:
            self._set(event.pos[0])
        return True

    def update(self):
        if self.dragging:
            self._set(pygame.mouse.get_pos()[0])

    def _set(self, x):
        self.value = min(1.0, max(0.0, (x - self.rect.x) / self.rect.w))

    def draw(self, surf):
        lbl = T.font(15).render(self.label, True, T.TEXT_DIM)
        surf.blit(lbl, lbl.get_rect(midright=(self.rect.x - 10, self.rect.centery)))
        pygame.draw.rect(surf, T.PANEL_CARD, self.rect, border_radius=5)
        fill = self.rect.copy()
        fill.w = int(self.rect.w * self.value)
        pygame.draw.rect(surf, T.GOLD, fill, border_radius=5)
        pygame.draw.circle(surf, T.TEXT, (self.rect.x + fill.w, self.rect.centery), 9)


def draw_backdrop(surf, title="HADUDU ARENA", subtitle=None, centre_line=True):
    surf.fill(T.BG)
    # chalk court silhouette in the background
    court = pygame.Rect(60, 150, T.WIDTH - 120, T.HEIGHT - 210)
    pygame.draw.rect(surf, (58, 48, 38), court, border_radius=4)
    pygame.draw.rect(surf, (90, 78, 62), court, 3)
    if centre_line:
        pygame.draw.line(surf, (90, 78, 62), (court.centerx, court.y), (court.centerx, court.bottom), 3)
    img = T.font(54, True).render(title, True, T.SAND)
    surf.blit(img, img.get_rect(center=(T.WIDTH / 2, 62)))
    if subtitle:
        sub = T.font(18).render(subtitle, True, T.TEXT_DIM)
        surf.blit(sub, sub.get_rect(center=(T.WIDTH / 2, 112)))


# ======================================================================
# App
# ======================================================================
class App:
    def __init__(self):
        pygame.init()
        T.reset_fonts()
        clear_cache()
        pygame.display.set_caption("Hadudu Arena")
        self.surface = pygame.display.set_mode((T.WIDTH, T.HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.settings = {"first": "A", "komi": 0.0, "formation": "Classic", "seed": "random"}
        self.screen = MenuScreen(self)

    def go(self, screen):
        if hasattr(self.screen, "leave"):
            self.screen.leave()
        self.screen = screen

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.screen.handle(event)
            self.screen.update(time.perf_counter())
            self.screen.draw(self.surface)
            pygame.display.flip()
            self.clock.tick(T.FPS)
        if hasattr(self.screen, "leave"):
            self.screen.leave()
        pygame.quit()


def run_app():
    App().run()


# ======================================================================
# Menu
# ======================================================================
class MenuScreen:
    def __init__(self, app: App):
        self.app = app
        st = app.settings
        x, w = 160, 300
        self.buttons = [
            Button((x, 190 + k * 70, w, 54), label, cb, size=22)
            for k, (label, cb) in enumerate([
                ("Human vs AI", lambda: app.go(SetupScreen(app, "hva"))),
                ("AI vs AI", lambda: app.go(SetupScreen(app, "ava"))),
                ("Rules", lambda: app.go(RulesScreen(app))),
                ("Quit", self.quit),
            ])
        ]
        sx, sw = 560, 400
        seeds = ["random"] + list(range(1, 21)) + [42]
        komis = [0.0, 0.5, 1.0, 1.5, 2.0]
        self.selectors = {
            "first": Selector(sx, 230, sw, "First raider", ["A", "B", "Coin toss"],
                              ["A", "B", "Coin toss"].index(st["first"])),
            "komi": Selector(sx, 290, sw, "Komi", komis, komis.index(st["komi"])),
            "formation": Selector(sx, 350, sw, "Formation", ["Classic", "Random CSP"],
                                  ["Classic", "Random CSP"].index(st["formation"])),
            "seed": Selector(sx, 410, sw, "Seed", seeds, seeds.index(st["seed"])),
        }

    def quit(self):
        self.app.running = False

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        for key, sel in self.selectors.items():
            if sel.handle(event):
                self.app.settings[key] = sel.value
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.quit()

    def update(self, now):
        pass

    def draw(self, surf):
        draw_backdrop(surf, subtitle="A Kabaddi raid-and-tackle game · Adversarial Search, MCTS, Fuzzy Logic & CSP")
        for b in self.buttons:
            b.draw(surf)
        hdr = T.font(20, True).render("Settings", True, T.SAND)
        surf.blit(hdr, (560, 190))
        for sel in self.selectors.values():
            sel.draw(surf)
        notes = ["Komi = extra points for the team that raids first.",
                 "Random CSP = start formation from the constraint solver",
                 "(mirrored for Team B so the match stays fair)."]
        for k, line in enumerate(notes):
            img = T.font(14).render(line, True, T.TEXT_DIM)
            surf.blit(img, (560, 470 + k * 20))
        # meet the teams: every player's character in his idle pose
        now = time.perf_counter()
        for team in (0, 1):
            for i in range(5):
                x = (150 + i * 86) if team == 0 else (T.WIDTH - 150 - (4 - i) * 86)
                draw_character(surf, x, 676, team, i, "idle", now, height=128,
                               name_colour=T.TEAM_LIGHT[team])
        vs = T.font(30, True).render("vs", True, T.SAND)
        surf.blit(vs, vs.get_rect(center=(T.WIDTH / 2, 620)))
        foot = T.font(14).render("CSE 3210 Artificial Intelligence Laboratory", True, T.TEXT_DIM)
        surf.blit(foot, foot.get_rect(center=(T.WIDTH / 2, T.HEIGHT - 24)))


# ======================================================================
# Setup for Human vs AI and AI vs AI
# ======================================================================
class SetupScreen:
    def __init__(self, app: App, mode: str):
        self.app = app
        self.mode = mode
        types = list(AI_TYPES)
        x, w = 300, 500
        if mode == "hva":
            self.selectors = [
                Selector(x, 220, w, "Your team", ["A (green)", "B (red)"]),
                Selector(x, 280, w, "AI type", types[:3]),
                Selector(x, 340, w, "Difficulty", DIFFICULTIES, 1),
            ]
        else:
            self.selectors = [
                Selector(x, 200, w, "Team A agent", types, 0),
                Selector(x, 250, w, "Team A difficulty", DIFFICULTIES, 1),
                Selector(x, 330, w, "Team B agent", types, 1),
                Selector(x, 380, w, "Team B difficulty", DIFFICULTIES, 1),
            ]
        self.buttons = [Button((x, 470, 240, 54), "Start", self.start, size=22),
                        Button((x + 260, 470, 240, 54), "Back", lambda: app.go(MenuScreen(app)), size=22)]

    @staticmethod
    def spec(type_label, difficulty):
        kind = AI_TYPES[type_label]
        return kind if kind == "random" else f"{kind}:{difficulty.lower()}"

    def start(self):
        if self.mode == "hva":
            human = 0 if self.selectors[0].index == 0 else 1
            ai = self.spec(self.selectors[1].value, self.selectors[2].value)
            specs = {human: "human", 1 - human: ai}
        else:
            specs = {0: self.spec(self.selectors[0].value, self.selectors[1].value),
                     1: self.spec(self.selectors[2].value, self.selectors[3].value)}
        self.app.go(GameScreen(self.app, specs, self.mode))

    def handle(self, event):
        for s in self.selectors:
            s.handle(event)
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go(MenuScreen(self.app))

    def update(self, now):
        pass

    def draw(self, surf):
        draw_backdrop(surf, subtitle="Human vs AI" if self.mode == "hva" else "AI vs AI")
        for s in self.selectors:
            s.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        hint = {"Easy": "Minimax 2 plies / MCTS 300 iterations",
                "Medium": "Minimax 3 plies / MCTS 800 iterations",
                "Hard": "Minimax 4 plies / MCTS 2000 iterations"}
        diff = self.selectors[2].value if self.mode == "hva" else self.selectors[1].value
        img = T.font(14).render(hint[diff], True, T.TEXT_DIM)
        surf.blit(img, (300, 420 if self.mode == "hva" else 430))


# ======================================================================
# Rules
# ======================================================================
RULES_TEXT = [
    "Court: 6 rows x 8 columns. Team A (green) owns columns 0-3, Team B (red) columns 4-7.",
    "Players move one cell in any of the 8 directions. Each team has 5 players.",
    "A match is 16 raids, 8 per team, alternating. Highest score wins; a tie is a draw.",
    "",
    "RAID: the attacking team picks a raider. He has 6 breath; each step or touch costs 1.",
    "  Touch tags every untagged defender next to him (only in the defenders' half).",
    "  Stop (free) ends the raid as empty - only before crossing and not on do-or-die.",
    "  After each raider action the defenders move ONE player one cell, or hold.",
    "",
    "SUCCESS: back in his own half after crossing - every tagged defender is out, +1 each.",
    "CAUGHT: 3+ defenders around him in their half, or out of breath there - raider out, +1 defenders.",
    "EMPTY RAID: no points. After 2 empty raids in a row the next raid is DO-OR-DIE:",
    "  no Stop, and an empty raid then costs the raider and gives the defenders +1.",
    "  Any point scored by either team resets both empty-raid counters.",
    "REVIVAL: every point scored brings back one of your out players (oldest first).",
    "ALL OUT (lona): if a whole team is out, the other team gets +2 and the team returns.",
    "",
    "Controls: click a player to pick the raider; click a highlighted cell to step;",
    "T = touch, S = stop, H = hold; defenders: click a defender, then a cell.",
    "U = undo, R = restart, Esc = menu. (A simplified version of real Kabaddi.)",
]


class RulesScreen:
    def __init__(self, app):
        self.app = app
        self.back = Button((T.WIDTH / 2 - 110, T.HEIGHT - 80, 220, 50), "Back",
                           lambda: app.go(MenuScreen(app)), size=22)

    def handle(self, event):
        self.back.handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go(MenuScreen(self.app))

    def update(self, now):
        pass

    def draw(self, surf):
        draw_backdrop(surf, "HOW TO PLAY", centre_line=False)
        for k, line in enumerate(RULES_TEXT):
            col = T.SAND if ":" in line and line.split(":")[0].split(" (")[0].isupper() else T.TEXT
            img = T.font(17).render(line, True, col)
            surf.blit(img, (110, 150 + k * 24))
        self.back.draw(surf)


# ======================================================================
# Game
# ======================================================================
class GameScreen:
    def __init__(self, app: App, specs: dict, mode: str):
        self.app = app
        self.specs = specs
        self.mode = mode                      # 'hva' (Human vs AI) | 'ava' (AI vs AI)
        self.renderer = Renderer(app.surface)
        st = app.settings
        seed = random.randrange(10**9) if st["seed"] == "random" else int(st["seed"])
        self.rng = random.Random(seed)
        first = {"A": 0, "B": 1}.get(st["first"], None)
        if first is None:                     # coin toss
            first = self.rng.randrange(2)
        formation = CLASSIC_START_A
        if st["formation"] == "Random CSP":
            from ai.formation_csp import generate_formation
            formation = generate_formation(seed)
        self.agents = {t: HumanAgent() if specs[t] == "human"
                       else make_agent(specs[t], seed=self.rng.randrange(10**9)) for t in (0, 1)}
        self.state = initial_state(first=first, komi=float(st["komi"]), formation_a=formation)
        self.history = [(self.state, 0)]     # (state, log length) for undo
        self.log = [f"Match start · seed {seed} · Team {TEAM_NAMES[first]} raids first"
                    + (f" · formation {formation}" if st["formation"] == "Random CSP" else "")]
        self.raid_records = []                # (raid no, attacker, outcome) for the results
        self.log_scroll = 0
        self.anim = {}
        self.flashes = []
        self.selected = None                  # selected defender index (human defender turn)
        self.thinking = None                  # box shared with the AI thread
        self.gen = 0                          # bumped on undo/restart -> stale AI results ignored
        self.ai_ready_at = 0.0
        self.over_at = None
        self.auto = True
        self.step_once = False
        self.speed = Slider((T.COURT_X + 520, T.COURT_Y + T.COURT_H + 110, 120, 10), 0.6, "speed")
        self.series = None
        self.series_n = Selector(0, 0, 10, "", [4, 10, 20], 0)
        self.banner = None                    # raid-result banner: (title, subtitle, colour, t0, duration, y)
        self.effects = []                     # short animations after a raid (celebrate, fall, walk off...)
        self.pending = None                   # AI move shown as a preview before it is played
        self.analysis = None                  # (team, what the AI thought about its last move)
        self._build_buttons()

    # ------------------------------------------------------------ buttons
    def _build_buttons(self):
        y = T.COURT_Y + T.COURT_H + 52
        x = T.COURT_X - 16
        human_turn = self.human_turn
        acts = lambda: ACTIONS(self.state)
        self.buttons = [
            Button((x, y, 120, 40), "Touch", self.do_touch, "T",
                   visible=lambda: self.mode != "ava",
                   enabled=lambda: human_turn() and ("touch",) in acts()),
            Button((x + 128, y, 110, 40), "Stop", self.do_stop, "S",
                   visible=lambda: self.mode != "ava" and human_turn() and ("stop",) in acts()),
            Button((x + 246, y, 110, 40), "Hold", self.do_hold, "H",
                   visible=lambda: self.mode != "ava",
                   enabled=lambda: human_turn() and self.state.phase == "defender"),
            Button((x + 364, y, 100, 40), "Undo", self.undo, "U",
                   visible=lambda: self.mode != "ava", enabled=lambda: len(self.history) > 1),
            Button((x + 472, y, 100, 40), "Restart", self.restart, "R"),
            Button((x + 580, y, 92, 40), "Menu", self.to_menu, "Esc", size=16),
        ]
        if self.mode == "ava":
            y2 = y
            self.buttons[4].rect.topleft = (x + 472, y2)
            self.buttons += [
                Button((x, y2, 150, 40), lambda: "Auto: ON" if self.auto else "Auto: OFF",
                       self.toggle_auto, "A"),
                Button((x + 158, y2, 100, 40), "Step", self.request_step, "N",
                       enabled=lambda: not self.auto and self.series is None),
                Button((x + 266, y2, 198, 40), lambda: "Stop series" if self.series and
                       not self.series["done"] else f"Run {self.series_n.value}-match series",
                       self.toggle_series, size=16),
            ]
            self.series_minus = Button((x + 266, y2 + 44, 40, 28), "-", lambda: self._cycle_series(-1))
            self.series_plus = Button((x + 312, y2 + 44, 40, 28), "+", lambda: self._cycle_series(1))
            self.buttons += [self.series_minus, self.series_plus]

    def _cycle_series(self, d):
        self.series_n.index = (self.series_n.index + d) % len(self.series_n.options)

    # ------------------------------------------------------------ helpers
    def current_agent(self):
        return self.agents[PLAYER(self.state)]

    def human_turn(self) -> bool:
        return not TERMINAL(self.state) and self.current_agent().is_human

    def agent_label(self, team) -> str:
        return self.agents[team].name

    def animating(self, now) -> bool:
        return any(now < t0 + dur for (_, _, t0, dur) in self.anim.values())

    def anim_time(self) -> float:
        if self.mode == "ava":
            return T.STEP_ANIM * (1.4 - self.speed.value)
        return T.STEP_ANIM

    def effect_scale(self) -> float:
        """Banner/effect durations: full length vs a human, shorter at high AI-vs-AI speed."""
        return 1.0 if self.mode == "hva" else max(0.3, 1.15 - self.speed.value)

    def preview_time(self) -> float:
        """How long an AI move is shown (arrow/label) before it is played."""
        return 0.55 if self.mode == "hva" else 0.6 * (1 - self.speed.value)

    def score_points(self):
        """(raid, score A, score B) after each finished raid, for the timeline."""
        pts = {}
        for st, _ in self.history:
            if st.raid > 0:
                pts[st.raid] = st.score
        return [(r, a, b) for r, (a, b) in sorted(pts.items())]

    # ------------------------------------------------------------ applying actions
    def apply(self, action):
        prev = self.state
        new = RESULT(prev, action)
        now = time.perf_counter()
        # step animations (only for one-cell moves inside the same raid)
        self.anim = {}
        for team in (0, 1):
            for i, (p0, p1) in enumerate(zip(prev.pos[team], new.pos[team])):
                if p0 and p1 and p0 != p1 and chebyshev(p0, p1) == 1:
                    self.anim[(team, i)] = (self.renderer.cell_center(p0),
                                            self.renderer.cell_center(p1), now, self.anim_time())
        if new.raid != prev.raid:
            self._raid_finished(prev, action, new, now)
        self.state = new
        self.selected = None
        self.history.append((new, len(self.log)))
        if TERMINAL(new):
            self.over_at = now

    def _raid_finished(self, prev, action, new, now):
        a, d = prev.attacker, prev.defender
        outcome = new.last_outcome
        kind = outcome[0]
        raider_cell = action[1] if action[0] == "step" else prev.raider_cell()
        name = player_name(a, prev.raider) if prev.raider is not None else "The raider"
        k = self.effect_scale()
        if kind in ("caught", "dod_fail") and raider_cell:
            self.flashes.append((raider_cell, a, now))
        if kind == "success":
            n = outcome[1]
            title = "SUPER RAID!" if n >= 3 else "SUCCESSFUL RAID!"
            sub = f"{name} tags {n} · +{n} to Team {TEAM_NAMES[a]}"
            colour = T.TEAM_LIGHT[a]
            # the raider celebrates, the tagged defenders walk off to the bench
            self.effects.append(dict(kind="celebrate", team=a, i=prev.raider, t0=now, dur=1.4 * k))
            for i in prev.tagged:
                self.flashes.append((prev.pos[d][i], d, now))
                self._walk_off(prev.pos[d][i], d, i, now, k)
        elif kind == "caught":
            title = {"tackle": "TACKLE!", "breath": "OUT OF BREATH!", "boxed": "BOXED IN!"}[outcome[1]]
            sub = f"{name} is caught · +1 to Team {TEAM_NAMES[d]}"
            colour = T.TEAM_LIGHT[d]
            # the raider goes down, the defenders around him pile in, then he walks off
            self.effects.append(dict(kind="fallen", team=a, i=prev.raider, cell=raider_cell,
                                     face=1 if a == 0 else -1, t0=now, dur=1.1 * k))
            for j, p in enumerate(new.pos[d]):
                if p is not None and chebyshev(p, raider_cell) == 1:
                    self.effects.append(dict(kind="pile", team=d, i=j, toward=raider_cell, t0=now, dur=0.8 * k))
            self._walk_off(raider_cell, a, prev.raider, now + 1.1 * k, k)
        elif kind == "dod_fail":
            title = "DO-OR-DIE FAILED"
            sub = f"{name} comes back without a touch · +1 to Team {TEAM_NAMES[d]}"
            colour = T.TEAM_LIGHT[d]
            self._walk_off(raider_cell, a, prev.raider, now, k)
        else:
            title, sub, colour = "EMPTY RAID", f"{name} comes back without a touch", T.TEXT_DIM
        if "all_out" in outcome:
            loser = d if kind == "success" else a
            title = "ALL OUT!"
            sub = f"Team {TEAM_NAMES[loser]} is all out · +2 bonus to Team {TEAM_NAMES[1 - loser]}"
            colour = T.GOLD
        # put the banner in the half of the court away from the action, so it hides nothing
        row = raider_cell[0] if raider_cell else 2
        banner_y = T.COURT_Y + T.COURT_H * (0.8 if row <= 2 else 0.2)
        self.banner = (title, sub, colour, now, (1.0 if kind == "empty" else 1.8) * k, banner_y)
        self.ai_ready_at = max(self.ai_ready_at, now + (0.6 if kind == "empty" else 1.3) * k)
        self.raid_records.append((prev.raid + 1, a, outcome))
        text = describe_outcome(outcome)
        self.log.append(f"Raid {prev.raid + 1} · {TEAM_NAMES[a]} ({self.agent_label(a)}): {name} {text}."
                        f"  [{new.score[0]}-{new.score[1]}]")
        self.log_scroll = 0

    def _walk_off(self, cell, team, i, t0, k):
        """A player who is out walks to the nearest side line, then sits on the bench."""
        to_y = (T.COURT_Y - 70) if cell[0] < 3 else (T.COURT_Y + T.COURT_H + 10)
        self.effects.append(dict(kind="walk", team=team, i=i, cell=cell, to_y=to_y, t0=t0, dur=1.0 * k))

    def _effect_layers(self, now):
        """Turn the running effects into pose overrides, ghost characters and
        the set of players who are still walking to the bench."""
        overrides, extras, walking = {}, [], set()
        s = self.state
        for e in self.effects:
            key = (e["team"], e["i"])
            k = (now - e["t0"]) / e["dur"]
            if e["kind"] == "walk" and k < 1:
                walking.add(key)
            if not 0 <= k <= 1:
                continue
            if e["kind"] == "celebrate" and s.pos[e["team"]][e["i"]] is not None:
                overrides[key] = {"pose": "celebrate"}
            elif e["kind"] == "pile" and s.pos[e["team"]][e["i"]] is not None:
                (px, py), (tx, ty) = (self.renderer.cell_center(s.pos[e["team"]][e["i"]]),
                                      self.renderer.cell_center(e["toward"]))
                push = 0.3 * math.sin(math.pi * k)
                overrides[key] = {"pose": "crouch", "offset": ((tx - px) * push, (ty - py) * push),
                                  "face": 1 if tx > px else -1}
            elif e["kind"] == "fallen":
                x, y = self.renderer.cell_center(e["cell"])
                extras.append(dict(x=x, y=y, team=e["team"], i=e["i"], pose="fallen", face=e["face"],
                                   alpha=255 if k < 0.8 else int(255 * (1 - k) / 0.2)))
            elif e["kind"] == "walk":
                x, y0 = self.renderer.cell_center(e["cell"])
                y = y0 + (e["to_y"] - y0) * k
                extras.append(dict(x=x, y=y, team=e["team"], i=e["i"], pose="walk", face=None,
                                   alpha=255 if k < 0.7 else int(255 * (1 - k) / 0.3)))
        return overrides, extras, walking

    # ------------------------------------------------------------ human controls
    def do_touch(self):
        if self.human_turn() and ("touch",) in ACTIONS(self.state):
            self.apply(("touch",))

    def do_stop(self):
        if self.human_turn() and ("stop",) in ACTIONS(self.state):
            self.apply(("stop",))

    def do_hold(self):
        if self.human_turn() and self.state.phase == "defender":
            self.apply(("hold",))

    def click_court(self, pos):
        if not self.human_turn():
            return
        cell = self.renderer.pixel_to_cell(pos)
        if cell is None:
            return
        s = self.state
        team = PLAYER(s)
        if s.phase == "pick":
            for i, p in enumerate(s.pos[team]):
                if p == cell:
                    self.apply(("pick", i))
            return
        if s.phase == "raider":
            if ("step", cell) in ACTIONS(s):
                self.apply(("step", cell))
            return
        # defender: first select one of our players, then a target cell
        for i, p in enumerate(s.pos[team]):
            if p == cell:
                self.selected = None if self.selected == i else i
                return
        if self.selected is not None and ("move", self.selected, cell) in ACTIONS(s):
            self.apply(("move", self.selected, cell))

    def undo(self):
        """Go back to the previous position where a human had to decide."""
        if self.mode == "ava" or len(self.history) <= 1:
            return
        self.gen += 1                         # any AI answer in flight is now stale
        self.history.pop()
        while len(self.history) > 1 and not self.agents[PLAYER(self.history[-1][0])].is_human:
            self.history.pop()
        self.state, log_len = self.history[-1]
        del self.log[log_len:]
        self.raid_records = [r for r in self.raid_records if r[0] <= self.state.raid]
        self.anim, self.flashes, self.selected, self.over_at = {}, [], None, None
        self.effects, self.banner, self.pending = [], None, None
        self.log.append("  (undo)")

    def restart(self):
        self.leave()
        self.app.go(GameScreen(self.app, self.specs, self.mode))

    def to_menu(self):
        self.app.go(MenuScreen(self.app))

    def leave(self):
        self.gen += 1
        if self.series:
            self.series["stop"] = True

    def toggle_auto(self):
        self.auto = not self.auto

    def request_step(self):
        self.step_once = True

    # ------------------------------------------------------------ AI vs AI series
    def toggle_series(self):
        if self.series and not self.series["done"]:
            self.series["stop"] = True
            return
        from experiments.tournament import play_match
        n = self.series_n.value
        st = self.app.settings
        box = {"n": n, "played": 0, "x": 0, "y": 0, "draw": 0, "first_wins": 0, "second_wins": 0,
               "pts_x": 0, "pts_y": 0, "done": False, "stop": False, "last": ""}
        spec_x, spec_y = self.specs[0], self.specs[1]
        seed = self.rng.randrange(10**9)
        self.auto = False

        def worker():
            rng = random.Random(seed)
            for g in range(n):
                if box["stop"]:
                    break
                x_team, first = g % 2, (g // 2) % 2     # colours and first raider swap
                formation = CLASSIC_START_A
                if st["formation"] == "Random CSP":
                    from ai.formation_csp import generate_formation
                    formation = generate_formation(rng.randrange(10**9))
                ax = make_agent(spec_x, rng.randrange(10**9))
                ay = make_agent(spec_y, rng.randrange(10**9))
                r = play_match({x_team: ax, 1 - x_team: ay}, first, float(st["komi"]), formation,
                               should_stop=lambda: box["stop"])
                if box["stop"]:
                    break
                dx = r.diff if x_team == 0 else -r.diff
                box["x" if dx > 0 else "y" if dx < 0 else "draw"] += 1
                if r.diff:
                    box["first_wins" if (r.diff > 0) == (first == 0) else "second_wins"] += 1
                box["pts_x"] += r.score[x_team]
                box["pts_y"] += r.score[1 - x_team]
                box["played"] += 1
                box["last"] = (f"Game {g + 1}: X={TEAM_NAMES[x_team]} first={TEAM_NAMES[first]} "
                               f"{r.score[0]}-{r.score[1]}")
            box["done"] = True

        self.series = box
        self.log.append(f"Series started: X = {self.agents[0].name}, Y = {self.agents[1].name}, "
                        f"{n} matches (colours and first raider swap).")
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ AI thread
    def _start_ai(self):
        agent = self.current_agent()
        state = self.state
        box = {"gen": self.gen, "done": False, "action": None, "error": None, "agent": agent}

        def work():
            try:
                box["action"] = agent.choose_action(state)
            except Exception as exc:          # never kill the UI because of an AI bug
                box["error"] = exc
            box["done"] = True

        self.thinking = box
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ events / update / draw
    def handle(self, event):
        for b in self.buttons:
            if b.handle(event):
                return
        if self.mode == "ava" and self.speed.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.click_court(event.pos)
        elif event.type == pygame.MOUSEWHEEL:
            self.log_scroll = max(0, self.log_scroll + event.y)
        elif event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_ESCAPE:
                self.to_menu()
            elif key == pygame.K_r:
                self.restart()
            elif key == pygame.K_u:
                self.undo()
            elif key == pygame.K_t:
                self.do_touch()
            elif key == pygame.K_s:
                self.do_stop()
            elif key == pygame.K_h:
                self.do_hold()
            elif key == pygame.K_a and self.mode == "ava":
                self.toggle_auto()
            elif key == pygame.K_n and self.mode == "ava":
                self.request_step()

    def update(self, now):
        self.speed.update()
        self.flashes = [f for f in self.flashes if now - f[2] < T.OUT_FLASH]
        # collect a finished AI decision
        if self.thinking and self.thinking["done"]:
            box, self.thinking = self.thinking, None
            if box["gen"] == self.gen and not TERMINAL(self.state):
                if box["error"] is not None:
                    self.log.append(f"AI error: {box['error']!r} - playing a random move")
                    action = random.choice(ACTIONS(self.state))
                else:
                    action = box["action"]
                team = PLAYER(self.state)
                self.analysis = (team, box["agent"].last_analysis)
                # show the chosen move first (arrow / label), play it a moment later
                self.pending = {"action": action, "team": team, "gen": self.gen,
                                "at": now + self.preview_time()}
        if self.pending and now >= self.pending["at"]:
            move, self.pending = self.pending, None
            if move["gen"] == self.gen and not TERMINAL(self.state):
                self.apply(move["action"])
                delay = 0.35 if self.mode == "hva" else 0.9 * (1 - self.speed.value)
                self.ai_ready_at = max(self.ai_ready_at, now + delay)
        self.effects = [e for e in self.effects if now < e["t0"] + e["dur"]]
        # start the AI when it is its turn
        if (self.thinking is None and self.pending is None and not TERMINAL(self.state)
                and not self.current_agent().is_human
                and now >= self.ai_ready_at and not self.animating(now)
                and (self.series is None or self.series["done"])):
            if self.mode != "ava" or self.auto or self.step_once:
                self.step_once = False
                self._start_ai()
        # match over -> results screen after a short pause
        if self.over_at is not None and now - self.over_at > 2.4 and not self.animating(now):
            if self.series is None or self.series["done"]:
                self.app.go(ResultsScreen(self.app, self))

    def turn_text(self):
        """Text and colour for the header banner: whose turn it is and what to do."""
        s = self.state
        if s.over:
            return "Full time", T.BUTTON, False
        team = PLAYER(s)
        name = self.agent_label(team)
        role = "raider" if s.phase in ("pick", "raider") else "defenders"
        if self.pending:
            return (f"Team {TEAM_NAMES[team]} ({name}) plays: {describe_action(s, self.pending['action'])}",
                    T.TEAM_COLOURS[team], False)
        if self.human_turn():
            todo = {"pick": "pick your raider", "raider": "step, touch (T) or stop (S)",
                    "defender": "move one defender or hold (H)"}[s.phase]
            return f"YOUR TURN · Team {TEAM_NAMES[team]} {role}: {todo}", T.TEAM_COLOURS[team], True
        if self.thinking:
            dots = "." * (1 + int(time.perf_counter() * 3) % 3)
            return f"Team {TEAM_NAMES[team]} ({name}) is thinking{dots}", T.TEAM_COLOURS[team], False
        return f"Team {TEAM_NAMES[team]} ({name}) to move", T.TEAM_COLOURS[team], False

    def draw(self, surf):
        now = time.perf_counter()
        s = self.state
        surf.fill(T.BG)
        title = T.font(26, True).render("HADUDU ARENA", True, T.SAND)
        surf.blit(title, (T.COURT_X - 10, 10))
        mode = {"hva": "Human vs AI", "ava": "AI vs AI"}[self.mode]
        img = T.font(15).render(mode, True, T.TEXT_DIM)
        surf.blit(img, (T.COURT_X + 214, 20))
        r = self.renderer
        text, colour, pulse = self.turn_text()
        r.draw_turn_banner(text, colour, now, pulse)
        r.draw_court()

        human = self.human_turn()
        raid_on = s.phase != "pick" and not s.over
        pickable, raider_cell, touch_targets = set(), s.raider_cell(), set()
        if human and s.phase == "pick":
            pickable = {(s.attacker, i) for i, p in enumerate(s.pos[s.attacker]) if p is not None}
        elif human and s.phase == "raider":
            r.draw_step_options(step_safety(s))
            if ("touch",) in ACTIONS(s):          # show who a Touch would tag
                touch_targets = {(s.defender, i) for i in s.adjacent_defenders(raider_cell)
                                 if i not in s.tagged}
        elif human and s.phase == "defender" and self.selected is not None:
            r.draw_cell_highlights([a[2] for a in ACTIONS(s) if a[0] == "move" and a[1] == self.selected],
                                   T.HIGHLIGHT, 60)
        if human and s.phase == "defender":
            pickable = {(s.defender, i) for i, p in enumerate(s.pos[s.defender]) if p is not None}
        if raid_on and legal_tackle_threat(s):
            r.draw_tackle_zone(raider_cell, now)
        if raid_on:
            cost, path = safe_return_cost(s)
            if path and len(path) > 1:
                r.draw_return_path(path, cost)
        selected = (s.defender, self.selected) if self.selected is not None else None
        overrides, extras, walking = self._effect_layers(now)
        r.draw_players(s, self.anim, now, pickable, selected, overrides, extras, touch_targets)
        r.draw_out_flashes(self.flashes, now)
        if self.pending and self.pending["gen"] == self.gen:
            r.draw_move_preview(s, self.pending["action"], self.pending["team"], now)
        r.draw_ticker(raid_on, now)
        banner_on = False
        if self.banner:
            b_title, b_sub, b_col, t0, dur, b_y = self.banner
            k = (now - t0) / dur
            banner_on = k <= 1
            r.draw_banner(b_title, b_sub, b_col, k, b_y)
        if human:
            hint = {"pick": "Click one of your players to send him on the raid.",
                    "raider": "Step colours: green safe · yellow risky · red danger · blue home.",
                    "defender": "Click a defender, then a highlighted cell, or press Hold."}[s.phase]
            img = T.font(15, True).render(hint, True, T.TEXT)
            surf.blit(img, img.get_rect(midleft=(T.COURT_X - 14, T.COURT_Y + T.COURT_H + 112)))
        if s.over and not banner_on:
            d = score_diff(s)
            r.draw_banner("DRAW" if d == 0 else f"TEAM {'A' if d > 0 else 'B'} WINS", "Full time",
                          T.GOLD, 0.5)

        for b in self.buttons:
            b.draw(surf)
        if self.mode == "ava":
            self.speed.draw(surf)
            lbl = T.font(14).render(f"series length {self.series_n.value}", True, T.TEXT_DIM)
            surf.blit(lbl, (self.series_plus.rect.right + 10, self.series_plus.rect.y + 6))

        # ---- side panel
        names = (self.agent_label(0), self.agent_label(1))
        y = r.draw_scoreboard(s, names)
        y = r.draw_breath(s, y, now)
        y = r.draw_benches(s, y, now, walking)
        fuzzy_team = next((t for t in (0, 1) if isinstance(self.agents[t], FuzzyMinimaxAgent)), None)
        if fuzzy_team is not None:
            att = s.attacker
            if isinstance(self.agents[att], FuzzyMinimaxAgent) and not s.over:
                y = r.draw_meter(f"Fuzzy aggression · {TEAM_NAMES[att]} raider", state_aggression(s), y)
            else:
                y = r.draw_meter(f"Fuzzy aggression · {TEAM_NAMES[fuzzy_team]} defending", 0.5, y)
        ai_team = next((t for t in (0, 1) if not self.agents[t].is_human), 0)
        if self.analysis:
            y = r.draw_thoughts(self.analysis[1], self.analysis[0], y)
        else:
            y = r.draw_thoughts(None, ai_team, y)
        if self.series:
            y = self._draw_series(surf, y)
        else:
            y = r.draw_timeline(self.score_points(), y)
        if raid_on:
            cost, _ = safe_return_cost(s)
            y = r.draw_info_line(f"Safe return (A*): cost {cost:g} vs breath {s.breath}", y,
                                 T.DANGER if cost > s.breath else T.TEXT)
        r.draw_log(self.log, pygame.Rect(T.PANEL_X, y + 2, T.PANEL_W, T.HEIGHT - y - 14), self.log_scroll)

    def _draw_series(self, surf, y):
        b = self.series
        rect = self.renderer.card(y + 2, 92)
        status = "running" if not b["done"] else ("stopped" if b["stop"] else "finished")
        lines = [f"Series ({status}): {b['played']} / {b['n']} matches",
                 f"X {self.agents[0].name}: {b['x']} wins   Y {self.agents[1].name}: {b['y']} wins   draws {b['draw']}",
                 f"points X {b['pts_x']}  Y {b['pts_y']}  ·  first raider {b['first_wins']}  second {b['second_wins']}",
                 b["last"]]
        for k, line in enumerate(lines):
            img = T.font(14, k == 0).render(line, True, T.GOLD if k == 0 else T.TEXT)
            surf.blit(img, (rect.x + 10, rect.y + 6 + k * 20))
        return rect.bottom + 4


def step_safety(s):
    """Colour each legal raider step for a human player:
    home   - steps back into his own half after crossing (the raid succeeds)
    danger - 3+ defenders next to that cell, or not enough breath to get home
    risky  - 2 defenders next to it, or exactly enough breath (A* cost) to get home
    safe   - otherwise
    """
    a = s.attacker
    out = []
    for act in ACTIONS(s):
        if act[0] != "step":
            continue
        cell = act[1]
        if in_half(a, cell):
            out.append((cell, "home" if s.crossed else "neutral"))
            continue
        row = list(s.pos[a])
        row[s.raider] = cell
        pos = (tuple(row), s.pos[1]) if a == 0 else (s.pos[0], tuple(row))
        after = s._replace(pos=pos)
        adjacent = len(after.adjacent_defenders(cell))
        cost, _ = safe_return_cost(after)
        margin = (s.breath - 1) - cost        # breath left after the step minus the way home
        if adjacent >= 3 or margin < 0:
            out.append((cell, "danger"))
        elif adjacent == 2 or margin == 0:
            out.append((cell, "risky"))
        else:
            out.append((cell, "safe"))
    return out


# ======================================================================
# Results
# ======================================================================
class ResultsScreen:
    def __init__(self, app, game: GameScreen):
        self.app = app
        self.game = game
        s = game.state
        self.state = s
        self.stats = {t: {"raids": 0, "success": 0, "touch_pts": 0, "tackles": 0,
                          "empty": 0, "all_outs": 0} for t in (0, 1)}
        for _, att, out in game.raid_records:
            st = self.stats[att]
            st["raids"] += 1
            if out[0] == "success":
                st["success"] += 1
                st["touch_pts"] += out[1]
                if "all_out" in out:
                    st["all_outs"] += 1
            elif out[0] in ("caught", "dod_fail"):
                self.stats[1 - att]["tackles"] += 1
                if "all_out" in out:
                    self.stats[1 - att]["all_outs"] += 1
            else:
                st["empty"] += 1
        cx = T.WIDTH / 2
        self.buttons = [
            Button((cx - 250, T.HEIGHT - 90, 230, 54), "Rematch", game.restart, size=22),
            Button((cx + 20, T.HEIGHT - 90, 230, 54), "Main menu", lambda: app.go(MenuScreen(app)), size=22),
        ]

    def handle(self, event):
        for b in self.buttons:
            b.handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go(MenuScreen(self.app))
            elif event.key == pygame.K_r:
                self.game.restart()

    def update(self, now):
        pass

    def draw(self, surf):
        s = self.state
        d = score_diff(s)
        draw_backdrop(surf, "FULL TIME", centre_line=False)
        msg = "It's a draw!" if d == 0 else f"Team {'A' if d > 0 else 'B'} wins!"
        col = T.GOLD if d == 0 else T.TEAM_LIGHT[0 if d > 0 else 1]
        img = T.font(40, True).render(msg, True, col)
        surf.blit(img, img.get_rect(center=(T.WIDTH / 2, 160)))
        score = T.font(64, True).render(f"{s.score[0]}  :  {s.score[1]}", True, T.TEXT)
        surf.blit(score, score.get_rect(center=(T.WIDTH / 2, 235)))
        if s.komi:
            a = s.score[0] + (s.komi if s.first == 0 else 0)
            b = s.score[1] + (s.komi if s.first == 1 else 0)
            k = T.font(16).render(f"komi +{s.komi:g} for Team {TEAM_NAMES[s.first]} (first raider)"
                                  f"  ->  {a:g} : {b:g}", True, T.TEXT_DIM)
            surf.blit(k, k.get_rect(center=(T.WIDTH / 2, 285)))
        rows = [("Raids", "raids"), ("Successful raids", "success"), ("Points from touches", "touch_pts"),
                ("Raiders caught (as defenders)", "tackles"), ("Empty raids", "empty"),
                ("All outs inflicted", "all_outs")]
        x0, y0 = T.WIDTH / 2 - 300, 320
        for t, x in ((0, x0 + 360), (1, x0 + 500)):
            h = T.font(18, True).render(f"Team {TEAM_NAMES[t]}", True, T.TEAM_LIGHT[t])
            surf.blit(h, h.get_rect(center=(x, y0)))
            n = T.font(14).render(self.game.agent_label(t), True, T.TEXT_DIM)
            surf.blit(n, n.get_rect(center=(x, y0 + 22)))
        for k, (label, key) in enumerate(rows):
            y = y0 + 52 + k * 30
            surf.blit(T.font(17).render(label, True, T.TEXT), (x0, y - 10))
            for t, x in ((0, x0 + 360), (1, x0 + 500)):
                v = T.font(18, True).render(str(self.stats[t][key]), True, T.TEXT)
                surf.blit(v, v.get_rect(center=(x, y)))
        for b in self.buttons:
            b.draw(surf)
