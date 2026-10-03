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
    assert main.active_tactics(19) == []
    assert main.active_tactics(30) == ["FLANK", "RELOAD"]
    assert main.active_tactics(60) == ["FLANK", "RELOAD", "ECM"]


@pytest.mark.parametrize("level,boss", [(1, False), (25, False), (45, False), (65, False), (90, False), (40, True)])
def test_missiles_never_fire(level, boss):
    """A missile's only attack is to reach the jet (proximity fuse in the game loop): update() never returns shots."""
    e = main.MissileEnemy(level, is_boss=boss, launch_x=400, ground_y=540)
    for f in range(1500):
        assert e.update([(200, 140), (600, 150)], 400 + 250 * math.cos(f * 0.02), 300, 800, 600) is None


def test_missiles_never_vanish_or_teleport():
    """Missiles come from launchers and stay in sight: no radar-cloak hiding or reappearing elsewhere."""
    e = main.MissileEnemy(60, launch_x=300, ground_y=540)
    holes = [(200, 140), (620, 150), (220, 480), (600, 470), (410, 310)]
    last = (e.x, e.y)
    for f in range(3000):
        e.update(holes, 400 + 300 * math.cos(f * 0.01), 300, 800, 600)
        if e.y + e.height / 2 >= 540 - 12:     # reached the ground: the game loop takes it from here
            break
        assert not e.is_burrowed
        assert math.hypot(e.x - last[0], e.y - last[1]) < 40
        last = (e.x, e.y)


def test_missile_waits_on_launcher_then_climbs():
    e = main.MissileEnemy(1, launch_x=300, ground_y=540, launch_delay=10)
    start = (e.x, e.y)
    for _ in range(10):
        e.update([(200, 140)], 100, 200, 800, 600)
    assert (e.x, e.y) == start                    # still on the launcher
    for _ in range(20):
        e.update([(200, 140)], 100, 200, 800, 600)
    assert e.y < start[1]                         # lifted off and climbing


def test_missile_turns_at_most_30_degrees_per_second():
    e = main.MissileEnemy(90, launch_x=400, ground_y=540)     # hypersonic: the most agile class
    worst = 0.0
    for f in range(1000):
        before = e.heading
        e.update([], 100 + 600 * (f // 120 % 2), 120, 800, 600)  # target jumps side to side every 2 s
        if e.age > 35 and not e.expired:                          # whole guided flight, edges included
            worst = max(worst, abs((e.heading - before + math.pi) % (2 * math.pi) - math.pi))
    assert math.degrees(worst) * 60 <= 30 + 1e-6


def test_missile_leaves_the_rail_angled_at_the_target():
    e = main.MissileEnemy(1, launch_x=200, ground_y=540)
    e.update([], 600, 200, 800, 600)                           # target up and to the right
    assert -math.pi / 2 < e.heading < 0                         # launched up-right, not straight up
    e2 = main.MissileEnemy(1, launch_x=600, ground_y=540)
    e2.update([], 600, 560, 800, 600)                          # target level with the rail
    assert math.degrees(e2.heading) <= -15 + 1e-6               # never below 15 degrees of elevation


def test_spent_missile_falls_far_from_its_launcher():
    e = main.MissileEnemy(1, launch_x=100, ground_y=540)
    for f in range(main.MISSILE_FLIGHT_FRAMES + 600):
        e.update([], 700, 150, 8000, 600)                       # wide sky so it never leaves the side
        if e.expired and e.y + e.height / 2 >= 540 - 12:
            break
    assert e.expired
    assert abs((e.x + e.width / 2) - 100) > 200                  # came down well away from the launcher


def test_arsenal_has_2_launchers_and_2_munitions_per_nation_and_is_json():
    import json
    nations = main.ARSENAL["nations"]
    assert [n["code"] for n in nations] == ["RUS", "IRN", "CHN", "UKR", "PRK", "USA", "GBR", "DEU"]
    for n in nations:
        assert len(n["launchers"]) == 2 and len(n["munitions"]) == 2
        for m in n["munitions"]:
            assert m["role"] in main.MUNITION_ROLES
    assert json.loads(json.dumps(main.ARSENAL)) == main.ARSENAL
    trails = [tuple(x["trail"]) for n in nations for x in n["launchers"] + n["munitions"]]
    assert len(set(trails)) == len(trails)                      # every system has its own trail colour
    ids = [x["id"] for n in nations for x in n["launchers"] + n["munitions"]] + [main.GENERIC_IR_MISSILE["id"]]
    assert len(set(ids)) == len(ids)
    # every weapon / launcher name is the game's own "-M" version, never the real system's name (user, 2026-10-03)
    names = [x["name"] for n in nations for x in n["launchers"] + n["munitions"]] + [main.GENERIC_IR_MISSILE["name"]]
    assert all(nm.endswith("-M") for nm in names)


def test_a_nation_unlocks_every_5_levels():
    assert main.unlocked_nations(4) == [] and main.jet_loadout(4) == []
    assert [n["code"] for n in main.unlocked_nations(5)] == ["RUS"]
    assert [n["code"] for n in main.unlocked_nations(9)] == ["RUS"]
    assert len(main.unlocked_nations(40)) == 8
    assert len(main.unlocked_launchers(15)) == 6
    assert [m["id"] for m in main.jet_loadout(5)] == ["r77", "kh29"]
    assert "ir_seeker" not in [m["id"] for m in main.jet_loadout(9)]
    assert "ir_seeker" in [m["id"] for m in main.jet_loadout(10)]          # heat seekers from level 10
    assert len(main.jet_loadout(60)) == 17


def test_multi_barrel_launchers_fire_salvos():
    sam = {"type": "SAM", "salvo": 1}
    mbml = {"type": "MBML", "salvo": 3}
    assert main.salvo_size(None, 50) == 1 and main.salvo_size(sam, 80) == 1
    assert main.salvo_size(mbml, 5) == 2 and main.salvo_size(mbml, 25) == 3


def test_missile_from_a_nation_launcher_carries_its_trail_and_speed():
    sysd = dict(main.ARSENAL["nations"][0]["launchers"][0], nation="RUS")
    plain = main.MissileEnemy(20, launch_x=300, ground_y=540)
    e = main.MissileEnemy(20, launch_x=300, ground_y=540, system=sysd)
    assert e.nation == "RUS" and e.trail_color == tuple(sysd["trail"])
    assert e.speed_stat == pytest.approx(plain.speed_stat * sysd["speed"])
    for f in range(400):                                          # still never fires
        assert e.update([], 400, 200, 800, 600) is None


def test_human_gets_15_percent_only_against_the_ai():
    assert main.human_buff("CAMPAIGN") == pytest.approx(1.15)
    assert main.human_buff("CAMPAIGN", "MANUAL") == pytest.approx(1.15)
    assert main.human_buff("DUEL", "AUTO") == pytest.approx(1.15)          # duel against the AI missile
    assert main.human_buff("DUEL") == main.human_buff("DUEL", "MANUAL") == 1.0   # human vs human: even


def test_silo_counts_by_level():
    assert [main.silo_count(l) for l in (9, 10, 19, 20, 30, 40, 50, 90)] == [0, 2, 2, 4, 6, 8, 10, 10]


def test_silo_hidden_spooling_firing_exposed():
    s = main.SiloLauncher(400, shots=2, first_delay=5)
    assert s.state == "HIDDEN" and not s.targetable and not s.hot
    fired = [s.update() for _ in range(5)]
    assert s.state == "SPOOLING" and s.hot and not s.targetable and not any(fired)
    for _ in range(main.SILO_SPOOL_FRAMES - 1):
        assert not s.update()
    assert s.update() is True                                   # ignition
    assert s.state == "FIRING" and s.targetable and s.shots == 1
    s.update()
    assert s.state == "EXPOSED" and s.targetable and not s.hot
    held = main.SiloLauncher(400, shots=1, first_delay=1)
    for _ in range(500):
        assert not held.update(hold=True)                         # stealth: it waits
    assert held.state == "HIDDEN"


def test_flir_cone_finds_silos_below_the_jet():
    # straight below, inside the active range: found when scanning, not passively while cold
    assert main.flir_sees(400, 200, 420, 534, active=True, hot=False)
    assert not main.flir_sees(400, 200, 420, 534, active=False, hot=False)
    assert main.flir_sees(400, 300, 420, 534, active=False, hot=True)      # passive picks up a hot silo close by
    assert not main.flir_sees(400, 200, 760, 534, active=True, hot=True)   # outside the 35 degree cone
    assert not main.flir_sees(400, 560, 400, 534, active=True, hot=True)   # silo above the pod


def test_rocket_motor_accelerates_then_drag_slows_it():
    o = {"speed": 3.0, "burn": 60, "burn_left": 60, "thrust": 0.55, "dry_mass": 1.0, "fuel_mass": 0.5,
         "drag": 0.0022, "vmax": 13.0}
    speeds = []
    for _ in range(200):
        main.motor_step(o)
        speeds.append(o["speed"])
    assert speeds[30] > speeds[0] and max(speeds) <= 13.0
    assert speeds[-1] < max(speeds)                              # motor burnt out: coasting, slowing


def test_proportional_navigation_hits_a_crossing_target():
    """A PN missile leads a target crossing its path and gets within fuse range; the turn never beats its G limit."""
    x, y, heading, los_prev = 0.0, 0.0, 0.0, None
    tx, ty, tvx = 400.0, -150.0, -2.0
    max_turn = math.radians(200) / 60
    best = 1e9
    for _ in range(200):
        los = math.atan2(ty - y, tx - x)
        new = main.guidance_turn(heading, los_prev, los, 4.0, max_turn)
        assert abs(main.angle_diff(new, heading)) <= max_turn + 1e-9
        heading, los_prev = new, los
        x += math.cos(heading) * 10
        y += math.sin(heading) * 10
        tx += tvx
        best = min(best, math.hypot(tx - x, ty - y))
    assert best < main.ORDNANCE_FUSE


def test_ir_seeker_only_sees_inside_its_cone():
    assert main.ir_pick_target(0, 0, 0.0, [(300, 20), (100, 0)], 45, 520) == (100, 0)
    assert main.ir_pick_target(0, 0, 0.0, [(-100, 0)], 45, 520) is None        # behind it
    assert main.ir_pick_target(0, 0, 0.0, [(600, 0)], 45, 520) is None         # out of range


def test_jet_crashes_when_it_touches_the_ground():
    assert not main.jet_hits_ground(540 - 40, 540)               # low flight is fine
    assert main.jet_hits_ground(540 - main.JET_GROUND_CLEARANCE, 540)
    assert main.jet_hits_ground(545, 540)


def test_drone_levels_and_launcher_counts():
    assert [main.drone_level(l) for l in (1, 2, 3, 20, 21, 100)] == [1, 2, 3, 20, 20, 20]
    # one more launcher every 10 levels, for missile launchers and drone launchers alike (user, 2026-10-03)
    steps = (1, 10, 11, 20, 21, 56, 90, 91, 100, 250)
    assert [main.launcher_count(l) for l in steps] == [1, 1, 2, 2, 3, 6, 9, 10, 10, 10]
    assert [main.drone_launcher_count(l) for l in steps] == [1, 1, 2, 2, 3, 6, 9, 10, 10, 10]
    assert [main.drones_per_launcher(l) for l in (1, 5, 6, 15, 20, 90)] == [1, 1, 2, 3, 4, 4]


def test_drone_flies_at_half_the_jet_speed_and_homes():
    jet_top = 5.4 * main.jet_pace(12)
    d = main.Drone(400, 514, main.drone_speed(jet_top), 12)
    assert d.speed == pytest.approx(jet_top / 2)
    start = math.hypot(100 - d.x, 200 - d.y)
    for _ in range(200):
        x0, y0 = d.x, d.y
        d.update(100, 200)
        assert math.hypot(d.x - x0, d.y - y0) == pytest.approx(d.speed)   # steady subsonic speed
    assert math.hypot(100 - d.x, 200 - d.y) < start


def test_spent_drone_glides_down():
    d = main.Drone(400, 300, 2.0, 1)
    for _ in range(main.DRONE_LIFE):
        d.update(400, 100)
    assert d.expired
    y_engine_off = d.y
    for _ in range(240):
        d.update(400, 100)                                      # no longer homes on the target above
    assert d.y > y_engine_off + 100                             # coming down


def test_autogun_fires_only_at_drones_in_range_with_lead():
    near = main.Drone(300, 100, 2.0, 1)
    near.age, near.heading = 100, 0.0                               # flying right, 100 px above the gun
    assert main.autogun_pick(300, 200, []) is None
    far = main.Drone(300 + main.AUTOGUN_RANGE + 50, 200, 2.0, 1)
    assert main.autogun_pick(300, 200, [far]) is None               # out of range: holds fire
    aim = main.autogun_pick(300, 200, [near, far])
    assert aim is not None and -math.pi / 2 < aim < 0              # up, and leading to the right


def test_drone_launcher_sends_its_drones_and_one_missile():
    dl = main.DroneLauncher(200, drones=2, first_delay=3, missile_delay=10)
    drones = missiles = 0
    for _ in range(2000):
        a, b = dl.update()
        drones += a
        missiles += b
    assert (drones, missiles) == (2, 1) and not dl.pending
    held = main.DroneLauncher(200, drones=2, first_delay=1, missile_delay=1)
    for _ in range(300):
        assert held.update(hold=True) == (False, False)              # stealth: nothing launches


def test_control_modes_toggle_and_are_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SAVE_FILE", tmp_path / "save.json")
    assert main.load_control_modes() == {"jet": "AUTO", "missile": "MANUAL", "difficulty": "NORMAL"}   # defaults
    assert main.toggle_mode("AUTO") == "MANUAL" and main.toggle_mode("MANUAL") == "AUTO"
    assert main.toggle_mode("NORMAL") == "EASY" and main.toggle_mode("EASY") == "NORMAL"
    main.save_control_modes({"jet": "MANUAL", "missile": "AUTO", "difficulty": "EASY"})
    main.update_save_data(500, 3)                                              # score saving keeps the modes
    assert main.load_control_modes() == {"jet": "MANUAL", "missile": "AUTO", "difficulty": "EASY"}
    assert main.load_save_data()["high_score"] == 500


def test_easy_ai_is_slower_and_duller_but_never_turns_faster():
    n = main.MissileEnemy(30, launch_x=400, ground_y=540)
    e = main.MissileEnemy(30, launch_x=400, ground_y=540, difficulty="EASY")
    assert e.speed_stat < n.speed_stat and e.turn_rate < n.turn_rate <= main.MISSILE_TURN_PER_FRAME
    assert e.fuse_factor < n.fuse_factor == 1.0
    easy, normal = main.difficulty_factors("EASY"), main.difficulty_factors("NORMAL")
    assert easy["duel_sees"] < normal["duel_sees"] and not easy["duel_burrow"] and normal["duel_lead"]
    assert main.difficulty_factors("???") == normal


def test_first_time_hints_show_once(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SAVE_FILE", tmp_path / "save.json")
    assert main.hints_due(4, []) == []
    assert [h[0] for h in main.hints_due(12, [])] == ["ordnance", "flir"]
    main.mark_hint_seen("ordnance")
    seen = main.load_save_data()["hints_seen"]
    assert [h[0] for h in main.hints_due(12, seen)] == ["flir"]
    for h in main.HINTS:
        assert set(h[2]) == {"keys", "touch", "pad"}


def test_level_1_drone_launchers_carry_no_missile():
    dl = main.DroneLauncher(200, drones=1, first_delay=1, missile_delay=1, has_missile=False)
    missiles = sum(dl.update()[1] for _ in range(1000))
    assert missiles == 0 and not dl.pending
    assert main.DRONE_MISSILE_LEVEL == 5


def test_missile_gives_up_after_20_seconds_and_falls():
    e = main.MissileEnemy(10, launch_x=400, ground_y=540)
    for f in range(main.MISSILE_FLIGHT_FRAMES + 5):
        e.update([], 400, 100, 800, 600)
    assert e.expired
    y0 = e.y
    for _ in range(120):
        e.update([], 400, 100, 800, 600)                       # it no longer chases the target above
    assert e.y > y0                                            # falling toward the ground
