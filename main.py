import array
import asyncio
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
def create_jet_sprite(tail_flag: bool = False, aura_color=None, alpha: int = 255) -> pygame.Surface:
    """The player's stealth fighter (F-35 style, own design, no real markings).
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
    (8,  "JINK"),     # sidesteps a jet bullet that is about to hit
    (20, "FLANK"),    # a wave spreads out and attacks from different sides
    (30, "RELOAD"),   # surviving ground launchers send extra missiles during the wave
    (35, "SPRINT"),   # speed burst when lined up on the jet at close range
    (55, "ECM"),      # short jamming pulse: blocks jet bullets, lasers do half damage
]


def active_tactics(level: int):
    return [name for lvl, name in AI_TACTICS if level >= lvl]


MISSILE_BODY_W, MISSILE_H = 36, 40   # missile body: half the original 72px length (user request 2026-10-02)
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
    The old burrow holes are now radar-cloak points: the missile vanishes from radar there
    and reappears at another one. Missiles never fire: they hit or blow up next to the jet."""

    def __init__(self, level: int, is_boss: bool = False, mutator: str = "NONE",
                 launch_x: float = None, ground_y: int = 600, launch_delay: int = 0):
        self.is_boss = is_boss
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
        self.speed_stat = stats["speed"] * self.pace * speed_mult * boss_mult
        self.turn_rate = stats["turn"] * (0.8 if is_boss else 1.0)
        self.power = level_power(level)        # missile damage grows with level, same curve as the jet
        self.contact_dmg = int(stats["contact_dmg"] * (1.6 if is_boss else 1.0) * self.power)

        # AI tactics unlocked by level (see AI_TACTICS)
        self.tactics = active_tactics(level)
        self.flank_angle = 0.0                 # set by the spawner so a wave attacks from different sides
        self.jink_cd = 0
        self.sprint_timer = 0
        self.sprint_cd = random.randint(60, 150)
        self.ecm_timer = 0
        self.ecm_cd = random.randint(180, 360)
        self.contact_cd = 0
        self.trail = []
        self.age = 0
        self.angle = math.degrees(self.heading)
        self.is_burrowed = False
        self.burrow_timer = 0
        self.burrow_cooldown = random.randint(180, 360)
        self.seek_timer = 0

        self.flash_timer = 0

    def update(self, holes, target_x, target_y, screen_w, screen_h, threats=()):
        """threats = the jet's bullets in flight (used by the JINK tactic)."""
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

        if self.age < 35 and self.launch_x is not None:
            # boost phase: climb straight up off the launcher before homing in
            self.y -= self.speed_stat * 1.3
            self.trail.append((self.x + self.width // 2, self.y + self.height // 2))
            if len(self.trail) > 14:
                self.trail.pop(0)
            return None

        if self.is_burrowed:
            self.burrow_timer -= 1
            if self.burrow_timer <= 0:
                dest = random.choice(holes)
                self.x = dest[0] - self.width // 2
                self.y = dest[1] - self.height // 2
                self.heading = math.atan2(target_y - dest[1], target_x - dest[0])
                self.trail.clear()
                self.is_burrowed = False
                self.burrow_cooldown = random.randint(200, 380)
                SFX.snd_burrow.play()
            return None

        center_x = self.x + self.width // 2
        center_y = self.y + self.height // 2
        steer_x, steer_y = target_x, target_y

        if self.burrow_cooldown > 0:
            self.burrow_cooldown -= 1
        elif len(holes) > 0 and (self.seek_timer > 0 or self.hp < self.max_hp * 0.5 or random.random() < 0.006):
            nearest = min(holes, key=lambda h: math.hypot(h[0] - center_x, h[1] - center_y))
            dist = math.hypot(nearest[0] - center_x, nearest[1] - center_y)
            self.seek_timer += 1
            # a missile can't stop on a point, so it cloaks when it passes close by, or
            # after 3 s of trying (jamming radar wherever it is)
            if dist < 70 or self.seek_timer > 180:
                self.is_burrowed = True
                self.burrow_timer = 110
                self.seek_timer = 0
                SFX.snd_burrow.play()
                return None
            steer_x, steer_y = nearest
        elif "FLANK" in self.tactics:
            # FLANK: approach a point off to this missile's side of the jet, then turn in for the hit
            if math.hypot(target_x - center_x, target_y - center_y) > 170:
                steer_x = target_x + math.cos(self.flank_angle) * 150
                steer_y = target_y + math.sin(self.flank_angle) * 150

        desired = math.atan2(steer_y - center_y, steer_x - center_x)
        if self.tier == 5:
            desired += math.sin(self.age * 0.12) * 0.45      # hypersonic weave
        diff = (desired - self.heading + math.pi) % (2 * math.pi) - math.pi
        self.heading += max(-self.turn_rate, min(self.turn_rate, diff))

        speed = self.speed_stat
        if self.tier == 4:
            # ballistic: slow while turning, steep fast dive once lined up on the target
            speed *= 0.7 + 0.9 * max(0.0, math.cos(diff))

        # SPRINT: short speed burst when lined up on the jet at close range
        if self.sprint_cd > 0:
            self.sprint_cd -= 1
        if "SPRINT" in self.tactics and self.sprint_cd == 0 and abs(diff) < 0.25 \
                and math.hypot(target_x - center_x, target_y - center_y) < 260:
            self.sprint_timer, self.sprint_cd = 30, 180
        if self.sprint_timer > 0:
            self.sprint_timer -= 1
            speed *= 1.8

        # ECM: brief jamming pulse that blocks the jet's bullets (lasers do half damage)
        if self.ecm_cd > 0:
            self.ecm_cd -= 1
        elif "ECM" in self.tactics:
            self.ecm_timer, self.ecm_cd = 60, 360

        self.x += math.cos(self.heading) * speed
        self.y += math.sin(self.heading) * speed

        # JINK: sidestep a jet bullet that is about to hit
        if self.jink_cd > 0:
            self.jink_cd -= 1
        elif "JINK" in self.tactics:
            for b in threats:
                bx, by = b["x"] - center_x, b["y"] - center_y
                closing = bx * b["vx"] + by * b["vy"] < 0          # bullet moving toward the missile
                if closing and math.hypot(bx, by) < 110:
                    side = 1 if (b["vx"] * by - b["vy"] * bx) > 0 else -1
                    bl = math.hypot(b["vx"], b["vy"]) or 1
                    self.x += -b["vy"] / bl * 28 * side
                    self.y += b["vx"] / bl * 28 * side
                    self.jink_cd = 45
                    break

        # bounce off the arena edges and pull up above the ground instead of leaving the
        # play area (each edge forces the heading back inward, so it can't flip outward)
        hx, hy = math.cos(self.heading), math.sin(self.heading)
        floor = min(screen_h, self.ground_y) - self.height // 2 - 20
        if self.x < 20:
            hx, self.x = abs(hx), 20
        elif self.x > screen_w - self.width - 20:
            hx, self.x = -abs(hx), screen_w - self.width - 20
        if self.y < 60:
            hy, self.y = abs(hy), 60
        elif self.y > floor:
            hy, self.y = -abs(hy), floor
        self.heading = math.atan2(hy, hx)
        self.angle = math.degrees(self.heading)

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
        if self.launch_delay == 0:   # engine lit: fire tail twice the missile's length
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
# MAIN ASYNC LOOP
# ==============================================================================
async def main():
    global joysticks
    SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    dark_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    pygame.display.set_caption("Jet vs Missile")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 14, bold=True)
    num_font = pygame.font.SysFont("consolas", 22, bold=True)
    big_font = pygame.font.SysFont("consolas", 28, bold=True)
    title_font = pygame.font.SysFont("consolas", 34, bold=True)

    scale = 2
    game_state = "MODE_SELECT"
    prev_mode = "CAMPAIGN"

    burrow_holes = [(200, 140), (620, 150), (220, 480), (600, 470), (410, 310)]
    active_decoys = []

    # AIR + GROUND: the jet flies in the sky, missiles launch from trucks/silos on the ground
    GROUND_Y = 540
    LAUNCH_SITES = [67, 200, 333, 467, 600, 733]   # one launcher per stretch of ground, edge to edge
    SILO_SITE = 3                                  # boss waves launch from an armoured silo here
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
    zone_w = SCREEN_WIDTH / len(LAUNCH_SITES)
    launchers = [{"x": float(x), "lo": i * zone_w + 32, "hi": (i + 1) * zone_w - 32,
                  "vx": random.choice((-1, 1)) * random.uniform(0.5, 1.1),
                  "hp": 1, "max_hp": 1, "alive": True, "reloads": 0, "reload_cd": 0}
                 for i, x in enumerate(LAUNCH_SITES)]

    def reset_launchers(lvl):
        boss = lvl % 10 == 0
        for i, ln in enumerate(launchers):
            ln["max_hp"] = 4 if boss and i == SILO_SITE else 2   # hits needed: at least two
            ln["hp"] = ln["max_hp"]
            ln["laser_frames"] = 0
            ln["alive"] = True
            ln["reloads"] = (1 + lvl // 40) if "RELOAD" in active_tactics(lvl) else 0
            ln["reload_cd"] = random.randint(300, 600)

    def launcher_rect(ln):
        return pygame.Rect(ln["x"] - 30, GROUND_Y - 30, 60, 32)

    def move_launchers(is_boss_wave, enemies):
        for i, ln in enumerate(launchers):
            if not ln["alive"]:
                continue
            if is_boss_wave and i == SILO_SITE:
                ln["x"] = float(LAUNCH_SITES[SILO_SITE])
                continue
            ln["x"] += ln["vx"]
            if ln["x"] < ln["lo"] or ln["x"] > ln["hi"]:
                ln["vx"] = -ln["vx"]
                ln["x"] = max(ln["lo"], min(ln["hi"], ln["x"]))
            elif random.random() < 0.004:
                ln["vx"] = -ln["vx"]          # change direction now and then
        for e in enemies:                     # a waiting missile rides on its launcher
            if e.launch_delay > 0 and e.site is not None:
                e.x = launchers[e.site]["x"] - e.width // 2

    def draw_launchers(is_boss_wave):
        for i, ln in enumerate(launchers):
            lx = int(ln["x"])
            if not ln["alive"]:
                pygame.draw.rect(screen, (35, 30, 28), (lx - 28, GROUND_Y - 10, 56, 10), border_radius=3)   # wreck
                pygame.draw.circle(screen, (60, 60, 65), (lx + random.randint(-6, 6), GROUND_Y - 18 - random.randint(0, 10)), random.randint(4, 8))
                continue
            if ln["hp"] < ln["max_hp"]:   # one block per hit left, shown once it has been hit
                seg = 44 // ln["max_hp"]
                for k in range(ln["max_hp"]):
                    col = (90, 230, 90) if k < ln["hp"] else (60, 20, 20)
                    pygame.draw.rect(screen, col, (lx - 22 + k * seg, GROUND_Y - 70, seg - 2, 5))
            if is_boss_wave and i == SILO_SITE:
                pygame.draw.rect(screen, (60, 60, 70), (lx - 26, GROUND_Y - 8, 52, 14))      # missile silo
                pygame.draw.rect(screen, (255, 40, 80), (lx - 26, GROUND_Y - 8, 52, 14), 2)
                pygame.draw.rect(screen, (20, 20, 25), (lx - 14, GROUND_Y - 6, 28, 8))
            else:
                cab_x = lx + 14 if ln["vx"] > 0 else lx - 30   # cab at the front, facing the way it drives
                pygame.draw.rect(screen, (70, 80, 60), (lx - 30, GROUND_Y - 16, 60, 14), border_radius=3)  # launcher truck
                pygame.draw.rect(screen, (90, 100, 75), (cab_x, GROUND_Y - 26, 16, 12), border_radius=2)  # cab
                pygame.draw.line(screen, (120, 125, 110), (lx - 4, GROUND_Y - 16), (lx - 4, GROUND_Y - 58), 4)  # launch rail
                for wx in (lx - 20, lx, lx + 20):
                    pygame.draw.circle(screen, (25, 25, 28), (wx, GROUND_Y - 1), 6)

    current_level = 1
    total_score = 0
    active_mutator = "NONE"
    saved_data = load_save_data()

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
        if near and ap["mode"] != "break" and not (ap["mode"] == "roll" and near[0] > 140):
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
        else:  # loop: keep pulling up until a full circle is flown
            step = 2 * math.pi / 100
            ap["head"] += -step if facing_right else step
            ap["loop_left"] -= step
            if ap["loop_left"] <= 0:
                ap["mode"], ap["t"] = "cruise", 90
            want = ap["head"]
            spd = cruise * 1.25

        # stay in the sky: turn back from the side edges, pull up near the ground, push down near the top
        if cx < 180:
            want = 0.0
        elif cx > SCREEN_WIDTH - 180:
            want = math.pi
        if cy > GROUND_Y - 150 and math.sin(want) > -0.3:
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
    p2_x, p2_y = 650.0, 300.0
    p2_speed = 4.4
    p2_max_hp = 120
    p2_hp = p2_max_hp
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
                         ground_y=GROUND_Y, launch_delay=delay)
        e.site = site
        e.flank_angle = flank_angle if flank_angle is not None else random.uniform(0, 2 * math.pi)
        return e

    def spawn_campaign_wave(lvl):
        nonlocal p1_max_hp
        # the jet grows tougher with the level too: max HP 300 -> 600 by level 101
        p1_max_hp = 300 + min(300, (lvl - 1) * 3)
        reset_launchers(lvl)
        enemies = []
        is_boss = (lvl % 10 == 0)
        if is_boss:
            enemies.append(launch_missile(lvl, SILO_SITE, 60, is_boss=True))
        else:
            num = min(4, 1 + (lvl // 15))
            spin = random.uniform(0, 2 * math.pi)
            for i in range(num):
                # missiles lift off one after another from launchers spread over the ground;
                # each gets its own flank angle so a FLANK wave attacks from different sides
                site = (i * 2 + random.randint(0, 1)) % len(launchers)
                enemies.append(launch_missile(lvl, site, 40 + i * 50, flank_angle=spin + i * 2 * math.pi / num))
        return enemies

    def damage_launcher(i, hits=1):
        """A launcher needs at least two hits (silo four); when destroyed, any missile still on it goes too."""
        nonlocal total_score
        ln = launchers[i]
        ln["hp"] -= hits
        if ln["hp"] <= 0 and ln["alive"]:
            ln["alive"] = False
            ln["reloads"] = 0
            SFX.snd_explode.play()
            total_score += 150
            for e in campaign_enemies[:]:
                if e.site == i and e.launch_delay > 0:
                    campaign_enemies.remove(e)

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
        p2_x, p2_y = 650.0, 300.0
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
    FIRE_C, FIRE_R = (715, 480), 58
    TOUCH_BUTTONS = [   # label, key it presses (None = held shield), centre, radius
        ("SHIELD", None, (598, 522), 30),
        ("HEAL", pygame.K_q, (598, 448), 26),
        ("SQUAD", pygame.K_t, (565, 378), 30),
        ("STEALTH", pygame.K_v, (630, 378), 30),
        ("CAMO", pygame.K_c, (695, 378), 30),
        ("FLARES", pygame.K_f, (760, 378), 30),
    ]
    TOUCH_MENU = pygame.Rect(SCREEN_WIDTH - 74, 32, 62, 24)
    CARD1 = pygame.Rect(55, 150, 335, 325)
    CARD2 = pygame.Rect(410, 150, 335, 325)
    touch_font = pygame.font.SysFont("consolas", 12, bold=True)
    touch_big = pygame.font.SysFont("consolas", 20, bold=True)
    last_fit_ms = -1000

    def post_key(k):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))

    def touch_aim_target(cx, cy):
        """FIRE on a phone aims at the nearest flying missile, else the nearest launcher."""
        if game_state == "CAMPAIGN":
            flying = [e for e in campaign_enemies if not e.is_burrowed]
            if flying:
                e = min(flying, key=lambda e: math.hypot(e.x + e.width / 2 - cx, e.y + e.height / 2 - cy))
                return e.x + e.width / 2, e.y + e.height / 2
            alive = [ln for ln in launchers if ln["alive"]]
            if alive:
                ln = min(alive, key=lambda ln: abs(ln["x"] - cx))
                return ln["x"], GROUND_Y - 14
        elif game_state == "DUEL" and p2_hp > 0 and not p2_is_burrowed:
            return p2_x + 40, p2_y + 25
        return None

    def finger_down(tx, ty, fid):
        touch["on"] = True
        if game_state == "MODE_SELECT":
            if CARD1.collidepoint(tx, ty):
                post_key(pygame.K_1)
            elif CARD2.collidepoint(tx, ty):
                post_key(pygame.K_2)
            return
        if game_state not in ("CAMPAIGN", "DUEL"):
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
        for label, key, c, r in TOUCH_BUTTONS:
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

    def draw_touch_controls():
        ui = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        base = touch["origin"] if touch["stick_id"] is not None else (120, 470)
        knob = (base[0] + touch["vec"][0] * STICK_R, base[1] + touch["vec"][1] * STICK_R)
        pygame.draw.circle(ui, (0, 229, 212, 45), base, STICK_R)
        pygame.draw.circle(ui, (0, 229, 212, 170), base, STICK_R, 3)
        pygame.draw.circle(ui, (0, 229, 212, 190), (int(knob[0]), int(knob[1])), 26)
        firing = bool(touch["fire_ids"])
        pygame.draw.circle(ui, (255, 70, 70, 235) if firing else (225, 40, 55, 190), FIRE_C, FIRE_R)
        pygame.draw.circle(ui, (255, 255, 255, 230), FIRE_C, FIRE_R, 4)
        for label, key, c, r in TOUCH_BUTTONS:
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
            held = label == "SHIELD" and bool(touch["shield_ids"])
            col = (0, 200, 255, 235) if held else ((40, 120, 200, 200) if ready else (60, 65, 80, 160))
            pygame.draw.circle(ui, col, c, r)
            pygame.draw.circle(ui, (230, 240, 255, 220), c, r, 2)
        screen.blit(ui, (0, 0))
        t = touch_big.render("FIRE", True, (255, 255, 255))
        screen.blit(t, t.get_rect(center=FIRE_C))
        for label, key, c, r in TOUCH_BUTTONS:
            t = touch_font.render(label, True, (255, 255, 255))
            screen.blit(t, t.get_rect(center=c))
        mv = touch_font.render("FLY", True, (180, 255, 245))
        screen.blit(mv, mv.get_rect(center=(base[0], base[1] + STICK_R + 12)))
        if game_state == "CAMPAIGN":
            pygame.draw.rect(screen, (30, 40, 60), TOUCH_MENU, border_radius=6)
            pygame.draw.rect(screen, (150, 170, 210), TOUCH_MENU, 1, border_radius=6)
            t = touch_font.render("MENU", True, (220, 230, 255))
            screen.blit(t, t.get_rect(center=TOUCH_MENU.center))

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

            # Mouse: clicking a mode card on the start screen picks that mode
            if game_state == "MODE_SELECT" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if CARD1.collidepoint(event.pos):
                    post_key(pygame.K_1)
                elif CARD2.collidepoint(event.pos):
                    post_key(pygame.K_2)

            # Game controller (player 1): using it hides the touch buttons. D-pad left/right = previous/next
            # level, up = stealth, down = camouflage. Desktop reports the d-pad as a hat, browsers as buttons 12-15.
            if event.type in (pygame.JOYBUTTONDOWN, pygame.JOYHATMOTION, pygame.JOYAXISMOTION) and getattr(event, "joy", 0) == 0:
                if event.type != pygame.JOYAXISMOTION or abs(event.value) > 0.5:
                    touch["on"] = False
            if game_state in ("CAMPAIGN", "DUEL"):
                dpad = None
                if event.type == pygame.JOYHATMOTION and event.joy == 0:
                    hx, hy = event.value
                    dpad = {(-1, 0): "left", (1, 0): "right", (0, 1): "up", (0, -1): "down"}.get((hx, hy))
                elif event.type == pygame.JOYBUTTONDOWN and event.joy == 0 and sys.platform == "emscripten":
                    dpad = {12: "up", 13: "down", 14: "left", 15: "right"}.get(event.button)
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
                    p1_max_hp = 300 + min(300, (current_level - 1) * 3)
                    p1_hp = p1_max_hp
                    p1_med_kits = 6
                    p1_decoys = 6
                    p1_split_charges = 3
                    p1_power_tier = 1
                    p1_power_charge = 0.0
                    SFX.snd_win.play()

                elif (event.type == pygame.KEYDOWN and event.key in (pygame.K_2, pygame.K_KP2)) or \
                     (event.type == pygame.JOYBUTTONDOWN and event.button == 1):
                    game_state = "DUEL"
                    p1_max_hp = 120
                    p1_hp = p1_max_hp
                    p1_med_kits = 2
                    p1_decoys = 3
                    p1_split_charges = 2
                    p1_power_tier = 1
                    p1_power_charge = 0.0
                    p2_max_hp = 120
                    p2_hp = p2_max_hp
                    p2_decoys = 3
                    p2_power_tier = 1
                    p2_power_charge = 0.0
                    SFX.snd_win.play()

            # P1 Heal
            if game_state in ("CAMPAIGN", "DUEL") and p1_med_kits > 0 and p1_hp < p1_max_hp:
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_m)) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button in (1, 2, 3)):
                    heal_amt = 60 if game_state == "CAMPAIGN" else 35
                    p1_hp = min(p1_max_hp, p1_hp + heal_amt)
                    p1_med_kits -= 1
                    SFX.snd_heal.play()
                    floating_texts.append([f"+{heal_amt} HP", p1_x + 10, p1_y - 20, (100, 255, 120), 35])

            # P1 Multi-Image Illusion Ring (Ravan / Shadow Clone Array on 'F' / Triangle)
            if game_state in ("CAMPAIGN", "DUEL") and p1_decoys > 0:
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_f) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button == 3):
                    p1_decoys -= 1
                    clone_count = 8
                    radius = 75
                    for i in range(clone_count):
                        angle = (2.0 * math.pi / clone_count) * i
                        cx = p1_x + math.cos(angle) * radius
                        cy = p1_y + math.sin(angle) * radius
                        active_decoys.append({"x": cx, "y": cy, "life": 260, "type": "p1"})
                    SFX.snd_decoy.play()
                    floating_texts.append(["8-MIRAGE ILLUSION ACTIVE!", p1_x - 30, p1_y - 30, (0, 240, 255), 45])

            # P1 TRIPLE JET SQUAD: SPLIT INTO 3 JETS (Key 'T' or Controller R3/Touchpad)
            if game_state in ("CAMPAIGN", "DUEL") and p1_split_charges > 0 and p1_split_timer == 0:
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_t) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button in (8, 10, 11)):
                    p1_split_charges -= 1
                    p1_split_timer = 480  # 8 full seconds of 3 combat jets
                    SFX.snd_split.play()
                    floating_texts.append(["TRIPLE JET SQUAD!", p1_x - 40, p1_y - 35, (255, 215, 60), 50])

            # P1 STEALTH (Key 'V'): 2 s invisible to missiles and launchers
            if game_state in ("CAMPAIGN", "DUEL") and p1_stealth_cd == 0 and p1_hp > 0:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_v:
                    p1_stealth_timer = STEALTH_DURATION
                    p1_stealth_cd = STEALTH_COOLDOWN
                    p1_stealth_x, p1_stealth_y = p1_x + 50, p1_y + 40
                    SFX.snd_decoy.play()

            # P1 CAMOUFLAGE (Key 'C' or Controller Share): fade out, missiles head for the last seen spot
            if game_state in ("CAMPAIGN", "DUEL") and p1_camo_cd == 0 and p1_hp > 0:
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_c) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p1 and event.joy == 0 and event.button == 6):
                    p1_camo_timer = CAMO_DURATION
                    p1_camo_cd = CAMO_COOLDOWN
                    p1_camo_x, p1_camo_y = p1_x + 50, p1_y + 40
                    SFX.snd_decoy.play()

            # P2 Decoy in Duel
            if game_state == "DUEL" and p2_decoys > 0:
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_KP7, pygame.K_LEFTBRACKET)) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p2 and event.joy == 1 and event.button == 4):
                    p2_decoys -= 1
                    clone_count = 6
                    radius = 70
                    for i in range(clone_count):
                        angle = (2.0 * math.pi / clone_count) * i
                        cx = p2_x + math.cos(angle) * radius
                        cy = p2_y + math.sin(angle) * radius
                        active_decoys.append({"x": cx, "y": cy, "life": 240, "type": "p2"})
                    SFX.snd_decoy.play()
                    floating_texts.append(["MISSILE HOLOGRAM DEPLOYED!", p2_x - 30, p2_y - 25, (200, 100, 255), 35])

            # P2 Burrow in Duel
            if game_state == "DUEL" and not p2_is_burrowed and p2_burrow_cd == 0:
                if (event.type == pygame.KEYDOWN and event.key in (pygame.K_KP_ENTER, pygame.K_SLASH)) or \
                   (event.type == pygame.JOYBUTTONDOWN and ps_pad_p2 and event.joy == 1 and event.button == 5):
                    nearest = min(burrow_holes, key=lambda h: math.hypot(h[0] - (p2_x + 40), h[1] - (p2_y + 25)))
                    if math.hypot(nearest[0] - (p2_x + 40), nearest[1] - (p2_y + 25)) < 110:
                        p2_is_burrowed = True
                        p2_burrow_timer = 90
                        p2_burrow_cd = 240
                        SFX.snd_burrow.play()

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

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                game_state = "MODE_SELECT"

        draw_world()

        # ======================================================================
        # STATE 1: MODE SELECT SCREEN
        # ======================================================================
        if game_state == "MODE_SELECT":
            t_surf = title_font.render("JET vs MISSILE", True, (255, 140, 0))
            sub_surf = font.render("CHOOSE GAMEPLAY MODE", True, (0, 220, 255))
            screen.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 45))
            screen.blit(sub_surf, (SCREEN_WIDTH // 2 - sub_surf.get_width() // 2, 90))

            lb_txt = f"BEST RECORD: LEVEL {saved_data.get('max_level_reached', 1)} | HIGH SCORE: {saved_data.get('high_score', 0)}"
            screen.blit(font.render(lb_txt, True, (255, 215, 60)), (SCREEN_WIDTH // 2 - 200, 120))

            card1 = pygame.Rect(55, 150, 335, 325)
            pygame.draw.rect(screen, (18, 22, 38), card1, border_radius=12)
            pygame.draw.rect(screen, (255, 140, 0), card1, 2, border_radius=12)

            screen.blit(big_font.render("1P CAMPAIGN", True, (255, 180, 80)), (75, 168))
            lines1 = [
                "Jet vs AI Missile Swarm",
                "[PLAYER GETS 3X EVERYTHING]:",
                "- 3x Max HP (300 Health) & Med-Kits",
                "- Press 'T': SPLIT INTO 3 ATTACK JETS",
                "- Auto-splits into 3 on Boss Waves!",
                "- 8-Clone Mirage Illusion on 'F'",
                "- Continuous Lasers (Press 'L')",
                "- Past Level 100: Endless Overdrive",
                "",
                ">> PRESS '1' OR CROSS (X) <<",
            ]
            y_c1 = 202
            for ln in lines1:
                col = (100, 255, 150) if ">>" in ln else ((255, 215, 60) if "'T'" in ln or "'L'" in ln or "'F'" in ln else ((255, 220, 100) if "3X" in ln or "SPLIT" in ln else (210, 220, 235)))
                screen.blit(font.render(ln, True, col), (70, y_c1))
                y_c1 += 22

            card2 = pygame.Rect(410, 150, 335, 325)
            pygame.draw.rect(screen, (18, 22, 38), card2, border_radius=12)
            pygame.draw.rect(screen, (0, 210, 255), card2, 2, border_radius=12)

            screen.blit(big_font.render("2P DUEL (PVP)", True, (0, 220, 255)), (435, 168))
            lines2 = [
                "P1 (Jet) vs P2 (Missile)",
                "[EQUAL BALANCED COMBAT]:",
                "- Equal 120 HP for both players",
                "- P1: Press 'T' to split into 3 units",
                "- P2 missile has no guns: ram the jet",
                "- Jet lasers at tiers 3-5 (Press 'L')",
                "- Camouflage [C] & Dogfight Autopilot",
                "- P2 Burrow & Teleport Ambush",
                "",
                ">> PRESS '2' OR CIRCLE (O) <<",
            ]
            y_c2 = 202
            for ln in lines2:
                col = (100, 255, 150) if ">>" in ln else ((0, 240, 255) if "EQUAL" in ln else (210, 220, 235))
                screen.blit(font.render(ln, True, col), (425, y_c2))
                y_c2 += 22

            pad_msg = "Game Controller Connected" if ps_pad_p1 else ("Touch Screen" if touch["on"] else "Keyboard Connected")
            screen.blit(font.render(f"Controller: {pad_msg} | Esc to Switch Modes", True, (160, 170, 190)), (SCREEN_WIDTH // 2 - 190, 505))
            if touch["on"]:
                hint = big_font.render("TAP A CARD TO PLAY", True, (100, 255, 150))
                screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 540)))
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

            r_msg = "ROUND WON BY THE JET!" if break_winner == "P1" else "ROUND WON BY THE MISSILES!"
            r_col = (255, 180, 80) if break_winner == "P1" else (0, 220, 255)
            screen.blit(title_font.render(r_msg, True, r_col), (SCREEN_WIDTH // 2 - 270, 240))
            screen.blit(font.render("RESTORING POSITIONS...", True, (200, 210, 230)), (SCREEN_WIDTH // 2 - 90, 290))

            if break_timer <= 0:
                if milestone_reward_pending:
                    # every-5th-win bonus
                    milestone_reward_pending = False
                    if prev_mode == "CAMPAIGN":
                        p1_hp = min(p1_max_hp, p1_hp + 10)   # +40 below = +50, as before
                        p1_med_kits = min(6, p1_med_kits + 1)
                        p1_decoys = min(6, p1_decoys + 1)
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

                reset_positions()

            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(0)
            continue

        # Draw Stealth Holes
        for hole in burrow_holes:
            pygame.draw.circle(screen, (35, 10, 50), hole, 22)
            pygame.draw.circle(screen, (160, 40, 255), hole, 22, 2)
            pygame.draw.circle(screen, (10, 5, 20), hole, 16)
        # ground missile launchers
        if game_state == "CAMPAIGN":
            move_launchers(current_level % 10 == 0, campaign_enemies)
            draw_launchers(current_level % 10 == 0)

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

        for dec in active_decoys[:]:
            dec["life"] -= 1
            if dec["life"] <= 0:
                active_decoys.remove(dec)

        # ======================================================================
        # PLAYER 1 CONTROLS
        # ======================================================================
        if p1_hp > 0:
            speed_mult = 1.35 if active_mutator == "HYPER SPEED STORM" else 1.0
            actual_p1_speed = p1_speed * speed_mult * (jet_pace(current_level) if game_state == "CAMPAIGN" else 1.0)

            pad_x = ps_pad_p1.get_axis(0) if ps_pad_p1 and abs(ps_pad_p1.get_axis(0)) > 0.15 else 0.0
            pad_y = ps_pad_p1.get_axis(1) if ps_pad_p1 and abs(ps_pad_p1.get_axis(1)) > 0.15 else 0.0

            in_x = (1 if (keys[pygame.K_d] or pad_x > 0.3) else 0) - (1 if (keys[pygame.K_a] or pad_x < -0.3) else 0)
            in_y = (1 if (keys[pygame.K_s] or pad_y > 0.3) else 0) - (1 if (keys[pygame.K_w] or pad_y < -0.3) else 0)
            if touch["stick_id"] is not None and math.hypot(*touch["vec"]) > 0.2:
                in_x, in_y = touch["vec"]          # thumb stick: fly where the thumb points
            old_head = math.atan2(p1_vy, p1_vx)
            if in_x or in_y:
                # manual: fly where the keys point, with a little momentum
                n = math.hypot(in_x, in_y)
                p1_vx += (in_x / n * actual_p1_speed - p1_vx) * 0.25
                p1_vy += (in_y / n * actual_p1_speed - p1_vy) * 0.25
                autopilot["head"] = math.atan2(p1_vy, p1_vx)
                autopilot["mode"], autopilot["t"], autopilot["roll"] = "cruise", 60, 0.0
            else:
                # hands off: the autopilot keeps the jet flying and manoeuvring
                if game_state == "CAMPAIGN":
                    threats = [(e.x + e.width / 2, e.y + e.height / 2, math.cos(e.heading) * e.speed_stat,
                                math.sin(e.heading) * e.speed_stat)
                               for e in campaign_enemies if not e.is_burrowed and e.launch_delay == 0]
                else:
                    threats = [(p2_x + 40, p2_y + 25, math.cos(math.radians(p2_angle)) * 4.0,
                                math.sin(math.radians(p2_angle)) * 4.0)] if p2_hp > 0 and not p2_is_burrowed else []
                want_vx, want_vy = autopilot_velocity(p1_x + 50, p1_y + 40, actual_p1_speed, threats)
                p1_vx += (want_vx - p1_vx) * 0.35
                p1_vy += (want_vy - p1_vy) * 0.35
            p1_x += p1_vx
            p1_y += p1_vy
            new_head = math.atan2(p1_vy, p1_vx)
            p1_turn_rate = (new_head - old_head + math.pi) % (2 * math.pi) - math.pi

            # the jet flies above the ground and inside the screen: bounce the velocity off the edges
            if p1_x < 10 or p1_x > SCREEN_WIDTH - 110:
                p1_x = max(10, min(SCREEN_WIDTH - 110, p1_x))
                p1_vx = -p1_vx * 0.5
            if p1_y < 55 or p1_y > GROUND_Y - 80:
                p1_y = max(55, min(GROUND_Y - 80, p1_y))
                p1_vy = -p1_vy * 0.5

            pad_guard = ps_pad_p1 and (ps_pad_p1.get_button(4) or ps_pad_p1.get_button(9) or ps_pad_p1.get_axis(4) > 0.3)
            if (keys[pygame.K_e] or pad_guard or touch["shield_ids"]) and p1_guard_energy > 5.0:
                p1_guard = True
                p1_guard_energy -= 0.6
            else:
                p1_guard = False
                if p1_guard_energy < 100.0:
                    p1_guard_energy += 0.3

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

            pad_shoot = ps_pad_p1 and (ps_pad_p1.get_button(0) or ps_pad_p1.get_button(5) or (ps_pad_p1.get_numaxes() > 5 and ps_pad_p1.get_axis(5) > 0.3))
            current_wpn = WEAPON_TIERS[p1_power_tier]
            on_level_bar = game_state == "CAMPAIGN" and mouse_pos[1] >= LEVEL_BAR_TOP   # clicking the strip doesn't shoot
            mouse_fire = mouse_buttons[0] and not on_level_bar and not touch["on"]   # a finger is not a mouse
            is_firing = (mouse_fire or touch["fire_ids"] or keys[pygame.K_SPACE] or pad_shoot) and not p1_guard

            # Calculate positions for the 3 jets when the squad is active
            jet_squad_origins = [(center_p1_x, center_p1_y)]
            if p1_split_timer > 0:
                w_off = 72 * jet_size_factor(center_p1_y)
                jet_squad_origins.append((center_p1_x - w_off, center_p1_y - w_off))
                jet_squad_origins.append((center_p1_x - w_off, center_p1_y + w_off))

            if current_wpn["type"] == "laser" and is_firing:
                p1_laser_active = True
                p1_laser_end_x = center_p1_x + math.cos(p1_aim_angle) * 900
                p1_laser_end_y = center_p1_y + math.sin(p1_aim_angle) * 900

                if random.random() < 0.2:
                    SFX.snd_laser.play()

                if active_mutator == "LOW GRAVITY ZONE":
                    p1_x -= math.cos(p1_aim_angle) * 1.5
                    p1_y -= math.sin(p1_aim_angle) * 1.5

                mult = (3 * level_power(current_level)) if game_state == "CAMPAIGN" else 1
                if p1_split_timer > 0:
                    mult *= 2.5
                laser_dmg = current_wpn["dmg"] * mult

                p1_dmg_box = pygame.Rect(min(center_p1_x, p1_laser_end_x) - 40, min(center_p1_y, p1_laser_end_y) - 40,
                                         abs(p1_laser_end_x - center_p1_x) + 80, abs(p1_laser_end_y - center_p1_y) + 80)

                if game_state == "CAMPAIGN":
                    for e in campaign_enemies:
                        if not e.is_burrowed and e.rect.colliderect(p1_dmg_box):
                            hit = laser_dmg * (0.5 if e.ecm_timer > 0 else 1.0)   # ECM halves laser damage
                            e.hp -= hit
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

                elif game_state == "DUEL" and p2_hp > 0 and not p2_is_burrowed:
                    p2_hitbox = pygame.Rect(p2_x + 10, p2_y + 10, 70, 45)
                    if p2_hitbox.colliderect(p1_dmg_box):
                        p2_hp = max(0, p2_hp - laser_dmg)
                        p2_flash_timer = 2
                        p1_power_charge += 1.5
                        if random.random() < 0.3:
                            hit_sparks.append([p2_x + 40, p2_y + 25, random.uniform(-4, 4), random.uniform(-4, 4), 3, current_wpn["color_outer"], 12])

                if p1_power_charge >= 100.0 and p1_power_tier < 5:
                    p1_power_charge = 0.0
                    p1_power_tier += 1
                    SFX.snd_win.play()
                    floating_texts.append([f"LASER UPGRADED: {WEAPON_TIERS[p1_power_tier]['name']}!", SCREEN_WIDTH // 2 - 140, 200, WEAPON_TIERS[p1_power_tier]["color_outer"], 45])

            elif current_wpn["type"] == "bullet":
                p1_dmg = int(current_wpn["dmg"] * ((3 * level_power(current_level)) if game_state == "CAMPAIGN" else 1))
                if p1_shoot_cd > 0:
                    p1_shoot_cd -= 1
                if is_firing and p1_shoot_cd == 0:
                    for ox, oy in jet_squad_origins:
                        p1_bullets.append({
                            "x": ox, "y": oy,
                            "vx": math.cos(p1_aim_angle) * current_wpn["speed"],
                            "vy": math.sin(p1_aim_angle) * current_wpn["speed"],
                            "radius": 6 + p1_power_tier,
                            "dmg": p1_dmg,
                            "color_outer": current_wpn["color_outer"],
                            "color_core": current_wpn["color_core"],
                        })
                    SFX.snd_shoot.play()
                    p1_shoot_cd = 12

        # ======================================================================
        # 1-PLAYER CAMPAIGN LOGIC
        # ======================================================================
        if game_state == "CAMPAIGN":
            p1_target_x = center_p1_x
            p1_target_y = center_p1_y

            p1_decoys_active = [d for d in active_decoys if d["type"] == "p1"]
            if len(p1_decoys_active) > 0:
                p1_target_x = p1_decoys_active[0]["x"] + 36
                p1_target_y = p1_decoys_active[0]["y"] + 30
            elif p1_camo_timer > 0:
                p1_target_x, p1_target_y = p1_camo_x, p1_camo_y
            if p1_stealth_timer > 0:
                p1_target_x, p1_target_y = p1_stealth_x, p1_stealth_y
                for e in campaign_enemies:
                    if e.launch_delay > 0:
                        e.launch_delay += 1   # launchers hold fire: no target to launch at

            for e in campaign_enemies:
                e.update(burrow_holes, p1_target_x, p1_target_y, SCREEN_WIDTH, SCREEN_HEIGHT, threats=p1_bullets)

            # PROXIMITY FUSE: a launcher's missile is built to bring the jet down. When it gets close
            # enough (a direct hit or a near miss) it blows itself up and the jet crashes. Only the
            # shield (E) survives the blast. The missile is gone either way; only missiles shot down
            # by the jet score points.
            jet_cx, jet_cy = p1_x + 50, p1_y + 40
            for e in campaign_enemies[:]:
                if e.is_burrowed or e.launch_delay > 0 or p1_hp <= 0 or p1_stealth_timer > 0:
                    continue
                ex, ey = e.x + e.width / 2, e.y + e.height / 2
                if math.hypot(ex - jet_cx, ey - jet_cy) > jet_fuse_radius(jet_cy) * (1.4 if e.is_boss else 1.0):
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
                        e.hp -= b["dmg"]
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
                    campaign_enemies.append(launch_missile(current_level, li, 45))

            # a downed jet always loses the round, even when the missile that got it was the
            # wave's last one (checking "wave cleared" first used to count that as a win)
            if p1_hp <= 0:
                start_jet_crash("CAMPAIGN")
            elif len(campaign_enemies) == 0 and not pending:
                handle_round_conclusion("P1", "CAMPAIGN")

        # ======================================================================
        # 2-PLAYER DUEL LOGIC
        # ======================================================================
        elif game_state == "DUEL":
            center_p2_x = p2_x + 40
            center_p2_y = p2_y + 25

            if p2_hp > 0:
                if p2_burrow_cd > 0:
                    p2_burrow_cd -= 1

                if p2_is_burrowed:
                    p2_burrow_timer -= 1
                    if p2_burrow_timer <= 0:
                        dest = random.choice(burrow_holes)
                        p2_x = dest[0] - 40
                        p2_y = dest[1] - 25
                        p2_is_burrowed = False
                        SFX.snd_burrow.play()
                else:
                    p2_pad_x = ps_pad_p2.get_axis(0) if ps_pad_p2 and abs(ps_pad_p2.get_axis(0)) > 0.15 else 0.0
                    p2_pad_y = ps_pad_p2.get_axis(1) if ps_pad_p2 and abs(ps_pad_p2.get_axis(1)) > 0.15 else 0.0

                    p2_vx, p2_vy = 0.0, 0.0
                    if keys[pygame.K_LEFT] or keys[pygame.K_KP4] or p2_pad_x < -0.3:
                        p2_vx -= p2_speed
                    if keys[pygame.K_RIGHT] or keys[pygame.K_KP6] or p2_pad_x > 0.3:
                        p2_vx += p2_speed
                    if keys[pygame.K_UP] or keys[pygame.K_KP8] or p2_pad_y < -0.3:
                        p2_vy -= p2_speed
                    if keys[pygame.K_DOWN] or keys[pygame.K_KP5] or keys[pygame.K_KP2] or p2_pad_y > 0.3:
                        p2_vy += p2_speed

                    if keys[pygame.K_RCTRL] or keys[pygame.K_KP_PERIOD] or (ps_pad_p2 and ps_pad_p2.get_button(5)):
                        p2_vx *= 1.6
                        p2_vy *= 1.6

                    p2_x += p2_vx
                    p2_y += p2_vy
                    p2_x = max(10, min(SCREEN_WIDTH - 90, p2_x))
                    p2_y = max(55, min(GROUND_Y - 60, p2_y))

                    aim_target_x = center_p1_x
                    aim_target_y = center_p1_y
                    p1_decoys_active = [d for d in active_decoys if d["type"] == "p1"]
                    if len(p1_decoys_active) > 0:
                        aim_target_x = p1_decoys_active[0]["x"] + 36
                        aim_target_y = p1_decoys_active[0]["y"] + 30
                    elif p1_camo_timer > 0:
                        aim_target_x, aim_target_y = p1_camo_x, p1_camo_y

                    p2_dx = aim_target_x - center_p2_x
                    p2_dy = aim_target_y - center_p2_y
                    p2_angle = math.degrees(math.atan2(p2_dy, p2_dx))

            if p2_flash_timer > 0:
                p2_flash_timer -= 1

            # P2's missile has no guns: like the AI missiles it wins by reaching the jet (proximity fuse).
            # Against a raised shield it blows itself up for nothing, and the jet wins the round.
            p2_hitbox = pygame.Rect(p2_x + 10, p2_y + 10, 70, 45)
            if p2_hp > 0 and p1_hp > 0 and not p2_is_burrowed and p1_stealth_timer == 0 and \
                    math.hypot(p2_x + 40 - center_p1_x, p2_y + 25 - center_p1_y) < jet_fuse_radius(center_p1_y):
                blasts.append([p2_x + 40, p2_y + 25, 0, 1.0])
                SFX.snd_explode.play()
                if p1_guard:
                    floating_texts.append(["BLOCKED!", center_p1_x - 20, center_p1_y - 40, (0, 255, 220), 20])
                    p2_hp = 0
                else:
                    p1_hp = 0

            for b in p1_bullets[:]:
                b_rect = pygame.Rect(b["x"] - 6, b["y"] - 6, 12, 12)
                if not p2_is_burrowed and p2_hitbox.colliderect(b_rect) and p2_hp > 0:
                    p2_hp = max(0, p2_hp - b["dmg"])
                    p2_flash_timer = 3
                    p1_bullets.remove(b)
                    SFX.snd_hit.play()
                    p1_power_charge += 24.0
                    if p1_power_charge >= 100.0 and p1_power_tier < 5:
                        p1_power_charge = 0.0
                        p1_power_tier += 1

            if p1_hp <= 0:
                p2_wins += 1
                start_jet_crash("DUEL")
            elif p2_hp <= 0:
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

        # Draw Cyber Laser Beams
        if p1_laser_active:
            wpn = WEAPON_TIERS[p1_power_tier]
            pygame.draw.line(screen, wpn["color_outer"], (center_p1_x, center_p1_y), (p1_laser_end_x, p1_laser_end_y), wpn["beam_w"] + 8)
            pygame.draw.line(screen, wpn["color_core"], (center_p1_x, center_p1_y), (p1_laser_end_x, p1_laser_end_y), wpn["beam_w"])
            pygame.draw.circle(screen, wpn["color_core"], (int(center_p1_x), int(center_p1_y)), wpn["beam_w"] + 4)

            # Draw clone jets' lasers if the squad is active
            if p1_split_timer > 0:
                w_off = 72 * jet_size_factor(center_p1_y)
                for ox, oy in [(center_p1_x - w_off, center_p1_y - w_off), (center_p1_x - w_off, center_p1_y + w_off)]:
                    lex = ox + math.cos(p1_aim_angle) * 900
                    ley = oy + math.sin(p1_aim_angle) * 900
                    pygame.draw.line(screen, wpn["color_outer"], (ox, oy), (lex, ley), wpn["beam_w"] + 4)
                    pygame.draw.line(screen, (255, 255, 255), (ox, oy), (lex, ley), max(2, wpn["beam_w"] - 2))


        for dec in active_decoys:
            alpha = 130 + int(math.sin(dec["life"] * 0.2) * 50)
            if dec["type"] == "p1":
                h_surf = pygame.transform.scale(create_jet_sprite(True, (0, 240, 255), alpha=alpha), (int(144 * JET_BASE_SCALE), int(120 * JET_BASE_SCALE)))
                screen.blit(h_surf, (dec["x"], dec["y"]))
                pygame.draw.circle(screen, (0, 240, 255), (int(dec["x"] + 36), int(dec["y"] + 30)), 45, 1)
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

            p1_aim = p1_aim_angle if 'p1_aim_angle' in locals() else 0.0
            pygame.draw.line(screen, WEAPON_TIERS[p1_power_tier]["color_outer"], (center_p1_x, center_p1_y),
                             (center_p1_x + math.cos(p1_aim) * 70 * jet_f, center_p1_y + math.sin(p1_aim) * 70 * jet_f), 3)

        # Draw Player 2 or Campaign Enemies
        if game_state == "CAMPAIGN":
            for e in campaign_enemies:
                e.draw(screen)
        elif game_state == "DUEL" and p2_hp > 0:
            if not p2_is_burrowed:
                # P2's missile grows from short range to hypersonic as its power tier rises
                p2_body_w, p2_body_h = MISSILE_BODY_W * 1.6, MISSILE_H * 1.6
                draw_missile_flame(screen, center_p2_x, center_p2_y, math.radians(p2_angle), p2_body_w, p2_body_h * 0.3,
                                   5, pygame.time.get_ticks() // 16)
                v_raw = pygame.transform.scale(create_missile_body(flash_white=(p2_flash_timer > 0), tier=5), (p2_body_w, p2_body_h))
                v_rot = pygame.transform.rotate(v_raw, -p2_angle)
                v_rect = v_rot.get_rect(center=(center_p2_x, center_p2_y))
                screen.blit(v_rot, v_rect.topleft)
            else:
                screen.blit(font.render("[UNDERGROUND]", True, (200, 100, 255)), (center_p2_x - 45, center_p2_y - 30))

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
        p1_title = "P1: JET (3X POWER)" if game_state == "CAMPAIGN" else "P1: JET"
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

        if game_state == "CAMPAIGN":
            lvl_col = (255, 60, 90) if current_level > 100 else (255, 230, 100)
            lvl_txt = f"OVERDRIVE WAVE {current_level}" if current_level > 100 else f"LEVEL {current_level} / 100"
            screen.blit(font.render(lvl_txt, True, lvl_col), (SCREEN_WIDTH // 2 - 80, 12))
            pw = level_power(current_level)
            screen.blit(font.render(f"POWER  JET x{pw:.2f}  MISSILE x{pw:.2f}", True, (200, 210, 240)), (SCREEN_WIDTH // 2 - 10, 30))
            tactics = active_tactics(current_level)
            screen.blit(font.render("AI: " + (", ".join(tactics) if tactics else "BASIC"), True, (255, 150, 150)), (SCREEN_WIDTH // 2 - 10, 46))

            if active_mutator != "NONE":
                screen.blit(font.render(f"MUTATOR: {active_mutator}", True, (255, 100, 200)), (SCREEN_WIDTH // 2 - 10, 62))

            screen.blit(font.render(f"SCORE: {total_score}", True, (200, 210, 240)), (SCREEN_WIDTH - 150, 12))
            draw_level_bar()

        elif game_state == "DUEL":
            p2_col = (0, 210, 255) if p2_hp > 35 else (255, 60, 60)
            p2_head = font.render("P2: MISSILE", True, (0, 210, 255))
            p2_num = num_font.render(f"HP: {int(p2_hp)} / {p2_max_hp}", True, p2_col)
            p2_sub = font.render(f"NO GUNS - RAM THE JET | WINS: {p2_wins}", True, (200, 210, 230))
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