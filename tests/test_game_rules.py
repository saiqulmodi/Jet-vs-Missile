"""Rules of Jet vs Missile: difficulty steps, missile classes, AI tactics, ammunition, missile flight."""

import math

import pygame
import pytest

import main


@pytest.fixture(scope="module", autouse=True)
def display():
    pygame.display.set_mode((800, 600))   # sprites need a display (dummy driver, see conftest.py)
    yield


def test_difficulty_rises_every_5_levels():
    assert [main.level_step(l) for l in (1, 5, 6, 10, 11, 96, 100, 101, 500)] == [0, 0, 1, 1, 2, 19, 19, 20, 20]
    assert main.level_power(1) == main.level_power(5) == 1.0
    assert main.level_power(6) == pytest.approx(1.1)
    assert main.level_power(51) == pytest.approx(2.0)
    assert main.level_power(101) == pytest.approx(3.0)
    # level 1 is the slowest; speed only changes when a new 5-level step starts
    assert main.missile_pace(1) == pytest.approx(0.55)
    assert main.jet_pace(1) == pytest.approx(0.75)
    assert main.missile_pace(4) == main.missile_pace(5) < main.missile_pace(6)
    assert main.jet_pace(4) == main.jet_pace(5) < main.jet_pace(6)


def test_missile_class_by_level():
    assert [main.missile_tier_for_level(l) for l in (1, 20, 21, 40, 41, 61, 81, 150)] == [1, 1, 2, 2, 3, 4, 5, 5]


def test_ai_tactics_unlock_with_level():
    assert main.active_tactics(1) == []
    assert main.active_tactics(8) == ["JINK"]
    assert main.active_tactics(30) == ["JINK", "FLANK", "RELOAD"]
    assert main.active_tactics(60) == ["JINK", "FLANK", "RELOAD", "SPRINT", "ECM"]


def test_ammunition_types_and_scaling():
    scatter = main.make_ammo("scatter", 0, 0, 0.0, 100, False)
    assert len(scatter) == 3
    flak = main.make_ammo("flak", 0, 0, 0.0, 300, False)
    assert flak[0]["kind"] == "flak" and flak[0]["fuse"] > 0
    homing = main.make_ammo("homing", 0, 0, 0.0, 500, False)
    assert homing[0]["kind"] == "homing" and homing[0]["life"] == 180
    # damage follows power (and bosses), speed follows pace
    strong = main.make_ammo("homing", 0, 0, 0.0, 500, True, power=2.0, pace=0.5)[0]
    assert strong["dmg"] == int(15 * 1.5 * 2.0)
    assert math.hypot(strong["vx"], strong["vy"]) == pytest.approx(4.2 * 0.5)


def test_arsenal_grows_with_missile_class():
    assert main.MissileEnemy(1).arsenal == []
    assert main.MissileEnemy(21).arsenal == ["scatter"]
    assert main.MissileEnemy(41).arsenal == ["scatter", "flak"]
    assert main.MissileEnemy(61).arsenal == ["scatter", "flak", "homing"]
    assert main.MissileEnemy(5, is_boss=True).arsenal == ["scatter", "flak", "homing"]


def test_missile_waits_on_launcher_then_climbs():
    e = main.MissileEnemy(1, launch_x=300, ground_y=540, launch_delay=10)
    start = (e.x, e.y)
    for _ in range(10):
        e.update([(200, 140)], 100, 200, 800, 600)
    assert (e.x, e.y) == start                    # still on the launcher
    for _ in range(20):
        e.update([(200, 140)], 100, 200, 800, 600)
    assert e.y < start[1]                         # lifted off and climbing


def test_missile_never_flies_into_the_ground():
    e = main.MissileEnemy(70, launch_x=400, ground_y=540)
    lowest = 0
    for f in range(2000):
        e.update([(200, 140), (600, 150)], 400 + 300 * math.cos(f * 0.02), 520, 800, 600)
        if not e.is_burrowed:
            lowest = max(lowest, e.y + e.height / 2)
    assert lowest <= 540 - 20 + 0.5
