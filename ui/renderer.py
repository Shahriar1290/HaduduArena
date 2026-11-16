"""Drawing code: the court, players, overlays and the side panel.

The renderer only reads the GameState; it never changes it.
"""
from __future__ import annotations

import math
import random

import pygame

from game.state import COLS, ROWS, TEAM_NAMES, GameState, chebyshev, in_half
from ui import theme as T
from ui.characters import HEAD_TOP, draw_character


class Renderer:
    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self.court = self._make_court_surface()

    # ------------------------------------------------------------ geometry
    @staticmethod
    def cell_rect(cell) -> pygame.Rect:
        r, c = cell
        return pygame.Rect(T.COURT_X + c * T.CELL, T.COURT_Y + r * T.CELL, T.CELL, T.CELL)

    @staticmethod
    def cell_center(cell) -> tuple[float, float]:
        r, c = cell
        return (T.COURT_X + c * T.CELL + T.CELL / 2, T.COURT_Y + r * T.CELL + T.CELL / 2)

    @staticmethod
    def pixel_to_cell(pos):
        x, y = pos
        c = (x - T.COURT_X) // T.CELL
        r = (y - T.COURT_Y) // T.CELL
        if 0 <= r < ROWS and 0 <= c < COLS:
            return (int(r), int(c))
        return None

    # ------------------------------------------------------------ court
    def _make_court_surface(self) -> pygame.Surface:
        """Sandy pitch with chalk lines, drawn once and reused every frame."""
        pad = 16
        surf = pygame.Surface((T.COURT_W + 2 * pad, T.COURT_H + 2 * pad))
        surf.fill(T.SAND)
        rng = random.Random(4)
        for _ in range(2600):                  # sand grains
            x, y = rng.randrange(surf.get_width()), rng.randrange(surf.get_height())
            col = T.SAND_SPECK if rng.random() < 0.5 else T.SAND_DARK
            surf.fill(col, (x, y, rng.choice((1, 2)), rng.choice((1, 2))))
        chalk = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        # faint grid lines
        for c in range(1, COLS):
            x = pad + c * T.CELL
            pygame.draw.line(chalk, (*T.CHALK, 55), (x, pad), (x, pad + T.COURT_H), 1)
        for r in range(1, ROWS):
            y = pad + r * T.CELL
            pygame.draw.line(chalk, (*T.CHALK, 55), (pad, y), (pad + T.COURT_W, y), 1)
        # boundary and centre line (slightly wobbly, like hand-drawn chalk)
        pygame.draw.rect(chalk, (*T.CHALK, 230), (pad - 3, pad - 3, T.COURT_W + 6, T.COURT_H + 6), 4)
        cx = pad + 4 * T.CELL
        for y in range(pad, pad + T.COURT_H, 6):
            wob = rng.choice((-1, 0, 0, 1))
            pygame.draw.line(chalk, (*T.CHALK, 240), (cx + wob, y), (cx + wob, y + 6), 5)
        surf.blit(chalk, (0, 0))
        return surf

    def draw_court(self) -> None:
        self.surface.blit(self.court, (T.COURT_X - 16, T.COURT_Y - 16))
        f = T.font(15, True)
        for team, x in ((0, T.COURT_X + T.COURT_W * 0.25), (1, T.COURT_X + T.COURT_W * 0.75)):
            img = f.render(f"TEAM {TEAM_NAMES[team]} HALF", True, T.TEAM_LIGHT[team])
            self.surface.blit(img, img.get_rect(center=(x, T.COURT_Y - 44)))

    def draw_cell_highlights(self, cells, colour, alpha=90) -> None:
        overlay = pygame.Surface((T.CELL, T.CELL), pygame.SRCALPHA)
        overlay.fill((*colour, alpha))
        for cell in cells:
            rect = self.cell_rect(cell)
            self.surface.blit(overlay, rect.topleft)
            pygame.draw.rect(self.surface, colour, rect.inflate(-6, -6), 2, border_radius=8)

    def draw_tackle_zone(self, raider_cell, now: float) -> None:
        """Flashing red ring of cells: the tackle is one defender move from closing."""
        if int(now * 4) % 2:
            return
        overlay = pygame.Surface((T.CELL, T.CELL), pygame.SRCALPHA)
        overlay.fill((*T.DANGER, 70))
        r0, c0 = raider_cell
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                cell = (r0 + dr, c0 + dc)
                if (dr or dc) and 0 <= cell[0] < ROWS and 0 <= cell[1] < COLS:
                    self.surface.blit(overlay, self.cell_rect(cell).topleft)

    # ------------------------------------------------------------ players
    def draw_players(self, s: GameState, anim: dict, now: float, pickable=(), selected=None,
                     overrides=None, extras=(), touch_targets=()) -> None:
        """Draw every in-player as a character.

        anim          (team, i) -> (from_xy, to_xy, t0, duration) step animations
        overrides     (team, i) -> {"pose", "offset", "face"} for short effects
                      (celebrating raider, defenders piling onto a tackle)
        extras        "ghost" characters no longer on the court: a fallen raider or
                      players walking off; dicts with x, y, team, i, pose, alpha
        touch_targets (team, i) of defenders that a Touch would tag right now

        Players are drawn from the top row down, so a player lower on the
        screen overlaps the one behind him.
        """
        overrides = overrides or {}
        raid_on = s.phase != "pick" and not s.over
        raider_key = (s.attacker, s.raider) if raid_on else None
        raider_cell = s.raider_cell() if raid_on else None
        items = []
        for team in (0, 1):
            for i, p in enumerate(s.pos[team]):
                if p is None:
                    continue
                x, y = self.cell_center(p)
                moving = False
                if (team, i) in anim:
                    (x0, y0), (x1, y1), t0, dur = anim[(team, i)]
                    k = min(1.0, (now - t0) / dur)
                    moving = k < 1.0
                    k = k * k * (3 - 2 * k)                 # smoothstep easing
                    x, y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
                face = None
                if (team, i) == raider_key:
                    pose = "raid"
                elif raid_on and team == s.defender and chebyshev(p, raider_cell) <= 3:
                    pose = "crouch"                         # close defenders get ready...
                    rx = self.cell_center(raider_cell)[0]
                    if abs(rx - x) > 1:                     # ...and turn to watch the raider
                        face = 1 if rx > x else -1
                else:
                    pose = "idle"                           # far from the action: relaxed
                ov = overrides.get((team, i))
                if ov:
                    pose = ov.get("pose", pose)
                    face = ov.get("face", face)
                    dx, dy = ov.get("offset", (0, 0))
                    x, y = x + dx, y + dy
                tagged = raid_on and team == s.defender and i in s.tagged
                items.append(dict(x=x, y=y, team=team, i=i, pose=pose, moving=moving, tagged=tagged,
                                  face=face, pick=(team, i) in pickable, sel=(team, i) == selected,
                                  touch=(team, i) in touch_targets))
        for e in extras:
            items.append(dict(e, moving=True, ghost=True))
        for it in sorted(items, key=lambda d: (d["y"], d["x"])):
            self._draw_player(it, now)

    def _draw_player(self, it, now):
        x, y, team, i, pose = it["x"], it["y"], it["team"], it["i"], it["pose"]
        feet_y = y + T.FEET_OFFSET           # feet low in the cell, head reaches above it
        head_top = feet_y - T.CHAR_HEIGHT * HEAD_TOP
        if it.get("ghost"):                  # fallen raider / player walking off
            draw_character(self.surface, x, feet_y, team, i, pose, now, True, height=T.CHAR_HEIGHT,
                           show_name=False, face=it.get("face"), alpha=it.get("alpha", 255))
            return
        feet = pygame.Rect(0, 0, int(T.CELL * 0.72), int(T.CELL * 0.24))
        feet.center = (x, feet_y)
        if pose == "raid":      # glowing gold spot under the raider
            glow = pygame.Surface((feet.w + 30, feet.h + 22), pygame.SRCALPHA)
            pulse = 0.6 + 0.4 * math.sin(now * 6)
            pygame.draw.ellipse(glow, (*T.GOLD, int(130 * pulse)), glow.get_rect())
            self.surface.blit(glow, glow.get_rect(center=feet.center))
            pygame.draw.ellipse(self.surface, T.GOLD, feet, 3)
        if it["pick"] or it["sel"]:
            pygame.draw.ellipse(self.surface, T.HIGHLIGHT, feet.inflate(8, 4), 3)
        if it["tagged"]:        # tagged defenders stand in an orange ring
            pygame.draw.ellipse(self.surface, T.TAG_RING, feet.inflate(10, 6), 4)
        if it["touch"]:         # would be tagged by a Touch now: pulsing dashed ring
            r = feet.inflate(14 + 6 * math.sin(now * 8), 8)
            for k in range(0, 360, 30):
                a0, a1 = math.radians(k), math.radians(k + 18)
                pygame.draw.arc(self.surface, T.TAG_RING, r, a0, a1, 3)
        draw_character(self.surface, x, feet_y, team, i, pose, now, it["moving"],
                       height=T.CHAR_HEIGHT, face=it["face"])
        if it["tagged"]:
            self._label("TAGGED", x, head_top - 8, T.TAG_RING, 13)
        elif it["touch"]:
            self._label("TAG?", x, head_top - 8, (200, 120, 30), 13)
        if pose == "raid":      # chant bubble next to the raider's head
            word = ("ha-", "du-", "du-", "du!")[int(now * 4) % 4]
            txt = T.font(13, True).render(word, True, (60, 40, 20))
            side = 1 if team == 0 else -1
            bub = txt.get_rect(center=(x + side * T.CHAR_HEIGHT * 0.26, head_top - 4)).inflate(10, 5)
            pygame.draw.ellipse(self.surface, T.CHALK, bub)
            pygame.draw.ellipse(self.surface, (120, 100, 70), bub, 1)
            self.surface.blit(txt, txt.get_rect(center=bub.center))
        if pose == "celebrate":
            self._label("YES!", x, head_top - 14, T.GOLD, 14, dark_text=True)

    def _label(self, text, x, y, colour, size=14, dark_text=False):
        img = T.font(size, True).render(text, True, (40, 28, 15) if dark_text else T.TEXT)
        bg = img.get_rect(center=(x, y)).inflate(10, 4)
        pygame.draw.rect(self.surface, colour, bg, border_radius=5)
        pygame.draw.rect(self.surface, (40, 28, 15), bg, 1, border_radius=5)
        self.surface.blit(img, img.get_rect(center=bg.center))

    # ------------------------------------------------------------ readability overlays
    SAFETY = {"safe": ((70, 190, 90), "safe"), "risky": ((240, 190, 40), "risky"),
              "danger": ((225, 60, 50), "danger"), "home": ((80, 160, 250), "home"),
              "neutral": ((255, 255, 255), "")}

    def draw_step_options(self, options) -> None:
        """Legal steps for a human raider, coloured by how safe they are."""
        f = T.font(12, True)
        for cell, level in options:
            col, word = self.SAFETY[level]
            rect = self.cell_rect(cell)
            overlay = pygame.Surface((T.CELL, T.CELL), pygame.SRCALPHA)
            overlay.fill((*col, 70))
            self.surface.blit(overlay, rect.topleft)
            pygame.draw.rect(self.surface, col, rect.inflate(-6, -6), 3, border_radius=8)
            if word:
                img = f.render(word, True, (35, 25, 15))
                tag = img.get_rect(topleft=(rect.x + 7, rect.y + 6)).inflate(6, 2)
                pygame.draw.rect(self.surface, col, tag, border_radius=4)
                self.surface.blit(img, img.get_rect(center=tag.center))

    def _arrow(self, a, b, colour) -> None:
        ax, ay = a
        bx, by = b
        d = math.hypot(bx - ax, by - ay) or 1
        ux, uy = (bx - ax) / d, (by - ay) / d
        tip = (bx - ux * 10, by - uy * 10)
        base = (tip[0] - ux * 22, tip[1] - uy * 22)
        for col, w, grow in (((30, 20, 10), 11, 3), (colour, 7, 0)):
            pygame.draw.line(self.surface, col, (ax + ux * 12, ay + uy * 12), base, w)
            head = [(tip[0] + ux * grow, tip[1] + uy * grow),
                    (base[0] - uy * (13 + grow), base[1] + ux * (13 + grow)),
                    (base[0] + uy * (13 + grow), base[1] - ux * (13 + grow))]
            pygame.draw.polygon(self.surface, col, head)

    def draw_move_preview(self, s: GameState, action, team: int, now: float) -> None:
        """Show the AI's chosen move for a moment before it is played."""
        col = T.TEAM_LIGHT[team]
        kind = action[0]
        feet = T.FEET_OFFSET - 10
        if kind in ("step", "move"):
            src = s.raider_cell() if kind == "step" else s.pos[s.defender][action[1]]
            dst = action[1] if kind == "step" else action[2]
            (x0, y0), (x1, y1) = self.cell_center(src), self.cell_center(dst)
            pygame.draw.rect(self.surface, col, self.cell_rect(dst).inflate(-4, -4), 4, border_radius=10)
            self._arrow((x0, y0 + feet), (x1, y1 + feet), col)
        elif kind == "pick":
            x, y = self.cell_center(s.pos[s.attacker][action[1]])
            r = pygame.Rect(0, 0, 90, 34)
            r.center = (x, y + T.FEET_OFFSET)
            pygame.draw.ellipse(self.surface, col, r.inflate(8 * math.sin(now * 10), 4), 4)
            self._label("RAIDER!", x, y + T.FEET_OFFSET - T.CHAR_HEIGHT - 6, col, 15, dark_text=True)
        elif kind in ("touch", "stop"):
            x, y = self.cell_center(s.raider_cell())
            self._label("TOUCH!" if kind == "touch" else "STOP", x,
                        y + T.FEET_OFFSET - T.CHAR_HEIGHT - 6, col, 16, dark_text=True)
        elif kind == "hold":
            half_x = T.COURT_X + T.COURT_W * (0.25 if s.defender == 0 else 0.75)
            self._label("DEFENDERS HOLD", half_x, T.COURT_Y + 20, col, 15, dark_text=True)

    def draw_banner(self, text: str, sub: str, colour, k: float, cy=None) -> None:
        """Big raid-result banner across the court; k = 0..1 progress of its life.
        ``cy`` = vertical centre (default: middle of the court)."""
        if not 0 <= k <= 1:
            return
        grow = min(1.0, k / 0.12)
        scale = 0.6 + 0.4 * (1 - (1 - grow) ** 3) + 0.06 * math.sin(min(1.0, k / 0.25) * math.pi)
        alpha = 255 if k < 0.75 else int(255 * (1 - (k - 0.75) / 0.25))
        cx = T.COURT_X + T.COURT_W / 2
        cy = T.COURT_Y + T.COURT_H / 2 if cy is None else cy
        band = pygame.Surface((T.COURT_W, 116), pygame.SRCALPHA)
        band.fill((20, 14, 8, int(175 * alpha / 255)))
        pygame.draw.line(band, (*colour, alpha), (0, 2), (T.COURT_W, 2), 4)
        pygame.draw.line(band, (*colour, alpha), (0, 113), (T.COURT_W, 113), 4)
        self.surface.blit(band, (T.COURT_X, cy - 58))
        big = T.font(54, True)
        w, h = big.size(text)
        title = pygame.Surface((w + 6, h + 6), pygame.SRCALPHA)
        shadow = big.render(text, True, (25, 15, 8))
        for dx, dy in ((0, 3), (6, 3), (3, 0), (3, 6), (6, 6)):
            title.blit(shadow, (dx, dy))
        title.blit(big.render(text, True, colour), (3, 3))
        title = pygame.transform.rotozoom(title, 0, scale)
        title.set_alpha(alpha)
        self.surface.blit(title, title.get_rect(center=(cx, cy - 12)))
        if sub:
            img = T.font(20, True).render(sub, True, T.TEXT)
            img.set_alpha(alpha)
            self.surface.blit(img, img.get_rect(center=(cx, cy + 34)))

    def draw_turn_banner(self, text: str, colour, now: float, pulse: bool) -> None:
        """Header pill saying whose turn it is and what to do."""
        rect = pygame.Rect(T.COURT_X + 300, 8, T.COURT_W - 300, 32)
        col = colour
        if pulse:
            col = tuple(int(c * (0.85 + 0.15 * math.sin(now * 5))) for c in colour)
        pygame.draw.rect(self.surface, col, rect, border_radius=16)
        pygame.draw.rect(self.surface, (25, 18, 10), rect, 2, border_radius=16)
        img = T.font(16, True).render(text, True, T.TEXT)
        if img.get_width() > rect.w - 20:
            img = T.font(14, True).render(text, True, T.TEXT)
        self.surface.blit(img, img.get_rect(center=rect.center))

    def draw_out_flashes(self, flashes: list, now: float) -> None:
        """Short burst where a player just went out."""
        for cell, team, t0 in flashes:
            k = (now - t0) / T.OUT_FLASH
            if not 0 <= k <= 1:
                continue
            x, y = self.cell_center(cell)
            surf = pygame.Surface((160, 160), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*T.TEAM_LIGHT[team], int(220 * (1 - k))), (80, 80), int(25 + 45 * k), 6)
            pygame.draw.circle(surf, (255, 255, 255, int(160 * (1 - k))), (80, 80), int(20 * (1 - k)) + 1)
            self.surface.blit(surf, (x - 80, y - 80))
            txt = T.font(18, True).render("OUT", True, T.TEXT)
            txt.set_alpha(int(255 * (1 - k)))
            self.surface.blit(txt, txt.get_rect(center=(x, y - 40 - 20 * k)))

    def draw_return_path(self, path, cost) -> None:
        """A* safe-return path as a dashed blue line plus its cost."""
        if len(path) < 2:
            return
        pts = [self.cell_center(c) for c in path]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dist = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(dist // 12))
            for k in range(0, n, 2):
                a, b = k / n, min(1, (k + 1) / n)
                pygame.draw.line(self.surface, T.PATH, (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a),
                                 (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), 4)
        x, y = pts[-1]
        pygame.draw.circle(self.surface, T.PATH, (x, y), 8)
        label = T.font(14, True).render(f"A* cost {cost:g}", True, T.TEXT)
        bg = pygame.Rect(0, 0, label.get_width() + 10, label.get_height() + 4)
        bg.midbottom = (x, y - 30)
        bg.clamp_ip(pygame.Rect(T.COURT_X, T.COURT_Y, T.COURT_W, T.COURT_H))
        pygame.draw.rect(self.surface, T.PATH, bg, border_radius=6)
        self.surface.blit(label, (bg.x + 5, bg.y + 2))

    def draw_ticker(self, active: bool, now: float) -> None:
        """'Ha-du-du-du' chant scrolling under the court while a raid is on."""
        rect = pygame.Rect(T.COURT_X - 16, T.COURT_Y + T.COURT_H + 18, T.COURT_W + 32, 26)
        pygame.draw.rect(self.surface, T.PANEL_BG, rect, border_radius=6)
        if not active:
            txt = T.font(16).render("The crowd waits for the next raider...", True, T.TEXT_DIM)
            self.surface.blit(txt, txt.get_rect(center=rect.center))
            return
        chant = T.font(18, True).render("Ha-du-du-du-du-du…   " * 3, True, T.GOLD)
        width = chant.get_width() // 3
        offset = int(now * 120) % width
        clip = self.surface.get_clip()
        self.surface.set_clip(rect)
        for k in range(-1, 3):
            self.surface.blit(chant, (rect.x - offset + k * width, rect.y + 2))
        self.surface.set_clip(clip)

    # ------------------------------------------------------------ side panel
    def card(self, y, h) -> pygame.Rect:
        rect = pygame.Rect(T.PANEL_X, y, T.PANEL_W, h)
        pygame.draw.rect(self.surface, T.PANEL_CARD, rect, border_radius=10)
        return rect

    def draw_scoreboard(self, s: GameState, names, y=20) -> int:
        rect = self.card(y, 92)
        big = T.font(40, True)
        a = big.render(str(s.score[0]), True, T.GREEN_LIGHT)
        b = big.render(str(s.score[1]), True, T.RED_LIGHT)
        colon = big.render(":", True, T.TEXT)
        cx = rect.centerx
        self.surface.blit(a, a.get_rect(midright=(cx - 18, rect.y + 32)))
        self.surface.blit(colon, colon.get_rect(center=(cx, rect.y + 30)))
        self.surface.blit(b, b.get_rect(midleft=(cx + 18, rect.y + 32)))
        small = T.font(15, True)
        la = small.render(f"A · {names[0]}", True, T.GREEN_LIGHT)
        lb = small.render(f"{names[1]} · B", True, T.RED_LIGHT)
        self.surface.blit(la, (rect.x + 12, rect.y + 8))
        self.surface.blit(lb, lb.get_rect(topright=(rect.right - 12, rect.y + 8)))
        if s.komi:
            k = T.font(13).render(f"komi +{s.komi:g} to {TEAM_NAMES[s.first]}", True, T.TEXT_DIM)
            self.surface.blit(k, (rect.x + 12, rect.y + 30))
        if s.over:
            line = "Match over"
        else:
            line = (f"Raid {s.raid + 1} / 16  ·  Team {TEAM_NAMES[s.attacker]} raiding"
                    f"  ·  {'pick a raider' if s.phase == 'pick' else s.phase + ' turn'}")
        img = T.font(15).render(line, True, T.TEXT)
        self.surface.blit(img, img.get_rect(center=(rect.centerx, rect.bottom - 18)))
        return rect.bottom + 8

    def draw_breath(self, s: GameState, y, now) -> int:
        rect = self.card(y, 64)
        breath = s.breath if s.phase != "pick" and not s.over else 0
        low = s.phase != "pick" and not s.over and breath <= 2
        if low:                                  # pulsing red frame: breath almost gone
            k = 0.5 + 0.5 * math.sin(now * 9)
            pygame.draw.rect(self.surface, _mix_col(T.PANEL_CARD, T.DANGER, k), rect, 4, border_radius=10)
        label = "BREATH" if s.phase == "pick" or s.over else f"BREATH  {breath} / 6"
        lbl = T.font(15, True).render(label, True, T.DANGER if low else T.TEXT)
        self.surface.blit(lbl, (rect.x + 12, rect.y + 6))
        if low and not s.dod:
            warn = T.font(14, True).render("get home!" if s.crossed else "low!", True, T.DANGER)
            self.surface.blit(warn, warn.get_rect(topright=(rect.right - 12, rect.y + 7)))
        bar = pygame.Rect(rect.x + 12, rect.y + 28, rect.w - 24, 24)
        pygame.draw.rect(self.surface, (40, 32, 24), bar, border_radius=6)
        seg_w = bar.w / 6
        for k in range(6):
            seg = pygame.Rect(bar.x + k * seg_w + 2, bar.y + 2, seg_w - 4, bar.h - 4)
            if k < breath:
                col = (60, 190, 230) if breath > 2 else (240, 120, 40) if breath == 2 else T.DANGER
                pygame.draw.rect(self.surface, col, seg, border_radius=4)
        if s.dod and s.phase != "pick" or (s.phase == "pick" and s.empty[s.attacker] >= 2 and not s.over):
            if int(now * 3) % 2 == 0 or s.phase == "pick":
                ban = T.font(16, True).render("DO-OR-DIE", True, T.TEXT)
                br = pygame.Rect(0, 0, ban.get_width() + 16, 22)
                br.topright = (rect.right - 10, rect.y + 4)
                pygame.draw.rect(self.surface, T.DOD, br, border_radius=5)
                self.surface.blit(ban, ban.get_rect(center=br.center))
        return rect.bottom + 8

    def draw_benches(self, s: GameState, y, now, hidden=()) -> int:
        """One card per team: players who are out sit on the bench in revival
        order (the left-most comes back first). ``hidden`` = players still
        walking off the court, not seated yet."""
        w = (T.PANEL_W - 8) // 2
        h = 114
        for team in (0, 1):
            rect = pygame.Rect(T.PANEL_X + team * (w + 8), y, w, h)
            pygame.draw.rect(self.surface, T.PANEL_CARD, rect, border_radius=10)
            pygame.draw.rect(self.surface, T.TEAM_COLOURS[team], rect, 3, border_radius=10)
            n_in = s.in_count(team)
            t1 = T.font(15, True).render(f"Team {TEAM_NAMES[team]} · in {n_in}", True, T.TEAM_LIGHT[team])
            self.surface.blit(t1, (rect.x + 10, rect.y + 6))
            emp = T.font(13).render(f"empty raids {s.empty[team]}", True,
                                    T.DANGER if s.empty[team] >= 2 else T.TEXT_DIM)
            self.surface.blit(emp, emp.get_rect(topright=(rect.right - 10, rect.y + 8)))
            feet_y = rect.bottom - 10
            seat_y = feet_y - 19
            # the bench: a wooden plank with two legs
            plank = pygame.Rect(rect.x + 8, seat_y - 3, rect.w - 16, 7)
            pygame.draw.rect(self.surface, (122, 86, 52), plank, border_radius=3)
            pygame.draw.rect(self.surface, (80, 55, 32), plank, 1, border_radius=3)
            for lx in (plank.x + 8, plank.right - 10):
                pygame.draw.line(self.surface, (80, 55, 32), (lx, plank.bottom), (lx, feet_y + 2), 3)
            seated = [i for i in s.outq[team] if (team, i) not in hidden]
            if not seated:
                img = T.font(13).render("bench empty", True, T.TEXT_DIM)
                self.surface.blit(img, img.get_rect(center=(rect.centerx, rect.y + 46)))
            for k, i in enumerate(seated):
                x = rect.x + 24 + k * 37
                draw_character(self.surface, x, feet_y, team, i, "sit", now, height=64, show_name=False)
                if k == 0:
                    tag = T.font(11, True).render("next", True, (40, 28, 15))
                    bg = tag.get_rect(center=(x, feet_y - 64)).inflate(8, 2)
                    pygame.draw.rect(self.surface, T.GOLD, bg, border_radius=4)
                    self.surface.blit(tag, tag.get_rect(center=bg.center))
        return y + h + 8

    def draw_timeline(self, points, y) -> int:
        """Score after every raid: A green, B red (step lines)."""
        rect = self.card(y, 74)
        self.surface.blit(T.font(13, True).render("Score by raid", True, T.TEXT), (rect.x + 10, rect.y + 4))
        plot = pygame.Rect(rect.x + 30, rect.y + 22, rect.w - 44, rect.h - 36)
        top = max(4, max((max(a, b) for _, a, b in points), default=0))
        f = T.font(11)
        for r in (0, 4, 8, 12, 16):
            x = plot.x + plot.w * r / 16
            pygame.draw.line(self.surface, (95, 82, 66), (x, plot.y), (x, plot.bottom), 1)
            img = f.render(str(r), True, T.TEXT_DIM)
            self.surface.blit(img, img.get_rect(midtop=(x, plot.bottom + 1)))
        pygame.draw.line(self.surface, T.TEXT_DIM, plot.bottomleft, plot.bottomright, 1)
        lbl = f.render(str(top), True, T.TEXT_DIM)
        self.surface.blit(lbl, lbl.get_rect(midright=(plot.x - 4, plot.y + 4)))

        def px(r, v):
            return plot.x + plot.w * r / 16, plot.bottom - plot.h * v / top
        for idx, col in ((1, T.GREEN_LIGHT), (2, T.RED_LIGHT)):
            pts, prev = [px(0, 0)], 0
            for p in points:
                pts.append(px(p[0], prev))
                pts.append(px(p[0], p[idx]))
                prev = p[idx]
            if len(pts) >= 2:
                pygame.draw.lines(self.surface, col, False, pts, 3)
        return rect.bottom + 8

    def draw_thoughts(self, analysis, team, y) -> int:
        """'What the AI was thinking': its top moves for the last decision."""
        rect = self.card(y, 112)
        if analysis is None:
            img = T.font(14).render("The AI's reasoning appears here after its first move.", True, T.TEXT_DIM)
            self.surface.blit(img, img.get_rect(center=rect.center))
            return rect.bottom + 8
        f_b, f = T.font(14, True), T.font(13)
        head = f_b.render(f"AI thinking · Team {TEAM_NAMES[team]} · {analysis['title']}", True, T.TEAM_LIGHT[team])
        if head.get_width() > rect.w - 20:
            head = T.font(12, True).render(f"Team {TEAM_NAMES[team]} · {analysis['title']}", True, T.TEAM_LIGHT[team])
        self.surface.blit(head, (rect.x + 10, rect.y + 6))
        self.surface.blit(f.render(analysis["detail"], True, T.TEXT_DIM), (rect.x + 10, rect.y + 25))
        for k, (text, value, chosen) in enumerate(analysis["moves"][:3]):
            row = pygame.Rect(rect.x + 6, rect.y + 46 + k * 21, rect.w - 12, 20)
            if chosen:
                pygame.draw.rect(self.surface, (110, 88, 40), row, border_radius=5)
            mark = ">" if chosen else f"{k + 1}."
            self.surface.blit(f_b.render(mark, True, T.GOLD if chosen else T.TEXT_DIM), (row.x + 6, row.y + 1))
            self.surface.blit(f.render(text, True, T.TEXT), (row.x + 26, row.y + 2))
            val = f_b.render(value, True, T.GOLD if chosen else T.TEXT)
            self.surface.blit(val, val.get_rect(topright=(row.right - 8, row.y + 1)))
        return rect.bottom + 8

    def draw_meter(self, label: str, value: float, y) -> int:
        rect = self.card(y, 52)
        lbl = T.font(14, True).render(label, True, T.TEXT)
        self.surface.blit(lbl, (rect.x + 12, rect.y + 5))
        bar = pygame.Rect(rect.x + 12, rect.y + 26, rect.w - 24, 16)
        for k in range(bar.w):               # cautious (blue) -> daring (red) gradient
            f = k / bar.w
            col = (int(60 + 180 * f), int(140 - 60 * f), int(220 - 180 * f))
            pygame.draw.line(self.surface, col, (bar.x + k, bar.y), (bar.x + k, bar.bottom))
        x = bar.x + value * bar.w
        pygame.draw.polygon(self.surface, T.TEXT, [(x, bar.y - 2), (x - 6, bar.y - 9), (x + 6, bar.y - 9)])
        pygame.draw.line(self.surface, T.TEXT, (x, bar.y), (x, bar.bottom), 3)
        word = "cautious" if value < 0.4 else "balanced" if value < 0.6 else "daring"
        val = T.font(14).render(f"{value:.2f} ({word})", True, T.TEXT)
        self.surface.blit(val, val.get_rect(topright=(rect.right - 12, rect.y + 5)))
        return rect.bottom + 8

    def draw_info_line(self, text: str, y, colour=T.TEXT) -> int:
        img = T.font(14).render(text, True, colour)
        self.surface.blit(img, (T.PANEL_X + 4, y))
        return y + 22

    def draw_log(self, lines: list[str], rect: pygame.Rect, scroll: int) -> None:
        """Scrollable raid log (newest at the bottom). ``scroll`` = lines up from the end."""
        pygame.draw.rect(self.surface, T.PANEL_BG, rect, border_radius=8)
        pygame.draw.rect(self.surface, T.PANEL_CARD, rect, 2, border_radius=8)
        f = T.font(14)
        wrapped = []
        for line in lines:
            wrapped.extend(wrap(line, f, rect.w - 16))
        per_page = max(1, (rect.h - 10) // 19)
        end = max(0, len(wrapped) - scroll)
        start = max(0, end - per_page)
        for k, line in enumerate(wrapped[start:end]):
            col = T.TEXT if not line.startswith("  ") else T.TEXT_DIM
            self.surface.blit(f.render(line, True, col), (rect.x + 8, rect.y + 6 + k * 19))
        if scroll:
            more = T.font(12).render(f"▼ {scroll} newer lines (scroll)", True, T.GOLD)
            self.surface.blit(more, more.get_rect(bottomright=(rect.right - 8, rect.bottom - 4)))


def _mix_col(a, b, t):
    return tuple(int(a[j] + (b[j] - a[j]) * t) for j in range(3))


def wrap(text: str, f: pygame.font.Font, width: int) -> list[str]:
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w) if cur else w
        if f.size(trial)[0] <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = "  " + w
    if cur:
        lines.append(cur)
    return lines


def legal_tackle_threat(s: GameState) -> bool:
    """True when ONE defender move would complete a tackle (for the flashing zone)."""
    from ai.pathing import intercept_distance
    cell = s.raider_cell()
    if cell is None or s.phase == "pick" or in_half(s.attacker, cell):
        return False
    adjacent = len(s.adjacent_defenders(cell))
    if adjacent >= 3:
        return True
    if adjacent < 2:
        return False
    dist = intercept_distance(s)
    return any(d == 1 for d in dist.values())
