"""Player characters, drawn entirely in code (no image files).

Every player has a name and his own look (skin tone, hair, face details).
A character is built from a simple "skeleton" of joints (head, shoulders,
elbows, wrists, hips, knees, ankles) in body units: 100 units = standing
height, x to the right, y downward, (0, 0) = the ground between the feet.
Limbs are tapered, outlined and shaded (light comes from the upper right).

Poses (each animated with a few frames):
    idle      - standing upright and breathing (between raids)
    raid      - the raider: leaning in, one arm reaching to touch, running legs,
                mouth open chanting "ha-du-du-du"
    crouch    - defenders during a raid: low wide stance, arms out ready to tackle
    celebrate - both arms up, jumping (after a successful raid)
    walk      - walking off the court after going out
    sit       - sitting on the bench, waiting to be revived
    fallen    - a tackled raider lying on the ground (a rotated crouch frame)

For smooth edges every frame is drawn 3x larger and scaled down
(supersampling). Finished frames are cached, so drawing is cheap.
"""
from __future__ import annotations

import math

import pygame

from ui import theme as T

SKIN = [(141, 85, 52), (196, 140, 98), (222, 178, 135), (166, 112, 72), (112, 72, 46)]
HAIR_BLACK = (28, 22, 20)
HAIR_BROWN = (74, 50, 32)
SHORTS = (38, 40, 52)

# One entry per player: name, skin tone, hair style, hair colour, extra face detail
ROSTER = (
    (   # Team A (green)
        dict(name="Rafiq", skin=SKIN[1], hair="short", hair_col=HAIR_BLACK, extra="mustache"),
        dict(name="Sumon", skin=SKIN[2], hair="spiky", hair_col=HAIR_BLACK, extra=None),
        dict(name="Babul", skin=SKIN[0], hair="curly", hair_col=HAIR_BLACK, extra="beard"),
        dict(name="Hasan", skin=SKIN[3], hair="band", hair_col=HAIR_BROWN, extra=None),
        dict(name="Milon", skin=SKIN[4], hair="side", hair_col=HAIR_BLACK, extra="mustache"),
    ),
    (   # Team B (red)
        dict(name="Jewel", skin=SKIN[2], hair="side", hair_col=HAIR_BROWN, extra=None),
        dict(name="Kamal", skin=SKIN[0], hair="band", hair_col=HAIR_BLACK, extra="mustache"),
        dict(name="Rubel", skin=SKIN[3], hair="spiky", hair_col=HAIR_BLACK, extra=None),
        dict(name="Shahin", skin=SKIN[1], hair="curly", hair_col=HAIR_BROWN, extra="beard"),
        dict(name="Tipu", skin=SKIN[4], hair="short", hair_col=HAIR_BLACK, extra=None),
    ),
)

FRAMES = {"idle": 6, "crouch": 4, "raid": 8, "celebrate": 6, "walk": 8, "sit": 1, "fallen": 1}
SS = 3                                          # supersampling factor
CANVAS_X = 52                                   # canvas spans x = -52..52 units
BUILD = 1.1                                     # body width factor (kabaddi players are stocky)
CANVAS_TOP, CANVAS_BOTTOM = 112, 8              # and y = -112..8 units (room for raised arms)
HEAD_TOP = 0.98                                 # top of the hair, as a fraction of height

_cache: dict = {}


def player_name(team: int, i: int) -> str:
    return ROSTER[team][i]["name"]


# ----------------------------------------------------------------------
# Colour helpers
# ----------------------------------------------------------------------
def _mul(col, k):
    return tuple(max(0, min(255, int(c * k))) for c in col)


def _mix(a, b, t):
    return tuple(int(a[j] + (b[j] - a[j]) * t) for j in range(3))


# ----------------------------------------------------------------------
# Skeletons (body units, written for a player facing right)
# ----------------------------------------------------------------------
def _skeleton(pose: str, frame: int) -> dict:
    """Joint positions for one frame, widened by BUILD."""
    return {k: (x * BUILD, y) for k, (x, y) in _raw_skeleton(pose, frame).items()}


def _raw_skeleton(pose: str, frame: int) -> dict:
    p = 2 * math.pi * frame / FRAMES[pose]
    if pose == "crouch":                       # low wide tackling stance
        b = math.sin(p) * 1.0                  # small bounce on the toes
        return {
            "head": (1.5, -76 + b), "neck_top": (1, -68 + b), "neck_base": (0.5, -65 + b),
            "sh_l": (-12.5, -63 + b), "sh_r": (12.5, -63 + b),
            "el_l": (-22, -54 + b), "el_r": (22, -54 + b),
            "wr_l": (-27, -45 + b), "wr_r": (27, -45 + b),
            "waist_l": (-9, -43 + b), "waist_r": (9, -43 + b),
            "hip_l": (-7.5, -37 + b), "hip_r": (7.5, -37 + b), "crotch": (0, -33 + b),
            "kn_l": (-16, -21), "kn_r": (16, -21),
            "an_l": (-15, -4), "an_r": (15, -4),
        }
    if pose == "raid":                         # leaning in, reaching, stepping
        s = math.sin(p)
        bob = -abs(s) * 1.5
        lean = 4
        sk = {
            "head": (lean + 2.5, -89 + bob), "neck_top": (lean + 1.5, -81 + bob),
            "neck_base": (lean, -77 + bob),
            "sh_l": (lean - 12, -75 + bob), "sh_r": (lean + 12, -75 + bob),
            # back arm swings for balance, front arm reaches out to touch
            "el_l": (-13 - 2 * s, -62 + bob), "wr_l": (-19 - 3 * s, -52 + bob),
            "el_r": (28, -74 + bob), "wr_r": (41, -72 + 1.5 * s + bob),
            "waist_l": (-7, -52 + bob), "waist_r": (11, -52 + bob),
            "hip_l": (-5, -47 + bob), "hip_r": (8, -47 + bob), "crotch": (1.5, -43 + bob),
        }
        for side, key in ((-1, "l"), (1, "r")):
            lift = max(0.0, s * side)          # this leg is lifted in mid-stride
            hx = sk["hip_" + key][0]
            sk["kn_" + key] = (hx + 1 + 5 * lift, -25 - 10 * lift + bob * 0.5)
            sk["an_" + key] = (hx + 0.5 + 2 * lift, -5 - 13 * lift)
        return sk
    if pose == "celebrate":                    # arms up, little jumps
        j = -abs(math.sin(p)) * 5
        sk = _idle(0)
        sk = {k: (x, y + j) for k, (x, y) in sk.items()}
        sk.update({"el_l": (-17, -88 + j), "el_r": (17, -88 + j),
                   "wr_l": (-15, -101 + j), "wr_r": (15, -101 + j)})
        return sk
    if pose == "walk":                         # stride with swinging arms
        s = math.sin(p)
        sk = _idle(-abs(s) * 0.8)
        sk.update({"el_l": (-14.5, -61), "el_r": (14.5, -61),
                   "wr_l": (-15.5 - 3 * s, -48), "wr_r": (15.5 - 3 * s, -48)})
        for side, key in ((-1, "l"), (1, "r")):
            lift = max(0.0, s * side)
            hx = sk["hip_" + key][0]
            sk["kn_" + key] = (hx - 1 + 2 * lift, -25 - 5 * lift)
            sk["an_" + key] = (hx - 1 + 1 * lift, -5 - 7 * lift)
        return sk
    if pose == "sit":                          # seated on the bench, hands on knees
        sk = _idle(0)
        sk = {k: (x, y + 17) for k, (x, y) in sk.items()}
        sk.update({"hip_l": (-6.5, -30), "hip_r": (6.5, -30), "crotch": (0, -27),
                   "kn_l": (-9, -27), "kn_r": (9, -27), "an_l": (-9, -5), "an_r": (9, -5),
                   "el_l": (-15, -45), "el_r": (15, -45), "wr_l": (-10.5, -31), "wr_r": (10.5, -31)})
        return sk
    return _idle(math.sin(p) * 0.7)             # idle: breathing


def _idle(b: float) -> dict:
    """Standing skeleton; ``b`` moves the upper body (breathing)."""
    return {
        "head": (1, -89 + b), "neck_top": (0.5, -81 + b), "neck_base": (0, -77 + b),
        "sh_l": (-12, -75 + b), "sh_r": (12, -75 + b),
        "el_l": (-15, -61 + b * 0.5), "el_r": (15, -61 + b * 0.5),
        "wr_l": (-16.5, -48), "wr_r": (16.5, -48),
        "waist_l": (-9, -52), "waist_r": (9, -52),
        "hip_l": (-6.5, -47), "hip_r": (6.5, -47), "crotch": (0, -43),
        "kn_l": (-7.5, -25), "kn_r": (7.5, -25),
        "an_l": (-7.5, -5), "an_r": (7.5, -5),
    }


# ----------------------------------------------------------------------
# Painter: draws one frame onto a supersampled canvas
# ----------------------------------------------------------------------
class _Painter:
    def __init__(self, unit_px: float, face: int):
        self.k = unit_px * SS            # pixels per body unit on the big canvas
        self.face = face                 # +1 faces right (Team A), -1 faces left (Team B)
        w = int(2 * CANVAS_X * self.k)
        h = int((CANVAS_TOP + CANVAS_BOTTOM) * self.k)
        self.surf = pygame.Surface((w, h), pygame.SRCALPHA)
        self.cx, self.gy = w / 2, CANVAS_TOP * self.k

    def P(self, pt):
        """Body units -> canvas pixels (mirrored for players facing left)."""
        return (self.cx + pt[0] * self.face * self.k, self.gy + pt[1] * self.k)

    def u(self, v):
        return v * self.k

    # -- primitives -----------------------------------------------------
    def poly(self, pts, col, outline=None, width=0.9):
        pp = [self.P(p) for p in pts]
        pygame.draw.polygon(self.surf, col, pp)
        if outline:
            pygame.draw.polygon(self.surf, outline, pp, max(1, int(self.u(width))))

    def ellipse(self, centre, rx, ry, col, outline=None, width=0.9):
        x, y = self.P(centre)
        rect = pygame.Rect(0, 0, 2 * self.u(rx), 2 * self.u(ry))
        rect.center = (x, y)
        pygame.draw.ellipse(self.surf, col, rect)
        if outline:
            pygame.draw.ellipse(self.surf, outline, rect, max(1, int(self.u(width))))

    def line(self, a, b, col, width):
        pygame.draw.line(self.surf, col, self.P(a), self.P(b), max(1, int(self.u(width))))

    def limb(self, pts, widths, fill, outline, shade):
        """A chain of tapered segments (e.g. shoulder-elbow-wrist).

        Outlines are drawn for the whole chain first, then the fills, so the
        joints blend smoothly. A darker strip on the left side gives volume.
        """
        P = [self.P(p) for p in pts]
        W = [self.u(w * BUILD) for w in widths]
        o = self.u(0.8)
        quads, shades = [], []
        for (a, b), (wa, wb) in zip(zip(P, P[1:]), zip(W, W[1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = math.hypot(dx, dy) or 1
            nx, ny = -dy / n, dx / n                 # perpendicular
            if nx > 0:                               # make n point to screen-left (shadow side)
                nx, ny = -nx, -ny
            quads.append((a, b, wa, wb, nx, ny))
        for a, b, wa, wb, nx, ny in quads:           # 1. outline
            pygame.draw.polygon(self.surf, outline, [
                (a[0] + nx * (wa / 2 + o), a[1] + ny * (wa / 2 + o)), (b[0] + nx * (wb / 2 + o), b[1] + ny * (wb / 2 + o)),
                (b[0] - nx * (wb / 2 + o), b[1] - ny * (wb / 2 + o)), (a[0] - nx * (wa / 2 + o), a[1] - ny * (wa / 2 + o))])
        for pt, w in zip(P, W):
            pygame.draw.circle(self.surf, outline, pt, w / 2 + o)
        for a, b, wa, wb, nx, ny in quads:           # 2. fill
            pygame.draw.polygon(self.surf, fill, [
                (a[0] + nx * wa / 2, a[1] + ny * wa / 2), (b[0] + nx * wb / 2, b[1] + ny * wb / 2),
                (b[0] - nx * wb / 2, b[1] - ny * wb / 2), (a[0] - nx * wa / 2, a[1] - ny * wa / 2)])
        for pt, w in zip(P, W):
            pygame.draw.circle(self.surf, fill, pt, w / 2)
        for a, b, wa, wb, nx, ny in quads:           # 3. shading strip
            pygame.draw.polygon(self.surf, shade, [
                (a[0] + nx * wa / 2, a[1] + ny * wa / 2), (b[0] + nx * wb / 2, b[1] + ny * wb / 2),
                (b[0] + nx * wb * 0.12, b[1] + ny * wb * 0.12), (a[0] + nx * wa * 0.12, a[1] + ny * wa * 0.12)])


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _render(team: int, i: int, pose: str, frame: int, height: int, face: int) -> pygame.Surface:
    look = ROSTER[team][i]
    pt = _Painter(height / 100.0, face)
    J = _skeleton(pose, frame)
    skin = look["skin"]
    skin_shade, skin_line = _mul(skin, 0.78), _mul(skin, 0.5)
    jersey, trim = T.TEAM_COLOURS[team], T.TEAM_LIGHT[team]
    jersey_shade, jersey_line = _mul(jersey, 0.72), _mul(jersey, 0.45)
    hair = look["hair_col"]

    # ground shadow
    shadow = pygame.Surface((int(pt.u(40)), int(pt.u(8))), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (45, 30, 15, 95), shadow.get_rect())
    pt.surf.blit(shadow, shadow.get_rect(center=pt.P((0, -1))))

    # -- legs, bare feet with team-colour anklets -------------------------
    for key in ("l", "r"):
        hip, kn, an = J["hip_" + key], J["kn_" + key], J["an_" + key]
        pt.limb([hip, kn, an], [9.5, 6.5, 4.2], skin, skin_line, skin_shade)
        toe = 1.5 if key == "r" else 0.5
        pt.ellipse((an[0] + toe, an[1] + 3.2), 4.4, 2.3, skin, skin_line, 0.7)
        pt.line((an[0] - 2.4, an[1] - 0.8), (an[0] + 2.4, an[1] - 0.8), trim, 1.3)

    # -- shorts ----------------------------------------------------------
    def leg_opening(key, side):
        hip, kn = J["hip_" + key], J["kn_" + key]
        c = _lerp(hip, kn, 0.42)
        return (c[0] + side * 5.6, c[1]), (c[0] - side * 4.6, c[1] + 0.6)
    out_l, in_l = leg_opening("l", -1)
    out_r, in_r = leg_opening("r", 1)
    wl, wr = J["waist_l"], J["waist_r"]
    shorts = [(wl[0] - 0.5, wl[1] + 1), (wr[0] + 0.5, wr[1] + 1), out_r, in_r, J["crotch"], in_l, out_l]
    pt.poly(shorts, SHORTS, _mul(SHORTS, 0.5))
    pt.line((wr[0] + 0.2, wr[1] + 2), out_r, trim, 1.1)         # side stripes
    pt.line((wl[0] - 0.2, wl[1] + 2), out_l, trim, 1.1)

    # -- back arm (raider only: it swings behind the body) ------------------
    if pose == "raid":
        pt.limb([J["sh_l"], J["el_l"], J["wr_l"]], [6.2, 4.6, 3.6], skin_shade, skin_line, _mul(skin, 0.65))
        pt.ellipse(J["wr_l"], 2.5, 2.7, skin_shade, skin_line, 0.6)

    # -- arms (drawn before the vest, so the vest covers the shoulder joints)
    arms = ("r",) if pose == "raid" else ("l", "r")
    for key in arms:
        pt.limb([J["sh_" + key], J["el_" + key], J["wr_" + key]], [6.4, 4.8, 3.7], skin, skin_line, skin_shade)
        pt.ellipse(J["wr_" + key], 2.6, 2.8, skin, skin_line, 0.6)

    # -- neck --------------------------------------------------------------
    pt.limb([J["neck_base"], J["neck_top"]], [7.2, 6.4], skin, skin_line, skin_shade)

    # -- jersey: sleeveless kabaddi vest with number ------------------------
    sl, sr, nb = J["sh_l"], J["sh_r"], J["neck_base"]
    pit_l = _lerp(sl, wl, 0.38)
    pit_r = _lerp(sr, wr, 0.38)
    hem_l, hem_r = (wl[0] - 0.3, wl[1] + 3), (wr[0] + 0.3, wr[1] + 3)
    neck_l, neck_r, dip = (nb[0] - 4.5, nb[1] - 0.5), (nb[0] + 4.5, nb[1] - 0.5), (nb[0], nb[1] + 5)
    vest = [neck_l, (sl[0] + 2.5, sl[1] + 0.3), (pit_l[0] + 1.2, pit_l[1]), hem_l, hem_r,
            (pit_r[0] - 1.2, pit_r[1]), (sr[0] - 2.5, sr[1] + 0.3), neck_r, dip]
    pt.poly(vest, jersey)
    # shading on the left side, a highlight on the right
    pt.poly([(sl[0] + 2.5, sl[1] + 0.3), (pit_l[0] + 1.2, pit_l[1]), hem_l, (hem_l[0] + 5, hem_l[1]),
             (pit_l[0] + 5, pit_l[1]), (sl[0] + 6, sl[1] + 1)], jersey_shade)
    pt.poly([(pit_r[0] - 1.2, pit_r[1]), (hem_r[0], hem_r[1]), (hem_r[0] - 2, hem_r[1]),
             (pit_r[0] - 3, pit_r[1] + 1)], _mix(jersey, (255, 255, 255), 0.18))
    pygame.draw.polygon(pt.surf, jersey_line, [pt.P(p) for p in vest], max(1, int(pt.u(0.9))))
    pt.line(neck_l, dip, trim, 1.2)                               # collar trim
    pt.line(dip, neck_r, trim, 1.2)
    pt.line((sl[0] + 2.5, sl[1] + 0.3), (pit_l[0] + 1.2, pit_l[1]), trim, 1.0)   # arm-hole trim
    pt.line((sr[0] - 2.5, sr[1] + 0.3), (pit_r[0] - 1.2, pit_r[1]), trim, 1.0)
    chest = ((sl[0] + sr[0]) / 2, (sl[1] + wl[1]) / 2 + 1)
    num = T.font(max(8, int(pt.u(11))), True).render(str(i + 1), True, (250, 248, 240))
    num_shadow = T.font(max(8, int(pt.u(11))), True).render(str(i + 1), True, jersey_line)
    cx, cy = pt.P(chest)
    pt.surf.blit(num_shadow, num_shadow.get_rect(center=(cx + pt.u(0.5), cy + pt.u(0.6))))
    pt.surf.blit(num, num.get_rect(center=(cx, cy)))

    _head(pt, J["head"], look, pose, frame, skin, skin_shade, skin_line, hair, trim)

    img = pygame.transform.smoothscale(pt.surf, (pt.surf.get_width() // SS, pt.surf.get_height() // SS))
    return img


def _head(pt: _Painter, h, look, pose, frame, skin, skin_shade, skin_line, hair, trim):
    hx, hy = h
    rx, ry = 6.8, 8.3
    fs = 1.6                                   # face turned slightly toward where he is going
    # ears
    for side in (-1, 1):
        pt.ellipse((hx + side * 6.6, hy + 0.8), 1.5, 2.3, skin_shade, skin_line, 0.6)
    # head with shading on the left
    pt.ellipse((hx, hy), rx, ry, skin_shade, skin_line, 0.9)
    pt.ellipse((hx + 0.9, hy - 0.3), rx - 1.1, ry - 0.9, skin)
    # hair
    _hair(pt, look["hair"], hx, hy, rx, ry, hair, trim)
    # beard / mustache
    if look["extra"] == "beard":
        jaw = [(hx + rx * math.cos(a), hy + ry * math.sin(a))
               for a in [math.radians(d) for d in range(0, 181, 15)]]
        inner = [(hx + fs + (rx - 2.5) * math.cos(a) * 0.75, hy + 3.2 + (ry - 4.5) * math.sin(a) * 0.8)
                 for a in [math.radians(d) for d in range(180, -1, -15)]]
        pt.poly(jaw + inner, _mix(hair, skin, 0.25))
    # eyebrows and eyes
    for side in (-1, 1):
        ex, ey = hx + fs + side * 2.7, hy + 0.2
        tilt = 0.8 if pose == "raid" else 0.0          # determined frown when raiding
        pt.line((ex - 1.5, ey - 2.3 - (tilt if side < 0 else 0) * 0.3),
                (ex + 1.5, ey - 2.3 + (tilt if side > 0 else 0) * 0.2 * side), hair, 0.9)
        pt.ellipse((ex, ey), 1.4, 0.95, (245, 240, 232))
        pt.ellipse((ex + 0.45, ey + 0.05), 0.75, 0.8, (40, 26, 18))
    # nose
    pt.line((hx + fs + 0.3, hy + 0.8), (hx + fs + 1.0, hy + 3.3), skin_line, 0.6)
    pt.line((hx + fs + 1.0, hy + 3.3), (hx + fs - 0.4, hy + 3.6), skin_line, 0.6)
    # mustache
    if look["extra"] == "mustache":
        pt.poly([(hx + fs - 2.8, hy + 4.9), (hx + fs, hy + 4.2), (hx + fs + 2.8, hy + 4.9),
                 (hx + fs + 2.2, hy + 5.5), (hx + fs, hy + 5.0), (hx + fs - 2.2, hy + 5.5)], hair)
    # mouth: the raider chants with his mouth open, everyone else keeps it shut
    lips = _mix(_mul(skin, 0.6), (150, 50, 50), 0.35)
    if pose in ("raid", "celebrate"):       # chanting / cheering
        open_ = 0.6 + 0.9 * abs(math.sin(2 * math.pi * frame / FRAMES[pose] * 2))
        pt.ellipse((hx + fs, hy + 6.1), 1.6, open_, (90, 25, 25), lips, 0.4)
    else:
        pt.line((hx + fs - 1.6, hy + 6.0), (hx + fs + 1.6, hy + 6.0), lips, 0.7)


def _hair(pt: _Painter, style, hx, hy, rx, ry, col, band_col):
    hi = _mix(col, (200, 190, 180), 0.25)

    def cap(extra, hairline, fringe_shift=0.0):
        top = [(hx + (rx + extra) * math.cos(a), hy + (ry + extra) * math.sin(a))
               for a in [math.radians(d) for d in range(180, 361, 10)]]
        line = [(hx + rx, hy + hairline + 1.5), (hx + rx * 0.4 + fringe_shift, hy + hairline),
                (hx - rx * 0.4 + fringe_shift, hy + hairline), (hx - rx, hy + hairline + 1.5)]
        return top + line

    if style == "curly":
        pt.poly(cap(1.6, -3.0), col)
        for d in range(170, 371, 20):
            a = math.radians(d)
            pt.ellipse((hx + (rx + 1.2) * math.cos(a), hy + (ry + 1.2) * math.sin(a) - 0.5),
                       2.2, 2.2, col, _mul(col, 0.6), 0.4)
    elif style == "spiky":
        pt.poly(cap(0.8, -3.6), col)
        for d in range(195, 346, 25):
            a = math.radians(d)
            base = (hx + (rx + 0.5) * math.cos(a), hy + (ry + 0.5) * math.sin(a))
            tip = (hx + (rx + 4.0) * math.cos(a + 0.12), hy + (ry + 4.0) * math.sin(a + 0.12))
            side = (hx + (rx + 0.5) * math.cos(a + 0.35), hy + (ry + 0.5) * math.sin(a + 0.35))
            pt.poly([base, tip, side], col)
    elif style == "side":
        pt.poly(cap(1.0, -2.6, fringe_shift=-1.5), col)
        pt.poly([(hx - rx - 0.5, hy - 1.5), (hx - 2, hy - ry - 1.4), (hx + 3, hy - ry - 0.6),
                 (hx - 1, hy - 4.5)], col)                       # swept fringe
    else:                                                        # short / band
        pt.poly(cap(0.7, -3.4), col)
    # sideburns + highlight
    for side in (-1, 1):
        pt.poly([(hx + side * (rx - 0.2), hy - 3), (hx + side * (rx - 1.4), hy - 3),
                 (hx + side * (rx - 1.2), hy + 1), (hx + side * (rx - 0.2), hy + 0.5)], col)
    a0, a1 = math.radians(250), math.radians(320)
    arc = [(hx + (rx - 0.6) * math.cos(a0 + (a1 - a0) * t / 6), hy + (ry - 0.4) * math.sin(a0 + (a1 - a0) * t / 6))
           for t in range(7)]
    for p, q in zip(arc, arc[1:]):
        pt.line(p, q, hi, 0.8)
    if style == "band":                                         # headband with knot tails
        pt.line((hx - rx - 0.3, hy - 3.6), (hx + rx + 0.3, hy - 3.6), band_col, 2.0)
        pt.line((hx - rx - 0.3, hy - 3.6), (hx - rx - 4.5, hy - 1.0), band_col, 1.2)
        pt.line((hx - rx - 0.3, hy - 3.6), (hx - rx - 3.5, hy + 0.8), band_col, 1.0)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def character_surface(team: int, i: int, pose: str, frame: int, height: int,
                      face: int | None = None) -> pygame.Surface:
    """Cached image of one animation frame. ``height`` = standing height in px.
    ``face`` = +1 looks right, -1 looks left (default: toward the other team)."""
    if face is None:
        face = 1 if team == 0 else -1
    key = (team, i, pose, frame % FRAMES[pose], int(height), face)
    if key not in _cache:
        if pose == "fallen":       # a crouched body tipped over onto the ground
            base = character_surface(team, i, "crouch", 0, height, face)
            _cache[key] = pygame.transform.rotozoom(base, -face * 78, 1.0)   # smooth rotation
        else:
            _cache[key] = _render(team, i, pose, key[3], key[4], face)
    return _cache[key]


def clear_cache() -> None:
    """Forget cached frames (needed after pygame.quit(), like the font cache)."""
    _cache.clear()


def frame_for(pose: str, now: float, moving: bool, i: int) -> int:
    rate = {"idle": 1.6, "crouch": 3.0, "raid": 14.0 if moving else 6.0, "celebrate": 9.0,
            "walk": 10.0, "sit": 0, "fallen": 0}[pose]
    return int(now * rate + i * 1.7) % FRAMES[pose]


def draw_character(surf, x: float, feet_y: float, team: int, i: int, pose: str, now: float,
                   moving: bool = False, height: int = 100, show_name: bool = True,
                   name_colour=(55, 40, 25), face: int | None = None, alpha: int = 255) -> None:
    """Draw player i of ``team`` with his feet at (x, feet_y)."""
    img = character_surface(team, i, pose, frame_for(pose, now, moving, i), height, face)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    k = height / 100.0
    if pose == "fallen":
        surf.blit(img, img.get_rect(center=(x, feet_y - 14 * k)))
        return
    surf.blit(img, (x - CANVAS_X * k, feet_y - CANVAS_TOP * k))
    if show_name:
        tag = T.font(max(10, int(12 * k)), True).render(ROSTER[team][i]["name"], True, name_colour)
        surf.blit(tag, tag.get_rect(midtop=(x, feet_y + 3 * k)))
