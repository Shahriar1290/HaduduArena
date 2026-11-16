"""Headless smoke tests for the Pygame UI (uses SDL's dummy video driver)."""
import os
import time

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

from game.rules import ACTIONS, PLAYER, TERMINAL  # noqa: E402
from ui.screens import (App, GameScreen, MenuScreen, ResultsScreen, RulesScreen,  # noqa: E402
                        SetupScreen)


@pytest.fixture
def app():
    a = App()
    a.settings["seed"] = 2
    yield a
    pygame.quit()


def test_static_screens_draw(app):
    for screen in (MenuScreen(app), SetupScreen(app, "hva"), SetupScreen(app, "ava"), RulesScreen(app)):
        screen.draw(app.surface)


def wait_for_human(g, timeout=30):
    deadline = time.time() + timeout
    while not g.human_turn() and not TERMINAL(g.state) and time.time() < deadline:
        g.update(time.perf_counter())
        g.draw(g.app.surface)
        time.sleep(0.005)


def test_human_clicks_and_undo(app):
    g = GameScreen(app, {0: "human", 1: "minimax:easy"}, "hva")
    app.go(g)
    g.click_court(g.renderer.cell_center((1, 3)))          # pick raider #2
    assert g.state.phase == "raider"
    g.click_court(g.renderer.cell_center((2, 4)))          # step across
    assert g.state.raider_cell() == (2, 4) and PLAYER(g.state) == 1
    wait_for_human(g)                                      # AI defender answers
    assert g.state.phase == "raider" or g.state.phase == "pick"
    g.draw(app.surface)
    g.undo()                                               # back before our step
    assert g.state.phase == "raider" and g.state.raider_cell() == (1, 3)
    g.undo()
    assert g.state.phase == "pick" and len(g.history) == 1


def test_menu_has_no_human_vs_human(app):
    labels = [b.label for b in MenuScreen(app).buttons]
    assert "Human vs Human" not in labels
    assert labels[:2] == ["Human vs AI", "AI vs AI"]


def test_every_player_has_a_character(app):
    from ui.characters import ROSTER, draw_character
    names = {p["name"] for team in ROSTER for p in team}
    assert len(names) == 10
    for team in (0, 1):
        for i in range(5):
            for pose in ("idle", "raid", "crouch"):
                draw_character(app.surface, 100, 100, team, i, pose, 1.0, moving=True)


def test_ai_vs_ai_plays_to_results(app):
    app.settings["formation"] = "Random CSP"
    g = GameScreen(app, {0: "minimax:easy", 1: "random"}, "ava")
    app.go(g)
    g.speed.value = 1.0
    deadline = time.time() + 120
    while app.screen is g and time.time() < deadline:
        pygame.event.pump()
        g.update(time.perf_counter())
        g.draw(app.surface)
        time.sleep(0.001)
    assert TERMINAL(g.state)
    assert isinstance(app.screen, ResultsScreen)
    app.screen.draw(app.surface)


def test_human_vs_ai_ai_answers_in_background(app):
    g = GameScreen(app, {0: "human", 1: "mcts:easy"}, "hva")
    app.go(g)
    g.click_court(g.renderer.cell_center((1, 3)))
    g.click_court(g.renderer.cell_center((2, 4)))
    assert PLAYER(g.state) == 1
    deadline = time.time() + 30
    while PLAYER(g.state) == 1 and not TERMINAL(g.state) and time.time() < deadline:
        g.update(time.perf_counter())
        g.draw(app.surface)                 # the UI keeps drawing while the AI thinks
        time.sleep(0.005)
    assert PLAYER(g.state) == 0 or TERMINAL(g.state)
    assert len(ACTIONS(g.state)) > 0 or TERMINAL(g.state)


def test_step_safety_colours():
    from ui.screens import step_safety
    from game.state import initial_state
    s = initial_state()._replace(
        pos=(((0, 2), (2, 4), (3, 1), (4, 3), (5, 2)), ((1, 5), (3, 6), (3, 5), (1, 7), (5, 5))),
        phase="raider", raider=1, breath=3, crossed=True)
    levels = dict(step_safety(s))
    assert levels[(2, 3)] == "home"                 # back home after crossing
    assert levels[(2, 5)] == "danger"               # (1,5),(3,5),(3,6) all adjacent -> tackle
    assert set(levels.values()) <= {"home", "safe", "risky", "danger", "neutral"}


def test_raid_end_creates_banner_and_effects(app):
    from game.state import initial_state
    g = GameScreen(app, {0: "human", 1: "minimax:easy"}, "hva")
    app.go(g)
    s = initial_state()._replace(
        pos=(((0, 2), (2, 4), (3, 1), (4, 3), (5, 2)), ((1, 5), (2, 5), (4, 6), (0, 7), (5, 7))),
        phase="defender", raider=1, breath=4, crossed=True, tagged=(0, 1))
    g.state, g.history = s, [(s, 0)]
    g.apply(("move", 2, (3, 5)))                    # completes the tackle
    assert g.banner[0] == "TACKLE!"
    kinds = {e["kind"] for e in g.effects}
    assert {"fallen", "pile", "walk"} <= kinds
    now = time.perf_counter()
    overrides, extras, walking = g._effect_layers(now + 0.2)
    assert any(e["pose"] == "fallen" for e in extras)
    assert (0, 1) in walking                        # Sumon is not on the bench yet
    g.draw(app.surface)


def test_ai_move_is_previewed_and_explained(app):
    g = GameScreen(app, {0: "minimax:easy", 1: "human"}, "hva")
    app.go(g)
    deadline = time.time() + 20
    while g.pending is None and time.time() < deadline:
        g.update(time.perf_counter())
        time.sleep(0.005)
    assert g.pending is not None and g.state.phase == "pick"   # shown, not played yet
    team, analysis = g.analysis
    assert team == 0 and analysis["moves"] and analysis["moves"][0][2]   # chosen move first
    g.draw(app.surface)
    while g.pending is not None and time.time() < deadline:
        g.update(time.perf_counter())
        time.sleep(0.005)
    assert g.state.phase == "raider"                # now it has been played
