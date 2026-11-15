"""Colours, sizes and fonts. Everything is drawn in code (no image/sound files)."""
import pygame

# ---- window / layout -------------------------------------------------
WIDTH, HEIGHT = 1220, 776
CELL = 92
COURT_X, COURT_Y = 24, 98            # top-left of the 8 x 6 grid (736 x 552 px)
CHAR_HEIGHT = int(CELL * 1.2)        # player characters are a bit taller than a cell
FEET_OFFSET = int(CELL * 0.34)       # feet sit this far below the cell centre
COURT_W, COURT_H = CELL * 8, CELL * 6
PANEL_X = COURT_X + COURT_W + 28     # side panel
PANEL_W = WIDTH - PANEL_X - 18
FPS = 60
STEP_ANIM = 0.15                     # seconds per step animation
OUT_FLASH = 0.5                      # seconds for the "player out" flash

# ---- colours -----------------------------------------------------------
SAND = (222, 196, 146)
SAND_DARK = (204, 175, 122)
SAND_SPECK = (190, 160, 110)
CHALK = (250, 248, 238)
BG = (46, 38, 30)                    # dark earth around the pitch
PANEL_BG = (60, 50, 40)
PANEL_CARD = (78, 66, 52)
TEXT = (245, 238, 224)
TEXT_DIM = (190, 178, 158)
GREEN = (36, 140, 64)                # Team A
GREEN_LIGHT = (120, 205, 135)
RED = (196, 44, 44)                  # Team B
RED_LIGHT = (240, 130, 120)
TEAM_COLOURS = (GREEN, RED)
TEAM_LIGHT = (GREEN_LIGHT, RED_LIGHT)
GOLD = (245, 196, 40)
TAG_RING = (255, 150, 30)
HIGHLIGHT = (255, 255, 255)
DANGER = (230, 50, 40)
PATH = (40, 90, 200)
BUTTON = (110, 88, 62)
BUTTON_HOVER = (140, 112, 80)
BUTTON_OFF = (80, 70, 60)
DOD = (220, 40, 40)

_fonts: dict = {}


def font(size: int, bold: bool = False) -> pygame.font.Font:
    """Cached system font (falls back to pygame's default font)."""
    key = (size, bold)
    if key not in _fonts:
        try:
            _fonts[key] = pygame.font.SysFont("segoeui,arial,dejavusans", size, bold=bold)
        except Exception:
            _fonts[key] = pygame.font.Font(None, size + 6)
    return _fonts[key]


def reset_fonts() -> None:
    """Forget cached fonts (they become invalid after pygame.quit())."""
    _fonts.clear()
