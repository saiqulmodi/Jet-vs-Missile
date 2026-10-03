import array
import asyncio
import functools
import json
import math
from pathlib import Path
import random
import sys
import pygame

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
pygame.joystick.init()

joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]

SAVE_FILE = Path("save.json")

GAME_W, GAME_H = 800, 600
_last_fit = None
_portrait = False   # phone held upright (taller than wide)


BASE_W = 800                  # the layout was designed at 800 x 600
MAX_W = 1334                  # 600 x 20:9 (wide phones held sideways)


def pick_game_width() -> int:
    """WIDE SCREEN (user, 2026-10-03: "remove black bar to make it wider"): the battlefield is always 600 tall
    and as wide as the screen's shape (800 for 4:3, 1067 for 16:9, up to 1334 for 20:9 phones), so the picture
    fills the screen with no side bars. Chosen once at start. JVM_ASPECT=1.78 forces it (tests); the
    headless test driver keeps 800."""
    import os
    aspect = 4 / 3
    if os.environ.get("JVM_ASPECT"):
        aspect = float(os.environ["JVM_ASPECT"])
    elif sys.platform == "emscripten":
        try:
            import platform
            w, h = int(platform.window.innerWidth), int(platform.window.innerHeight)
            # a phone loaded upright will be turned sideways to play: use its long side
            aspect = max(w, h) / max(1, min(w, h)) if detect_mobile() else w / max(1, h)
        except Exception:
            pass
    elif os.environ.get("SDL_VIDEODRIVER", "") != "dummy":
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
            aspect = dw / max(1, dh)
        except Exception:
            pass
    return int(max(BASE_W, min(MAX_W, round(GAME_H * aspect))))


def desktop_fullscreen_allowed() -> bool:
    """Full screen only for the real desktop game: not in the browser, not with the test/dummy video driver,
    and not when JVM_WINDOWED=1 is set."""
    import os
    return (sys.platform != "emscripten" and os.environ.get("SDL_VIDEODRIVER", "") != "dummy"
            and os.environ.get("JVM_WINDOWED") != "1")


def detect_mobile():
    """True on phones/tablets (finger as the main pointer) or with ?mobile in the link.
    Desktop tests can force it with the JVM_MOBILE=1 environment variable."""
    import os
    if os.environ.get("JVM_MOBILE") == "1":
        return True
    if sys.platform != "emscripten":
        return False
    try:
        import platform
        win = platform.window
        if "mobile" in str(win.location.search).lower():
            return True
        return bool(win.matchMedia("(pointer: coarse)").matches)
    except Exception:
        return False


def fit_canvas_to_browser():
    """Browser only: scale the 800x600 game to fill the window without cropping (black bars
    fill any spare space). Re-applied regularly because the loader resizes the canvas itself."""
    global _last_fit, _portrait
    if sys.platform != "emscripten":
        return
    try:
        import platform
        win = platform.window
        vw, vh = int(win.innerWidth), int(win.innerHeight)
        _portrait = vh > vw
        k = min(vw / GAME_W, vh / GAME_H)
        w, h = int(GAME_W * k), int(GAME_H * k)
        style = win.canvas.style
        if _last_fit == (vw, vh) and style.width == f"{w}px" and style.height == f"{h}px":
            return
        _last_fit = (vw, vh)
        body = win.document.body.style
        body.margin = "0"
        body.padding = "0"
        body.overflow = "hidden"
        body.backgroundColor = "#05060d"
        style.position = "fixed"
        style.margin = "0"
        style.padding = "0"
        style.border = "none"
        style.display = "block"
        style.left = f"{(vw - w) // 2}px"
        style.top = f"{(vh - h) // 2}px"
        style.width = f"{w}px"
        style.height = f"{h}px"
    except Exception:
        pass


# ==============================================================================
# PERSISTENT SAVE & LEADERBOARD SYSTEM
# ==============================================================================
def load_save_data() -> dict:
    if SAVE_FILE.exists():
        try:
            with open(SAVE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"high_score": 0, "max_level_reached": 1, "total_drones_destroyed": 0}


def update_save_data(score: int, level: int):
    data = load_save_data()
    updated = False
    if score > data.get("high_score", 0):
        data["high_score"] = score
        updated = True
    if level > data.get("max_level_reached", 1):
        data["max_level_reached"] = level
        updated = True
    if updated:
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


# CONTROL MODES (user, 2026-10-03): each side MANUAL or AUTO, chosen on the start screen (J / K, click or tap),
# remembered in save.json. JET AUTO: autopilot flies it when hands off and its guns aim and fire by themselves;
# JET MANUAL: no autopilot, no auto-fire (hands off = it holds its course). MISSILE AUTO: the computer flies P2's
# missile in the duel; MISSILE MANUAL: player 2 flies it. Campaign missiles are always computer-guided.
CONTROL_MODES = ("AUTO", "MANUAL")


DIFFICULTIES = ("NORMAL", "EASY")

# AI DIFFICULTY (user, 2026-10-03): EASY / NORMAL for the computer side (campaign missiles, drones, duel AI missile).
# NORMAL is the game as tuned before; EASY slows and dulls the AI. Never changes the player's own stats.
DIFFICULTY_FACTORS = {
    "NORMAL": {"missile_speed": 1.0, "missile_turn": 1.0, "fuse": 1.0, "drone_speed": 1.0, "drone_dmg": 1.0,
               "drone_gap": 1.0, "duel_sees": 0.6, "duel_speed": 1.0, "duel_burrow": True, "duel_lead": True},
    "EASY":   {"missile_speed": 0.8, "missile_turn": 0.75, "fuse": 0.85, "drone_speed": 0.8, "drone_dmg": 0.7,
               "drone_gap": 1.4, "duel_sees": 0.25, "duel_speed": 0.8, "duel_burrow": False, "duel_lead": False},
}


def difficulty_factors(d: str) -> dict:
    return DIFFICULTY_FACTORS.get(d, DIFFICULTY_FACTORS["NORMAL"])


def load_control_modes() -> dict:
    data = load_save_data()
    jet = data.get("jet_mode", "AUTO")
    missile = data.get("missile_mode", "MANUAL")
    diff = data.get("difficulty", "NORMAL")
    return {"jet": jet if jet in CONTROL_MODES else "AUTO", "missile": missile if missile in CONTROL_MODES else "MANUAL",
            "difficulty": diff if diff in DIFFICULTIES else "NORMAL"}


def save_control_modes(modes: dict):
    data = load_save_data()
    data["jet_mode"], data["missile_mode"] = modes["jet"], modes["missile"]
    data["difficulty"] = modes.get("difficulty", "NORMAL")
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def toggle_mode(m: str) -> str:
    return {"AUTO": "MANUAL", "MANUAL": "AUTO", "EASY": "NORMAL", "NORMAL": "EASY"}[m]


# FIRST-TIME HINTS (user, 2026-10-03): shown once ever (remembered in save.json) when a feature unlocks.
# Each: (id, level, {"keys": ..., "touch": ..., "pad": ...}) -- the text matches how the player is playing.
HINTS = [
    ("ordnance", 5, {"keys": "NEW: nation weapons! R or right click launches, G picks the next one",
                     "touch": "NEW: nation weapons! Tap MSL to launch, WPN to pick the next one",
                     "pad": "NEW: nation weapons! Tap button 7 to launch, hold it + d-pad left/right to pick"}),
    ("flir", 10, {"keys": "NEW: hidden silos! Press X: the FLIR pod scans the ground below you",
                  "touch": "NEW: hidden silos! Tap FLIR: the pod scans the ground below you",
                  "pad": "NEW: hidden silos! Hold button 7 + d-pad up: the FLIR pod scans below you"}),
]
HINT_FRAMES = 330


def hints_due(level: int, seen) -> list:
    """Hints whose feature is unlocked at this level and that the player has never been shown."""
    return [h for h in HINTS if level >= h[1] and h[0] not in seen]


# PLAYER NAMES (user, 2026-10-03: "add a customise feature to add player name, player 1, player 2, before the game
# starts, so that his score is also fixed there"). Names live in save.json "names"; each name's own record in
# "players": {name: {"high_score", "best_level", "wins"}}. The first time "PLAYER 1" is renamed, the record
# made under "PLAYER 1" (the record from before names existed, too) moves to the new name.
MAX_NAME_LEN = 12
DEFAULT_NAMES = ("PLAYER 1", "PLAYER 2")


def clean_name(s: str, default: str) -> str:
    s = "".join(ch for ch in str(s) if ch.isalnum() or ch in " -_.'").strip()[:MAX_NAME_LEN]
    return s.upper() if s else default


def load_player_names():
    names = load_save_data().get("names", list(DEFAULT_NAMES))
    if not isinstance(names, list) or len(names) != 2:
        names = list(DEFAULT_NAMES)
    return [clean_name(names[0], DEFAULT_NAMES[0]), clean_name(names[1], DEFAULT_NAMES[1])]


def _write_save(data: dict):
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def player_record(name: str, data: dict = None) -> dict:
    """A name's record; "PLAYER 1" with no record yet inherits the record from before names existed."""
    data = data if data is not None else load_save_data()
    rec = data.get("players", {}).get(name)
    if rec is None and name == DEFAULT_NAMES[0]:
        rec = {"high_score": data.get("high_score", 0), "best_level": data.get("max_level_reached", 1), "wins": 0}
    return {"high_score": 0, "best_level": 1, "wins": 0, **(rec or {})}


def save_player_names(names, old_p1: str = None):
    names = [clean_name(names[0], DEFAULT_NAMES[0]), clean_name(names[1], DEFAULT_NAMES[1])]
    data = load_save_data()
    players = data.setdefault("players", {})
    if old_p1 == DEFAULT_NAMES[0] and names[0] != old_p1 and names[0] not in players:
        players[names[0]] = player_record(old_p1, data)      # "PLAYER 1"'s record becomes the new name's
        players.pop(old_p1, None)
    data["names"] = list(names)
    _write_save(data)


def record_result(name: str, score: int = None, level: int = None, win: bool = False):
    """Keep a player's best score and level, and count duel wins, under their name."""
    data = load_save_data()
    rec = player_record(name, data)
    if score is not None:
        rec["high_score"] = max(rec["high_score"], int(score))
    if level is not None:
        rec["best_level"] = max(rec["best_level"], int(level))
    if win:
        rec["wins"] += 1
    data.setdefault("players", {})[name] = rec
    _write_save(data)


def mark_hint_seen(hint_id: str):
    data = load_save_data()
    seen = set(data.get("hints_seen", []))
    seen.add(hint_id)
    data["hints_seen"] = sorted(seen)
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ==============================================================================
# PROCEDURAL AUDIO SYNTHESIZER
# ==============================================================================
class RetroSoundEngine:
    @staticmethod
    def create_tone(freq_start: float, freq_end: float, duration: float, wave_type: str = "square", volume: float = 0.5) -> pygame.mixer.Sound:
        sample_rate = 44100
        total_samples = int(sample_rate * duration)
        raw_samples = array.array("h")

        for i in range(total_samples):
            t = i / total_samples
            freq = freq_start + (freq_end - freq_start) * t
            phase = (2.0 * math.pi * freq * (i / sample_rate)) % (2.0 * math.pi)

            if wave_type == "sine":
                val = math.sin(phase)
            elif wave_type == "square":
                val = 1.0 if math.sin(phase) >= 0 else -1.0
            elif wave_type == "noise":
                val = random.uniform(-1.0, 1.0)
            else:
                val = 2.0 * (phase / (2.0 * math.pi)) - 1.0

            envelope = (1.0 - t) ** 1.3
            sample_val = int(val * envelope * 32767 * volume)
            raw_samples.append(sample_val)
            raw_samples.append(sample_val)

        return pygame.mixer.Sound(buffer=raw_samples)

    def __init__(self):
        self.snd_shoot = self.create_tone(880, 240, 0.08, "square", volume=0.25)
        self.snd_laser = self.create_tone(950, 1200, 0.05, "sine", volume=0.15)
        self.snd_hit = self.create_tone(1100, 350, 0.06, "sine", volume=0.3)
        self.snd_explode = self.create_tone(160, 40, 0.35, "noise", volume=0.45)
        self.snd_shield = self.create_tone(400, 800, 0.15, "sine", volume=0.35)
        self.snd_heal = self.create_tone(523, 1046, 0.22, "sine", volume=0.35)
        self.snd_decoy = self.create_tone(600, 1200, 0.2, "sine", volume=0.35)
        self.snd_burrow = self.create_tone(280, 90, 0.28, "square", volume=0.3)
        self.snd_win = self.create_tone(440, 880, 0.35, "sine", volume=0.4)
        self.snd_bonus = self.create_tone(500, 1400, 0.25, "sine", volume=0.45)
        self.snd_split = self.create_tone(350, 1050, 0.3, "sine", volume=0.4)
        self.snd_ordnance = self.create_tone(260, 760, 0.2, "saw", volume=0.3)   # jet missile / bomb release
        self.snd_drone = self.create_tone(520, 300, 0.12, "square", volume=0.2)    # drone leaves its launcher
        self.snd_autogun = self.create_tone(1400, 600, 0.04, "noise", volume=0.18)  # auto-gun round
        self.snd_ignite =self.create_tone(120, 320, 0.25, "noise", volume=0.35)  # underground silo ignition


SFX = RetroSoundEngine()


# ==============================================================================
# OVERDRIVE MUTATORS (past level 100)
# ==============================================================================
OVERDRIVE_MUTATORS = [
    ("LOW GRAVITY ZONE", "Floats high in air; laser recoil kicks backward!"),
    ("BLACKOUT FOG", "Pitch black arena! Only neon glows reveal targets!"),
    ("HYPER SPEED STORM", "1.5x arena movement & rapid weapon discharge!")
]


# ==============================================================================
# SPRITE GENERATION
# ==============================================================================
JET_GROUND_CLEARANCE = 12   # the jet's centre this close to the ground line = it hit the ground

# AEROBATIC FLIGHT (user, 2026-10-03: "jet should have aerobatic movement"): when steered, the jet turns its nose
# at a limited rate and keeps its speed, so it flies arcs, loops and rolls instead of stopping and reversing.
# Asked to reverse, it pulls up through a half loop (Immelmann) -- or, near the top, dives through one (split-S).
JET_TURN_PER_FRAME = 0.085   # about 290 degrees per second
HALF_LOOP_TOP = 150          # above this height a reversal goes down through the half loop instead of up

# SKY ESCAPE (user, 2026-10-03: "it goes up into sky to escape from attack, let it go, come back within 3 seconds"):
# the jet may fly out of the top of the screen. Up there it is out of sight (missiles and drones head for the spot
# where it vanished, their fuses can't find it). After SKY_RETURN frames above the top it turns back down by
# itself, so it is always back in the fight within 3 s; SKY_CEILING stops it climbing too far.
SKY_RETURN = 75
SKY_CEILING = -170
SKY_MAX_FRAMES = 180


def aerobatic_heading(head: float, want: float, cy: float) -> float:
    """Next heading of a steered jet flying at `head` that is asked to fly toward `want` (screen y points down)."""
    diff = angle_diff(want, head)
    if abs(diff) > 2.6:                                 # a reversal: fly a half loop, not a skid
        nose_up = -1.0 if math.cos(head) >= 0 else 1.0  # turning this way lifts the nose
        diff = abs(diff) * (nose_up if cy > HALF_LOOP_TOP else -nose_up)
    return head + max(-JET_TURN_PER_FRAME, min(JET_TURN_PER_FRAME, diff))


def jet_hits_ground(center_y: float, ground_y: float) -> bool:
    return center_y >= ground_y - JET_GROUND_CLEARANCE


@functools.lru_cache(maxsize=64)   # drawn every frame: build each look once, then reuse it (callers only scale/rotate copies)
def create_jet_sprite(tail_flag: bool = False, aura_color=None, alpha: int = 255) -> pygame.Surface:
    """The player's stealth fighter (F-35-M style, own design, no real markings).
    Top-down view, nose pointing right. tail_flag = shield/glow outline; aura_color
    tints the afterburner and outline (the current weapon tier's colour)."""
    surf = pygame.Surface((72, 60), pygame.SRCALPHA)

    glow = aura_color if aura_color else (255, 140, 0)
    body = (95, 103, 118)
    dark = (55, 60, 72)
    edge = (140, 150, 165)

    fuselage = [(71, 30), (58, 25), (44, 22), (22, 22), (14, 25), (14, 35), (22, 38), (44, 38), (58, 35)]
    wing_top = [(46, 23), (27, 4), (19, 6), (24, 23)]
    wing_bot = [(46, 37), (27, 56), (19, 54), (24, 37)]
    tail_top = [(22, 24), (12, 13), (8, 15), (14, 26)]
    tail_bot = [(22, 36), (12, 47), (8, 45), (14, 34)]

    # afterburner flame
    pygame.draw.polygon(surf, (*glow, alpha), [(12, 25), (0, 30), (12, 35)])
    pygame.draw.polygon(surf, (255, 240, 180, alpha), [(12, 28), (5, 30), (12, 32)])

    for poly in (wing_top, wing_bot, tail_top, tail_bot):
        pygame.draw.polygon(surf, (*dark, alpha), poly)
        pygame.draw.polygon(surf, (*edge, alpha), poly, width=1)
    pygame.draw.polygon(surf, (*body, alpha), fuselage)
    pygame.draw.polygon(surf, (*edge, alpha), fuselage, width=1)

    # twin canted vertical fins (seen from above as thin slivers)
    pygame.draw.polygon(surf, (*edge, alpha), [(27, 25), (17, 19), (16, 21), (25, 27)])
    pygame.draw.polygon(surf, (*edge, alpha), [(27, 35), (17, 41), (16, 39), (25, 33)])

    pygame.draw.rect(surf, (*dark, alpha), (11, 27, 5, 6))                 # engine nozzle

    # gold-tint bubble canopy with the pilot's helmet inside
    pygame.draw.ellipse(surf, (200, 160, 50, alpha), (44, 23, 20, 14))
    pygame.draw.ellipse(surf, (120, 95, 30, alpha), (44, 23, 20, 14), width=1)
    pygame.draw.circle(surf, (230, 230, 235, alpha), (53, 30), 4)          # pilot helmet
    pygame.draw.ellipse(surf, (40, 45, 60, alpha), (54, 28, 4, 4))          # visor
    pygame.draw.ellipse(surf, (255, 235, 150, alpha), (57, 25, 5, 2))       # canopy glint

    if tail_flag:
        pygame.draw.polygon(surf, (*glow, alpha), fuselage, width=2)
        pygame.draw.polygon(surf, (*glow, alpha), wing_top, width=2)
        pygame.draw.polygon(surf, (*glow, alpha), wing_bot, width=2)

    return surf


# ==============================================================================
# MISSILE RANGE TIERS (lower ranges -> higher ranges as levels rise)
# ==============================================================================
MISSILE_TIERS = {
    1: {"name": "SHORT-RANGE MISSILE", "levels": "1-20", "speed": 3.2, "turn": 0.035, "contact_dmg": 15,
        "trail": (255, 170, 80)},
    2: {"name": "MEDIUM-RANGE MISSILE", "levels": "21-40", "speed": 4.0, "turn": 0.045, "contact_dmg": 20,
        "trail": (255, 210, 90)},
    3: {"name": "LONG-RANGE CRUISE MISSILE", "levels": "41-60", "speed": 4.6, "turn": 0.05, "contact_dmg": 25,
        "trail": (200, 200, 210)},
    4: {"name": "BALLISTIC MISSILE", "levels": "61-80", "speed": 5.0, "turn": 0.04, "contact_dmg": 32,
        "trail": (255, 120, 60)},
    5: {"name": "HYPERSONIC GLIDE VEHICLE", "levels": "81+", "speed": 7.2, "turn": 0.065, "contact_dmg": 40,
        "trail": (120, 200, 255)},
}


def missile_tier_for_level(level: int) -> int:
    return min(5, 1 + (max(1, level) - 1) // 20)


def level_step(level: int) -> int:
    """Difficulty rises in steps of 5 levels: 0 for levels 1-5, 1 for 6-10, ... 19 for 96-100."""
    return min(20, (max(1, level) - 1) // 5)


def level_power(level: int) -> float:
    """Damage multiplier for BOTH sides: +0.1 every 5 levels, x2 at level 51, x3 from level 101."""
    return 1.0 + level_step(level) * 0.1


def missile_pace(level: int) -> float:
    """Missile and enemy-shot speed: slow at level 1 (x0.55), +0.045 every 5 levels (x1.45 at 96+)."""
    return 0.55 + level_step(level) * 0.045


def jet_pace(level: int) -> float:
    """Jet speed in the 1P game: x0.75 at level 1, +0.025 every 5 levels (x1.25 at 96+)."""
    return 0.75 + level_step(level) * 0.025


# AI TACTICS: extra options the missile AI uses to apply its power, unlocked as the level rises
AI_TACTICS = [
    (20, "FLANK"),    # a wave spreads out and attacks from different sides
    (30, "RELOAD"),   # surviving ground launchers send extra missiles during the wave
    (55, "ECM"),      # short jamming pulse: blocks jet bullets, lasers do half damage
]


def active_tactics(level: int):
    return [name for lvl, name in AI_TACTICS if level >= lvl]


MISSILE_BODY_W, MISSILE_H = 36, 40   # missile body: half the original 72px length (user request 2026-10-02)
# user, 2026-10-03: a missile tracks the jet for 20 s, then falls and blows up on the ground (its launcher
# sends the next one), and it can turn at most 30 degrees per second while flying
MISSILE_FLIGHT_FRAMES = 20 * 60
MISSILE_TURN_DEG_PER_S = 30
MISSILE_TURN_PER_FRAME = math.radians(MISSILE_TURN_DEG_PER_S) / 60
LAUNCH_MIN_ELEV = math.radians(15)   # a launch rail fires at least 15 degrees above the horizon
MISSILE_GRAVITY = 0.12               # px/frame^2 pulling a spent missile down
MISSILE_OFFSCREEN = 60               # a missile this far past a screen edge has left the fight
FLAME_LEN_FACTOR = 2.0               # fire tail = twice the missile body's length


def create_missile_body(is_boss: bool = False, flash_white: bool = False, alpha: int = 255, tier: int = 1) -> pygame.Surface:
    """The missile without its exhaust, squeezed to half length (36x40). The long fire tail
    is drawn live by draw_missile_flame so it flickers and follows the heading."""
    full = create_missile_sprite(is_boss=is_boss, flash_white=flash_white, alpha=alpha, tier=tier, with_flame=False)
    return pygame.transform.smoothscale(full.subsurface((12, 0, 72, 40)).copy(), (MISSILE_BODY_W, MISSILE_H))


def draw_missile_flame(surface, cx, cy, heading, body_len, thick, tier, tick):
    """Fire tail behind a missile centred at (cx, cy), FLAME_LEN_FACTOR x its body length."""
    dx, dy = math.cos(heading), math.sin(heading)
    px, py = -dy, dx                                         # perpendicular
    base_x, base_y = cx - dx * body_len / 2, cy - dy * body_len / 2
    flicker = 0.85 + 0.15 * math.sin(tick * 0.6) + random.uniform(-0.06, 0.06)
    length = body_len * FLAME_LEN_FACTOR * flicker
    outer = (120, 200, 255) if tier == 5 else (255, 120, 30)
    mid = (180, 230, 255) if tier == 5 else (255, 190, 60)
    core = (240, 250, 255)
    for col, w_frac, l_frac in ((outer, 0.36, 1.0), (mid, 0.24, 0.72), (core, 0.12, 0.42)):
        w = thick * w_frac
        tip = (base_x - dx * length * l_frac, base_y - dy * length * l_frac)
        pygame.draw.polygon(surface, col, [(base_x + px * w, base_y + py * w), tip, (base_x - px * w, base_y - py * w)])


def create_missile_sprite(is_boss: bool = False, flash_white: bool = False, alpha: int = 255, tier: int = 1,
                        with_flame: bool = True) -> pygame.Surface:
    """A missile, side/top view with the nose pointing right (so rotate(-angle)
    points it along its flight direction). Each range tier has its own shape."""
    surf = pygame.Surface((84, 40), pygame.SRCALPHA)

    def c(col):
        return (255, 255, 255, alpha) if flash_white else (*col, alpha)

    accent = (255, 40, 80) if is_boss else None
    flame_outer = (120, 200, 255) if tier == 5 else (255, 150, 40)
    flame_core = (230, 245, 255) if tier == 5 else (255, 235, 150)

    # short rocket exhaust (only on the full-length sprite; the game uses the long live flame)
    if with_flame:
        pygame.draw.polygon(surf, c(flame_outer), [(13, 15), (0, 20), (13, 25)])
        pygame.draw.polygon(surf, c(flame_core), [(13, 18), (5, 20), (13, 22)])

    if tier == 1:      # slim short-range missile
        pygame.draw.polygon(surf, c((200, 40, 50)), [(12, 16), (21, 16), (12, 9)])
        pygame.draw.polygon(surf, c((200, 40, 50)), [(12, 24), (21, 24), (12, 31)])
        pygame.draw.rect(surf, c((235, 235, 240)), (12, 16, 56, 8))
        pygame.draw.rect(surf, c((200, 40, 50)), (52, 16, 3, 8))
        pygame.draw.polygon(surf, c((200, 40, 50)), [(68, 16), (80, 20), (68, 24)])
    elif tier == 2:    # medium range: canards + yellow bands
        pygame.draw.polygon(surf, c((90, 95, 105)), [(12, 15), (25, 15), (10, 5)])
        pygame.draw.polygon(surf, c((90, 95, 105)), [(12, 25), (25, 25), (10, 35)])
        pygame.draw.rect(surf, c((185, 190, 200)), (12, 15, 58, 10))
        pygame.draw.polygon(surf, c((90, 95, 105)), [(54, 15), (61, 15), (56, 9)])
        pygame.draw.polygon(surf, c((90, 95, 105)), [(54, 25), (61, 25), (56, 31)])
        for bx in (30, 46):
            pygame.draw.rect(surf, c((240, 200, 40)), (bx, 15, 3, 10))
        pygame.draw.polygon(surf, c((70, 75, 85)), [(70, 15), (82, 20), (70, 25)])
    elif tier == 3:    # long-range cruise missile: pop-out wings, intake
        pygame.draw.polygon(surf, c((85, 95, 60)), [(38, 15), (50, 15), (31, 1)])
        pygame.draw.polygon(surf, c((85, 95, 60)), [(38, 25), (50, 25), (31, 39)])
        pygame.draw.polygon(surf, c((85, 95, 60)), [(12, 15), (20, 15), (11, 8)])
        pygame.draw.polygon(surf, c((85, 95, 60)), [(12, 25), (20, 25), (11, 32)])
        pygame.draw.rect(surf, c((115, 125, 80)), (12, 15, 60, 10), border_radius=4)
        pygame.draw.circle(surf, c((115, 125, 80)), (72, 20), 5)
        pygame.draw.rect(surf, c((40, 45, 35)), (28, 24, 12, 3))
    elif tier == 4:    # thick ballistic missile with checker pattern
        for sign in (-1, 1):
            pygame.draw.polygon(surf, c((30, 30, 35)), [(10, 20 + sign * 7), (24, 20 + sign * 7), (8, 20 + sign * 17)])
        pygame.draw.rect(surf, c((240, 240, 240)), (10, 13, 58, 14))
        for i, bx in enumerate(range(18, 64, 10)):
            pygame.draw.rect(surf, c((30, 30, 35)), (bx, 13 if i % 2 == 0 else 20, 5, 7))
        pygame.draw.polygon(surf, c((30, 30, 35)), [(68, 13), (83, 20), (68, 27)])
    else:              # tier 5: hypersonic glide vehicle, wedge with plasma edges
        wedge = [(83, 20), (15, 4), (9, 11), (9, 29), (15, 36)]
        pygame.draw.polygon(surf, c((40, 40, 55)), wedge)
        pygame.draw.line(surf, c((255, 120, 60)), (83, 20), (15, 4), 2)
        pygame.draw.line(surf, c((255, 120, 60)), (83, 20), (15, 36), 2)
        pygame.draw.line(surf, c((90, 95, 120)), (20, 20), (76, 20), 1)
        pygame.draw.circle(surf, c((255, 210, 140)), (79, 20), 4)

    if accent and not flash_white:
        pygame.draw.circle(surf, (*accent, alpha), (44, 20), 4)
        pygame.draw.line(surf, (*accent, alpha), (16, 20), (66, 20), 2)

    return surf


# ==============================================================================
# SINGLE-PLAYER AI ENEMY CLASS
# ==============================================================================
class MissileEnemy:
    """A homing missile. It turns toward its target at a limited rate (its range
    tier sets speed and turn rate) and blows itself up when it gets close to the jet
    (proximity fuse, handled in the game loop).
    Every missile starts on a ground launcher and stays in sight until it is shot down or
    explodes. Missiles never fire: they hit or blow up next to the jet."""

    def __init__(self, level: int, is_boss: bool = False, mutator: str = "NONE",
                 launch_x: float = None, ground_y: int = 600, launch_delay: int = 0, system: dict = None,
                 difficulty: str = "NORMAL"):
        self.is_boss = is_boss
        # launcher system it was fired from (nation arsenal, level 5+): own trail colour and speed
        self.system = system
        self.nation = system.get("nation") if system else None
        self.trail_color = tuple(system["trail"]) if system else None
        self.barrel_off = 0.0     # sideways place on a multi-barrel launcher while waiting
        self.silo = None          # the underground silo it came from, if any
        self.ground_y = ground_y
        self.launch_delay = launch_delay   # frames sitting on the ground launcher before lift-off
        self.tier = missile_tier_for_level(level)
        stats = MISSILE_TIERS[self.tier]
        self.scale = 2.4 if is_boss else 1.5
        self.width = int(MISSILE_BODY_W * self.scale)
        self.height = int(MISSILE_H * self.scale)
        self.mutator = mutator

        self.normal_sprite = pygame.transform.scale(
            create_missile_body(is_boss=is_boss, flash_white=False, tier=self.tier), (self.width, self.height)
        )
        self.flash_sprite = pygame.transform.scale(
            create_missile_body(is_boss=is_boss, flash_white=True, tier=self.tier), (self.width, self.height)
        )

        if launch_x is not None:
            # surface-to-air: sits on a ground launcher pointing up, then climbs out
            self.x = launch_x - self.width // 2
            self.y = ground_y - 30 - self.height // 2
            self.heading = -math.pi / 2
        else:
            # air-launched from the right-hand side, heading left toward the jet
            self.x = random.uniform(540, 700) - self.width // 2
            self.y = random.uniform(100, 480) - self.height // 2
            self.heading = math.pi + random.uniform(-0.4, 0.4)
        self.launch_x = launch_x
        self.site = None   # index of the ground launcher it rides until lift-off (set by the spawner)

        base_hp = 260 if is_boss else 70
        hp_growth = 22 if is_boss else 8
        self.max_hp = base_hp + (level * hp_growth)
        self.hp = self.max_hp

        speed_mult = 1.4 if mutator == "HYPER SPEED STORM" else 1.0
        boss_mult = 0.85 if is_boss else 1.0   # bosses are bigger and a little slower
        self.pace = missile_pace(level)        # slow at level 1, one step faster every 5 levels
        self.speed_stat = stats["speed"] * self.pace * speed_mult * boss_mult * (system.get("speed", 1.0) if system else 1.0)
        self.turn_rate = MISSILE_TURN_PER_FRAME   # 30 degrees per second, every class (user, 2026-10-03)
        df = difficulty_factors(difficulty)       # EASY: slower, wider-turning missiles (never above 30 deg/s)
        self.speed_stat *= df["missile_speed"]
        self.turn_rate *= df["missile_turn"]
        self.fuse_factor = df["fuse"]             # EASY: has to get closer before its fuse fires
        self.expired = False                      # 20 s of flight used up: falling to the ground
        self.vx = self.vy = 0.0                   # velocity while falling as a spent projectile
        self.power = level_power(level)        # missile damage grows with level, same curve as the jet
        self.contact_dmg = int(stats["contact_dmg"] * (1.6 if is_boss else 1.0) * self.power)

        # AI tactics unlocked by level (see AI_TACTICS)
        self.tactics = active_tactics(level)
        self.flank_angle = 0.0                 # set by the spawner so a wave attacks from different sides
        self.ecm_timer = 0
        self.ecm_cd = random.randint(180, 360)
        self.contact_cd = 0
        self.trail = []
        self.age = 0
        self.angle = math.degrees(self.heading)
        self.is_burrowed = False   # always False for missiles now (kept for the shared checks)

        self.flash_timer = 0

    def update(self, holes, target_x, target_y, screen_w, screen_h, threats=()):
        """threats = the jet's bullets in flight (not used now: missiles fly as projectiles and don't dodge)."""
        if self.flash_timer > 0:
            self.flash_timer -= 1
        if self.contact_cd > 0:
            self.contact_cd -= 1
        if self.ecm_timer > 0:
            self.ecm_timer -= 1
        if self.launch_delay > 0:          # still on the launcher: can be shot, doesn't move
            self.launch_delay -= 1
            return None
        self.age += 1

        # A missile flies like a projectile, not an aerobatic jet (user, 2026-10-03): it leaves the rail
        # angled at the target, flies at a steady speed in smooth arcs (30 deg/s turn), never bounces off
        # the edges (the game loop retires it when it leaves the sky or hits the ground) and, when its
        # 20 s are up, falls as a projectile, keeping its forward speed, so it lands far from the launcher.
        if self.age == 1 and self.launch_x is not None:
            a = math.atan2(target_y - (self.y + self.height / 2), target_x - (self.x + self.width / 2))
            if a >= 0:                                   # target at or below the rail: launch low over the ground
                a = -LAUNCH_MIN_ELEV if math.cos(a) >= 0 else -math.pi + LAUNCH_MIN_ELEV
            self.heading = max(-math.pi + LAUNCH_MIN_ELEV, min(-LAUNCH_MIN_ELEV, a))
        if self.age < 35 and self.launch_x is not None:
            # boost phase: straight along the launch line
            self.x += math.cos(self.heading) * self.speed_stat * 1.3
            self.y += math.sin(self.heading) * self.speed_stat * 1.3
            self.angle = math.degrees(self.heading)
            self.trail.append((self.x + self.width // 2, self.y + self.height // 2))
            if len(self.trail) > 14:
                self.trail.pop(0)
            return None

        if self.age >= MISSILE_FLIGHT_FRAMES and not self.expired:
            self.expired = True
            self.vx, self.vy = math.cos(self.heading) * self.speed_stat, math.sin(self.heading) * self.speed_stat
        if self.expired:
            # engine off: a falling projectile -- forward speed kept, gravity bends the path down
            self.vy = min(self.vy + MISSILE_GRAVITY, 10.0)   # air drag: terminal falling speed
            self.x += self.vx
            self.y += self.vy
            self.heading = math.atan2(self.vy, self.vx)
            self.angle = math.degrees(self.heading)
            return None

        # Every missile comes from a ground launcher and stays in sight until it is shot down or
        # explodes (user, 2026-10-02): the old radar-cloak vanish/reappear at the purple holes is gone.
        center_x = self.x + self.width // 2
        center_y = self.y + self.height // 2
        steer_x, steer_y = target_x, target_y

        if "FLANK" in self.tactics:
            # FLANK: approach a point off to this missile's side of the jet, then turn in for the hit
            if math.hypot(target_x - center_x, target_y - center_y) > 170:
                steer_x = target_x + math.cos(self.flank_angle) * 150
                steer_y = target_y + math.sin(self.flank_angle) * 150

        desired = math.atan2(steer_y - center_y, steer_x - center_x)
        diff = (desired - self.heading + math.pi) % (2 * math.pi) - math.pi
        self.heading += max(-self.turn_rate, min(self.turn_rate, diff))

        # ECM: brief jamming pulse that blocks the jet's shots
        if self.ecm_cd > 0:
            self.ecm_cd -= 1
        elif "ECM" in self.tactics:
            self.ecm_timer, self.ecm_cd = 60, 360

        self.x += math.cos(self.heading) * self.speed_stat      # steady speed: no sprints, no jinks
        self.y += math.sin(self.heading) * self.speed_stat
        self.angle = math.degrees(self.heading)

        # flew out of the battle area (past a side or the top): motor cut, it falls back as a projectile
        if not (0 <= self.x + self.width / 2 <= screen_w) or self.y + self.height / 2 < 0:
            self.expired = True
            self.vx, self.vy = math.cos(self.heading) * self.speed_stat, math.sin(self.heading) * self.speed_stat

        self.trail.append((self.x + self.width // 2, self.y + self.height // 2))
        if len(self.trail) > 14:
            self.trail.pop(0)

        # missiles carry no guns: their only attack is to reach the jet (proximity fuse in the game loop)
        return None

    @property
    def rect(self):
        # the sprite rotates, so use a centred square a bit smaller than the (short) missile body
        side = int(self.width * 0.8)
        return pygame.Rect(self.x + self.width // 2 - side // 2, self.y + self.height // 2 - side // 2, side, side)

    def draw(self, surface):
        if self.is_burrowed:
            return
        if self.trail_color and len(self.trail) > 1:     # nation-coloured smoke trail: who fired it, at a glance
            n = len(self.trail)
            for k in range(1, n):
                w = max(1, int(1 + 5 * k / n))
                pygame.draw.line(surface, self.trail_color, self.trail[k - 1], self.trail[k], w)
        if self.launch_delay == 0 and not self.expired:   # engine lit: fire tail twice the missile's length
            draw_missile_flame(surface, self.x + self.width // 2, self.y + self.height // 2, self.heading,
                               self.width, self.height * 0.3, self.tier, self.age)
        base_surf = self.flash_sprite if self.flash_timer > 0 else self.normal_sprite
        rotated = pygame.transform.rotate(base_surf, -self.angle)
        rot_rect = rotated.get_rect(center=(self.x + self.width // 2, self.y + self.height // 2))
        surface.blit(rotated, rot_rect.topleft)
        if self.ecm_timer > 0:   # ECM jamming pulse: jet bullets bounce off this ring
            pygame.draw.circle(surface, (0, 255, 220), (int(self.x + self.width // 2), int(self.y + self.height // 2)),
                               int(self.width * 0.75), 2)


# ==============================================================================
# WEAPON TIERS & CONTINUOUS LASER RAY SYSTEM
# ==============================================================================
WEAPON_TIERS = {
    1: {"type": "bullet", "speed": 14, "color_outer": (255, 140, 0), "color_core": (255, 230, 80), "dmg": 20, "name": "AMBER SPARK"},
    2: {"type": "bullet", "speed": 19, "color_outer": (0, 220, 255), "color_core": (200, 255, 255), "dmg": 30, "name": "CYAN PULSE"},
    3: {"type": "laser",  "beam_w": 8,  "color_outer": (220, 50, 255), "color_core": (255, 200, 255), "dmg": 4,  "name": "MAGENTA LASER RAY"},
    4: {"type": "laser",  "beam_w": 12, "color_outer": (40, 255, 120), "color_core": (210, 255, 220), "dmg": 6,  "name": "EMERALD ION BEAM"},
    5: {"type": "laser",  "beam_w": 18, "color_outer": (255, 50, 120), "color_core": (255, 255, 255), "dmg": 9,  "name": "HYPER NOVA DEATH-RAY"},
}


# ==============================================================================
# NATION ARSENAL (user spec, 2026-10-03): every 5 levels one more nation unlocks. Its 2 ground
# launchers join the enemy launcher pool (each with its own trail colour) and its 2 jet munitions
# join the jet's ordnance loadout. Plain lists/dicts, so the table round-trips through JSON.
# Launcher "type": SAM fires one missile, MBML (multi-barrel) fires a salvo; "speed" scales the
# missile's flight speed. Munition "role" picks its physics from MUNITION_ROLES below.
# ==============================================================================
ARSENAL = {"nations": [
    {"code": "RUS", "name": "RUSSIA", "unlock_level": 5, "color": [230, 60, 60],
     "launchers": [{"id": "pantsir_s1", "name": "PANTSIR-S1-M", "type": "SAM", "salvo": 1, "speed": 1.10, "trail": [255, 80, 80]},
                   {"id": "tos_1a", "name": "TOS-1A-M", "type": "MBML", "salvo": 3, "speed": 0.90, "trail": [255, 140, 70]}],
     "munitions": [{"id": "r77", "name": "R-77-M", "role": "AA", "trail": [255, 110, 110]},
                   {"id": "kh29", "name": "KH-29-M", "role": "AG", "hits": 2, "trail": [200, 40, 40]}]},
    {"code": "IRN", "name": "IRAN", "unlock_level": 10, "color": [60, 200, 90],
     "launchers": [{"id": "bavar_373", "name": "BAVAR-373-M", "type": "SAM", "salvo": 1, "speed": 1.05, "trail": [80, 230, 110]},
                   {"id": "fajr_5", "name": "FAJR-5-M", "type": "MBML", "salvo": 3, "speed": 0.92, "trail": [150, 240, 90]}],
     "munitions": [{"id": "fakour_90", "name": "FAKOUR-90-M", "role": "AA", "trail": [110, 255, 150]},
                   {"id": "ghaem", "name": "GHAEM-M", "role": "PGM", "trail": [40, 170, 70]}]},
    {"code": "CHN", "name": "CHINA", "unlock_level": 15, "color": [255, 210, 40],
     "launchers": [{"id": "hq_9", "name": "HQ-9-M", "type": "SAM", "salvo": 1, "speed": 1.12, "trail": [255, 225, 70]},
                   {"id": "phl_03", "name": "PHL-03-M", "type": "MBML", "salvo": 3, "speed": 0.95, "trail": [255, 180, 30]}],
     "munitions": [{"id": "pl15", "name": "PL-15-M", "role": "AA", "trail": [255, 240, 130]},
                   {"id": "kd88", "name": "KD-88-M", "role": "AG", "hits": 2, "trail": [220, 170, 0]}]},
    {"code": "UKR", "name": "UKRAINE", "unlock_level": 20, "color": [60, 140, 255],
     "launchers": [{"id": "neptune", "name": "NEPTUNE-M", "type": "SAM", "salvo": 1, "speed": 0.95, "trail": [70, 150, 255]},
                   {"id": "vilkha", "name": "VILKHA-M", "type": "MBML", "salvo": 2, "speed": 1.00, "trail": [120, 185, 255]}],
     "munitions": [{"id": "r27et", "name": "R-27ET-M", "role": "IR", "trail": [90, 170, 255]},
                   {"id": "ukr_guided_bomb", "name": "GUIDED BOMB-M", "role": "PGM", "trail": [40, 110, 230]}]},
    {"code": "PRK", "name": "NORTH KOREA", "unlock_level": 25, "color": [180, 60, 200],
     "launchers": [{"id": "kn_09", "name": "KN-09-M", "type": "MBML", "salvo": 3, "speed": 0.95, "trail": [205, 95, 235]},
                   {"id": "kn_25", "name": "KN-25-M", "type": "MBML", "salvo": 2, "speed": 1.08, "trail": [150, 40, 180]}],
     "munitions": [{"id": "prk_glide_bomb", "name": "GLIDE BOMB-M", "role": "GLIDE", "trail": [220, 120, 255]},
                   {"id": "prk_freefall_bomb", "name": "FREE-FALL BOMB-M", "role": "BOMB", "trail": [120, 60, 150]}]},
    {"code": "USA", "name": "UNITED STATES", "unlock_level": 30, "color": [235, 240, 255],
     "launchers": [{"id": "patriot_pac3", "name": "PATRIOT PAC-3-M", "type": "SAM", "salvo": 1, "speed": 1.15, "trail": [255, 255, 255]},
                   {"id": "himars", "name": "M142 HIMARS-M", "type": "MBML", "salvo": 2, "speed": 1.00, "trail": [200, 220, 255]}],
     "munitions": [{"id": "aim120", "name": "AIM-120 AMRAAM-M", "role": "AA", "trail": [230, 240, 255]},
                   {"id": "jdam", "name": "JDAM-M", "role": "PGM", "trail": [170, 190, 220]}]},
    {"code": "GBR", "name": "UNITED KINGDOM", "unlock_level": 35, "color": [0, 220, 230],
     "launchers": [{"id": "sky_sabre", "name": "SKY SABRE-M", "type": "SAM", "salvo": 1, "speed": 1.10, "trail": [60, 240, 240]},
                   {"id": "stormer_hvm", "name": "STORMER HVM-M", "type": "MBML", "salvo": 2, "speed": 1.12, "trail": [0, 190, 200]}],
     "munitions": [{"id": "meteor", "name": "METEOR-M", "role": "AA", "vmax": 14.0, "trail": [140, 255, 255]},
                   {"id": "brimstone", "name": "BRIMSTONE-M", "role": "AG", "trail": [0, 160, 170]}]},
    {"code": "DEU", "name": "GERMANY", "unlock_level": 40, "color": [255, 120, 0],
     "launchers": [{"id": "iris_t_slm", "name": "IRIS-T SLM-M", "type": "SAM", "salvo": 1, "speed": 1.10, "trail": [255, 150, 40]},
                   {"id": "mars_2", "name": "MARS II-M", "type": "MBML", "salvo": 3, "speed": 0.95, "trail": [230, 100, 0]}],
     "munitions": [{"id": "iris_t", "name": "IRIS-T-M", "role": "IR", "trail": [255, 170, 80]},
                   {"id": "taurus_kepd", "name": "TAURUS KEPD 350-M", "role": "AG", "hits": 2, "trail": [200, 90, 0]}]},
]}

# Level 10 sensor unlock: heat-seeking missiles for the jet + the FLIR pod (key X)
IR_UNLOCK_LEVEL = 10
GENERIC_IR_MISSILE = {"id": "ir_seeker", "name": "IR HEAT-SEEKER-M", "role": "IR", "trail": [255, 90, 160], "nation": ""}


def munition_label(m: dict) -> str:
    """'RUS R-77-M', or just the name for the generic IR seeker (no nation)."""
    return f"{m['nation']} {m['name']}" if m.get("nation") else m["name"]

# Jet ordnance physics per role (px and frames, 60 frames = 1 s). Rockets: thrust / mass while the motor
# burns (mass falls as fuel burns), quadratic drag always, speed capped at vmax, turn rate capped (G limit).
# Bombs: released at the jet's velocity, gravity + drag; PGM/GLIDE steer gently toward their target.
MUNITION_ROLES = {
    "AA":    {"kind": "rocket", "guidance": "radar", "target": "air", "thrust": 0.55, "dry_mass": 1.0, "fuel_mass": 0.5,
              "burn": 60, "drag": 0.0022, "vmax": 13.0, "turn_deg_s": 200, "nav": 4.0, "hits": 1, "ammo": 4, "life": 240},
    "IR":    {"kind": "rocket", "guidance": "ir", "target": "air", "thrust": 0.60, "dry_mass": 1.0, "fuel_mass": 0.4,
              "burn": 45, "drag": 0.0026, "vmax": 12.0, "turn_deg_s": 240, "nav": 4.0, "hits": 1, "ammo": 4, "life": 200,
              "seeker_fov_deg": 45, "seeker_range": 520},
    "AG":    {"kind": "rocket", "guidance": "radar", "target": "ground", "thrust": 0.45, "dry_mass": 1.2, "fuel_mass": 0.6,
              "burn": 80, "drag": 0.0025, "vmax": 10.0, "turn_deg_s": 120, "nav": 3.5, "hits": 1, "ammo": 2, "life": 300,
              "blast": 30},
    "PGM":   {"kind": "bomb", "guidance": "bomb", "target": "ground", "gravity": 0.14, "steer_deg_s": 90, "hits": 2,
              "ammo": 2, "blast": 46, "life": 600},
    "GLIDE": {"kind": "bomb", "guidance": "bomb", "target": "ground", "gravity": 0.06, "steer_deg_s": 60, "hits": 2,
              "ammo": 2, "blast": 40, "life": 900},
    "BOMB":  {"kind": "bomb", "guidance": "none", "target": "ground", "gravity": 0.16, "hits": 2, "ammo": 3,
              "blast": 55, "life": 600},
}
BOMB_DRAG = 0.004          # bombs lose 0.4% of their speed per frame to the air
ORDNANCE_FUSE = 20         # an air-to-air missile this close to a flying missile destroys it
ORDNANCE_COOLDOWN = 36     # frames between ordnance launches (shortened by the vs-AI buff)

# Human vs AI (single player only): +15% damage and reload rate. The 2P duel stays symmetric (0%).
HUMAN_VS_AI_BUFF = 1.15


def human_buff(mode: str, missile_mode: str = "MANUAL") -> float:
    """+15% for the player whenever the opponent is the computer: the campaign, and the duel with the
    missile on AUTO (always the case on phones). A human-vs-human duel stays even."""
    return HUMAN_VS_AI_BUFF if mode == "CAMPAIGN" or (mode == "DUEL" and missile_mode == "AUTO") else 1.0


def unlocked_nations(level: int):
    return [n for n in ARSENAL["nations"] if level >= n["unlock_level"]]


def unlocked_launchers(level: int):
    """Enemy launcher systems available at this level, each tagged with its nation code."""
    return [dict(ln, nation=n["code"]) for n in unlocked_nations(level) for ln in n["launchers"]]


def munition_stats(m: dict) -> dict:
    """A munition's role defaults with its own overrides on top."""
    return {**MUNITION_ROLES[m["role"]], **m}


def jet_loadout(level: int):
    """The jet's ordnance at this level: the generic IR seeker from level 10, plus every unlocked
    nation's 2 munitions, in unlock order."""
    out = []
    for n in unlocked_nations(level):
        out.extend(munition_stats(dict(m, nation=n["code"])) for m in n["munitions"])
        if n["unlock_level"] <= IR_UNLOCK_LEVEL < n["unlock_level"] + 5 and level >= IR_UNLOCK_LEVEL:
            out.append(munition_stats(dict(GENERIC_IR_MISSILE)))
    return out


def salvo_size(launcher: dict, level: int) -> int:
    """Rockets a launcher fires per launch: SAMs 1, multi-barrel launchers up to their salvo,
    2 from level 5 and one more every 25 levels."""
    if not launcher or launcher.get("type") != "MBML":
        return 1
    return max(1, min(launcher["salvo"], 2 + level // 25))


# ==============================================================================
# GUIDANCE & MOTOR PHYSICS (jet ordnance)
# ==============================================================================
def angle_diff(a: float, b: float) -> float:
    """Signed smallest difference a - b in radians."""
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def motor_step(o: dict):
    """One frame of a rocket motor: thrust / current mass while fuel burns (mass falls as the fuel is
    used, so it accelerates harder late in the burn), quadratic air drag always, speed capped at vmax."""
    accel = 0.0
    if o["burn_left"] > 0:
        mass = o["dry_mass"] + o["fuel_mass"] * o["burn_left"] / o["burn"]
        accel = o["thrust"] / mass
        o["burn_left"] -= 1
    o["speed"] = min(o["vmax"], max(0.0, o["speed"] + accel - o["drag"] * o["speed"] ** 2))


def guidance_turn(heading: float, los_prev, los_now: float, nav: float, max_turn: float) -> float:
    """Proportional navigation: turn the velocity N times as fast as the line of sight rotates
    (constant-speed 2D form, d(heading) = N * d(LOS)), which flies a lead-collision course instead of
    chasing the target's tail. While the heading is more than 60 degrees off the line of sight (just
    after launch) it pure-pursues instead. Either way the turn is capped by the airframe's G limit."""
    off = angle_diff(los_now, heading)
    if los_prev is None or abs(off) > math.radians(60):
        cmd = off
    else:
        cmd = nav * angle_diff(los_now, los_prev)
    return heading + max(-max_turn, min(max_turn, cmd))


def ir_pick_target(x: float, y: float, heading: float, sources, fov_deg: float, rng: float):
    """Heat seeker: the nearest hot source [(sx, sy), ...] inside its field of view and range, else None."""
    best, best_d = None, rng
    for sx, sy in sources:
        d = math.hypot(sx - x, sy - y)
        if d <= best_d and abs(angle_diff(math.atan2(sy - y, sx - x), heading)) <= math.radians(fov_deg):
            best, best_d = (sx, sy), d
    return best


# ==============================================================================
# FLIR POD & UNDERGROUND SILO LAUNCHERS (level 10+)
# ==============================================================================
FLIR_HALF_ANGLE = math.radians(35)   # the pod looks straight down, +-35 degrees
FLIR_RANGE = 460                     # active scan (X held on): cold, hidden silos inside this range
FLIR_HOT_FACTOR = 1.5                # a spooling silo is hot: seen 1.5x further
FLIR_PASSIVE_RANGE = 300             # pod off: it still picks up hot (spooling) silos this close
SILO_UNLOCK_LEVEL = 10
SILO_SPOOL_FRAMES = 90               # 1.5 s spooling (hatch opening, motor heating) before ignition


def flir_sees(jx: float, jy: float, sx: float, sy: float, active: bool, hot: bool) -> bool:
    """FLIR cone from the jet pointing down at the terrain: is the thermal signature at (sx, sy) detected?"""
    dx, dy = sx - jx, sy - jy
    if dy <= 0 or abs(math.atan2(dx, dy)) > FLIR_HALF_ANGLE:
        return False
    d = math.hypot(dx, dy)
    if active:
        return d <= FLIR_RANGE * (FLIR_HOT_FACTOR if hot else 1.0)
    return hot and d <= FLIR_PASSIVE_RANGE


def silo_count(level: int) -> int:
    """Underground launchers per wave: 2 at level 10, 4 at 20, 6 at 30, 8 at 40, 10 from 50."""
    return 0 if level < SILO_UNLOCK_LEVEL else 2 * min(5, level // 10)


class SiloLauncher:
    """A fixed underground launcher: HIDDEN -> SPOOLING -> FIRING -> EXPOSED.
    HIDDEN: not drawn, not on the HUD, can't be hit or targeted, until the FLIR pod finds it
    (`revealed`) or it fires. SPOOLING: hatch opening, motor heating: a hot FLIR contact.
    FIRING: the ignition frame (update() returns True and the game launches a missile from it).
    EXPOSED: open pad in plain sight; 2 hits destroy it. While it has shots left an exposed silo
    spools up again for its next launch."""

    def __init__(self, x: float, shots: int, first_delay: int, system=None):
        self.x = x
        self.shots = shots
        self.state = "HIDDEN"
        self.timer = first_delay
        self.revealed = False     # FLIR found it, or it has fired
        self.fired = False        # has launched at least once: hatch open, in plain sight
        self.alive = True
        self.hp = self.max_hp = 2
        self.laser_frames = 0
        self.system = system

    @property
    def hot(self) -> bool:
        return self.alive and self.state in ("SPOOLING", "FIRING")

    @property
    def targetable(self) -> bool:
        return self.alive and (self.revealed or self.state in ("FIRING", "EXPOSED"))

    @property
    def pending(self) -> bool:
        return self.alive and self.shots > 0

    def update(self, hold: bool = False) -> bool:
        """One frame; hold = jet hidden by stealth or the sky is full (the silo waits). True = ignition."""
        if not self.alive:
            return False
        if self.state == "FIRING":
            self.state = "EXPOSED"
            self.timer = random.randint(420, 720)
            return False
        if hold or self.shots <= 0:
            return False
        self.timer -= 1
        if self.timer > 0:
            return False
        if self.state != "SPOOLING":
            self.state, self.timer = "SPOOLING", SILO_SPOOL_FRAMES
            return False
        self.state = "FIRING"
        self.shots -= 1
        self.revealed = self.fired = True
        return True


# ==============================================================================
# DRONES & DRONE LAUNCHERS (user, 2026-10-03)
# Drone level 1..20 follows the game level (then stays at 20); drone launchers 1..10 (one more per level
# up to level 10). Each drone launcher sends out its drones one by one and also carries 1 missile.
# Drones are subsonic: half the jet's top speed. They home on the jet and blow up against it (HP damage,
# the shield E blocks it). The jet's protective AUTO-GUN fires by itself at drones inside its range.
# ==============================================================================
# SAFEGUARD (user, 2026-10-03: "safe guard jet like patriot technology, one key ... for 3 seconds which will
# [destroy] entire fly objects except jet, and same key active after ten seconds"): key B (touch SAFE, controller
# hold 7 + Cross/A). For SAFEGUARD_FRAMES every enemy missile and drone in the air is shot down by the jet's
# interceptors; ready again SAFEGUARD_COOLDOWN frames after it was switched on. The jet's own weapons, its flares
# and missiles still sitting on their launchers are not touched. (Own name: no real system names in the game.)
SAFEGUARD_FRAMES = 180      # 3 s
SAFEGUARD_COOLDOWN = 600    # 10 s from activation
SAFEGUARD_KILL_SCORE = 50   # per missile it brings down (drones score as usual)
LAUNCHER_REVIVE_FRAMES = 120   # a destroyed launcher (truck or drone launcher) is rebuilt 2 s later (user, 2026-10-03)
DRONE_MAX_LEVEL = 20
DRONE_MISSILE_LEVEL = 5      # drone launchers carry their missile only from level 5 (keeps level 1 calm)
DRONE_LAUNCHER_MAX = 10
DRONE_SPEED_FACTOR = 0.5                         # half the jet's top speed
DRONE_TURN_PER_FRAME = math.radians(60) / 60     # 60 degrees per second
DRONE_LIFE = 25 * 60                             # 25 s of fuel, then it glides down and crashes
DRONE_HIT_DMG = 35                               # x level_power, HP lost when one reaches the jet
DRONE_HIT_RADIUS = 26
DRONE_KILL_SCORE = 40
AUTOGUN_RANGE = 220                              # auto-gun opens fire on drones closer than this
AUTOGUN_COOLDOWN = 8                             # frames between auto-gun rounds
AUTOGUN_SPEED = 16                               # auto-gun round speed, px/frame


def drone_level(level: int) -> int:
    return max(1, min(DRONE_MAX_LEVEL, level))


def launcher_count(level: int) -> int:
    """Missile launchers on the ground (user, 2026-10-03): 1 at levels 1-10, 2 at 11-20 ... 10 from level 91."""
    return max(1, min(10, 1 + (max(1, level) - 1) // 10))


def drone_launcher_count(level: int) -> int:
    """Drone launchers, the same steps (user, 2026-10-03: "similar for drone launcher also"): 1 at 1-10 ... 10 at 91+."""
    return max(1, min(DRONE_LAUNCHER_MAX, 1 + (max(1, level) - 1) // 10))


def drones_per_launcher(level: int) -> int:
    """Drones each launcher sends per wave: 1 at drone level 1-5, 2 at 6-10, 3 at 11-15, 4 at 16-20."""
    return 1 + (drone_level(level) - 1) // 5


def drone_speed(jet_top_speed: float) -> float:
    return jet_top_speed * DRONE_SPEED_FACTOR


def create_drone_sprite() -> pygame.Surface:
    """A small delta-wing attack drone, top view, nose pointing right, pusher propeller at the back."""
    s = pygame.Surface((30, 26), pygame.SRCALPHA)
    pygame.draw.polygon(s, (150, 155, 145), [(29, 13), (6, 1), (9, 13), (6, 25)])          # delta wing
    pygame.draw.polygon(s, (95, 100, 92), [(29, 13), (6, 1), (9, 13), (6, 25)], 1)
    pygame.draw.rect(s, (115, 120, 110), (5, 11, 22, 4))                                  # body
    pygame.draw.line(s, (60, 60, 60), (3, 6), (3, 20), 2)                                 # propeller
    pygame.draw.circle(s, (255, 70, 60), (25, 13), 2)                                     # warhead light
    return s


class Drone:
    """A subsonic homing drone: climbs off its launcher, then flies at a steady speed toward its target,
    turning at most 60 deg/s. After DRONE_LIFE frames its engine stops and it glides down to the ground."""

    def __init__(self, x: float, y: float, speed: float, level: int, dmg_factor: float = 1.0):
        self.x, self.y = x, y
        self.heading = -math.pi / 2
        self.speed = speed
        self.age = 0
        self.expired = False
        self.vx = self.vy = 0.0
        self.level = drone_level(level)
        self.dmg = int(DRONE_HIT_DMG * level_power(level) * dmg_factor)

    @property
    def velocity(self):
        if self.expired:
            return self.vx, self.vy
        return math.cos(self.heading) * self.speed, math.sin(self.heading) * self.speed

    def update(self, tx: float, ty: float):
        self.age += 1
        if not self.expired and self.age >= DRONE_LIFE:
            self.expired = True
            self.vx, self.vy = self.velocity
        if self.expired:
            self.vy = min(self.vy + MISSILE_GRAVITY * 0.5, 6.0)
            self.x += self.vx
            self.y += self.vy
            self.heading = math.atan2(self.vy, self.vx)
            return
        if self.age > 30:   # after the climb-out: home on the target
            diff = angle_diff(math.atan2(ty - self.y, tx - self.x), self.heading)
            self.heading += max(-DRONE_TURN_PER_FRAME, min(DRONE_TURN_PER_FRAME, diff))
        self.x += math.cos(self.heading) * self.speed
        self.y += math.sin(self.heading) * self.speed


def autogun_pick(gx: float, gy: float, drones, rng: float = AUTOGUN_RANGE, shot_speed: float = AUTOGUN_SPEED):
    """Auto-gun fire control: the nearest drone within range -> aim angle with lead (where the drone will be
    when the round gets there), else None. Spent (falling) drones are ignored."""
    live = [d for d in drones if not d.expired and math.hypot(d.x - gx, d.y - gy) <= rng]
    if not live:
        return None
    d = min(live, key=lambda d: math.hypot(d.x - gx, d.y - gy))
    vx, vy = d.velocity
    t = math.hypot(d.x - gx, d.y - gy) / shot_speed
    t = math.hypot(d.x + vx * t - gx, d.y + vy * t - gy) / shot_speed     # one refinement step
    return math.atan2(d.y + vy * t - gy, d.x + vx * t - gx)


class DroneLauncher:
    """Fixed ground launcher for drones, with 1 missile on board too. Launches its drones one by one
    (holds while the jet is in stealth); 2 hits destroy it."""

    def __init__(self, x: float, drones: int, first_delay: int, missile_delay: int, has_missile: bool = True,
                 gap: float = 1.0):
        self.x = x
        self.drones_left = drones
        self.timer = first_delay
        self.gap = gap                 # EASY: longer wait between drones
        self.shots = 1 if has_missile else 0   # its missile (from level 5) ("shots" so a missile that falls gives it back, like a silo)
        self.missile_timer = missile_delay
        self.alive = True
        self.hp = self.max_hp = 2
        self.laser_frames = 0
        self.targetable = True
        # it drives back and forth along the ground inside its own stretch (user, 2026-10-03: "launcher can move")
        self.lo, self.hi = x - 30, x + 30
        self.vx = random.choice((-1, 1)) * random.uniform(0.4, 0.9)
        self.revive = 0                # frames until a destroyed one is rebuilt (it keeps the drones it had left)

    def destroy(self):
        self.alive = False
        self.revive = LAUNCHER_REVIVE_FRAMES

    def tick_revive(self) -> bool:
        """One frame of rebuilding; True on the frame it is back (full armour, same drones / missile left)."""
        if self.alive or self.revive <= 0:
            return False
        self.revive -= 1
        if self.revive == 0:
            self.alive = True
            self.hp = self.max_hp
            self.laser_frames = 0
            return True
        return False

    def move(self):
        if not self.alive:
            return
        self.x += self.vx
        if self.x < self.lo or self.x > self.hi:
            self.vx = -self.vx
            self.x = max(self.lo, min(self.hi, self.x))

    @property
    def pending(self) -> bool:
        return (self.alive or self.revive > 0) and (self.drones_left > 0 or self.shots > 0)

    def update(self, hold: bool = False, hold_missile: bool = False):
        """One frame -> (launch a drone now?, launch the missile now?)."""
        if not self.alive or hold:
            return False, False
        drone = missile = False
        if self.drones_left > 0:
            self.timer -= 1
            if self.timer <= 0:
                self.drones_left -= 1
                self.timer = int(random.randint(150, 240) * self.gap)
                drone = True
        if self.shots > 0 and not hold_missile:
            self.missile_timer -= 1
            if self.missile_timer <= 0:
                self.shots -= 1
                self.missile_timer = random.randint(420, 600)
                missile = True
        return drone, missile


# ==============================================================================
# MAIN ASYNC LOOP
# ==============================================================================
async def main():
    global joysticks, GAME_W
    SCREEN_WIDTH, SCREEN_HEIGHT = pick_game_width(), 600
    GAME_W = SCREEN_WIDTH            # the browser fit uses it too
    XC = (SCREEN_WIDTH - BASE_W) // 2   # shifts centred screens (start menu) to the middle of a wide field
    XR = SCREEN_WIDTH - BASE_W          # shifts right-hand things (touch buttons) to the right edge
    # FULL SCREEN (user, 2026-10-03: "start it in full screen always"): on a computer the game ALWAYS starts
    # full screen, scaled to the monitor (SCALED maps the mouse). Only F11 switches to a window (and back);
    # Esc never leaves full screen; Alt+F4 closes. In the browser the page itself handles full screen (index.html).
    desktop_fs = desktop_fullscreen_allowed()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT),
                                     (pygame.SCALED | pygame.FULLSCREEN) if desktop_fs else 0)
    fullscreen = {"on": desktop_fs}

    def set_fullscreen(on):
        if not desktop_fs or fullscreen["on"] == on:
            return
        try:
            pygame.display.toggle_fullscreen()
            fullscreen["on"] = on
        except pygame.error:
            pass
    dark_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    pygame.display.set_caption("Jet vs Missile")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 14, bold=True)
    num_font = pygame.font.SysFont("consolas", 22, bold=True)
    big_font = pygame.font.SysFont("consolas", 28, bold=True)
    title_font = pygame.font.SysFont("consolas", 34, bold=True)
    tag_font = pygame.font.SysFont("consolas", 10, bold=True)

    scale = 2
    game_state = "MODE_SELECT"
    prev_mode = "CAMPAIGN"

    active_decoys = []

    # AIR + GROUND: the jet flies in the sky, missiles launch from trucks/silos on the ground
    GROUND_Y = 540
    sky = pygame.Surface((SCREEN_WIDTH, GROUND_Y))
    for gy in range(GROUND_Y):
        t = gy / GROUND_Y
        sky.fill((int(8 + 22 * t), int(12 + 40 * t), int(30 + 70 * t)), (0, gy, SCREEN_WIDTH, 1))
    clouds = [[random.uniform(0, SCREEN_WIDTH), random.uniform(70, GROUND_Y - 120), random.uniform(0.4, 1.4),
               random.randint(40, 110)] for _ in range(9)]
    hills = [(x, GROUND_Y - 18 - int(14 * math.sin(x * 0.02) + 8 * math.sin(x * 0.053))) for x in range(0, SCREEN_WIDTH + 20, 20)]
    ground_scroll = 0.0

    def draw_world():
        nonlocal ground_scroll
        screen.blit(sky, (0, 0))
        for cl in clouds:
            cl[0] -= cl[2]
            if cl[0] < -cl[3]:
                cl[0] = SCREEN_WIDTH + cl[3]
                cl[1] = random.uniform(70, GROUND_Y - 120)
            shade = (40, 55, 85)
            pygame.draw.ellipse(screen, shade, (cl[0], cl[1], cl[3], cl[3] * 0.32))
            pygame.draw.ellipse(screen, shade, (cl[0] + cl[3] * 0.25, cl[1] - cl[3] * 0.1, cl[3] * 0.55, cl[3] * 0.3))
        pygame.draw.polygon(screen, (22, 38, 30), [(0, SCREEN_HEIGHT)] + hills + [(SCREEN_WIDTH, SCREEN_HEIGHT)])
        pygame.draw.rect(screen, (30, 48, 34), (0, GROUND_Y, SCREEN_WIDTH, SCREEN_HEIGHT - GROUND_Y))
        ground_scroll = (ground_scroll + 1.5) % 40
        for gx in range(-40, SCREEN_WIDTH + 40, 40):
            pygame.draw.line(screen, (45, 66, 46), (gx - ground_scroll, GROUND_Y + 22), (gx - ground_scroll + 18, GROUND_Y + 22), 2)
        pygame.draw.line(screen, (70, 100, 70), (0, GROUND_Y), (SCREEN_WIDTH, GROUND_Y), 2)

    # Mobile launchers spread over the whole ground: each drives back and forth inside its own
    # stretch, takes many hits to destroy (tougher every level) and is rebuilt for the next wave.
    # On boss waves the middle one is an armoured silo that doesn't move.
    # How many: launcher_count(level) -- 1 at levels 1-10, one more every 10 levels, 10 from level 91
    # (user, 2026-10-03). The row is rebuilt for every wave, each launcher in its own stretch of ground.
    launchers = []

    def boss_site():
        return len(launchers) // 2         # boss waves: the middle launcher is the armoured silo

    def reset_launchers(lvl):
        n = launcher_count(lvl)
        zone_w = SCREEN_WIDTH / n
        launchers[:] = [{"x": (i + 0.5) * zone_w, "home": (i + 0.5) * zone_w,
                         # the truck keeps to the first 60% of its stretch; its drone launcher sits at 75%
                         "lo": i * zone_w + min(32, zone_w * 0.3), "hi": i * zone_w + zone_w * 0.6,
                         "vx": random.choice((-1, 1)) * random.uniform(0.5, 1.1)} for i in range(n)]
        for i, ln in enumerate(launchers):
            ln["max_hp"] = 2   # every launcher, the boss silo too, is destroyed by its 2nd hit
            ln["hp"] = ln["max_hp"]
            ln["laser_frames"] = 0
            ln["alive"] = True
            ln["reloads"] = (1 + lvl // 40) if "RELOAD" in active_tactics(lvl) else 0
            ln["reload_cd"] = random.randint(300, 600)
            pool = unlocked_launchers(lvl)     # level 5+: each launcher is one of the unlocked nations' systems
            ln["system"] = random.choice(pool) if pool else None

    def launcher_rect(ln):
        return pygame.Rect(ln["x"] - 30, GROUND_Y - 30, 60, 32)

    def move_launchers(is_boss_wave, enemies):
        for i, ln in enumerate(launchers):
            if not ln["alive"]:
                if ln.get("revive", 0) > 0:           # being rebuilt: back with full armour after 2 s
                    ln["revive"] -= 1
                    if ln["revive"] == 0:
                        ln["alive"], ln["hp"], ln["laser_frames"] = True, ln["max_hp"], 0
                continue
            if is_boss_wave and i == boss_site():
                ln["x"] = float(ln["home"])
                continue
            ln["x"] += ln["vx"]
            if ln["x"] < ln["lo"] or ln["x"] > ln["hi"]:
                ln["vx"] = -ln["vx"]
                ln["x"] = max(ln["lo"], min(ln["hi"], ln["x"]))
            elif random.random() < 0.004:
                ln["vx"] = -ln["vx"]          # change direction now and then
            for dl in drone_launchers:        # never drives through a drone launcher: turns back before it
                if dl.alive and abs(dl.x - ln["x"]) < 52 and (dl.x - ln["x"]) * ln["vx"] > 0:
                    ln["vx"] = -ln["vx"]
                    break
        for e in enemies:                     # a waiting missile rides on its launcher
            if e.launch_delay > 0 and e.site is not None:
                e.x = launchers[e.site]["x"] - e.width // 2 + e.barrel_off

    def draw_launchers(is_boss_wave):
        for i, ln in enumerate(launchers):
            lx = int(ln["x"])
            if not ln["alive"]:
                pygame.draw.rect(screen, (35, 30, 28), (lx - 28, GROUND_Y - 10, 56, 10), border_radius=3)   # wreck
                pygame.draw.circle(screen, (60, 60, 65), (lx + random.randint(-6, 6), GROUND_Y - 18 - random.randint(0, 10)), random.randint(4, 8))
                if ln.get("revive", 0) > 0:
                    t = tag_font.render(f"REBUILD {ln['revive'] / 60:.1f}s", True, (200, 200, 210))
                    screen.blit(t, t.get_rect(center=(lx, GROUND_Y - 34)))
                continue
            if ln["hp"] < ln["max_hp"]:   # one block per hit left, shown once it has been hit
                seg = 44 // ln["max_hp"]
                for k in range(ln["max_hp"]):
                    col = (90, 230, 90) if k < ln["hp"] else (60, 20, 20)
                    pygame.draw.rect(screen, col, (lx - 22 + k * seg, GROUND_Y - 70, seg - 2, 5))
            if is_boss_wave and i == boss_site():
                pygame.draw.rect(screen, (60, 60, 70), (lx - 26, GROUND_Y - 8, 52, 14))      # missile silo
                pygame.draw.rect(screen, (255, 40, 80), (lx - 26, GROUND_Y - 8, 52, 14), 2)
                pygame.draw.rect(screen, (20, 20, 25), (lx - 14, GROUND_Y - 6, 28, 8))
            else:
                cab_x = lx + 14 if ln["vx"] > 0 else lx - 30   # cab at the front, facing the way it drives
                pygame.draw.rect(screen, (70, 80, 60), (lx - 30, GROUND_Y - 16, 60, 14), border_radius=3)  # launcher truck
                pygame.draw.rect(screen, (90, 100, 75), (cab_x, GROUND_Y - 26, 16, 12), border_radius=2)  # cab
                sysd = ln.get("system")
                if sysd and sysd["type"] == "MBML":   # multi-barrel rack: a block of launch tubes
                    pygame.draw.rect(screen, (105, 112, 95), (lx - 16, GROUND_Y - 34, 26, 18), border_radius=2)
                    for k in range(4):
                        pygame.draw.circle(screen, (35, 38, 32), (lx - 11 + k * 6, GROUND_Y - 25), 2)
                else:
                    pygame.draw.line(screen, (120, 125, 110), (lx - 4, GROUND_Y - 16), (lx - 4, GROUND_Y - 58), 4)  # launch rail
                for wx in (lx - 20, lx, lx + 20):
                    pygame.draw.circle(screen, (25, 25, 28), (wx, GROUND_Y - 1), 6)
            if ln.get("system"):   # nation + system name under the truck, in its trail colour
                tag = tag_font.render(f"{ln['system']['nation']} {ln['system']['name']}", True, ln["system"]["trail"])
                screen.blit(tag, tag.get_rect(center=(lx, GROUND_Y + 14)))

    current_level = 1
    total_score = 0
    active_mutator = "NONE"
    saved_data = load_save_data()
    modes = load_control_modes()   # jet / duel missile AUTO-MANUAL and AI difficulty (needed by the first wave)

    break_timer = 0
    break_winner = "P1"
    milestone_count = 0
    milestone_reward_pending = False

    p1_x, p1_y = 120.0, 300.0
    p1_speed = 5.4
    p1_max_hp = 300
    p1_hp = p1_max_hp
    p1_guard = False
    p1_guard_energy = 100.0
    p1_med_kits = 6
    p1_decoys = 6
    p1_shoot_cd = 0
    p1_power_tier = 1
    p1_power_charge = 0.0

    # FLIGHT MODEL: the jet is always flying. Keys/stick steer it; hands off, the autopilot flies
    # real manoeuvres: cruise, climb, dive, loop, barrel roll, and dogfight break turns.
    p1_vx, p1_vy = 3.0, 0.0
    p1_turn_rate = 0.0                       # heading change last frame (drives the bank effect)
    autopilot = {"mode": "cruise", "t": 120, "head": 0.0, "loop_left": 0.0, "roll": 0.0, "roll_left": 0.0}
    sky_esc = {"t": 0, "x": 0.0, "ret": False}   # "ret": turning back down -- keys / autopilot wait until it is back                 # frames the jet has spent above the top of the screen (sky escape)
    AUTOPILOT_TURN = 0.065                   # max heading change per frame (radians)

    def autopilot_velocity(cx, cy, speed, threats):
        """Next velocity for the hands-off jet. threats = [(x, y, vx, vy), ...] of incoming missiles."""
        ap = autopilot
        ap["t"] -= 1
        cruise = speed * 0.62
        facing_right = math.cos(ap["head"]) >= 0
        level_head = 0.0 if facing_right else math.pi

        # DOGFIGHT: a missile closing inside 240 px -> hard break turn across its path
        near = None
        for tx, ty, tvx, tvy in threats:
            d = math.hypot(tx - cx, ty - cy)
            closing = (cx - tx) * tvx + (cy - ty) * tvy > 0
            if d < 240 and closing and (near is None or d < near[0]):
                near = (d, tx, ty, tvx, tvy)
        ap["esc_cd"] = max(0, ap.get("esc_cd", 0) - 1)
        # SKY ESCAPE (user, 2026-10-03): now and then, with a missile close and the jet high enough, it climbs
        # straight up out of the sky instead; it is pulled back into the fight within 3 s (see SKY_RETURN)
        if near and cy < 300 and ap["esc_cd"] == 0 and ap["mode"] not in ("break", "escape") \
                and random.random() < 0.5:
            ap["mode"], ap["t"], ap["esc_cd"] = "escape", 150, 600
        elif near and ap["mode"] not in ("break", "escape") and not (ap["mode"] == "roll" and near[0] > 140):
            path = math.atan2(near[4], near[3])
            side = 1 if (near[3] * (cy - near[2]) - near[4] * (cx - near[1])) > 0 else -1
            ap["break_head"] = path + side * math.pi / 2
            ap["mode"], ap["t"] = "break", 40

        # pick the next manoeuvre when the current one is finished
        if ap["t"] <= 0 and ap["mode"] != "loop":
            ap["mode"] = random.choice(["cruise", "cruise", "climb", "dive", "loop", "roll"])
            if ap["mode"] == "loop" and not (170 < cy < GROUND_Y - 170):
                ap["mode"] = "cruise"                      # no room for a loop up here / down there
            ap["t"] = {"cruise": random.randint(90, 180), "climb": 70, "dive": 55, "loop": 999, "roll": 50}[ap["mode"]]
            ap["loop_left"] = 2 * math.pi
            ap["roll_left"] = 2 * math.pi

        mode = ap["mode"]
        spd = cruise
        if mode == "cruise":
            want = level_head + math.sin(pygame.time.get_ticks() * 0.0015) * 0.25   # gentle altitude waves
        elif mode == "climb":
            want = level_head + (-0.55 if facing_right else 0.55)
            spd = cruise * 1.05
        elif mode == "dive":
            want = level_head + (0.55 if facing_right else -0.55)
            spd = cruise * 1.4
        elif mode == "roll":
            want = level_head
            spd = cruise * 1.2
            step = 2 * math.pi / 50
            ap["roll"] += step
            ap["roll_left"] -= step
        elif mode == "break":
            want = ap["break_head"]
            spd = speed * 1.1
        elif mode == "escape":   # full power, nose straight up, out of the top of the sky
            want = -math.pi / 2 + (0.15 if facing_right else -0.15)
            spd = speed * 1.15
            if cy < -60:
                ap["mode"], ap["t"] = "dive", 60
        else:  # loop: keep pulling up until a full circle is flown
            step = 2 * math.pi / 100
            ap["head"] += -step if facing_right else step
            ap["loop_left"] -= step
            if ap["loop_left"] <= 0:
                ap["mode"], ap["t"] = "cruise", 90
            want = ap["head"]
            spd = cruise * 1.25

        # stay in the sky: turn back from the side edges, pull up near the ground, push down near the top
        # (an escape climb is allowed out of the top: SKY_RETURN brings the jet back)
        if mode == "escape":
            pass
        elif cx < 180:
            want = 0.0
        elif cx > SCREEN_WIDTH - 180:
            want = math.pi
        if mode == "escape":
            pass
        elif cy > GROUND_Y - 150 and math.sin(want) > -0.3:
            want = -0.6 if math.cos(want) >= 0 else math.pi + 0.6
            if mode == "loop":
                ap["mode"], ap["t"] = "climb", 40
        elif cy < 140 and math.sin(want) < 0.3:
            want = 0.6 if math.cos(want) >= 0 else math.pi - 0.6
            if mode == "loop":
                ap["mode"], ap["t"] = "dive", 30

        if mode != "loop":
            diff = (want - ap["head"] + math.pi) % (2 * math.pi) - math.pi
            ap["head"] += max(-AUTOPILOT_TURN, min(AUTOPILOT_TURN, diff))
        if ap["roll_left"] <= 0:
            ap["roll"] = 0.0
        return math.cos(ap["head"]) * spd, math.sin(ap["head"]) * spd

    FLARE_COUNT = 10          # flares per press of F
    FLARE_LIFE = 240          # 4 s burning
    FLARE_CATCH = 32          # a missile this close to a flare blows up on it
    FIRE_CONE = math.radians(30)   # guns point forward: shots at most 30 degrees off the flight path

    # TRIPLE JET SQUAD (3 jets on 'T')
    p1_split_timer = 0
    p1_split_cd = 0
    p1_split_charges = 3

    # CAMOUFLAGE ('C' key / gamepad Share): jet fades out, missiles lose their lock
    CAMO_DURATION = 240      # 4 s
    # STEALTH ('V'): 2 s fully hidden from missiles AND launchers -- no lock, fuses can't sense the jet,
    # launchers hold fire -- then 8 s to recharge (counted from activation)
    STEALTH_DURATION = 120
    STEALTH_COOLDOWN = 480
    p1_stealth_timer = 0
    p1_stealth_cd = 0
    p1_stealth_x, p1_stealth_y = 0.0, 0.0
    CAMO_COOLDOWN = 720      # 12 s from activation until it can be used again
    p1_camo_timer = 0
    p1_camo_cd = 0
    p1_camo_x, p1_camo_y = 0.0, 0.0   # last position the missiles saw

    p1_wins = 0
    p2_wins = 0
    # DUEL = JET vs LAUNCHER (user, 2026-10-03: "keep it simple man vs AI: jet will fly, missile and drone should fire
    # from launcher only, launcher can move, AI or man playing as missile launcher"). P2 is a launcher that drives
    # along the ground (p2_x = its centre) and fires missiles and drones. Unlike the campaign trucks (2 hits) it is
    # armoured (p2_max_hp hits): with 2 hits an auto-firing jet ended every round in about 2 seconds.
    p2_x, p2_y = SCREEN_WIDTH - 150.0, 300.0
    p2_speed = 4.4
    p2_max_hp = 12                     # hits: the duel launcher is armoured (2 hits ended a round in ~2 s)
    p2_hp = p2_max_hp
    DUEL_LEVEL = 30                    # missile / drone strength in the duel (medium-range missiles)
    DUEL_DRIVE = 2.2                   # launcher driving speed, px per frame (x1.8 when it sprints from a shot)
    DUEL_MISSILE_RELOAD = 120          # frames between its missiles (2 s)
    DUEL_DRONE_RELOAD = 240            # frames between its drones (4 s)
    DUEL_MAX_MISSILES = 3              # at most this many of its missiles in the sky at once
    DUEL_MAX_DRONES = 3
    duel = {"missiles": [], "missile_cd": 90, "drone_cd": 150, "vx": 0.0, "want_missile": False, "want_drone": False,
            "laser_frames": 0}
    p2_angle = 180.0
    p2_shoot_cd = 0
    p2_flash_timer = 0
    p2_is_burrowed = False
    p2_burrow_timer = 0
    p2_burrow_cd = 0
    p2_decoys = 3
    p2_power_tier = 1
    p2_power_charge = 0.0

    def launch_missile(lvl, site, delay, is_boss=False, flank_angle=None):
        mutator = active_mutator if lvl > 100 else "NONE"
        e = MissileEnemy(lvl, is_boss=is_boss, mutator=mutator, launch_x=launchers[site]["x"],
                         ground_y=GROUND_Y, launch_delay=delay, system=None if is_boss else launchers[site].get("system"),
                         difficulty=modes["difficulty"])
        e.site = site
        e.flank_angle = flank_angle if flank_angle is not None else random.uniform(0, 2 * math.pi)
        return e

    MAX_WAVE_MISSILES = 8      # salvos never put more than this many missiles in one wave's opening launch

    def launch_salvo(lvl, site, delay, flank_angle=None, room=MAX_WAVE_MISSILES):
        """A launch from one launcher: 1 missile from a SAM, a rippled salvo from a multi-barrel launcher."""
        n = max(1, min(room, salvo_size(launchers[site].get("system"), lvl)))
        out = []
        for k in range(n):
            e = launch_missile(lvl, site, delay + k * 14, flank_angle=None if flank_angle is None else flank_angle + k * 0.5)
            e.barrel_off = (k - (n - 1) / 2) * 8
            out.append(e)
        return out

    # ordnance, silos and unlock notices are refilled by spawn_campaign_wave, so they are defined first
    silos = []
    p1_ordnance = []                      # jet munitions in flight
    p1_ammo = {}                          # munition id -> rounds left this wave
    ord_sel = {"i": 0, "cd": 0, "fire": False}
    flir = {"on": False, "energy": 100.0}
    notices = []                          # unlock messages, shown as floating text by the main loop
    drone_launchers = []
    drones = []
    autogun = {"cd": 0, "rounds": [], "firing": 0}
    drone_img = create_drone_sprite()

    def spawn_drone_launchers(lvl):
        drone_launchers.clear()
        drones.clear()
        autogun["rounds"].clear()
        n = drone_launcher_count(lvl)
        for i in range(n):
            x = (i + 0.75) * SCREEN_WIDTH / n        # three quarters into each stretch (trucks start in the middle)
            drone_launchers.append(DroneLauncher(x, drones_per_launcher(lvl), first_delay=90 + i * 45 + random.randint(0, 60),
                                                 missile_delay=480 + i * 90 + random.randint(0, 180),
                                                 has_missile=lvl >= DRONE_MISSILE_LEVEL,
                                                 gap=difficulty_factors(modes["difficulty"])["drone_gap"]))

    def spawn_silos(lvl):
        silos.clear()
        n = silo_count(lvl)
        pool = [s for s in unlocked_launchers(lvl) if s["type"] == "SAM"] or [None]
        xs, tries = [], 0
        while len(xs) < n:
            tries += 1
            x = random.uniform(40, SCREEN_WIDTH - 40)
            if all(abs(x - o) > 60 for o in xs) or tries > 400:   # spread out; give up spacing if it can't fit
                xs.append(x)
        for i, x in enumerate(xs):
            silos.append(SiloLauncher(x, shots=1 + lvl // 30, first_delay=150 + i * 100 + random.randint(0, 120),
                                      system=random.choice(pool)))

    def spawn_campaign_wave(lvl):
        nonlocal p1_max_hp
        # the jet grows tougher with the level too: max HP 300 -> 600 by level 101
        p1_max_hp = round((300 + min(300, (lvl - 1) * 3)) * human_buff("CAMPAIGN"))
        reset_launchers(lvl)
        enemies = []
        is_boss = (lvl % 10 == 0)
        if is_boss:
            enemies.append(launch_missile(lvl, boss_site(), 60, is_boss=True))
        else:
            num = min(4, 1 + (lvl // 15))
            spin = random.uniform(0, 2 * math.pi)
            for i in range(num):
                # missiles lift off one after another from launchers spread over the ground;
                # each gets its own flank angle so a FLANK wave attacks from different sides
                site = (i * 2 + random.randint(0, 1)) % len(launchers)
                enemies.extend(launch_salvo(lvl, site, 40 + i * 50, flank_angle=spin + i * 2 * math.pi / num,
                                            room=MAX_WAVE_MISSILES - len(enemies) - (num - 1 - i)))
        spawn_silos(lvl)
        spawn_drone_launchers(lvl)
        # the jet's ordnance: full racks every wave
        p1_ammo.clear()
        for m in jet_loadout(lvl):
            p1_ammo[m["id"]] = round(m["ammo"] * human_buff("CAMPAIGN"))
        p1_ordnance.clear()
        ord_sel["i"] = min(ord_sel["i"], max(0, len(p1_ammo) - 1))
        for n in ARSENAL["nations"]:
            if n["unlock_level"] == lvl:
                notices.append((f"UNLOCKED: {n['name']} - " + ", ".join(x["name"] for x in n["launchers"] + n["munitions"]),
                                tuple(n["color"])))
        if lvl == IR_UNLOCK_LEVEL:
            notices.append(("UNLOCKED: IR HEAT-SEEKER + FLIR POD [X] + UNDERGROUND SILOS", (255, 90, 160)))
        return enemies

    def damage_launcher(i, hits=1):
        """A launcher is destroyed by its 2nd hit; any missile still on it goes too."""
        nonlocal total_score
        ln = launchers[i]
        ln["hp"] -= hits
        if ln["hp"] <= 0 and ln["alive"]:
            ln["alive"] = False
            ln["reloads"] = 0
            ln["revive"] = LAUNCHER_REVIVE_FRAMES     # rebuilt 2 s later (user, 2026-10-03); its RELOADs stay lost
            SFX.snd_explode.play()
            total_score += 150
            for e in campaign_enemies[:]:
                if e.site == i and e.launch_delay > 0:
                    campaign_enemies.remove(e)

    def silo_rect(s):
        return pygame.Rect(s.x - 24, GROUND_Y - 12, 48, 14)

    def damage_silo(s, hits=1):
        """A silo that has fired (or that the FLIR pod found) is destroyed by its 2nd hit."""
        nonlocal total_score
        if not s.targetable:
            return
        s.hp -= hits
        if s.hp <= 0:
            s.alive = False
            blasts.append([s.x, GROUND_Y - 10, 0, 1.2])
            SFX.snd_explode.play()
            total_score += 200

    def ground_blast(x, y, radius, hits):
        """A bomb or air-to-ground warhead goes off: every launcher and targetable silo within reach takes the hits."""
        blasts.append([x, y, 0, max(0.8, radius / 35)])
        SFX.snd_explode.play()
        if y < GROUND_Y - 70:
            return                                  # burst too high to reach the ground
        for li, ln in enumerate(launchers):
            if ln["alive"] and abs(ln["x"] - x) <= radius + 30:
                damage_launcher(li, hits)
        for s in silos:
            if s.targetable and abs(s.x - x) <= radius + 24:
                damage_silo(s, hits)
        for dl in drone_launchers:
            if dl.alive and abs(dl.x - x) <= radius + 20:
                damage_drone_launcher(dl, hits)

    def drone_launcher_rect(dl):
        return pygame.Rect(dl.x - 18, GROUND_Y - 22, 36, 22)

    def damage_drone_launcher(dl, hits=1):
        """A drone launcher is destroyed by its 2nd hit; it is rebuilt LAUNCHER_REVIVE_FRAMES (2 s) later and goes on
        with the drones / missile it had left (user, 2026-10-03)."""
        nonlocal total_score
        if not dl.alive:
            return
        dl.hp -= hits
        if dl.hp <= 0:
            dl.destroy()
            blasts.append([dl.x, GROUND_Y - 12, 0, 1.0])
            SFX.snd_explode.play()
            total_score += 120

    def kill_drone(d, x, y):
        nonlocal total_score
        if d in drones:
            drones.remove(d)
        blasts.append([x, y, 0, 0.5])
        SFX.snd_hit.play()
        total_score += DRONE_KILL_SCORE

    def update_drones_and_autogun(jcx, jcy, tx, ty, hp):
        """Drones home on (tx, ty) -- the jet, or where camouflage / stealth left it -- and blow up against the jet
        at (jcx, jcy) (HP damage; the shield blocks). The jet's protective AUTO-GUN fires by itself at the nearest
        drone inside its range. Shared by the campaign and the duel. Returns the jet's HP."""
        # DRONES: subsonic, home on the jet (or where camouflage / stealth left it), blow up against it
        for d in drones[:]:
            d.update(tx, ty)
            if d.y >= GROUND_Y - 8:              # spent drone glided into the ground (or flew into it)
                drones.remove(d)
                blasts.append([d.x, GROUND_Y - 8, 0, 0.5])
                SFX.snd_explode.play()
                continue
            if d.x < -80 or d.x > SCREEN_WIDTH + 80 or d.y < -300:
                drones.remove(d)
                continue
            if hp > 0 and p1_stealth_timer == 0 and sky_esc["t"] == 0 and not d.expired and \
                    math.hypot(d.x - jcx, d.y - jcy) < DRONE_HIT_RADIUS + 30 * jet_size_factor(jcy):
                drones.remove(d)
                blasts.append([d.x, d.y, 0, 0.7])
                SFX.snd_explode.play()
                if p1_guard:
                    floating_texts.append(["BLOCKED!", jcx - 20, jcy - 40, (0, 255, 220), 20])
                else:
                    hp = max(0, hp - d.dmg)
                    floating_texts.append([f"DRONE HIT -{d.dmg}", jcx - 30, jcy - 40, (255, 90, 90), 30])

        # PROTECTIVE AUTO-GUN: fires by itself, all round, at the nearest drone inside AUTOGUN_RANGE
        if autogun["cd"] > 0:
            autogun["cd"] -= 1
        if autogun["firing"] > 0:
            autogun["firing"] -= 1
        if hp > 0 and autogun["cd"] == 0:
            aim = autogun_pick(jcx, jcy, drones, rng=AUTOGUN_RANGE * pbuff())
            if aim is not None:
                autogun["rounds"].append({"x": jcx, "y": jcy, "vx": math.cos(aim) * AUTOGUN_SPEED,
                                          "vy": math.sin(aim) * AUTOGUN_SPEED, "life": int(AUTOGUN_RANGE * 1.3 / AUTOGUN_SPEED)})
                autogun["cd"] = round(AUTOGUN_COOLDOWN / pbuff())
                autogun["firing"] = 20
                SFX.snd_autogun.stop()           # restart, never stack into a drone
                SFX.snd_autogun.play()
        for r in autogun["rounds"][:]:
            r["x"] += r["vx"]
            r["y"] += r["vy"]
            r["life"] -= 1
            hit = next((d for d in drones if math.hypot(d.x - r["x"], d.y - r["y"]) < 14), None)
            if hit:
                kill_drone(hit, r["x"], r["y"])
            if hit or r["life"] <= 0:
                autogun["rounds"].remove(r)
        return hp


    def draw_drone_launchers():
        for dl in drone_launchers:
            x = int(dl.x)
            if not dl.alive:
                pygame.draw.rect(screen, (35, 30, 28), (x - 16, GROUND_Y - 6, 32, 6), border_radius=2)
                if dl.revive > 0:
                    t = tag_font.render(f"REBUILD {dl.revive / 60:.1f}s", True, (200, 200, 210))
                    screen.blit(t, t.get_rect(center=(x, GROUND_Y - 22)))
                continue
            pygame.draw.rect(screen, (78, 84, 70), (x - 18, GROUND_Y - 10, 36, 10), border_radius=2)     # base
            pygame.draw.polygon(screen, (100, 106, 90), [(x - 14, GROUND_Y - 10), (x + 12, GROUND_Y - 24),
                                                         (x + 16, GROUND_Y - 20), (x - 8, GROUND_Y - 10)])  # ramp
            if dl.drones_left > 0:   # next drone sitting on the ramp
                pygame.draw.polygon(screen, (150, 155, 145), [(x + 10, GROUND_Y - 25), (x - 2, GROUND_Y - 25), (x + 2, GROUND_Y - 17)])
            if dl.shots > 0:         # its missile, in a tube beside the ramp
                pygame.draw.rect(screen, (200, 200, 205), (x - 17, GROUND_Y - 22, 4, 12))
                pygame.draw.rect(screen, (200, 40, 50), (x - 17, GROUND_Y - 24, 4, 3))
            if dl.hp < dl.max_hp:
                for k in range(dl.max_hp):
                    pygame.draw.rect(screen, (90, 230, 90) if k < dl.hp else (60, 20, 20), (x - 16 + k * 17, GROUND_Y - 34, 15, 4))

    def draw_drones():
        for d in drones:
            img = pygame.transform.rotate(drone_img, -math.degrees(d.heading))
            screen.blit(img, img.get_rect(center=(int(d.x), int(d.y))))

    def ground_targets():
        return ([(ln["x"], GROUND_Y - 14) for ln in launchers if ln["alive"]] +
                [(s.x, GROUND_Y - 6) for s in silos if s.targetable] +
                [(dl.x, GROUND_Y - 10) for dl in drone_launchers if dl.alive])

    def flying_missiles():
        return [e for e in campaign_enemies if e.launch_delay == 0 and not e.expired]

    def selected_munition():
        loadout = jet_loadout(current_level)
        return loadout[ord_sel["i"] % len(loadout)] if loadout else None

    def fire_ordnance(nx, ny, head, jet_speed, buff):
        """Launch the selected munition from the jet: rockets leave the nose along the flight path,
        bombs drop from the belly at the jet's own velocity."""
        m = selected_munition()
        if not m or ord_sel["cd"] > 0:
            return
        if p1_ammo.get(m["id"], 0) <= 0:
            floating_texts.append([f"{m['name']}: EMPTY", nx - 30, ny - 30, (160, 165, 180), 25])
            return
        p1_ammo[m["id"]] -= 1
        ord_sel["cd"] = int(ORDNANCE_COOLDOWN / buff)
        o = dict(m)
        o.update(x=nx, y=ny, heading=head, speed=max(2.0, jet_speed), burn_left=m.get("burn", 0), age=0,
                 los=None, lock=None, aim=None, pts=[], dmg=int(60 * level_power(current_level) * buff))
        if m["kind"] == "bomb":
            o["vx"], o["vy"] = math.cos(head) * jet_speed, math.sin(head) * jet_speed + 0.5
        if m["target"] == "air" and m["guidance"] == "radar":     # radar missile: locks the nearest missile ahead
            air = flying_missiles()
            ahead = [e for e in air if abs(angle_diff(math.atan2(e.y + e.height / 2 - ny, e.x + e.width / 2 - nx), head)) < math.radians(60)]
            pick = ahead or air
            if pick:
                o["lock"] = min(pick, key=lambda e: math.hypot(e.x + e.width / 2 - nx, e.y + e.height / 2 - ny))
        elif m["target"] == "ground":                              # nearest launcher / silo in front, else nearest
            pts = ground_targets()
            fwd = [p for p in pts if (p[0] - nx) * math.cos(head) >= 0] or pts
            if fwd:
                o["aim"] = min(fwd, key=lambda p: math.hypot(p[0] - nx, p[1] - ny))
        p1_ordnance.append(o)
        SFX.snd_ordnance.play()

    def update_ordnance():
        nonlocal total_score
        air = flying_missiles()
        for o in p1_ordnance[:]:
            o["age"] += 1
            o["pts"].append((o["x"], o["y"]))
            if len(o["pts"]) > 12:
                o["pts"].pop(0)
            gone = o["age"] > o["life"]
            if o["target"] == "ground":   # the launcher drives on: follow the ground target nearest the aim point
                pts = ground_targets()
                if o["aim"] and pts:
                    near = min(pts, key=lambda p: math.hypot(p[0] - o["aim"][0], p[1] - o["aim"][1]))
                    o["aim"] = near if math.hypot(near[0] - o["aim"][0], near[1] - o["aim"][1]) < 120 else o["aim"]

            if o["kind"] == "rocket":
                motor_step(o)
                tgt = None
                if o["target"] == "air":
                    if o["guidance"] == "ir":      # heat seeker: hottest = nearest lit motor inside its seeker cone
                        tgt = ir_pick_target(o["x"], o["y"], o["heading"],
                                             [(e.x + e.width / 2, e.y + e.height / 2) for e in air],
                                             o["seeker_fov_deg"], o["seeker_range"])
                    else:                          # radar: keeps its lock; ECM jamming blinds it
                        if o["lock"] not in air or o["lock"] not in campaign_enemies:
                            o["lock"] = min(air, key=lambda e: math.hypot(e.x - o["x"], e.y - o["y"])) if air else None
                        if o["lock"] is not None and o["lock"].ecm_timer == 0:
                            tgt = (o["lock"].x + o["lock"].width / 2, o["lock"].y + o["lock"].height / 2)
                else:
                    tgt = o["aim"]
                if tgt:
                    los = math.atan2(tgt[1] - o["y"], tgt[0] - o["x"])
                    o["heading"] = guidance_turn(o["heading"], o["los"], los, o["nav"], math.radians(o["turn_deg_s"]) / 60)
                    o["los"] = los
                else:
                    o["los"] = None
                o["x"] += math.cos(o["heading"]) * o["speed"]
                o["y"] += math.sin(o["heading"]) * o["speed"]
                if o["burn_left"] == 0 and o["speed"] < 2.5:
                    gone = True                    # motor out and too slow to fly: it falls away
                if o["target"] == "air":
                    for e in air:
                        if e in campaign_enemies and math.hypot(e.x + e.width / 2 - o["x"], e.y + e.height / 2 - o["y"]) < ORDNANCE_FUSE + e.width * 0.3:
                            blasts.append([o["x"], o["y"], 0, 0.7])
                            SFX.snd_explode.play()
                            if not (o["guidance"] == "radar" and e.ecm_timer > 0):   # jammed: it blows up short
                                campaign_enemies.remove(e)
                                total_score += o["dmg"]
                                floating_texts.append([f"{o['name']} KILL +{o['dmg']}", o["x"], o["y"] - 15, tuple(o["trail"]), 30])
                            gone = "hit"
                            break
                    if gone != "hit" and o["y"] >= GROUND_Y - 6:
                        blasts.append([o["x"], GROUND_Y - 6, 0, 0.6])
                        gone = "hit"
                else:
                    struck = o["y"] >= GROUND_Y - 14 or any(
                        ln["alive"] and launcher_rect(ln).collidepoint(o["x"], o["y"]) for ln in launchers) or any(
                        s.targetable and silo_rect(s).collidepoint(o["x"], o["y"]) for s in silos) or any(
                        dl.alive and drone_launcher_rect(dl).collidepoint(o["x"], o["y"]) for dl in drone_launchers)
                    if struck:
                        ground_blast(o["x"], min(o["y"], GROUND_Y - 10), o["blast"], o["hits"])
                        gone = "hit"
            else:   # bomb: released at the jet's velocity, gravity + air drag; guided ones steer gently
                o["vy"] += o["gravity"]
                o["vx"] *= 1 - BOMB_DRAG
                o["vy"] *= 1 - BOMB_DRAG
                if o["guidance"] == "bomb" and o["aim"]:
                    cur = math.atan2(o["vy"], o["vx"])
                    sp = math.hypot(o["vx"], o["vy"])
                    want = math.atan2(o["aim"][1] - o["y"], o["aim"][0] - o["x"])
                    step = math.radians(o["steer_deg_s"]) / 60
                    cur += max(-step, min(step, angle_diff(want, cur)))
                    o["vx"], o["vy"] = math.cos(cur) * sp, math.sin(cur) * sp
                o["x"] += o["vx"]
                o["y"] += o["vy"]
                o["heading"] = math.atan2(o["vy"], o["vx"])
                if o["y"] >= GROUND_Y - 6:
                    ground_blast(o["x"], GROUND_Y - 6, o["blast"], o["hits"])
                    gone = "hit"
            if not (-60 <= o["x"] <= SCREEN_WIDTH + 60) or o["y"] < -200:
                gone = True
            if gone:
                p1_ordnance.remove(o)

    def draw_ordnance():
        for o in p1_ordnance:
            col = tuple(o["trail"])
            for k in range(1, len(o["pts"])):
                pygame.draw.line(screen, col, o["pts"][k - 1], o["pts"][k], max(1, 1 + 3 * k // len(o["pts"])))
            dx, dy = math.cos(o["heading"]), math.sin(o["heading"])
            if o["kind"] == "rocket":
                if o["burn_left"] > 0:
                    pygame.draw.line(screen, (255, 200, 90), (o["x"] - dx * 6, o["y"] - dy * 6), (o["x"] - dx * 14, o["y"] - dy * 14), 3)
                pygame.draw.line(screen, (225, 228, 235), (o["x"] - dx * 6, o["y"] - dy * 6), (o["x"] + dx * 6, o["y"] + dy * 6), 3)
                pygame.draw.circle(screen, col, (int(o["x"] + dx * 6), int(o["y"] + dy * 6)), 2)
            else:
                pygame.draw.circle(screen, (60, 64, 70), (int(o["x"]), int(o["y"])), 5)
                pygame.draw.circle(screen, col, (int(o["x"]), int(o["y"])), 5, 1)
                pygame.draw.line(screen, col, (o["x"] - dx * 5, o["y"] - dy * 5), (o["x"] - dx * 10, o["y"] - dy * 10), 2)

    def draw_silos():
        for s in silos:
            sx = int(s.x)
            if not s.alive:
                if s.revealed:   # crater
                    pygame.draw.ellipse(screen, (25, 22, 20), (sx - 24, GROUND_Y - 6, 48, 10))
                continue
            if s.fired:          # open concrete pad, in plain sight
                pygame.draw.rect(screen, (85, 85, 92), (sx - 24, GROUND_Y - 6, 48, 10), border_radius=2)
                hatch = (255, 120, 30) if s.hot else (15, 15, 18)
                pygame.draw.rect(screen, hatch, (sx - 12, GROUND_Y - 4, 24, 6))
                if s.hp < s.max_hp:
                    for k in range(s.max_hp):
                        pygame.draw.rect(screen, (90, 230, 90) if k < s.hp else (60, 20, 20), (sx - 22 + k * 22, GROUND_Y - 22, 20, 4))
                if s.state == "FIRING":
                    pygame.draw.circle(screen, (255, 230, 150), (sx, GROUND_Y - 12), 26)
            elif s.revealed:     # FLIR contact: thermal bracket over a still-closed silo
                c = (255, 90, 40) if s.hot else (120, 255, 140)
                for bx, by, ex, ey in ((-22, -16, -12, -16), (-22, -16, -22, -8), (22, -16, 12, -16), (22, -16, 22, -8),
                                       (-22, 4, -12, 4), (-22, 4, -22, -4), (22, 4, 12, 4), (22, 4, 22, -4)):
                    pygame.draw.line(screen, c, (sx + bx, GROUND_Y + by), (sx + ex, GROUND_Y + ey), 2)
                screen.blit(tag_font.render("IR", True, c), (sx - 6, GROUND_Y - 30))
            # hidden and not found by the FLIR pod: nothing to see

    def draw_flir_cone(cx, cy):
        h = GROUND_Y - cy
        if h <= 0:
            return
        depth = min(h, FLIR_RANGE)
        half = math.tan(FLIR_HALF_ANGLE) * depth
        # drawn on a surface just the cone's size (not the whole screen): much cheaper on phones
        w, hh = int(half * 2) + 2, int(depth) + 2
        cone = pygame.Surface((w, hh), pygame.SRCALPHA)
        pts = [(w / 2, 0), (1, depth), (w - 1, depth)]
        pygame.draw.polygon(cone, (120, 255, 140, 40), pts)
        pygame.draw.polygon(cone, (120, 255, 140, 120), pts, 1)
        screen.blit(cone, (cx - w / 2, cy))

    campaign_enemies = spawn_campaign_wave(current_level)
    p1_bullets = []
    hit_sparks = []
    floating_texts = []

    # missile self-destruct fireballs: [x, y, age, scale]
    FUSE_RADIUS = 60          # fuse distance for a jet flying low (full size); see jet_fuse_radius

    # JET SIZE (user, 2026-10-02): the jet is small, and smaller the further it is from the targets on the
    # ground -- perspective: low over the launchers = closest = biggest, top of the sky = 60% of that.
    JET_BASE_SCALE = 0.62     # of the original 144x120 drawing

    def jet_size_factor(cy):
        t = max(0.0, min(1.0, (cy - 95) / (GROUND_Y - 40 - 95)))   # 0 = top of the sky, 1 = lowest flight
        return JET_BASE_SCALE * (0.6 + 0.4 * t)

    def jet_fuse_radius(cy):
        # a missile detonates when it touches the jet as drawn: half the jet's length plus the missile's nose
        return 15 + 72 * jet_size_factor(cy)
    BLAST_FRAMES = 20
    blasts = []

    def draw_blasts():
        for bl in blasts[:]:
            bl[2] += 1
            if bl[2] > BLAST_FRAMES:
                blasts.remove(bl)
                continue
            r = int((10 + bl[2] * 2.6) * bl[3])
            fade = 1 - bl[2] / BLAST_FRAMES
            cx, cy = int(bl[0]), int(bl[1])
            pygame.draw.circle(screen, (int(200 * fade + 40), int(50 * fade), 0), (cx, cy), r)
            pygame.draw.circle(screen, (255, int(150 * fade + 60), 0), (cx, cy), int(r * 0.65))
            pygame.draw.circle(screen, (255, 240, int(160 * fade)), (cx, cy), int(r * 0.3))

    def handle_round_conclusion(winner: str, origin_mode: str):
        nonlocal game_state, break_timer, break_winner, prev_mode, milestone_count, active_mutator, p1_split_timer, milestone_reward_pending
        prev_mode = origin_mode
        break_winner = winner
        p1_split_timer = 0

        update_save_data(total_score, current_level)
        if origin_mode == "CAMPAIGN":            # this player's own record, under their name
            record_result(names[0], score=total_score, level=current_level)
        elif winner == "P1":
            record_result(names[0], win=True)
        elif modes["missile"] == "MANUAL":       # a human drove the launcher: the win is theirs
            record_result(names[1], win=True)
        saved_data.update(load_save_data())      # keeps "continue from level N" up to date
        refresh_records()

        wins = p1_wins if winner == "P1" else p2_wins
        is_5th_milestone = False

        if origin_mode == "DUEL" and wins > 0 and wins % 5 == 0:
            is_5th_milestone = True
            milestone_count = wins
        elif origin_mode == "CAMPAIGN" and current_level > 0 and current_level % 5 == 0 and winner == "P1":
            is_5th_milestone = True
            milestone_count = current_level

        if current_level >= 100 and current_level % 5 == 0:
            active_mutator = random.choice(OVERDRIVE_MUTATORS)[0]

        if is_5th_milestone:
            # every 5th win: bonus (+HP, med-kit, decoy) handed out at the short break
            milestone_reward_pending = True

        game_state = "NORMAL_ROUND_BREAK"
        break_timer = 75
        SFX.snd_hit.play()

    def reset_positions():
        nonlocal p1_x, p1_y, p2_x, p2_y, p1_bullets, active_decoys, p1_split_timer, p1_vx, p1_vy
        p1_x, p1_y = 120.0, 300.0
        p1_vx, p1_vy = 3.0, 0.0
        autopilot.update({"mode": "cruise", "t": 120, "head": 0.0, "roll": 0.0})
        sky_esc["t"], sky_esc["ret"] = 0, False
        safeguard["t"] = 0                          # (its recharge carries on across rounds)
        safeguard["zaps"].clear()
        p2_x, p2_y = SCREEN_WIDTH - 150.0, 300.0
        p1_bullets.clear()
        active_decoys.clear()
        p1_split_timer = 0

    # JET CRASH: when the jet is shot down it catches fire, spins and falls, then explodes
    # on the ground like a fire bomb before the round ends
    crash = {}

    def start_jet_crash(origin):
        nonlocal game_state
        if game_state not in ("CAMPAIGN", "DUEL"):
            return
        crash.clear()
        crash.update({"x": p1_x + 50, "y": p1_y + 40, "vx": random.uniform(0.8, 2.2), "vy": -2.5, "rot": 0.0,
                      "phase": "fall", "boom": 0, "fire": [], "origin": origin, "level_boss": current_level % 10 == 0})
        game_state = "JET_CRASH"

    # LEVEL STRIP at the bottom of the 1P screen: click a number, or N = next / P = previous
    LEVEL_BAR_TOP = SCREEN_HEIGHT - 30
    LEVEL_SLOT_W = 38

    def level_bar_slots():
        lo = max(1, current_level - 5)
        x0 = SCREEN_WIDTH // 2 - (11 * LEVEL_SLOT_W) // 2
        return [(lo + i, pygame.Rect(x0 + i * LEVEL_SLOT_W + 2, LEVEL_BAR_TOP + 4, LEVEL_SLOT_W - 4, 22)) for i in range(11)]

    def jump_to_level(lvl):
        nonlocal current_level, campaign_enemies
        current_level = max(1, lvl)
        campaign_enemies = spawn_campaign_wave(current_level)
        reset_positions()

    def draw_level_bar():
        pygame.draw.rect(screen, (10, 14, 20), (0, LEVEL_BAR_TOP, SCREEN_WIDTH, SCREEN_HEIGHT - LEVEL_BAR_TOP))
        screen.blit(font.render("[P] PREV", True, (180, 190, 210)), (24, LEVEL_BAR_TOP + 8))
        screen.blit(font.render("NEXT [N]", True, (180, 190, 210)), (SCREEN_WIDTH - 90, LEVEL_BAR_TOP + 8))
        for lvl, r in level_bar_slots():
            current = lvl == current_level
            boss = lvl % 10 == 0
            hover = r.collidepoint(mouse_pos)
            fill = (255, 140, 0) if current else ((60, 70, 95) if hover else (28, 34, 50))
            pygame.draw.rect(screen, fill, r, border_radius=4)
            pygame.draw.rect(screen, (255, 60, 90) if boss else (80, 95, 125), r, 1, border_radius=4)
            label = font.render(str(lvl), True, (20, 20, 20) if current else (220, 225, 240))
            screen.blit(label, label.get_rect(center=r.center))

    # ======================================================================
    # TOUCH CONTROLS (phones / tablets): thumb joystick on the left half, FIRE (auto-aim) and
    # SHIELD (hold) plus tap buttons on the right. Shown from the start on phones, or as soon as
    # the screen is touched; hidden again when a game controller is used.
    # ======================================================================
    MOBILE = detect_mobile()
    touch = {"on": MOBILE, "stick_id": None, "origin": (0.0, 0.0), "vec": (0.0, 0.0),
             "fire_ids": set(), "shield_ids": set(), "finger_seen": False}
    STICK_R = 70
    FIRE_C, FIRE_R = (715 + XR, 480), 58
    TOUCH_BUTTONS = [   # label, key it presses (None = held shield), centre, radius
        ("SHIELD", None, (598 + XR, 522), 30),
        ("HEAL", pygame.K_q, (598 + XR, 448), 26),
        ("SQUAD", pygame.K_t, (565 + XR, 378), 30),
        ("STEALTH", pygame.K_v, (630 + XR, 378), 30),
        ("CAMO", pygame.K_c, (695 + XR, 378), 30),
        ("FLARES", pygame.K_f, (760 + XR, 378), 30),
        ("WPN", pygame.K_g, (630 + XR, 312), 26),       # next munition (1P, level 5+)
        ("MSL", pygame.K_r, (695 + XR, 312), 26),       # launch the selected munition
        ("FLIR", pygame.K_x, (760 + XR, 312), 26),      # FLIR pod on/off (1P, level 10+)
        ("SAFE", pygame.K_b, (565 + XR, 312), 26),      # SAFEGUARD: 3 s, every missile / drone in the air goes down
    ]

    def visible_touch_buttons():
        out = []
        for b in TOUCH_BUTTONS:
            if b[0] in ("WPN", "MSL") and not (game_state == "CAMPAIGN" and p1_ammo):
                continue
            if b[0] == "FLIR" and not (game_state == "CAMPAIGN" and current_level >= IR_UNLOCK_LEVEL):
                continue
            out.append(b)
        return out
    TOUCH_MENU = pygame.Rect(SCREEN_WIDTH - 74, 32, 62, 24)
    CARD1 = pygame.Rect(55 + XC, 150, 335, 325)
    CARD2 = pygame.Rect(410 + XC, 150, 335, 325)
    NAME_BTN1 = pygame.Rect(SCREEN_WIDTH // 2 - 340, 86, 335, 26)   # start screen: player 1 name
    NAME_BTN2 = pygame.Rect(SCREEN_WIDTH // 2 + 5, 86, 335, 26)     # start screen: player 2 name
    MODE_JET_BTN = pygame.Rect(55 + XC, 482, 223, 22)       # start screen: JET MANUAL / AUTO
    MODE_MSL_BTN = pygame.Rect(288 + XC, 482, 224, 22)      # start screen: DUEL MISSILE MANUAL / AUTO
    MODE_DIFF_BTN = pygame.Rect(522 + XC, 482, 223, 22)     # start screen: AI EASY / NORMAL
    CONTINUE_BTN = pygame.Rect(75 + XC, 436, 295, 26)       # inside the campaign card: continue from the best level
    TOUCH_PAUSE = pygame.Rect(SCREEN_WIDTH // 2 - 31, 80, 62, 24)
    if MOBILE:
        modes["missile"] = "AUTO"   # phones: always player vs AI (user, 2026-10-03), no second human player

    def pbuff():
        """The player's vs-AI bonus right now (1.15 vs the computer, 1.0 in a human-vs-human duel)."""
        return human_buff(game_state, modes["missile"])

    def toggle_control(which):
        if which == "missile" and MOBILE:
            floating_texts.append(["PHONE: ALWAYS YOU vs AI", SCREEN_WIDTH // 2 - 90, 230, (255, 230, 120), 50])
            return
        modes[which] = toggle_mode(modes[which])
        save_control_modes(modes)                 # (no sound: sounds are only for actions -- user rule)
        if game_state in ("CAMPAIGN", "DUEL"):
            name = {"jet": "JET", "missile": "DUEL LAUNCHER", "difficulty": "AI"}[which]
            floating_texts.append([f"{name}: {modes[which]}", SCREEN_WIDTH // 2 - 50, 230, (255, 230, 120), 50])
            if which == "difficulty" and game_state == "CAMPAIGN":
                floating_texts.append(["(from the next wave)", SCREEN_WIDTH // 2 - 70, 250, (200, 200, 210), 50])
    touch_font = pygame.font.SysFont("consolas", 12, bold=True)
    touch_big = pygame.font.SysFont("consolas", 20, bold=True)
    last_fit_ms = -1000
    PAD_ORD_BUTTON = 7          # the one controller button no other action uses
    pad_ord = {"down": False, "used": False}
    pause = {"on": False, "drawn": False}
    safeguard = {"t": 0, "cd": 0, "zaps": []}      # SAFEGUARD: frames left on, frames to recharge, interceptor lines

    def run_safeguard(cx, cy):
        """One frame of SAFEGUARD: every enemy missile in the air and every drone is shot down by an interceptor
        from the jet at (cx, cy). Missiles still on their launchers are not flying, so they are left alone."""
        nonlocal total_score
        targets = []
        if game_state == "CAMPAIGN":
            for e in [e for e in campaign_enemies if e.launch_delay == 0]:
                campaign_enemies.remove(e)
                targets.append((e.x + e.width / 2, e.y + e.height / 2))
                total_score += SAFEGUARD_KILL_SCORE
        elif game_state == "DUEL":
            for e in duel["missiles"][:]:
                duel["missiles"].remove(e)
                targets.append((e.x + e.width / 2, e.y + e.height / 2))
        for d in drones[:]:
            kill_drone(d, d.x, d.y)
            targets.append((d.x, d.y))
        for tx, ty in targets:
            blasts.append([tx, ty, 0, 0.8])
            safeguard["zaps"].append([cx, cy, tx, ty, 10])
        if targets:
            SFX.snd_explode.play()
    hint = {"text": "", "frames": 0}

    names = load_player_names()                     # [player 1, player 2]
    name_edit = {"who": None, "buf": ""}            # which name box is being typed into (0 / 1 / None)
    records = {}

    def refresh_records():
        records.clear()
        data = load_save_data()
        for nm in names:
            records[nm] = player_record(nm, data)

    refresh_records()

    def best_level():
        """Continue from PLAYER 1's own best level."""
        return max(1, int(records.get(names[0], {}).get("best_level", 1)))

    def p2_display_name():
        return "AI" if modes["missile"] == "AUTO" else names[1]

    def finish_name_edit(text=None):
        who = name_edit["who"]
        if who is None:
            return
        old = names[who]
        typed = name_edit["buf"] if text is None else text
        names[who] = clean_name(typed, old)          # nothing typed: keep the old name
        if names[0] == names[1]:                    # two players can't share a name
            names[who] = (names[who][:MAX_NAME_LEN - 2] + " " + str(who + 1)).strip()
        save_player_names(names, old_p1=old if who == 0 else None)
        name_edit["who"], name_edit["buf"] = None, ""
        refresh_records()

    def start_name_edit(who):
        if sys.platform == "emscripten":            # phones / browser: the page's own text box (brings up the keyboard)
            try:
                import platform
                answer = platform.window.prompt(f"Player {who + 1} name:", names[who])
                if answer is not None:
                    name_edit["who"] = who
                    finish_name_edit(str(answer))
                return
            except Exception:
                pass
        name_edit["who"], name_edit["buf"] = who, ""   # starts empty: type the new name

    def input_kind():
        """How the player is playing right now, for hint wording."""
        if touch["on"]:
            return "touch"
        return "pad" if joysticks else "keys"

    def post_key(k):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))

    def touch_aim_target(cx, cy):
        """FIRE on a phone aims at the nearest flying missile, else the nearest launcher."""
        head = math.atan2(p1_vy, p1_vx)

        def ahead(x, y):     # inside the guns' forward cone
            d = (math.atan2(y - cy, x - cx) - head + math.pi) % (2 * math.pi) - math.pi
            return abs(d) <= FIRE_CONE
        if game_state == "CAMPAIGN":
            flying = [e for e in campaign_enemies if not e.is_burrowed and ahead(e.x + e.width / 2, e.y + e.height / 2)]
            if flying:
                e = min(flying, key=lambda e: math.hypot(e.x + e.width / 2 - cx, e.y + e.height / 2 - cy))
                return e.x + e.width / 2, e.y + e.height / 2
            alive = [ln for ln in launchers if ln["alive"] and ahead(ln["x"], GROUND_Y - 14)]
            if alive:
                ln = min(alive, key=lambda ln: abs(ln["x"] - cx))
                return ln["x"], GROUND_Y - 14
        elif game_state == "DUEL":   # its missiles first, else the launcher on the ground
            flying = [e for e in duel["missiles"] if ahead(e.x + e.width / 2, e.y + e.height / 2)]
            if flying:
                e = min(flying, key=lambda e: math.hypot(e.x + e.width / 2 - cx, e.y + e.height / 2 - cy))
                return e.x + e.width / 2, e.y + e.height / 2
            if p2_hp > 0 and ahead(p2_x, GROUND_Y - 14):
                return p2_x, GROUND_Y - 14
        return None

    def finger_down(tx, ty, fid):
        touch["on"] = True
        if name_edit["who"] is not None:      # a tap while typing a name = done
            finish_name_edit()
            return
        if game_state == "MODE_SELECT":
            if NAME_BTN1.inflate(0, 12).collidepoint(tx, ty):
                start_name_edit(0)
            elif NAME_BTN2.inflate(0, 12).collidepoint(tx, ty):
                start_name_edit(1)
            elif MODE_JET_BTN.inflate(0, 16).collidepoint(tx, ty):
                post_key(pygame.K_j)
            elif MODE_MSL_BTN.inflate(0, 16).collidepoint(tx, ty):
                post_key(pygame.K_k)
            elif MODE_DIFF_BTN.inflate(0, 16).collidepoint(tx, ty):
                post_key(pygame.K_h)
            elif CONTINUE_BTN.inflate(0, 10).collidepoint(tx, ty) and best_level() > 1:
                post_key(pygame.K_3)
            elif CARD1.collidepoint(tx, ty):
                post_key(pygame.K_1)
            elif CARD2.collidepoint(tx, ty):
                post_key(pygame.K_2)
            return
        if game_state not in ("CAMPAIGN", "DUEL"):
            return
        if pause["on"] or TOUCH_PAUSE.inflate(16, 20).collidepoint(tx, ty):   # PAUSE button / tap to resume
            post_key(pygame.K_RETURN)
            return
        if game_state == "CAMPAIGN":
            if TOUCH_MENU.inflate(16, 20).collidepoint(tx, ty):
                post_key(pygame.K_ESCAPE)
                return
            if ty >= LEVEL_BAR_TOP:
                for lvl, r in level_bar_slots():
                    if r.inflate(2, 14).collidepoint(tx, ty):
                        jump_to_level(lvl)
                        return
                if tx < 120:
                    post_key(pygame.K_p)
                elif tx > SCREEN_WIDTH - 120:
                    post_key(pygame.K_n)
                return
        for label, key, c, r in visible_touch_buttons():
            if math.hypot(tx - c[0], ty - c[1]) < r * 1.3:
                if key is None:
                    touch["shield_ids"].add(fid)
                else:
                    post_key(key)
                return
        if tx < SCREEN_WIDTH / 2:
            touch["stick_id"] = fid
            touch["origin"] = (tx, ty)
            touch["vec"] = (0.0, 0.0)
        else:
            touch["fire_ids"].add(fid)        # FIRE button, or anywhere else on the right half

    def finger_motion(tx, ty, fid):
        if fid == touch["stick_id"]:
            ox, oy = touch["origin"]
            vx, vy = (tx - ox) / STICK_R, (ty - oy) / STICK_R
            m = math.hypot(vx, vy)
            if m < 0.2:
                vx = vy = 0.0
            elif m > 1.0:
                vx, vy = vx / m, vy / m
            touch["vec"] = (vx, vy)

    def finger_up(fid):
        touch["fire_ids"].discard(fid)
        touch["shield_ids"].discard(fid)
        if fid == touch["stick_id"]:
            touch["stick_id"] = None
            touch["vec"] = (0.0, 0.0)

    touch_cache = {"key": None, "layer": None}

    def draw_touch_controls():
        """Phone controls. The whole layer (circles + labels) is cached and only redrawn when something on it
        changes (stick moved, a button became ready / held), which saves a full-screen redraw every frame."""
        base = touch["origin"] if touch["stick_id"] is not None else (120, 470)
        knob = (base[0] + touch["vec"][0] * STICK_R, base[1] + touch["vec"][1] * STICK_R)
        firing = bool(touch["fire_ids"])
        states = []
        for label, key, c, r in visible_touch_buttons():
            ready = True
            if label == "STEALTH":
                ready = p1_stealth_cd == 0
            elif label == "CAMO":
                ready = p1_camo_cd == 0
            elif label == "HEAL":
                ready = p1_med_kits > 0
            elif label == "FLARES":
                ready = p1_decoys > 0
            elif label == "SQUAD":
                ready = p1_split_charges > 0 and p1_split_timer == 0
            elif label == "WPN":
                ready = len(p1_ammo) > 1
            elif label == "MSL":
                sel = selected_munition()
                ready = bool(sel) and p1_ammo.get(sel["id"], 0) > 0 and ord_sel["cd"] == 0
            elif label == "FLIR":
                ready = flir["on"] or flir["energy"] > 10
            elif label == "SAFE":
                ready = safeguard["cd"] == 0
            held = (label == "SHIELD" and bool(touch["shield_ids"])) or (label == "FLIR" and flir["on"]) or \
                   (label == "SAFE" and safeguard["t"] > 0)
            states.append((label, c, r, ready, held))
        key = ((int(base[0]), int(base[1])), (int(knob[0]), int(knob[1])), firing, tuple(states), game_state)
        if key != touch_cache["key"]:
            ui = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pygame.draw.circle(ui, (0, 229, 212, 45), base, STICK_R)
            pygame.draw.circle(ui, (0, 229, 212, 170), base, STICK_R, 3)
            pygame.draw.circle(ui, (0, 229, 212, 190), (int(knob[0]), int(knob[1])), 26)
            pygame.draw.circle(ui, (255, 70, 70, 235) if firing else (225, 40, 55, 190), FIRE_C, FIRE_R)
            pygame.draw.circle(ui, (255, 255, 255, 230), FIRE_C, FIRE_R, 4)
            for label, c, r, ready, held in states:
                col = (0, 200, 255, 235) if held else ((40, 120, 200, 200) if ready else (60, 65, 80, 160))
                pygame.draw.circle(ui, col, c, r)
                pygame.draw.circle(ui, (230, 240, 255, 220), c, r, 2)
            t = touch_big.render("FIRE", True, (255, 255, 255))
            ui.blit(t, t.get_rect(center=FIRE_C))
            for label, c, r, ready, held in states:
                t = touch_font.render(label, True, (255, 255, 255))
                ui.blit(t, t.get_rect(center=c))
            mv = touch_font.render("FLY", True, (180, 255, 245))
            ui.blit(mv, mv.get_rect(center=(base[0], base[1] + STICK_R + 12)))
            buttons = [(TOUCH_PAUSE, "PAUSE")] + ([(TOUCH_MENU, "MENU")] if game_state == "CAMPAIGN" else [])
            for rect, text in buttons:
                pygame.draw.rect(ui, (30, 40, 60, 230), rect, border_radius=6)
                pygame.draw.rect(ui, (150, 170, 210, 255), rect, 1, border_radius=6)
                t = touch_font.render(text, True, (220, 230, 255))
                ui.blit(t, t.get_rect(center=rect.center))
            touch_cache["key"], touch_cache["layer"] = key, ui
        screen.blit(touch_cache["layer"], (0, 0))

    def draw_portrait_hint():
        if MOBILE and _portrait:
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 200))
            screen.blit(shade, (0, 0))
            t = big_font.render("TURN YOUR PHONE SIDEWAYS", True, (255, 230, 120))
            screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

    running = True
    while running:
        if pygame.time.get_ticks() - last_fit_ms > 500:
            last_fit_ms = pygame.time.get_ticks()
            fit_canvas_to_browser()
        mouse_pos = pygame.mouse.get_pos()
        ps_pad_p1 = joysticks[0] if len(joysticks) > 0 else None
        ps_pad_p2 = joysticks[1] if len(joysticks) > 1 else None

        for event in pygame.event.get():
            # Touch screens also send fake mouse events for every finger; fingers are handled below
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION) and getattr(event, "touch", False):
                continue
            # Phones whose browser reports taps only as mouse clicks: treat the mouse as a finger
            if (MOBILE and not touch["finger_seen"] and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                    and getattr(event, "button", 1) == 1):
                if event.type == pygame.MOUSEMOTION and not event.buttons[0]:
                    continue
                ftype = {pygame.MOUSEBUTTONDOWN: pygame.FINGERDOWN, pygame.MOUSEBUTTONUP: pygame.FINGERUP,
                         pygame.MOUSEMOTION: pygame.FINGERMOTION}[event.type]
                event = pygame.event.Event(ftype, x=event.pos[0] / SCREEN_WIDTH, y=event.pos[1] / SCREEN_HEIGHT,
                                           finger_id=-1, from_mouse=True)
            if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION) and not getattr(event, "from_mouse", False):
                touch["finger_seen"] = True
            if event.type == pygame.FINGERDOWN:
                finger_down(event.x * SCREEN_WIDTH, event.y * SCREEN_HEIGHT, event.finger_id)
                continue
            if event.type == pygame.FINGERMOTION:
                finger_motion(event.x * SCREEN_WIDTH, event.y * SCREEN_HEIGHT, event.finger_id)
                continue
            if event.type == pygame.FINGERUP:
                finger_up(event.finger_id)
                continue

            # NAME TYPING (start screen): letters go into the name box, Enter / Tab = done, Esc = cancel, a click = done.
            # Nothing else reacts to the keys meanwhile (typing "J" must not switch the jet mode).
            if name_edit["who"] is not None:
                if event.type == pygame.TEXTINPUT:
                    name_edit["buf"] = (name_edit["buf"] + event.text)[:MAX_NAME_LEN]
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                        finish_name_edit()
                        pygame.key.stop_text_input()
                    elif event.key == pygame.K_ESCAPE:
                        name_edit["who"], name_edit["buf"] = None, ""
                        pygame.key.stop_text_input()
                    elif event.key == pygame.K_BACKSPACE:
                        name_edit["buf"] = name_edit["buf"][:-1]
                elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                    finish_name_edit()
                    pygame.key.stop_text_input()
                if event.type != pygame.QUIT:
                    continue
            if game_state == "MODE_SELECT" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 \
                    and not getattr(event, "touch", False):
                for who, rect in enumerate((NAME_BTN1, NAME_BTN2)):
                    if rect.collidepoint(event.pos):
                        start_name_edit(who)
                        if name_edit["who"] is not None:
                            pygame.key.start_text_input()
                if name_edit["who"] is not None:
                    continue

            # PAUSE (Enter / Pause key, touch PAUSE, controller: hold button 7 + d-pad down): everything freezes.
            # While paused only resume (the same keys, a tap, any controller button), Esc (menu) and closing work.
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_PAUSE) and \
                    game_state in ("CAMPAIGN", "DUEL"):
                pause["on"], pause["drawn"] = not pause["on"], False
                continue
            if pause["on"]:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    pause["on"] = False                 # goes on to the Esc handler below: back to the menu
                elif event.type == pygame.JOYBUTTONDOWN:
                    pause["on"] = False
                    pad_ord["down"] = False
                    continue
                elif event.type != pygame.QUIT:
                    continue

            # Mouse: clicking a mode card on the start screen picks that mode
            if game_state == "MODE_SELECT" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if MODE_JET_BTN.collidepoint(event.pos):
                    post_key(pygame.K_j)
                elif MODE_MSL_BTN.collidepoint(event.pos):
                    post_key(pygame.K_k)
                elif MODE_DIFF_BTN.collidepoint(event.pos):
                    post_key(pygame.K_h)
                elif CONTINUE_BTN.collidepoint(event.pos) and best_level() > 1:
                    post_key(pygame.K_3)
                elif CARD1.collidepoint(event.pos):
                    post_key(pygame.K_1)
                elif CARD2.collidepoint(event.pos):
                    post_key(pygame.K_2)

            # CONTROL MODES: J = jet MANUAL/AUTO, K = missile MANUAL/AUTO (start screen or in play);
            # on the start screen a controller's Square (2) / Triangle (3) do the same
            if event.type == pygame.KEYDOWN and event.key == pygame.K_j:
                toggle_control("jet")
            if event.type == pygame.KEYDOWN and event.key == pygame.K_k:
                toggle_control("missile")
            if event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                toggle_control("difficulty")
            if game_state == "MODE_SELECT" and event.type == pygame.JOYBUTTONDOWN and event.joy == 0:
                if event.button == 2:
                    toggle_control("jet")
                elif event.button == 3:
                    toggle_control("missile")
                elif event.button == 4:          # L1: AI difficulty
                    toggle_control("difficulty")
                elif event.button == 5 and best_level() > 1:   # R1: continue from the best level
                    post_key(pygame.K_3)
            # CONTINUE ('3' on the start screen): the campaign starts at the best level reached
            if game_state == "MODE_SELECT" and event.type == pygame.KEYDOWN and event.key in (pygame.K_3, pygame.K_KP3) \
                    and best_level() > 1:
                jump_to_level(best_level())
                post_key(pygame.K_1)

            # Game controller (player 1): using it hides the touch buttons. D-pad left/right = previous/next
            # level, up = stealth, down = camouflage. Desktop reports the d-pad as a hat, browsers as buttons 12-15.
            if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYHATMOTION, pygame.JOYAXISMOTION) and getattr(event, "joy", 0) == 0:
                if event.type != pygame.JOYAXISMOTION or abs(event.value) > 0.5:
                    touch["on"] = False
            # Controller ORDNANCE button (PAD_ORD_BUTTON: R2 in browsers, Start on desktop pads), 1P campaign:
            # tap = launch the selected munition; hold it + d-pad left/right = previous/next munition,
            # hold it + d-pad up = FLIR pod on/off. Without it held the d-pad works as before.
            if event.type == pygame.JOYBUTTONDOWN and event.joy == 0 and event.button == PAD_ORD_BUTTON:
                pad_ord["down"], pad_ord["used"] = True, False
            elif event.type == pygame.JOYBUTTONDOWN and event.joy == 0 and event.button == 0 and pad_ord["down"]:
                pad_ord["used"] = True                 # hold 7 + Cross/A = SAFEGUARD
                post_key(pygame.K_b)
            elif event.type == pygame.JOYBUTTONUP and event.joy == 0 and event.button == PAD_ORD_BUTTON:
                if pad_ord["down"] and not pad_ord["used"]:
                    post_key(pygame.K_r)
                pad_ord["down"] = False
            if game_state in ("CAMPAIGN", "DUEL"):
                dpad = None
                if event.type == pygame.JOYHATMOTION and event.joy == 0:
                    hx, hy = event.value
                    dpad = {(-1, 0): "left", (1, 0): "right", (0, 1): "up", (0, -1): "down"}.get((hx, hy))
                elif event.type == pygame.JOYBUTTONDOWN and event.joy == 0 and sys.platform == "emscripten":
                    dpad = {12: "up", 13: "down", 14: "left", 15: "right"}.get(event.button)
                if dpad and pad_ord["down"] and game_state == "CAMPAIGN":
                    pad_ord["used"] = True                 # a d-pad combo, not a launch tap
                    if dpad in ("left", "right"):
                        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, mod=0, unicode="",
                                                             scancode=0, pad_prev=(dpad == "left")))
                    elif dpad == "up":
                        post_key(pygame.K_x)
                    elif dpad == "down":
                        post_key(pygame.K_RETURN)      # pause
                    dpad = None
                if dpad == "up":
                    post_key(pygame.K_v)
                elif dpad == "down":
                    post_key(pygame.K_c)
                elif dpad == "left" and game_state == "CAMPAIGN":
                    post_key(pygame.K_p)
                elif dpad == "right" and game_state == "CAMPAIGN":
                    post_key(pygame.K_n)

            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.JOYDEVICEADDED:
                joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]

            # Mode Selection
            if game_state == "MODE_SELECT":
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_1, pygame.K_KP1)) or \
                   (event.type == pygame.JOYBUTTONDOWN and event.button == 0):
                    game_state = "CAMPAIGN"
                    p1_max_hp = round((300 + min(300, (current_level - 1) * 3)) * pbuff())
                    p1_hp = p1_max_hp
                    p1_med_kits = round(6 * pbuff())
                    p1_decoys = round(6 * pbuff())
                    p1_split_charges = round(3 * pbuff())
                    p1_power_tier = 1
                    p1_power_charge = 0.0
                    SFX.snd_win.play()

                elif (event.type == pygame.KEYDOWN and event.key in (pygame.K_2, pygame.K_KP2)) or \
                     (event.type == pygame.JOYBUTTONDOWN and event.button == 1):
                    game_state = "DUEL"
                    p1_max_hp = round(120 * pbuff())    # 138 vs the AI missile, 120 vs a human
                    p1_hp = p1_max_hp
                    p1_med_kits = round(2 * pbuff())
                    p1_decoys = round(3 * pbuff())
                    p1_split_charges = round(2 * pbuff())
                    p1_power_tier = 1
                    p1_power_charge = 0.0
                    p2_hp = p2_max_hp                   # the armoured duel launcher
                    duel["missiles"].clear()
                    drones.clear()
                    autogun["rounds"].clear()
                    p2_x = SCREEN_WIDTH - 150.0
                    p2_decoys = 3
                    p2_power_tier = 1
                    p2_power_charge = 0.0
                    SFX.snd_win.play()

            # P1 Heal
            if game_state in ("CAMPAIGN", "DUEL") and p1_med_kits > 0 and p1_hp < p1_max_hp:
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_m)) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button in (1, 2, 3)):
                    heal_amt = round((60 if game_state == "CAMPAIGN" else 35) * pbuff())
                    p1_hp = min(p1_max_hp, p1_hp + heal_amt)
                    p1_med_kits -= 1
                    SFX.snd_heal.play()
                    floating_texts.append([f"+{heal_amt} HP", p1_x + 10, p1_y - 20, (100, 255, 120), 35])

            # P1 FLARES ('F' / Triangle): 10 burning flares thrown out behind the jet. Every missile chases
            # the flare nearest to it instead of the jet, and blows up harmlessly when it reaches it.
            if game_state in ("CAMPAIGN", "DUEL") and p1_decoys > 0 and p1_hp > 0:
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_f) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button == 3):
                    p1_decoys -= 1
                    back = math.atan2(p1_vy, p1_vx) + math.pi
                    n_fl = round(FLARE_COUNT * pbuff())     # 12 vs the AI
                    for i in range(n_fl):
                        a = back + (i / (n_fl - 1) - 0.5) * 2.6 + random.uniform(-0.12, 0.12)  # fan behind the jet
                        sp = random.uniform(2.0, 4.2)
                        active_decoys.append({"x": p1_x + 50, "y": p1_y + 40, "vx": math.cos(a) * sp,
                                              "vy": math.sin(a) * sp, "life": FLARE_LIFE, "type": "flare"})
                    SFX.snd_decoy.play()
                    floating_texts.append([f"{n_fl} FLARES!", p1_x + 10, p1_y - 30, (255, 200, 80), 40])

            # P1 TRIPLE JET SQUAD: SPLIT INTO 3 JETS (Key 'T' or Controller R3/Touchpad)
            if game_state in ("CAMPAIGN", "DUEL") and p1_split_charges > 0 and p1_split_timer == 0:
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_t) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button in (8, 10, 11)):
                    p1_split_charges -= 1
                    p1_split_timer = round(480 * pbuff())  # 8 full seconds of 3 combat jets (+15% vs the AI)
                    SFX.snd_split.play()
                    floating_texts.append(["TRIPLE JET SQUAD!", p1_x - 40, p1_y - 35, (255, 215, 60), 50])

            # P1 STEALTH (Key 'V'): 2 s invisible to missiles and launchers
            if game_state in ("CAMPAIGN", "DUEL") and p1_stealth_cd == 0 and p1_hp > 0:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_v:
                    p1_stealth_timer = round(STEALTH_DURATION * pbuff())
                    p1_stealth_cd = round(STEALTH_COOLDOWN / pbuff())
                    p1_stealth_x, p1_stealth_y = p1_x + 50, p1_y + 40
                    SFX.snd_decoy.play()

            # P1 SAFEGUARD (Key 'B', touch SAFE, controller hold 7 + Cross): 3 s, everything flying at the jet goes down
            if game_state in ("CAMPAIGN", "DUEL") and safeguard["cd"] == 0 and p1_hp > 0:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                    safeguard["t"], safeguard["cd"] = SAFEGUARD_FRAMES, SAFEGUARD_COOLDOWN
                    SFX.snd_shield.play()
                    floating_texts.append(["SAFEGUARD!", p1_x, p1_y - 30, (120, 220, 255), 40])

            # P1 CAMOUFLAGE (Key 'C' or Controller Share): fade out, missiles head for the last seen spot
            if game_state in ("CAMPAIGN", "DUEL") and p1_camo_cd == 0 and p1_hp > 0:
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_c) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button == 6):
                    p1_camo_timer = round(CAMO_DURATION * pbuff())
                    p1_camo_cd = round(CAMO_COOLDOWN / pbuff())
                    p1_camo_x, p1_camo_y = p1_x + 50, p1_y + 40
                    SFX.snd_decoy.play()
            # P2 LAUNCHER (duel, player 2 / MANUAL): UP (or keypad 8) fires a missile, DOWN (keypad 2 / 5) sends a drone;
            # a second game controller: button 0 missile, button 1 drone. Left / right drive it (in the duel loop).
            if game_state == "DUEL" and modes["missile"] == "MANUAL" and p2_hp > 0:
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_KP8)) or \
                   (event.type == pygame.JOYBUTTONDOWN and event.joy == 1 and event.button == 0):
                    duel["want_missile"] = True
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_DOWN, pygame.K_KP2, pygame.K_KP5)) or \
                   (event.type == pygame.JOYBUTTONDOWN and event.joy == 1 and event.button == 1):
                    duel["want_drone"] = True

            # ORDNANCE (1P, level 5+): G = next munition, R / right click = launch it.
            # FLIR POD (1P, level 10+): X = active scan on/off (drains its energy).
            if game_state == "CAMPAIGN" and p1_hp > 0:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_g and p1_ammo:
                    ord_sel["i"] = (ord_sel["i"] + (-1 if getattr(event, "pad_prev", False) else 1)) % len(p1_ammo)
                    sel = selected_munition()
                    msg = f"{munition_label(sel)} x{p1_ammo.get(sel['id'], 0)}"
                    floating_texts.append([msg, max(10, min(SCREEN_WIDTH - 10 - len(msg) * 8, p1_x)), p1_y - 25, tuple(sel["trail"]), 35])
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_r) or \
                   (event.type == pygame.MOUSEBUTTONDOWN and event.button == 3):
                    ord_sel["fire"] = True
                if event.type == pygame.KEYDOWN and event.key == pygame.K_x and current_level >= IR_UNLOCK_LEVEL:
                    if flir["on"]:
                        flir["on"] = False
                    elif flir["energy"] > 10:
                        flir["on"] = True

            # QUICK LASER TOGGLE KEY ('L' Key toggles directly to Laser Ray Tiers 3, 4, 5)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_l and game_state in ("CAMPAIGN", "DUEL"):
                if p1_power_tier < 3:
                    p1_power_tier = 3
                elif p1_power_tier == 3:
                    p1_power_tier = 4
                elif p1_power_tier == 4:
                    p1_power_tier = 5
                else:
                    p1_power_tier = 1
                if game_state == "DUEL":
                    p2_power_tier = p1_power_tier
                SFX.snd_win.play()
                floating_texts.append([f"LASER MODE: {WEAPON_TIERS[p1_power_tier]['name']}!", SCREEN_WIDTH // 2 - 140, 210, WEAPON_TIERS[p1_power_tier]["color_outer"], 50])

            # Level testing cheat: Press 'N' to skip wave
            # Level strip: N = next level, P = previous level, or click a level number
            if event.type == pygame.KEYDOWN and event.key == pygame.K_n and game_state == "CAMPAIGN":
                jump_to_level(current_level + 1)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_p and game_state == "CAMPAIGN":
                jump_to_level(current_level - 1)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and game_state == "CAMPAIGN":
                for lvl, r in level_bar_slots():
                    if r.collidepoint(event.pos):
                        jump_to_level(lvl)
                        break

            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                set_fullscreen(not fullscreen["on"])
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                game_state = "MODE_SELECT"         # Esc never leaves full screen (user: "start it in full screen always")
                saved_data.update(load_save_data())

        if game_state == "CAMPAIGN":   # unlock messages from the last wave set-up
            for k, (txt, col) in enumerate(notices):
                floating_texts.append([txt, max(10, SCREEN_WIDTH // 2 - len(txt) * 4), 250 + k * 22, col, 150])
            notices.clear()
            if hint["frames"] == 0:    # first-time hint for a newly unlocked feature (once ever)
                due = hints_due(current_level, saved_data.get("hints_seen", []))
                if due:
                    hid = due[0][0]
                    hint["text"], hint["frames"] = due[0][2][input_kind()], HINT_FRAMES
                    mark_hint_seen(hid)
                    saved_data.setdefault("hints_seen", []).append(hid)

        # PAUSED: the last frame stays on screen under a shade; nothing moves
        if pause["on"] and game_state in ("CAMPAIGN", "DUEL"):
            if not pause["drawn"]:
                shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 150))
                screen.blit(shade, (0, 0))
                t = title_font.render("PAUSED", True, (255, 230, 120))
                screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20)))
                how = {"touch": "TAP TO RESUME", "pad": "PRESS ANY BUTTON TO RESUME"}.get(input_kind(), "ENTER TO RESUME  |  ESC = MENU")
                t = font.render(how, True, (220, 225, 240))
                screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20)))
                pause["drawn"] = True
            pygame.display.flip()
            clock.tick(30)
            await asyncio.sleep(0)
            continue
        if game_state == "MODE_SELECT":
            pause["on"] = False

        draw_world()

        # ======================================================================
        # STATE 1: MODE SELECT SCREEN
        # ======================================================================
        if game_state == "MODE_SELECT":
            t_surf = title_font.render("JET vs MISSILE", True, (255, 140, 0))
            screen.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 45))

            # PLAYER NAMES: click / tap a box to type a name (Enter = done); each name keeps its own record
            for who, rect in enumerate((NAME_BTN1, NAME_BTN2)):
                editing = name_edit["who"] == who
                hov = rect.collidepoint(mouse_pos) and not touch["on"]
                pygame.draw.rect(screen, (40, 52, 80) if (hov or editing) else (24, 30, 48), rect, border_radius=6)
                pygame.draw.rect(screen, (255, 230, 120) if editing else (0, 220, 255), rect, 2 if editing else 1, border_radius=6)
                shown = name_edit["buf"] + ("_" if (pygame.time.get_ticks() // 400) % 2 else " ") if editing else names[who]
                hint_txt = "  (ENTER = done)" if editing else ("" if touch["on"] else "  [click to edit]")
                t = font.render(f"PLAYER {who + 1}: {shown}{hint_txt}", True, (255, 230, 120) if editing else (0, 220, 255))
                screen.blit(t, t.get_rect(center=rect.center))

            r1 = records.get(names[0], {"best_level": 1, "high_score": 0, "wins": 0})
            r2 = records.get(names[1], {"wins": 0})
            lb_txt = (f"{names[0]}: BEST LEVEL {r1['best_level']} | HIGH SCORE {r1['high_score']} | DUEL WINS {r1['wins']}"
                      f"     {names[1]}: DUEL WINS {r2['wins']}")
            t = font.render(lb_txt, True, (255, 215, 60))
            screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, 128)))

            card1 = CARD1
            pygame.draw.rect(screen, (18, 22, 38), card1, border_radius=12)
            pygame.draw.rect(screen, (255, 140, 0), card1, 2, border_radius=12)

            screen.blit(big_font.render("1P CAMPAIGN", True, (255, 180, 80)), (75 + XC, 168))
            lines1 = [
                "Jet vs AI missiles, drones & silos",
                "[YOU: 3X POWER, +15% vs AI]:",
                "- 345+ HP, med-kits, 12 flares (F)",
                "- Nation weapons every 5 levels (G/R)",
                "- Drones + auto-gun, silos + FLIR (X)",
                "- 'T' squad, 'L' lasers, 'V' stealth",
                "- Levels 1-100, then endless overdrive",
                "",
                ">> PRESS '1' OR CROSS (X) <<",
            ]
            y_c1 = 202
            for ln in lines1:
                col = (100, 255, 150) if ">>" in ln else ((255, 220, 100) if "3X" in ln else (210, 220, 235))
                screen.blit(font.render(ln, True, col), (70 + XC, y_c1))
                y_c1 += 22
            if best_level() > 1:   # continue the campaign from the best level reached
                hov = CONTINUE_BTN.collidepoint(mouse_pos) and not touch["on"]
                pygame.draw.rect(screen, (60, 46, 20) if hov else (40, 32, 16), CONTINUE_BTN, border_radius=6)
                pygame.draw.rect(screen, (255, 180, 80), CONTINUE_BTN, 1, border_radius=6)
                key3 = {"touch": "", "pad": "  [R1]"}.get(input_kind(), "  [3]")
                t = font.render(f"CONTINUE FROM LEVEL {best_level()}{key3}", True, (255, 200, 110))
                screen.blit(t, t.get_rect(center=CONTINUE_BTN.center))

            card2 = CARD2
            pygame.draw.rect(screen, (18, 22, 38), card2, border_radius=12)
            pygame.draw.rect(screen, (0, 210, 255), card2, 2, border_radius=12)

            duel_vs_ai = modes["missile"] == "AUTO"     # always on phones
            screen.blit(big_font.render("JET vs AI LAUNCHER" if duel_vs_ai else "JET vs LAUNCHER", True, (0, 220, 255)), (435 + XC, 168))
            lines2 = [
                "You fly the jet vs an AI launcher" if duel_vs_ai else "P1 flies the jet, P2 drives",
                "[YOU GET +15% IN EVERYTHING]:" if duel_vs_ai else "[EQUAL BALANCED COMBAT]:",
                "- Jet " + ("138" if duel_vs_ai else "120") + " HP; launcher: 12 hits",
                "- Missiles & drones come only from it",
                "- The launcher drives along the ground",
                "- P2: arrows drive, UP missile, DOWN drone",
                "- Jet: flares F, stealth V, camo C, squad T",
                "- Wreck the armoured launcher to win",
                "",
                ">> PRESS '2' OR CIRCLE (O) <<",
            ]
            y_c2 = 202
            for ln in lines2:
                col = (100, 255, 150) if ">>" in ln else ((0, 240, 255) if "EQUAL" in ln or "+15%" in ln else (210, 220, 235))
                screen.blit(font.render(ln, True, col), (425 + XC, y_c2))
                y_c2 += 22

            # three simple switches (click / tap, keys J / K / H, controller Square / Triangle / L1)
            kind = input_kind()
            keyname = {"keys": ("J", "K", "H"), "pad": ("SQUARE", "TRIANGLE", "L1"), "touch": ("", "", "")}[kind]
            for rect, label, mode, keyhint, good in (
                    (MODE_JET_BTN, "JET", modes["jet"], keyname[0], "AUTO"),
                    (MODE_MSL_BTN, "DUEL LAUNCHER", modes["missile"], "PHONE" if MOBILE else keyname[1], "AUTO"),
                    (MODE_DIFF_BTN, "AI", modes["difficulty"], keyname[2], "EASY")):
                on = mode == good
                hover = rect.collidepoint(mouse_pos) and not touch["on"]
                pygame.draw.rect(screen, (40, 52, 80) if hover else (24, 30, 48), rect, border_radius=6)
                pygame.draw.rect(screen, (100, 255, 150) if on else (255, 180, 80), rect, 1, border_radius=6)
                t = font.render(f"{label}: {mode}" + (f" [{keyhint}]" if keyhint else ""), True,
                                (100, 255, 150) if on else (255, 180, 80))
                screen.blit(t, t.get_rect(center=rect.center))
            # what the switches mean right now, in plain words
            meaning = "  |  ".join((
                ("autopilot flies, you fire" if MOBILE else "autopilot + auto-aim help you") if modes["jet"] == "AUTO"
                else "you fly & shoot yourself",
                "AI drives the launcher" if modes["missile"] == "AUTO" else "a friend drives the launcher",
                "slower, simpler AI" if modes["difficulty"] == "EASY" else "full-strength AI"))
            t = font.render(meaning, True, (200, 210, 230))
            screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, 516)))

            pad_msg = "Game Controller Connected" if ps_pad_p1 else ("Touch Screen" if touch["on"] else "Keyboard Connected")
            fs_tip = " | F11 = window | Alt+F4 = close" if desktop_fs else ""
            t = font.render(f"Controller: {pad_msg} | Esc = menu{fs_tip}", True, (140, 150, 170))
            screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, 536)))
            if touch["on"]:
                tap_hint = big_font.render("TAP A CARD TO PLAY", True, (100, 255, 150))
                screen.blit(tap_hint, tap_hint.get_rect(center=(SCREEN_WIDTH // 2, 566)))
            draw_portrait_hint()

            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(0)
            continue

        # ======================================================================
        # STATE 1B: JET CRASH (shot down -> burning fall -> fireball on the ground)
        # ======================================================================
        if game_state == "JET_CRASH":
            draw_blasts()   # the blast that brought the jet down keeps burning while it falls
            if crash["origin"] == "CAMPAIGN":
                draw_launchers(crash["level_boss"])
                draw_silos()
                draw_drone_launchers()
                draw_drones()
                for e in campaign_enemies:
                    e.draw(screen)
            if crash["phase"] == "fall":
                crash["vy"] += 0.22
                crash["x"] += crash["vx"]
                crash["y"] += crash["vy"]
                crash["rot"] += 7
                for _ in range(3):   # flames and smoke pouring off the falling jet
                    crash["fire"].append([crash["x"] + random.uniform(-14, 14), crash["y"] + random.uniform(-10, 10),
                                          random.uniform(-0.8, 0.8), random.uniform(-2.2, -0.6), random.randint(18, 34)])
                if crash["y"] >= GROUND_Y - 22:
                    crash["y"] = GROUND_Y - 22
                    crash["phase"] = "boom"
                    SFX.snd_explode.play()
            for fp in crash["fire"][:]:
                fp[0] += fp[2]
                fp[1] += fp[3]
                fp[4] -= 1
                if fp[4] <= 0:
                    crash["fire"].remove(fp)
                    continue
                col = (255, 230, 120) if fp[4] > 26 else ((255, 140, 20) if fp[4] > 16 else (90, 90, 95))
                pygame.draw.circle(screen, col, (int(fp[0]), int(fp[1])), max(2, (40 - fp[4]) // 4))
            if crash["phase"] == "fall":
                wf = jet_size_factor(crash["y"])
                wreck = pygame.transform.scale(create_jet_sprite(False, (255, 90, 0)), (int(144 * wf), int(120 * wf)))
                wreck = pygame.transform.rotate(wreck, crash["rot"])
                screen.blit(wreck, wreck.get_rect(center=(crash["x"], crash["y"])))
            else:
                crash["boom"] += 1
                b = crash["boom"]
                cx, cy = int(crash["x"]), int(crash["y"])
                r = min(120, 12 + b * 3)
                pygame.draw.circle(screen, (200, 40, 0), (cx, cy - r // 3), r)           # fireball
                pygame.draw.circle(screen, (255, 140, 0), (cx, cy - r // 3), int(r * 0.7))
                pygame.draw.circle(screen, (255, 235, 150), (cx, cy - r // 3), int(r * 0.35))
                for k in range(6):                                                        # burning debris
                    a = k * math.pi / 3 + b * 0.05
                    pygame.draw.circle(screen, (255, 120, 20), (int(cx + math.cos(a) * r * 1.1), int(cy - r // 3 + math.sin(a) * r * 0.6)), 5)
                if b >= 55:
                    handle_round_conclusion("P2", crash["origin"])
            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(0)
            continue

        # ======================================================================
        # STATE 2A: FAST 1-SECOND TACTICAL ROUND INTERLUDE
        # ======================================================================
        if game_state == "NORMAL_ROUND_BREAK":
            break_timer -= 1

            if break_winner == "P1":
                r_msg = f"ROUND WON BY {names[0]} (JET)!"
            elif prev_mode == "DUEL":
                r_msg = f"ROUND WON BY {p2_display_name()} (LAUNCHER)!"
            else:
                r_msg = "ROUND WON BY THE MISSILES!"
            r_col = (255, 180, 80) if break_winner == "P1" else (0, 220, 255)
            t = title_font.render(r_msg, True, r_col)
            screen.blit(t, t.get_rect(center=(SCREEN_WIDTH // 2, 256)))
            screen.blit(font.render("RESTORING POSITIONS...", True, (200, 210, 230)), (SCREEN_WIDTH // 2 - 90, 290))

            if break_timer <= 0:
                if milestone_reward_pending:
                    # every-5th-win bonus
                    milestone_reward_pending = False
                    if prev_mode == "CAMPAIGN":
                        p1_hp = min(p1_max_hp, p1_hp + 10)   # +40 below = +50, as before
                        p1_med_kits = min(round(6 * human_buff("CAMPAIGN")), p1_med_kits + 1)
                        p1_decoys = min(round(6 * human_buff("CAMPAIGN")), p1_decoys + 1)
                    else:
                        p1_med_kits = 2
                        p1_decoys = 3
                        p2_decoys = 3
                if prev_mode == "CAMPAIGN":
                    game_state = "CAMPAIGN"
                    if break_winner == "P1":
                        current_level += 1
                    p1_hp = min(p1_max_hp, p1_hp + 40)
                    campaign_enemies = spawn_campaign_wave(current_level)
                    if break_winner == "P2":
                        p1_hp = p1_max_hp   # the jet was shot down: a fresh jet takes off with full HP
                    # Auto split into 3 jets on Boss Stages (Every 10th level)
                    if current_level % 10 == 0:
                        p1_split_timer = 500
                        SFX.snd_split.play()
                else:
                    game_state = "DUEL"
                    p1_hp = p1_max_hp
                    p2_hp = p2_max_hp
                    duel["missiles"].clear()          # a fresh round: the sky is empty, the launcher reloads
                    drones.clear()
                    autogun["rounds"].clear()
                    duel["missile_cd"], duel["drone_cd"], duel["vx"] = 90, 150, 0.0

                reset_positions()

            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(0)
            continue

        # ground missile launchers
        if game_state == "CAMPAIGN":
            move_launchers(current_level % 10 == 0, campaign_enemies)
            draw_launchers(current_level % 10 == 0)
            draw_silos()
            draw_drone_launchers()

        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed()

        center_p1_x = p1_x + 50
        center_p1_y = p1_y + 40
        p1_laser_active = False

        if p1_split_timer > 0:
            p1_split_timer -= 1
        if p1_camo_timer > 0:
            p1_camo_timer -= 1
        if p1_camo_cd > 0:
            p1_camo_cd -= 1
        if p1_stealth_timer > 0:
            p1_stealth_timer -= 1
        if p1_stealth_cd > 0:
            p1_stealth_cd -= 1
        if safeguard["cd"] > 0:
            safeguard["cd"] -= 1
        if safeguard["t"] > 0:              # SAFEGUARD on: everything flying at the jet is shot down
            safeguard["t"] -= 1
            if p1_hp > 0:
                run_safeguard(center_p1_x, center_p1_y)

        for dec in active_decoys[:]:
            dec["life"] -= 1
            if dec["life"] <= 0:
                active_decoys.remove(dec)
            elif dec["type"] == "flare":          # flares slow down and sink as they burn
                dec["x"] += dec["vx"]
                dec["y"] += dec["vy"]
                dec["vx"] *= 0.97
                dec["vy"] = dec["vy"] * 0.97 + 0.05
                if dec["y"] > GROUND_Y - 6:
                    dec["y"], dec["vy"] = GROUND_Y - 6, 0.0

        # ======================================================================
        # PLAYER 1 CONTROLS
        # ======================================================================
        if p1_hp > 0:
            speed_mult = 1.35 if active_mutator == "HYPER SPEED STORM" else 1.0
            actual_p1_speed = p1_speed * speed_mult * (jet_pace(current_level) if game_state == "CAMPAIGN" else 1.0) * pbuff()

            pad_x = ps_pad_p1.get_axis(0) if ps_pad_p1 and abs(ps_pad_p1.get_axis(0)) > 0.15 else 0.0
            pad_y = ps_pad_p1.get_axis(1) if ps_pad_p1 and abs(ps_pad_p1.get_axis(1)) > 0.15 else 0.0

            in_x = (1 if (keys[pygame.K_d] or pad_x > 0.3) else 0) - (1 if (keys[pygame.K_a] or pad_x < -0.3) else 0)
            in_y = (1 if (keys[pygame.K_s] or pad_y > 0.3) else 0) - (1 if (keys[pygame.K_w] or pad_y < -0.3) else 0)
            if touch["stick_id"] is not None and math.hypot(*touch["vec"]) > 0.2:
                in_x, in_y = touch["vec"]          # thumb stick: fly where the thumb points
            old_head = math.atan2(p1_vy, p1_vx)
            if sky_esc["ret"]:
                pass   # coming back down from a sky escape: the return manoeuvre below has the controls
            elif in_x or in_y:
                # steered: the nose turns toward where the keys / stick point at a limited rate and the jet keeps
                # its speed (never stalls), so it flies arcs and half loops -- aerobatic, not a skidding stop
                spd = math.hypot(p1_vx, p1_vy)
                spd = max(actual_p1_speed * 0.55, spd + (actual_p1_speed - spd) * 0.08)
                head = aerobatic_heading(old_head, math.atan2(in_y, in_x), p1_y + 40)
                p1_vx, p1_vy = math.cos(head) * spd, math.sin(head) * spd
                autopilot["head"] = head
                autopilot["mode"], autopilot["t"], autopilot["roll"] = "cruise", 60, 0.0
            elif modes["jet"] == "MANUAL":
                pass   # JET MANUAL: no autopilot; hands off, the jet holds its course and speed
            else:
                # hands off: the autopilot keeps the jet flying and manoeuvring
                if game_state == "CAMPAIGN":
                    threats = [(e.x + e.width / 2, e.y + e.height / 2, math.cos(e.heading) * e.speed_stat,
                                math.sin(e.heading) * e.speed_stat)
                               for e in campaign_enemies if not e.is_burrowed and e.launch_delay == 0]
                else:
                    threats = [(e.x + e.width / 2, e.y + e.height / 2, math.cos(e.heading) * e.speed_stat,
                                math.sin(e.heading) * e.speed_stat) for e in duel["missiles"]]
                want_vx, want_vy = autopilot_velocity(p1_x + 50, p1_y + 40, actual_p1_speed, threats)
                p1_vx += (want_vx - p1_vx) * 0.35
                p1_vy += (want_vy - p1_vy) * 0.35
            # SKY ESCAPE: above the top of the screen the jet is out of sight; after SKY_RETURN frames up there it
            # turns back down by itself (whatever the keys or the autopilot say), so it is back within 3 s
            if p1_y + 40 < 0:
                if sky_esc["t"] == 0:
                    sky_esc["x"] = p1_x + 50                 # where the missiles last saw it
                sky_esc["t"] += 1
            elif p1_y + 40 > 20:
                sky_esc["t"] = 0
            if sky_esc["t"] >= SKY_RETURN:
                sky_esc["ret"] = True
            elif p1_y + 40 > 60:
                sky_esc["ret"] = False
            if sky_esc["ret"]:
                spd = max(math.hypot(p1_vx, p1_vy), actual_p1_speed * 0.8)
                down = math.pi / 2 + (-0.35 if p1_vx >= 0 else 0.35)
                head = aerobatic_heading(math.atan2(p1_vy, p1_vx), down, -1000.0)   # dive back in, nose first
                p1_vx, p1_vy = math.cos(head) * spd, math.sin(head) * spd
                autopilot["head"] = head
                if autopilot["mode"] == "escape":
                    autopilot["mode"], autopilot["t"] = "dive", 40
            p1_x += p1_vx
            p1_y += p1_vy
            new_head = math.atan2(p1_vy, p1_vx)
            p1_turn_rate = (new_head - old_head + math.pi) % (2 * math.pi) - math.pi

            # the jet flies above the ground and inside the screen: bounce the velocity off the edges
            if p1_x < 10 or p1_x > SCREEN_WIDTH - 110:
                p1_x = max(10, min(SCREEN_WIDTH - 110, p1_x))
                p1_vx = -p1_vx * 0.5
            if p1_y + 40 < SKY_CEILING:           # the top of the escape climb
                p1_y = SKY_CEILING - 40
                p1_vy = max(0.0, p1_vy)
            # flying into the ground crashes the jet (user, 2026-10-03); the shield doesn't help
            if jet_hits_ground(p1_y + 40, GROUND_Y):
                p1_y = GROUND_Y - JET_GROUND_CLEARANCE - 40
                p1_hp = 0

            pad_guard = ps_pad_p1 and (ps_pad_p1.get_button(4) or ps_pad_p1.get_button(9) or ps_pad_p1.get_axis(4) > 0.3)
            if (keys[pygame.K_e] or pad_guard or touch["shield_ids"]) and p1_guard_energy > 5.0:
                p1_guard = True
                p1_guard_energy -= 0.6 / pbuff()
            else:
                p1_guard = False
                if p1_guard_energy < 100.0:
                    p1_guard_energy += 0.3 * pbuff()

            pad_aim_x = ps_pad_p1.get_axis(2) if ps_pad_p1 and abs(ps_pad_p1.get_axis(2)) > 0.2 else 0.0
            pad_aim_y = ps_pad_p1.get_axis(3) if ps_pad_p1 and abs(ps_pad_p1.get_axis(3)) > 0.2 else 0.0

            if math.hypot(pad_aim_x, pad_aim_y) > 0.3:
                p1_aim_angle = math.atan2(pad_aim_y, pad_aim_x)
            elif touch["on"]:
                # phone: no mouse, so FIRE aims itself (nearest missile, else a launcher, else straight ahead)
                tgt = touch_aim_target(center_p1_x, center_p1_y)
                p1_aim_angle = math.atan2(tgt[1] - center_p1_y, tgt[0] - center_p1_x) if tgt else math.atan2(p1_vy, p1_vx)
            else:
                p1_aim_angle = math.atan2(mouse_pos[1] - center_p1_y, mouse_pos[0] - center_p1_x)

            # the jet's guns only point forward: shots leave the nose, at most 30 degrees off the flight path
            fly_head = math.atan2(p1_vy, p1_vx)
            off = (p1_aim_angle - fly_head + math.pi) % (2 * math.pi) - math.pi
            p1_aim_angle = fly_head + max(-FIRE_CONE, min(FIRE_CONE, off))
            nose_len = 72 * jet_size_factor(center_p1_y)
            nose_dx, nose_dy = math.cos(fly_head) * nose_len, math.sin(fly_head) * nose_len
            nose_x, nose_y = center_p1_x + nose_dx, center_p1_y + nose_dy

            pad_shoot = ps_pad_p1 and (ps_pad_p1.get_button(0) or ps_pad_p1.get_button(5) or (ps_pad_p1.get_numaxes() > 5 and ps_pad_p1.get_axis(5) > 0.3))
            current_wpn = WEAPON_TIERS[p1_power_tier]
            on_level_bar = game_state == "CAMPAIGN" and mouse_pos[1] >= LEVEL_BAR_TOP   # clicking the strip doesn't shoot
            mouse_fire = mouse_buttons[0] and not on_level_bar and not touch["on"]   # a finger is not a mouse
            is_firing = (mouse_fire or touch["fire_ids"] or keys[pygame.K_SPACE] or pad_shoot) and not p1_guard
            # JET AUTO: while you aren't firing yourself, the guns aim at the nearest target in front of the nose
            # (missile, else launcher; P2's missile in the duel) and fire by themselves
            # (never on phones -- user, 2026-10-03: "in mobile mode it automatically firing": there FIRE is the only trigger)
            if modes["jet"] == "AUTO" and not is_firing and not p1_guard and not MOBILE and not touch["on"]:
                tgt = touch_aim_target(center_p1_x, center_p1_y)
                if tgt:
                    a = math.atan2(tgt[1] - center_p1_y, tgt[0] - center_p1_x)
                    if abs(angle_diff(a, fly_head)) <= FIRE_CONE:
                        p1_aim_angle = a
                        is_firing = True

            # jet ordnance (1P): launched from the nose along the flight path
            if ord_sel["cd"] > 0:
                ord_sel["cd"] -= 1
            if ord_sel["fire"]:
                ord_sel["fire"] = False
                if game_state == "CAMPAIGN":
                    fire_ordnance(nose_x, nose_y, fly_head, math.hypot(p1_vx, p1_vy), pbuff())

            # Calculate positions for the 3 jets when the squad is active
            jet_squad_origins = [(nose_x, nose_y)]
            if p1_split_timer > 0:
                w_off = 72 * jet_size_factor(center_p1_y)
                jet_squad_origins.append((center_p1_x - w_off + nose_dx, center_p1_y - w_off + nose_dy))
                jet_squad_origins.append((center_p1_x - w_off + nose_dx, center_p1_y + w_off + nose_dy))

            if current_wpn["type"] == "laser" and is_firing:
                p1_laser_active = True
                p1_laser_x, p1_laser_y = nose_x, nose_y
                p1_laser_end_x = nose_x + math.cos(p1_aim_angle) * 900
                p1_laser_end_y = nose_y + math.sin(p1_aim_angle) * 900

                if random.random() < 0.2:
                    SFX.snd_laser.play()

                if active_mutator == "LOW GRAVITY ZONE":
                    p1_x -= math.cos(p1_aim_angle) * 1.5
                    p1_y -= math.sin(p1_aim_angle) * 1.5

                mult = ((3 * level_power(current_level)) if game_state == "CAMPAIGN" else 1) * pbuff()
                if p1_split_timer > 0:
                    mult *= 2.5
                laser_dmg = current_wpn["dmg"] * mult

                p1_dmg_box = pygame.Rect(min(nose_x, p1_laser_end_x) - 40, min(nose_y, p1_laser_end_y) - 40,
                                         abs(p1_laser_end_x - nose_x) + 80, abs(p1_laser_end_y - nose_y) + 80)

                if game_state == "CAMPAIGN":
                    for e in campaign_enemies:
                        if not e.is_burrowed and e.rect.colliderect(p1_dmg_box):
                            if e.ecm_timer > 0:   # ECM pulse: the beam is jammed this frame
                                continue
                            hit = laser_dmg
                            e.hp = 0              # one hit destroys a missile (user, 2026-10-03)
                            e.flash_timer = 2
                            total_score += int(hit)
                            p1_power_charge += 1.5
                            if random.random() < 0.3:
                                hit_sparks.append([e.x + e.width // 2, e.y + e.height // 2, random.uniform(-4, 4), random.uniform(-4, 4), 3, current_wpn["color_outer"], 12])
                            if e.hp <= 0:
                                campaign_enemies.remove(e)
                                SFX.snd_explode.play()
                    for li, ln in enumerate(launchers):   # a laser held on a launcher counts one hit per 20 frames
                        if ln["alive"] and launcher_rect(ln).colliderect(p1_dmg_box):
                            ln["laser_frames"] += 1
                            if ln["laser_frames"] >= 20:
                                ln["laser_frames"] = 0
                                damage_launcher(li)
                    for d in drones[:]:                   # the beam burns drones down at once
                        if d in drones and p1_dmg_box.collidepoint(d.x, d.y):
                            kill_drone(d, d.x, d.y)
                    for dl in drone_launchers:            # a drone launcher: one hit per 20 frames of beam
                        if dl.alive and drone_launcher_rect(dl).colliderect(p1_dmg_box):
                            dl.laser_frames += 1
                            if dl.laser_frames >= 20:
                                dl.laser_frames = 0
                                damage_drone_launcher(dl)
                    for s in silos:                       # ...and so does one held on a found / exposed silo
                        if s.targetable and silo_rect(s).colliderect(p1_dmg_box):
                            s.laser_frames += 1
                            if s.laser_frames >= 20:
                                s.laser_frames = 0
                                damage_silo(s)

                # (in the duel the beam's hits on the launcher, its missiles and drones are counted in the duel loop)

                if p1_power_charge >= 100.0 and p1_power_tier < 5:
                    p1_power_charge = 0.0
                    p1_power_tier += 1
                    SFX.snd_win.play()
                    floating_texts.append([f"LASER UPGRADED: {WEAPON_TIERS[p1_power_tier]['name']}!", SCREEN_WIDTH // 2 - 140, 200, WEAPON_TIERS[p1_power_tier]["color_outer"], 45])

            elif current_wpn["type"] == "bullet":
                p1_dmg = int(current_wpn["dmg"] * ((3 * level_power(current_level)) if game_state == "CAMPAIGN" else 1) * pbuff())
                if p1_shoot_cd > 0:
                    p1_shoot_cd -= 1
                if is_firing and p1_shoot_cd == 0:
                    for ox, oy in jet_squad_origins:
                        p1_bullets.append({
                            "x": ox, "y": oy,
                            "vx": math.cos(p1_aim_angle) * current_wpn["speed"] * pbuff(),
                            "vy": math.sin(p1_aim_angle) * current_wpn["speed"] * pbuff(),
                            "radius": 6 + p1_power_tier,
                            "dmg": p1_dmg,
                            "color_outer": current_wpn["color_outer"],
                            "color_core": current_wpn["color_core"],
                        })
                    SFX.snd_shoot.play()
                    p1_shoot_cd = round(12 / pbuff())   # +15% reload rate vs the AI

        # ======================================================================
        # 1-PLAYER CAMPAIGN LOGIC
        # ======================================================================
        if game_state == "CAMPAIGN":
            p1_target_x = center_p1_x
            p1_target_y = center_p1_y

            if p1_camo_timer > 0:
                p1_target_x, p1_target_y = p1_camo_x, p1_camo_y
            if sky_esc["t"] > 0:   # escaped up out of the sky: missiles and drones head for where it vanished
                p1_target_x, p1_target_y = sky_esc["x"], -30.0
            if p1_stealth_timer > 0:
                p1_target_x, p1_target_y = p1_stealth_x, p1_stealth_y
                for e in campaign_enemies:
                    if e.launch_delay > 0:
                        e.launch_delay += 1   # launchers hold fire: no target to launch at

            flares = [d for d in active_decoys if d["type"] == "flare"]
            for e in campaign_enemies:
                tx, ty = p1_target_x, p1_target_y
                e.decoyed = bool(flares)   # locked on a flare: its fuse ignores the jet
                if flares:   # heat-seekers: the nearest burning flare beats everything else
                    ex, ey = e.x + e.width / 2, e.y + e.height / 2
                    fl = min(flares, key=lambda d: math.hypot(d["x"] - ex, d["y"] - ey))
                    tx, ty = fl["x"], fl["y"]
                e.update([], tx, ty, SCREEN_WIDTH, SCREEN_HEIGHT, threats=p1_bullets)

            # a missile that leaves the sky (overshot past an edge) or hits the ground (dived into it,
            # or fell there after its 20 s) is out of the fight; its launcher (or another one if it is
            # gone or busy) launches the next missile. No points: the jet didn't stop it.
            for e in campaign_enemies[:]:
                if e.launch_delay > 0 or e.age < 35:
                    continue
                mx, my = e.x + e.width / 2, e.y + e.height / 2
                hit_ground = my >= GROUND_Y - 12
                # (above the top it is only gone once very high: a spent missile arcs back down into view)
                left_sky = (mx < -MISSILE_OFFSCREEN or mx > SCREEN_WIDTH + MISSILE_OFFSCREEN or my < -400)
                if hit_ground or left_sky:
                    campaign_enemies.remove(e)
                    if hit_ground:
                        blasts.append([mx, GROUND_Y - 12, 0, 1.0])
                        SFX.snd_explode.play()
                    if e.silo is not None:            # a silo's missile: that silo (if still there) fires the next one
                        if e.silo.alive:
                            e.silo.shots += 1
                        continue
                    alive = [i for i, ln in enumerate(launchers) if ln["alive"]]
                    free = [i for i in alive if not any(m.site == i and m.launch_delay > 0 for m in campaign_enemies)]
                    if free:
                        site = e.site if e.site in free else random.choice(free)
                        campaign_enemies.append(launch_missile(current_level, site, 45))

            # a missile that reaches a flare blows up on it (no points: the flare did the work)
            for e in campaign_enemies[:]:
                if e.is_burrowed or e.launch_delay > 0:
                    continue
                ex, ey = e.x + e.width / 2, e.y + e.height / 2
                for fl in flares:
                    if math.hypot(fl["x"] - ex, fl["y"] - ey) < FLARE_CATCH:
                        campaign_enemies.remove(e)
                        if fl in active_decoys:
                            active_decoys.remove(fl)
                        flares.remove(fl)
                        blasts.append([ex, ey, 0, 0.8])
                        SFX.snd_explode.play()
                        break

            # PROXIMITY FUSE: a launcher's missile is built to bring the jet down. When it gets close
            # enough (a direct hit or a near miss) it blows itself up and the jet crashes. Only the
            # shield (E) survives the blast. The missile is gone either way; only missiles shot down
            # by the jet score points.
            jet_cx, jet_cy = p1_x + 50, p1_y + 40
            for e in campaign_enemies[:]:
                if e.is_burrowed or e.launch_delay > 0 or p1_hp <= 0 or p1_stealth_timer > 0 or sky_esc["t"] > 0 or getattr(e, "decoyed", False) or e.expired:
                    continue
                ex, ey = e.x + e.width / 2, e.y + e.height / 2
                if math.hypot(ex - jet_cx, ey - jet_cy) > jet_fuse_radius(jet_cy) * (1.4 if e.is_boss else 1.0) * e.fuse_factor:
                    continue
                campaign_enemies.remove(e)
                blasts.append([ex, ey, 0, 1.6 if e.is_boss else 1.0])
                SFX.snd_explode.play()
                if p1_guard:
                    floating_texts.append(["BLOCKED!", center_p1_x - 20, center_p1_y - 40, (0, 255, 220), 20])
                else:
                    p1_hp = 0   # missile reached the jet: it goes down (crash sequence below)

            for b in p1_bullets[:]:
                b_rect = pygame.Rect(b["x"] - b["radius"], b["y"] - b["radius"], b["radius"] * 2, b["radius"] * 2)
                for e in campaign_enemies[:]:
                    if not e.is_burrowed and e.rect.colliderect(b_rect):
                        if b in p1_bullets:
                            p1_bullets.remove(b)
                        if e.ecm_timer > 0:   # ECM pulse: the bullet bounces off
                            SFX.snd_shield.play()
                            break
                        e.hp = 0                  # one hit destroys a missile (user, 2026-10-03)
                        e.flash_timer = 3
                        SFX.snd_hit.play()

                        total_score += b["dmg"]
                        p1_power_charge += 24.0
                        if p1_power_charge >= 100.0 and p1_power_tier < 5:
                            p1_power_charge = 0.0
                            p1_power_tier += 1
                            SFX.snd_win.play()
                            floating_texts.append([f"POWER TIER {p1_power_tier}!", SCREEN_WIDTH // 2 - 90, 200, (255, 215, 60), 40])

                        floating_texts.append([f"+{b['dmg']} PTS", b["x"], b["y"] - 15, b["color_core"], 25])

                        if e.hp <= 0:
                            campaign_enemies.remove(e)
                            SFX.snd_explode.play()
                        break
                if b in p1_bullets:
                    for li, ln in enumerate(launchers):
                        if ln["alive"] and launcher_rect(ln).colliderect(b_rect):
                            p1_bullets.remove(b)
                            damage_launcher(li)
                            SFX.snd_hit.play()
                            break
                if b in p1_bullets:                # the jet's guns shoot drones down too (one hit)
                    d = next((d for d in drones if math.hypot(d.x - b["x"], d.y - b["y"]) < b["radius"] + 12), None)
                    if d:
                        p1_bullets.remove(b)
                        kill_drone(d, b["x"], b["y"])
                if b in p1_bullets:
                    for dl in drone_launchers:
                        if dl.alive and drone_launcher_rect(dl).colliderect(b_rect):
                            p1_bullets.remove(b)
                            damage_drone_launcher(dl)
                            SFX.snd_hit.play()
                            break
                if b in p1_bullets:
                    for s in silos:                # hidden silos can't be hit until they fire or the FLIR finds them
                        if s.targetable and silo_rect(s).colliderect(b_rect):
                            p1_bullets.remove(b)
                            damage_silo(s)
                            SFX.snd_hit.play()
                            break

            # RELOAD tactic: surviving launchers send extra missiles during the wave
            pending = [li for li, ln in enumerate(launchers) if ln["alive"] and ln["reloads"] > 0]
            for li in pending:
                ln = launchers[li]
                if p1_stealth_timer > 0:
                    continue                                   # launchers hold fire while the jet is hidden
                ln["reload_cd"] -= 1
                if not campaign_enemies:
                    ln["reload_cd"] = min(ln["reload_cd"], 60)   # sky is empty: launch soon
                riding = any(e.site == li and e.launch_delay > 0 for e in campaign_enemies)
                if ln["reload_cd"] <= 0 and not riding and len(campaign_enemies) < 6:
                    ln["reloads"] -= 1
                    ln["reload_cd"] = random.randint(360, 600)
                    campaign_enemies.extend(launch_salvo(current_level, li, 45, room=6 - len(campaign_enemies)))

            # UNDERGROUND SILOS (level 10+): Hidden -> Spooling -> Firing -> Exposed. They hold fire while
            # the jet is in stealth or the sky is already full.
            hold_silos = p1_stealth_timer > 0 or len(campaign_enemies) >= MAX_WAVE_MISSILES
            for s in silos:
                if s.update(hold=hold_silos):
                    e = MissileEnemy(current_level, mutator=active_mutator if current_level > 100 else "NONE",
                                     launch_x=s.x, ground_y=GROUND_Y, system=s.system, difficulty=modes["difficulty"])
                    e.silo = s
                    e.y = GROUND_Y - e.height / 2 - 2   # rises out of the hatch, not out of thin air above it
                    campaign_enemies.append(e)
                    SFX.snd_ignite.play()
                    floating_texts.append(["SILO LAUNCH!", s.x - 40, GROUND_Y - 60, (255, 120, 60), 40])

            # FLIR POD (level 10+): passive, it picks up spooling (hot) silos close below the jet; the
            # active scan (X) also finds cold hidden ones further away. A found silo can be targeted.
            if current_level >= IR_UNLOCK_LEVEL:
                if flir["on"]:
                    flir["energy"] -= 0.35 / pbuff()
                    if flir["energy"] <= 0:
                        flir["on"], flir["energy"] = False, 0.0
                elif flir["energy"] < 100.0:
                    flir["energy"] = min(100.0, flir["energy"] + 0.15 * pbuff())
                for s in silos:
                    if s.alive and not s.revealed and p1_hp > 0 and \
                            flir_sees(center_p1_x, center_p1_y, s.x, GROUND_Y - 6, flir["on"], s.hot):
                        s.revealed = True
                        floating_texts.append(["IR CONTACT", s.x - 35, GROUND_Y - 50, (120, 255, 140), 40])
            else:
                flir["on"] = False

            update_ordnance()

            # DRONE LAUNCHERS: drones one by one, plus the launcher's own missile (held while the sky is full);
            # all hold while the jet is in stealth
            top_speed = p1_speed * (1.35 if active_mutator == "HYPER SPEED STORM" else 1.0) * jet_pace(current_level)
            for dl in drone_launchers:
                if any(ln["alive"] and abs(ln["x"] - dl.x) < 52 and (ln["x"] - dl.x) * dl.vx > 0 for ln in launchers):
                    dl.vx = -dl.vx                   # turns back before it would drive into a truck
                dl.tick_revive()                     # a destroyed one is rebuilt after 2 s
                dl.move()
                want_drone, want_missile = dl.update(hold=p1_stealth_timer > 0,
                                                     hold_missile=len(campaign_enemies) >= MAX_WAVE_MISSILES)
                if want_drone:
                    dfx = difficulty_factors(modes["difficulty"])
                    drones.append(Drone(dl.x, GROUND_Y - 26, drone_speed(top_speed) * dfx["drone_speed"], current_level,
                                        dmg_factor=dfx["drone_dmg"]))
                    SFX.snd_drone.play()
                if want_missile:
                    e = MissileEnemy(current_level, mutator=active_mutator if current_level > 100 else "NONE",
                                     launch_x=dl.x, ground_y=GROUND_Y, difficulty=modes["difficulty"])
                    e.silo = dl          # if it falls to the ground, this launcher gets the shot back
                    campaign_enemies.append(e)

            p1_hp = update_drones_and_autogun(center_p1_x, center_p1_y, p1_target_x, p1_target_y, p1_hp)

            # a downed jet always loses the round, even when the missile that got it was the
            # wave's last one (checking "wave cleared" first used to count that as a win)
            if p1_hp <= 0:
                start_jet_crash("CAMPAIGN")
            elif len(campaign_enemies) == 0 and not pending and not any(s.pending for s in silos) \
                    and not drones and not any(dl.pending for dl in drone_launchers):
                handle_round_conclusion("P1", "CAMPAIGN")

        # ======================================================================
        # 2-PLAYER DUEL: JET vs LAUNCHER
        # ======================================================================
        elif game_state == "DUEL":
            dfx_duel = difficulty_factors(modes["difficulty"])
            ai_launcher = modes["missile"] == "AUTO"
            reload_mult = 1.6 if modes["difficulty"] == "EASY" and ai_launcher else 1.0
            if duel["missile_cd"] > 0:
                duel["missile_cd"] -= 1
            if duel["drone_cd"] > 0:
                duel["drone_cd"] -= 1
            if p2_flash_timer > 0:
                p2_flash_timer -= 1
            duel_target_x, duel_target_y = center_p1_x, center_p1_y   # where its missiles and drones head
            if sky_esc["t"] > 0:                         # escaped up into the sky: they head for where it vanished
                duel_target_x, duel_target_y = sky_esc["x"], -30.0
            elif p1_stealth_timer > 0:
                duel_target_x, duel_target_y = p1_stealth_x, p1_stealth_y
            elif p1_camo_timer > 0:
                duel_target_x, duel_target_y = p1_camo_x, p1_camo_y

            # on phones it stays in the open, between the thumb stick and the button cluster
            duel_lo, duel_hi = (230.0, SCREEN_WIDTH - 270.0) if touch["on"] else (40.0, SCREEN_WIDTH - 40.0)
            if p2_hp > 0:
                # DRIVE: player 2 with left / right (or a 2nd controller's stick); AUTO: the computer keeps away from
                # under the jet's nose and dodges incoming shots, never leaving the ground
                p2_pad_x = ps_pad_p2.get_axis(0) if ps_pad_p2 and abs(ps_pad_p2.get_axis(0)) > 0.3 else 0.0
                drive = 0.0
                if not ai_launcher:
                    if keys[pygame.K_LEFT] or keys[pygame.K_KP4] or p2_pad_x < 0:
                        drive -= 1.0
                    if keys[pygame.K_RIGHT] or keys[pygame.K_KP6] or p2_pad_x > 0:
                        drive += 1.0
                else:
                    jet_dir = 1.0 if p1_vx >= 0 else -1.0
                    in_front = (p2_x - center_p1_x) * jet_dir > 0
                    want_x = center_p1_x - jet_dir * 260          # sit behind the jet, out of its forward guns
                    if in_front and abs(p2_x - center_p1_x) < 320:
                        want_x = p2_x + jet_dir * 200              # the jet is heading for it: drive away
                    # reads where each shot will come down; if it would land on the truck, it sprints out of the way
                    # (it notices 60% of the shots on NORMAL, 25% on EASY -- decided once per shot)
                    sprint = 1.0
                    threats = []
                    for b in p1_bullets:
                        if b["vy"] <= 0.5:
                            continue
                        land_x = b["x"] + b["vx"] * (GROUND_Y - 14 - b["y"]) / b["vy"]
                        if abs(land_x - p2_x) < 55 and b.setdefault("p2_sees", random.random() < dfx_duel["duel_sees"]):
                            threats.append(land_x)
                    if threats:
                        land_x = min(threats, key=lambda lx: abs(lx - p2_x))
                        want_x = p2_x + (140 if p2_x >= land_x else -140)
                        if want_x < duel_lo or want_x > duel_hi:          # cornered: dodge the other way
                            want_x = p2_x - (want_x - p2_x)
                        sprint = 1.8
                    want_x = max(duel_lo, min(duel_hi, want_x))
                    if abs(want_x - p2_x) > 8:
                        drive = 1.0 if want_x > p2_x else -1.0
                    drive *= dfx_duel["duel_speed"] * sprint
                    if duel["missile_cd"] == 0 and p1_stealth_timer == 0:
                        duel["want_missile"] = True
                    if duel["drone_cd"] == 0 and p1_stealth_timer == 0:
                        duel["want_drone"] = True
                duel["vx"] += (drive * DUEL_DRIVE - duel["vx"]) * 0.2     # a heavy truck: it speeds up and brakes
                p2_x = max(duel_lo, min(duel_hi, p2_x + duel["vx"]))

                # FIRE: missiles and drones only ever leave the launcher (user, 2026-10-03)
                if duel["want_missile"] and duel["missile_cd"] == 0 and len(duel["missiles"]) < DUEL_MAX_MISSILES:
                    e = MissileEnemy(DUEL_LEVEL, launch_x=p2_x, ground_y=GROUND_Y, difficulty=modes["difficulty"])
                    duel["missiles"].append(e)
                    duel["missile_cd"] = int(DUEL_MISSILE_RELOAD * reload_mult)
                    SFX.snd_ignite.play()
                if duel["want_drone"] and duel["drone_cd"] == 0 and len(drones) < DUEL_MAX_DRONES:
                    drones.append(Drone(p2_x, GROUND_Y - 26, drone_speed(p1_speed) * dfx_duel["drone_speed"], DUEL_LEVEL,
                                        dmg_factor=dfx_duel["drone_dmg"]))
                    duel["drone_cd"] = int(DUEL_DRONE_RELOAD * reload_mult)
                    SFX.snd_drone.play()
            duel["want_missile"] = duel["want_drone"] = False

            # its missiles: the same projectile rules as the campaign (30 deg/s, 20 s, proximity fuse, flares)
            duel_flares = [d for d in active_decoys if d["type"] == "flare"]
            for e in duel["missiles"][:]:
                tx, ty = duel_target_x, duel_target_y
                e.decoyed = bool(duel_flares)
                if duel_flares:
                    ex, ey = e.x + e.width / 2, e.y + e.height / 2
                    fl = min(duel_flares, key=lambda d: math.hypot(d["x"] - ex, d["y"] - ey))
                    tx, ty = fl["x"], fl["y"]
                e.update([], tx, ty, SCREEN_WIDTH, SCREEN_HEIGHT)
                mx, my = e.x + e.width / 2, e.y + e.height / 2
                if e.age >= 35 and (my >= GROUND_Y - 12 or mx < -MISSILE_OFFSCREEN or mx > SCREEN_WIDTH + MISSILE_OFFSCREEN or my < -400):
                    duel["missiles"].remove(e)
                    if my >= GROUND_Y - 12:
                        blasts.append([mx, GROUND_Y - 12, 0, 1.0])
                        SFX.snd_explode.play()
                    continue
                caught = next((fl for fl in duel_flares if math.hypot(fl["x"] - mx, fl["y"] - my) < FLARE_CATCH), None)
                if caught:
                    duel["missiles"].remove(e)
                    if caught in active_decoys:
                        active_decoys.remove(caught)
                    blasts.append([mx, my, 0, 0.8])
                    SFX.snd_explode.play()
                    continue
                if p1_hp > 0 and p1_stealth_timer == 0 and sky_esc["t"] == 0 and not e.decoyed and not e.expired and \
                        math.hypot(mx - center_p1_x, my - center_p1_y) <= jet_fuse_radius(center_p1_y) * e.fuse_factor:
                    duel["missiles"].remove(e)
                    blasts.append([mx, my, 0, 1.0])
                    SFX.snd_explode.play()
                    if p1_guard:
                        floating_texts.append(["BLOCKED!", center_p1_x - 20, center_p1_y - 40, (0, 255, 220), 20])
                    else:
                        p1_hp = 0

            # its drones and the jet's protective auto-gun (same as the campaign)
            p1_hp = update_drones_and_autogun(center_p1_x, center_p1_y, duel_target_x, duel_target_y, p1_hp)

            # the jet's shots: one hit downs a missile or a drone; the armoured launcher takes p2_max_hp hits
            p2_rect = pygame.Rect(p2_x - 30, GROUND_Y - 30, 60, 32)
            for b in p1_bullets[:]:
                b_rect = pygame.Rect(b["x"] - b["radius"], b["y"] - b["radius"], b["radius"] * 2, b["radius"] * 2)
                hit_m = next((e for e in duel["missiles"] if e.rect.colliderect(b_rect)), None)
                if hit_m:
                    duel["missiles"].remove(hit_m)
                    p1_bullets.remove(b)
                    blasts.append([hit_m.x + hit_m.width / 2, hit_m.y + hit_m.height / 2, 0, 0.7])
                    SFX.snd_explode.play()
                    continue
                hit_d = next((d for d in drones if math.hypot(d.x - b["x"], d.y - b["y"]) < b["radius"] + 12), None)
                if hit_d:
                    p1_bullets.remove(b)
                    kill_drone(hit_d, b["x"], b["y"])
                    continue
                if p2_hp > 0 and p2_rect.colliderect(b_rect):
                    p1_bullets.remove(b)
                    p2_hp -= 1
                    p2_flash_timer = 6
                    SFX.snd_hit.play()
                    p1_power_charge += 24.0
                    if p1_power_charge >= 100.0 and p1_power_tier < 5:
                        p1_power_charge = 0.0
                        p1_power_tier += 1
            if p1_laser_active:
                beam = pygame.Rect(min(p1_laser_x, p1_laser_end_x) - 40, min(p1_laser_y, p1_laser_end_y) - 40,
                                   abs(p1_laser_end_x - p1_laser_x) + 80, abs(p1_laser_end_y - p1_laser_y) + 80)
                for e in duel["missiles"][:]:
                    if e.rect.colliderect(beam):
                        duel["missiles"].remove(e)
                        blasts.append([e.x + e.width / 2, e.y + e.height / 2, 0, 0.7])
                        SFX.snd_explode.play()
                for d in drones[:]:
                    if beam.collidepoint(d.x, d.y):
                        kill_drone(d, d.x, d.y)
                if p2_hp > 0 and p2_rect.colliderect(beam):
                    duel["laser_frames"] += 1
                    if duel["laser_frames"] >= 20:           # a held beam: one hit per 20 frames, like any launcher
                        duel["laser_frames"] = 0
                        p2_hp -= 1
                        p2_flash_timer = 6
                        SFX.snd_hit.play()

            if p1_hp <= 0:
                p2_wins += 1
                start_jet_crash("DUEL")
            elif p2_hp <= 0:
                blasts.append([p2_x, GROUND_Y - 14, 0, 1.6])
                SFX.snd_explode.play()
                p1_wins += 1
                handle_round_conclusion("P1", "DUEL")

        # Update Projectiles
        for b in p1_bullets[:]:
            b["x"] += b["vx"]
            b["y"] += b["vy"]
            if b["x"] < 0 or b["x"] > SCREEN_WIDTH or b["y"] < 0 or b["y"] > SCREEN_HEIGHT:
                p1_bullets.remove(b)

        # Draw Projectiles
        for b in p1_bullets:
            pygame.draw.circle(screen, b["color_outer"], (int(b["x"]), int(b["y"])), b["radius"])
            pygame.draw.circle(screen, b["color_core"], (int(b["x"]), int(b["y"])), max(2, b["radius"] - 3))

        if game_state == "CAMPAIGN":
            if flir["on"] and p1_hp > 0:
                draw_flir_cone(center_p1_x, center_p1_y)
            draw_ordnance()

        # Draw Cyber Laser Beams
        if p1_laser_active:
            wpn = WEAPON_TIERS[p1_power_tier]
            pygame.draw.line(screen, wpn["color_outer"], (p1_laser_x, p1_laser_y), (p1_laser_end_x, p1_laser_end_y), wpn["beam_w"] + 8)
            pygame.draw.line(screen, wpn["color_core"], (p1_laser_x, p1_laser_y), (p1_laser_end_x, p1_laser_end_y), wpn["beam_w"])
            pygame.draw.circle(screen, wpn["color_core"], (int(p1_laser_x), int(p1_laser_y)), wpn["beam_w"] + 4)

            # Draw clone jets' lasers if the squad is active
            if p1_split_timer > 0:
                w_off = 72 * jet_size_factor(center_p1_y)
                nl = 72 * jet_size_factor(center_p1_y)
                fh = math.atan2(p1_vy, p1_vx)
                for ox, oy in [(center_p1_x - w_off + math.cos(fh) * nl, center_p1_y - w_off + math.sin(fh) * nl),
                               (center_p1_x - w_off + math.cos(fh) * nl, center_p1_y + w_off + math.sin(fh) * nl)]:
                    lex = ox + math.cos(p1_aim_angle) * 900
                    ley = oy + math.sin(p1_aim_angle) * 900
                    pygame.draw.line(screen, wpn["color_outer"], (ox, oy), (lex, ley), wpn["beam_w"] + 4)
                    pygame.draw.line(screen, (255, 255, 255), (ox, oy), (lex, ley), max(2, wpn["beam_w"] - 2))


        for dec in active_decoys:
            alpha = 130 + int(math.sin(dec["life"] * 0.2) * 50)
            if dec["type"] == "flare":
                fx, fy = int(dec["x"]), int(dec["y"])
                burn = dec["life"] / FLARE_LIFE
                glow = int(9 + 4 * burn + random.uniform(-1.5, 1.5))
                pygame.draw.circle(screen, (255, 110, 20), (fx, fy), glow)
                pygame.draw.circle(screen, (255, 200, 80), (fx, fy), max(2, glow // 2))
                pygame.draw.circle(screen, (255, 255, 230), (fx, fy), max(1, glow // 4))
                pygame.draw.circle(screen, (120, 120, 130), (fx - int(dec["vx"] * 4), fy - int(dec["vy"] * 4)), 3)   # smoke
            else:
                v_h_raw = pygame.transform.scale(create_missile_body(is_boss=False, flash_white=False, alpha=alpha, tier=5), (MISSILE_BODY_W * 1.6, MISSILE_H * 1.6))
                screen.blit(v_h_raw, (dec["x"] + 40 - MISSILE_BODY_W * 0.8, dec["y"] + 25 - MISSILE_H * 0.8))
                pygame.draw.circle(screen, (200, 100, 255), (int(dec["x"] + 40), int(dec["y"] + 25)), 45, 1)

        for spark in hit_sparks[:]:
            spark[0] += spark[2]
            spark[1] += spark[3]
            spark[6] -= 1
            if spark[6] <= 0:
                hit_sparks.remove(spark)
            else:
                pygame.draw.circle(screen, spark[5], (int(spark[0]), int(spark[1])), spark[4])

        for ft in floating_texts[:]:
            ft[2] -= 1.2
            ft[4] -= 1
            if ft[4] <= 0:
                floating_texts.remove(ft)
            else:
                screen.blit(font.render(ft[0], True, ft[3]), (int(ft[1]), int(ft[2])))

        # Draw Player 1 & active jet squad
        camo_alpha = 35 if p1_stealth_timer > 0 else (60 if p1_camo_timer > 0 else 255)
        # the jet points its nose where it is flying; banking into a turn (and barrel rolls)
        # squeeze the wings, so it reads as a real aircraft manoeuvring
        jet_heading = math.atan2(p1_vy, p1_vx)
        bank = max(-1.1, min(1.1, p1_turn_rate * 14)) + autopilot["roll"]
        wing_scale = max(0.18, abs(math.cos(bank)))

        jet_f = jet_size_factor(center_p1_y)
        wing_off = 72 * jet_f            # wingmen fly half a jet-length behind and to the sides

        def flying_jet(surf):
            sq = pygame.transform.scale(surf, (int(144 * jet_f), max(6, int(120 * jet_f * wing_scale))))
            return pygame.transform.rotate(sq, -math.degrees(jet_heading))

        s_surf = create_jet_sprite(p1_guard, WEAPON_TIERS[p1_power_tier]["color_outer"], alpha=camo_alpha)
        if p1_hp > 0:
            j_img = flying_jet(s_surf)
            screen.blit(j_img, j_img.get_rect(center=(center_p1_x, center_p1_y)))

            # Draw the 2 orbiting Combat Clones if Split Active
            if p1_split_timer > 0:
                c1_img = flying_jet(create_jet_sprite(False, (255, 215, 60), alpha=min(210, camo_alpha)))
                screen.blit(c1_img, c1_img.get_rect(center=(center_p1_x - wing_off, center_p1_y - wing_off)))
                screen.blit(c1_img, c1_img.get_rect(center=(center_p1_x - wing_off, center_p1_y + wing_off)))
                pygame.draw.line(screen, (255, 215, 60), (center_p1_x, center_p1_y), (center_p1_x - wing_off, center_p1_y - wing_off), 1)
                pygame.draw.line(screen, (255, 215, 60), (center_p1_x, center_p1_y), (center_p1_x - wing_off, center_p1_y + wing_off), 1)

            if p1_guard:
                pygame.draw.circle(screen, (0, 220, 255), (int(center_p1_x), int(center_p1_y)), int(jet_fuse_radius(center_p1_y)), 3)

            if sky_esc["t"] > 0:   # escaped above the screen: a marker on the top edge shows where it is and the countdown
                mx = int(max(20, min(SCREEN_WIDTH - 20, center_p1_x)))
                pygame.draw.polygon(screen, (255, 230, 120), [(mx, 2), (mx - 9, 16), (mx + 9, 16)])
                left = max(1, math.ceil((SKY_MAX_FRAMES - sky_esc["t"]) / 60))
                t = font.render(f"JET IN THE SKY - BACK IN {left}s", True, (255, 230, 120))
                box = t.get_rect(midtop=(max(140, min(SCREEN_WIDTH - 140, mx)), 18)).inflate(10, 4)
                pygame.draw.rect(screen, (10, 14, 24), box, border_radius=4)       # readable over the HUD
                screen.blit(t, t.get_rect(center=box.center))

            p1_aim = p1_aim_angle if 'p1_aim_angle' in locals() else 0.0
            pygame.draw.line(screen, WEAPON_TIERS[p1_power_tier]["color_outer"], (center_p1_x, center_p1_y),
                             (center_p1_x + math.cos(p1_aim) * 70 * jet_f, center_p1_y + math.sin(p1_aim) * 70 * jet_f), 3)

        # Draw Player 2 or Campaign Enemies
        if game_state == "CAMPAIGN":
            draw_drones()
            for r in autogun["rounds"]:              # auto-gun tracer rounds
                pygame.draw.line(screen, (255, 245, 170), (r["x"], r["y"]), (r["x"] - r["vx"] * 0.6, r["y"] - r["vy"] * 0.6), 2)
            if autogun["firing"] > 0 and p1_hp > 0:  # the protective ring shows while the auto-gun is shooting
                pygame.draw.circle(screen, (255, 230, 120), (int(center_p1_x), int(center_p1_y)), int(AUTOGUN_RANGE * pbuff()), 1)
            for e in campaign_enemies:
                e.draw(screen)
        elif game_state == "DUEL":
            draw_drones()
            for r in autogun["rounds"]:
                pygame.draw.line(screen, (255, 245, 170), (r["x"], r["y"]), (r["x"] - r["vx"] * 0.6, r["y"] - r["vy"] * 0.6), 2)
            if autogun["firing"] > 0 and p1_hp > 0:
                pygame.draw.circle(screen, (255, 230, 120), (int(center_p1_x), int(center_p1_y)), int(AUTOGUN_RANGE * pbuff()), 1)
            for e in duel["missiles"]:
                e.draw(screen)
            if p2_hp > 0:   # P2's launcher truck on the ground: missile rail + drone ramp
                lx = int(p2_x)
                body = (255, 255, 255) if p2_flash_timer > 0 else (70, 80, 60)
                cab_x = lx + 14 if duel["vx"] >= 0 else lx - 30
                pygame.draw.rect(screen, body, (lx - 30, GROUND_Y - 16, 60, 14), border_radius=3)
                pygame.draw.rect(screen, (90, 100, 75), (cab_x, GROUND_Y - 26, 16, 12), border_radius=2)
                pygame.draw.line(screen, (120, 125, 110), (lx - 8, GROUND_Y - 16), (lx - 8, GROUND_Y - 58), 4)
                pygame.draw.polygon(screen, (100, 106, 90), [(lx + 2, GROUND_Y - 16), (lx + 22, GROUND_Y - 30),
                                                             (lx + 25, GROUND_Y - 26), (lx + 8, GROUND_Y - 16)])
                for wx in (lx - 20, lx, lx + 20):
                    pygame.draw.circle(screen, (25, 25, 28), (wx, GROUND_Y - 1), 6)
                pygame.draw.rect(screen, (60, 20, 20), (lx - 25, GROUND_Y - 70, 50, 5))            # armour bar
                pygame.draw.rect(screen, (90, 230, 90), (lx - 25, GROUND_Y - 70, int(50 * p2_hp / p2_max_hp), 5))
                tag = tag_font.render("AI LAUNCHER" if modes["missile"] == "AUTO" else "P2 LAUNCHER", True, (0, 210, 255))
                screen.blit(tag, tag.get_rect(center=(lx, GROUND_Y + 14)))

        # SAFEGUARD: a pulsing protective dome around the jet and the interceptor trails to what it shot down
        if safeguard["t"] > 0 and p1_hp > 0:
            r = int(70 + 8 * math.sin(pygame.time.get_ticks() * 0.02))
            pygame.draw.circle(screen, (120, 220, 255), (int(center_p1_x), int(center_p1_y)), r, 2)
            pygame.draw.circle(screen, (200, 240, 255), (int(center_p1_x), int(center_p1_y)), r - 6, 1)
        for z in safeguard["zaps"][:]:
            z[4] -= 1
            if z[4] <= 0:
                safeguard["zaps"].remove(z)
            else:
                pygame.draw.line(screen, (200, 240, 255), (z[0], z[1]), (z[2], z[3]), 2)

        draw_blasts()   # missile self-destruct fireballs, on top of the jet and missiles

        if active_mutator == "BLACKOUT FOG" and game_state == "CAMPAIGN":
            dark_overlay.fill((5, 5, 10, 230))
            pygame.draw.circle(dark_overlay, (0, 0, 0, 0), (int(center_p1_x), int(center_p1_y)), 140)
            for e in campaign_enemies:
                pygame.draw.circle(dark_overlay, (0, 0, 0, 0), (int(e.x + e.width // 2), int(e.y + e.height // 2)), 60)
            screen.blit(dark_overlay, (0, 0))

        if not ps_pad_p1:
            pygame.draw.circle(screen, WEAPON_TIERS[p1_power_tier]["color_outer"], mouse_pos, 8, 2)
            pygame.draw.circle(screen, (255, 255, 255), mouse_pos, 2)

        # ======================================================================
        # DIGITAL NUMERIC HUD
        # ======================================================================
        p1_col = (255, 140, 0) if p1_hp > 50 else (255, 60, 60)
        p1_title = (f"{names[0]}: JET [{modes['jet']}] (3X, +15% vs AI)" if game_state == "CAMPAIGN"
                    else f"{names[0]}: JET [{modes['jet']}]" + (" (+15% vs AI)" if pbuff() > 1 else ""))
        screen.blit(font.render(p1_title, True, (255, 180, 80)), (20, 12))
        screen.blit(num_font.render(f"HP: {int(p1_hp)} / {p1_max_hp}", True, p1_col), (20, 30))
        wpn_desc = f"PWR TIER {p1_power_tier}: {WEAPON_TIERS[p1_power_tier]['name']} (Press 'L')"
        screen.blit(font.render(wpn_desc, True, WEAPON_TIERS[p1_power_tier]["color_outer"]), (20, 56))

        # Split status display
        split_stat = f"TRIPLE SQUAD ACTIVE ({p1_split_timer // 60}s)" if p1_split_timer > 0 else f"TRIPLE SPLIT [T]: {p1_split_charges} CHARGES"
        screen.blit(font.render(split_stat, True, (255, 215, 60) if p1_split_charges > 0 else (120, 130, 150)), (20, 76))

        if p1_camo_timer > 0:
            camo_stat, camo_col = f"CAMOUFLAGE ACTIVE ({p1_camo_timer // 60 + 1}s)", (120, 255, 160)
        elif p1_camo_cd > 0:
            camo_stat, camo_col = f"CAMOUFLAGE [C]: RECHARGING {p1_camo_cd // 60 + 1}s", (120, 130, 150)
        else:
            camo_stat, camo_col = "CAMOUFLAGE [C]: READY", (120, 255, 160)
        screen.blit(font.render(camo_stat, True, camo_col), (20, 96))
        if p1_stealth_timer > 0:
            st_stat, st_col = f"STEALTH ACTIVE ({p1_stealth_timer // 60 + 1}s)", (150, 200, 255)
        elif p1_stealth_cd > 0:
            st_stat, st_col = f"STEALTH [V]: RECHARGING {p1_stealth_cd // 60 + 1}s", (120, 130, 150)
        else:
            st_stat, st_col = "STEALTH [V]: READY", (150, 200, 255)
        screen.blit(font.render(st_stat, True, st_col), (20, 116))
        if safeguard["t"] > 0:
            sg_stat, sg_col = f"SAFEGUARD ACTIVE ({safeguard['t'] // 60 + 1}s)", (120, 220, 255)
        elif safeguard["cd"] > 0:
            sg_stat, sg_col = f"SAFEGUARD [B]: RECHARGING {safeguard['cd'] // 60 + 1}s", (120, 130, 150)
        else:
            sg_stat, sg_col = "SAFEGUARD [B]: READY", (120, 220, 255)
        screen.blit(font.render(sg_stat, True, sg_col), (20, 196 if game_state == "CAMPAIGN" else 136))

        if game_state == "CAMPAIGN":
            sel = selected_munition()
            if sel:
                left = p1_ammo.get(sel["id"], 0)
                o_txt = f"ORDNANCE [G/R]: {munition_label(sel)} ({sel['role']}) x{left}  [{ord_sel['i'] % len(p1_ammo) + 1}/{len(p1_ammo)}]"
                screen.blit(font.render(o_txt, True, tuple(sel["trail"]) if left else (120, 130, 150)), (20, 136))
            else:
                screen.blit(font.render("ORDNANCE: NATION WEAPONS FROM LEVEL 5", True, (120, 130, 150)), (20, 136))
            if current_level >= IR_UNLOCK_LEVEL:
                f_txt = f"FLIR [X]: {'SCANNING' if flir['on'] else 'PASSIVE'} {int(flir['energy'])}%"
                screen.blit(font.render(f_txt, True, (120, 255, 140) if flir["on"] else (150, 190, 160)), (20, 156))
                contacts = sum(1 for s in silos if s.alive and s.revealed)
                screen.blit(font.render(f"SILO CONTACTS: {contacts}", True, (255, 150, 90)), (SCREEN_WIDTH - 150, 64))
            alive_dl = sum(1 for dl in drone_launchers if dl.alive)
            d_txt = (f"DRONES LV {drone_level(current_level)}: {len(drones)} IN AIR | DRONE LAUNCHERS {alive_dl}/{len(drone_launchers)}"
                     f" | AUTO-GUN {'FIRING' if autogun['firing'] else 'ARMED'}")
            screen.blit(font.render(d_txt, True, (230, 220, 150)), (20, 176))

        if game_state == "CAMPAIGN":
            lvl_col = (255, 60, 90) if current_level > 100 else (255, 230, 100)
            lvl_txt = f"OVERDRIVE WAVE {current_level}" if current_level > 100 else f"LEVEL {current_level} / 100"
            screen.blit(font.render(lvl_txt, True, lvl_col), (SCREEN_WIDTH // 2 - 80, 12))
            pw = level_power(current_level)
            screen.blit(font.render(f"POWER  JET x{pw:.2f}  MISSILE x{pw:.2f}", True, (200, 210, 240)), (SCREEN_WIDTH // 2 - 10, 30))
            tactics = active_tactics(current_level)
            screen.blit(font.render("AI: " + (", ".join(tactics) if tactics else "BASIC") + f" ({modes['difficulty']})", True,
                                    (255, 150, 150)), (SCREEN_WIDTH // 2 - 10, 46))
            if hint["frames"] > 0:   # first-time hint box for a newly unlocked feature
                hint["frames"] -= 1
                t = font.render(hint["text"], True, (20, 20, 25))
                box = t.get_rect(center=(SCREEN_WIDTH // 2, 214)).inflate(18, 10)
                pygame.draw.rect(screen, (255, 220, 110), box, border_radius=6)
                screen.blit(t, t.get_rect(center=box.center))

            if active_mutator != "NONE":
                screen.blit(font.render(f"MUTATOR: {active_mutator}", True, (255, 100, 200)), (SCREEN_WIDTH // 2 - 10, 62))

            screen.blit(font.render(f"SCORE: {total_score}", True, (200, 210, 240)), (SCREEN_WIDTH - 150, 12))
            draw_level_bar()

        elif game_state == "DUEL":
            p2_col = (0, 210, 255) if p2_hp > 1 else (255, 60, 60)
            p2_head = font.render("AI LAUNCHER" if modes["missile"] == "AUTO" else f"{names[1]}: LAUNCHER", True, (0, 210, 255))
            p2_num = num_font.render(f"HITS LEFT: {int(p2_hp)} / {p2_max_hp}", True, p2_col)
            p2_sub = font.render(("FIRES MISSILES & DRONES" if modes["missile"] == "AUTO" else
                                  "ARROWS DRIVE | UP MISSILE | DOWN DRONE") + f" | WINS: {p2_wins}", True, (200, 210, 230))
            screen.blit(p2_head, (SCREEN_WIDTH - p2_head.get_width() - 20, 12))
            screen.blit(p2_num, (SCREEN_WIDTH - p2_num.get_width() - 20, 30))
            screen.blit(p2_sub, (SCREEN_WIDTH - p2_sub.get_width() - 20, 56))

        if touch["on"] and game_state in ("CAMPAIGN", "DUEL") and p1_hp > 0:
            draw_touch_controls()
        draw_portrait_hint()

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
