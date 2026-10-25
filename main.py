import array
import asyncio
import functools
import math
from pathlib import Path
import random
import sys
import pygame

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
pygame.joystick.init()

# ==============================================================================
# FLIGHT TRAJECTORY (PERSISTENT HIGH-ALTITUDE CONTRAILS)
# ==============================================================================
class FlightTrajectory:
    def __init__(self, max_points=120, color=(220, 240, 255), width=2):
        self.points = []
        self.max_points = max_points
        self.color = color
        self.width = width

    def record(self, wx: float, wy: float):
        self.points.append([float(wx), float(wy)])
        if len(self.points) > self.max_points:
            self.points.pop(0)

    def draw(self, surface: pygame.Surface, cam_x: float, cam_y: float):
        n = len(self.points)
        if n < 2:
            return
        for i in range(1, n):
            p1 = (int(self.points[i - 1][0] - cam_x), int(self.points[i - 1][1] - cam_y))
            p2 = (int(self.points[i][0] - cam_x), int(self.points[i][1] - cam_y))
            frac = i / n
            pygame.draw.line(surface, self.color, p1, p2, max(1, int(self.width * frac)))


# ==============================================================================
# PROCEDURAL AUDIO SYNTHESIZER
# ==============================================================================
class RetroSoundEngine:
    @staticmethod
    def create_tone(freq_start: float, freq_end: float, duration: float, volume: float = 0.35) -> pygame.mixer.Sound:
        sample_rate = 44100
        total_samples = int(sample_rate * duration)
        raw_samples = array.array("h")
        for i in range(total_samples):
            t = i / total_samples
            freq = freq_start + (freq_end - freq_start) * t
            phase = (2.0 * math.pi * freq * (i / sample_rate)) % (2.0 * math.pi)
            val = math.sin(phase)
            sample_val = int(val * ((1.0 - t) ** 1.3) * 32767 * volume)
            raw_samples.append(sample_val)
            raw_samples.append(sample_val)
        return pygame.mixer.Sound(buffer=raw_samples)

    def __init__(self):
        self.snd_shoot = self.create_tone(840, 260, 0.08)
        self.snd_explode = self.create_tone(150, 40, 0.35)
        self.snd_ignite = self.create_tone(140, 380, 0.25)
        self.snd_switch = self.create_tone(600, 980, 0.1)

SFX = RetroSoundEngine()


# ==============================================================================
# 35,000-FT STRATOSPHERIC COUNTRY MAP
# ==============================================================================
class CountryLandscape:
    def __init__(self, world_w=14000, world_h=5000):
        self.world_w = world_w
        self.world_h = world_h
        rng = random.Random(2026)

        # Continental River Flow
        self.river_nodes = []
        rx, ry = 0.0, world_h * 0.45
        while rx <= world_w:
            self.river_nodes.append((rx, ry))
            rx += rng.uniform(180, 320)
            ry = max(world_h * 0.15, min(world_h * 0.85, ry + rng.uniform(-140, 140)))

        # Metropolises and Industrial Hubs
        self.cities = []
        for i in range(12):
            cx = 800 + i * 950 + rng.uniform(-150, 150)
            cy = rng.uniform(400, world_h - 400)
            c_size = rng.randint(240, 480)
            self.cities.append({"x": cx, "y": cy, "size": c_size, "name": f"SECTOR-{chr(65 + i)}"})

        # Dispersed Air Defense Fortresses (50 Installations / 1,000 Missiles)
        self.sam_sites = []
        for i in range(50):
            sx = 400 + (i / 50) * (world_w - 800) + rng.uniform(-100, 100)
            sy = rng.uniform(250, world_h - 250)
            self.sam_sites.append({"id": i, "x": sx, "y": sy, "missiles": 20, "hp": 2})

    def draw(self, surface: pygame.Surface, cam_x: float, cam_y: float, screen_w: int, screen_h: int):
        # 1. Base Continental Grassland
        surface.fill((28, 54, 34))

        # 2. Western Coastline & Ocean
        sea_coast_x = 700 - cam_x
        if sea_coast_x > 0:
            pygame.draw.rect(surface, (16, 36, 75), (0, 0, max(0, int(sea_coast_x)), screen_h))
            pygame.draw.line(surface, (180, 215, 230), (sea_coast_x, 0), (sea_coast_x, screen_h), 4)

        # 3. Farmland Pastures
        grid_step = 280
        start_gx = int((cam_x // grid_step) * grid_step)
        start_gy = int((cam_y // grid_step) * grid_step)
        for gx in range(start_gx - grid_step, start_gx + screen_w + grid_step, grid_step):
            for gy in range(start_gy - grid_step, start_gy + screen_h + grid_step, grid_step):
                field_rng = (gx * 73856093 ^ gy * 19349663) % 100
                field_col = (32, 60, 36) if field_rng > 50 else (26, 48, 30)
                pygame.draw.rect(surface, field_col, (int(gx - cam_x), int(gy - cam_y), grid_step - 14, grid_step - 14))

        # 4. Winding River
        for i in range(len(self.river_nodes) - 1):
            p1 = (int(self.river_nodes[i][0] - cam_x), int(self.river_nodes[i][1] - cam_y))
            p2 = (int(self.river_nodes[i + 1][0] - cam_x), int(self.river_nodes[i + 1][1] - cam_y))
            pygame.draw.line(surface, (20, 65, 110), p1, p2, 16)
            pygame.draw.line(surface, (45, 120, 180), p1, p2, 8)

        # 5. Cities & Infrastructure
        for c in self.cities:
            scx = int(c["x"] - cam_x)
            scy = int(c["y"] - cam_y)
            if -c["size"] <= scx <= screen_w + c["size"] and -c["size"] <= scy <= screen_h + c["size"]:
                pygame.draw.circle(surface, (65, 70, 75), (scx, scy), c["size"] // 2)
                half = c["size"] // 2
                for off in range(-half + 25, half, 35):
                    pygame.draw.line(surface, (190, 185, 130), (scx + off, scy - half + 10), (scx + off, scy + half - 10), 2)
                    pygame.draw.line(surface, (190, 185, 130), (scx - half + 10, scy + off), (scx + half - 10, scy + off), 2)

        # 6. Fortified Air Defense Installations
        for s in self.sam_sites:
            sx = int(s["x"] - cam_x)
            sy = int(s["y"] - cam_y)
            if -40 <= sx <= screen_w + 40 and -40 <= sy <= screen_h + 40:
                pygame.draw.circle(surface, (40, 48, 42), (sx, sy), 14)
                pygame.draw.circle(surface, (0, 230, 180), (sx, sy), 5)
                pygame.draw.rect(surface, (80, 95, 85), (sx + 8, sy - 8, 8, 16), border_radius=2)


# ==============================================================================
# SQUADRON AIRCRAFT (10X SLOWER REALISTIC BASE SPEED)
# ==============================================================================
class SquadronJet:
    def __init__(self, jet_id: int, x: float, y: float, hue: float, callsign: str):
        self.id = jet_id
        self.x, self.y = x, y
        self.heading = 0.0
        self.base_speed = 0.35  # 10x slower base stratospheric drift
        self.hue = hue
        self.callsign = callsign
        self.hp = 300
        self.trajectory = FlightTrajectory(max_points=110, color=self.get_contrail_color(), width=2)

    def get_contrail_color(self):
        c = pygame.Color(0)
        c.hsva = (self.hue % 360, 60, 100, 100)
        return (c.r, c.g, c.b)

    def get_paint(self):
        def hsv(h, s, v):
            c = pygame.Color(0)
            c.hsva = (h % 360, max(0, min(100, s)), max(0, min(100, v)), 100)
            return (c.r, c.g, c.b)
        return (hsv(self.hue, 50, 85), hsv(self.hue, 65, 45), hsv(self.hue - 20, 25, 95))


@functools.lru_cache(maxsize=32)
def draw_jet_model_topdown(paint):
    surf = pygame.Surface((38, 38), pygame.SRCALPHA)
    body, dark, edge = paint
    fuselage = [(36, 19), (22, 14), (8, 16), (2, 19), (8, 22), (22, 24)]
    wing_left = [(22, 14), (10, 2), (4, 4), (12, 16)]
    wing_right = [(22, 24), (10, 36), (4, 34), (12, 22)]
    tail_l = [(8, 16), (2, 8), (0, 10), (4, 18)]
    tail_r = [(8, 22), (2, 30), (0, 28), (4, 20)]

    for w in (wing_left, wing_right, tail_l, tail_r):
        pygame.draw.polygon(surf, dark, w)
        pygame.draw.polygon(surf, edge, w, 1)
    pygame.draw.polygon(surf, body, fuselage)
    pygame.draw.polygon(surf, edge, fuselage, 1)
    pygame.draw.ellipse(surf, (255, 215, 60), (22, 17, 8, 4))
    return surf


# ==============================================================================
# MISSILES & SLOW-FALLING ORDNANCE
# ==============================================================================
class SAMMissile:
    def __init__(self, x: float, y: float, tx: float, ty: float, speed: float = 0.65):
        self.x, self.y = x, y
        self.heading = math.atan2(ty - y, tx - x)
        self.speed = speed
        self.trajectory = FlightTrajectory(max_points=80, color=(255, 120, 40), width=3)

    def update(self, tx: float, ty: float):
        desired = math.atan2(ty - self.y, tx - self.x)
        diff = (desired - self.heading + math.pi) % (2 * math.pi) - math.pi
        self.heading += max(-0.025, min(0.025, diff))
        self.x += math.cos(self.heading) * self.speed
        self.y += math.sin(self.heading) * self.speed
        self.trajectory.record(self.x, self.y)

    def draw(self, surface: pygame.Surface, cam_x: float, cam_y: float):
        self.trajectory.draw(surface, cam_x, cam_y)
        sx, sy = int(self.x - cam_x), int(self.y - cam_y)
        pygame.draw.circle(surface, (255, 120, 30), (sx, sy), 4)


class DroppedBomb:
    def __init__(self, x: float, y: float, heading: float, spd: float):
        self.x, self.y = x, y
        self.vx = math.cos(heading) * spd
        self.vy = math.sin(heading) * spd
        self.altitude = 35000.0
        self.trajectory = FlightTrajectory(max_points=60, color=(255, 230, 100), width=1)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.altitude -= 140.0
        self.trajectory.record(self.x, self.y)

    def draw(self, surface: pygame.Surface, cam_x: float, cam_y: float):
        self.trajectory.draw(surface, cam_x, cam_y)
        sx, sy = int(self.x - cam_x), int(self.y - cam_y)
        r = max(2, int(6 * (self.altitude / 35000.0)))
        pygame.draw.circle(surface, (255, 220, 90), (sx, sy), r)


# ==============================================================================
# MAIN ASYNC LOOP WITH 100 PROGRESSIVE LEVELS
# ==============================================================================
async def main():
    SCREEN_W, SCREEN_H = 1024, 600
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Stratospheric Command: 100 Levels of Real-World Flight")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 12, bold=True)
    big_font = pygame.font.SysFont("consolas", 16, bold=True)

    country = CountryLandscape(world_w=14000, world_h=5000)

    # 10 High-Altitude Aircraft
    squadron = []
    callsigns = ["VIPER-1", "EAGLE-2", "GHOST-3", "TITAN-4", "HAWK-5", "FALCON-6", "RAVEN-7", "SHADOW-8", "VALKYRIE-9", "OMEGA-10"]
    for i in range(10):
        hue = (i * 36) % 360
        squadron.append(SquadronJet(i, 1600 + (i % 5) * 120, 1200 + (i // 5) * 95, hue, callsigns[i]))

    active_jet_idx = 0
    current_level = 1  # Progression across 100 Levels

    active_missiles = []
    dropped_bombs = []
    blasts = []

    cam_x, cam_y = 1200.0, 900.0

    LEVEL_BAR_TOP = SCREEN_H - 28
    LEVEL_SLOT_W = 38

    def get_level_speed(lvl: int) -> float:
        # Starts 10x slower at 0.35 px/frame; increases by 0.01 per level up to 1.35 at Level 100
        return 0.35 + (min(100, max(1, lvl)) - 1) * 0.01

    running = True
    while running:
        speed_factor = get_level_speed(current_level)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    active_jet_idx = (active_jet_idx + 1) % len(squadron)
                    SFX.snd_switch.play()
                elif event.key == pygame.K_SPACE:
                    cur = squadron[active_jet_idx]
                    dropped_bombs.append(DroppedBomb(cur.x, cur.y, cur.heading, speed_factor * 0.9))
                    SFX.snd_shoot.play()
                elif event.key == pygame.K_m:
                    cur = squadron[active_jet_idx]
                    nearest = min(country.sam_sites, key=lambda s: math.hypot(s["x"] - cur.x, s["y"] - cur.y))
                    if nearest["missiles"] > 0:
                        nearest["missiles"] -= 1
                        active_missiles.append(SAMMissile(nearest["x"], nearest["y"], cur.x, cur.y, speed=speed_factor * 1.3))
                        SFX.snd_ignite.play()
                elif event.key == pygame.K_n:
                    # Next Level
                    current_level = min(100, current_level + 1)
                elif event.key == pygame.K_p:
                    # Previous Level
                    current_level = max(1, current_level - 1)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # Check level bar click
                if my >= LEVEL_BAR_TOP:
                    lo = max(1, current_level - 5)
                    x0 = SCREEN_W // 2 - (11 * LEVEL_SLOT_W) // 2
                    for i in range(11):
                        r = pygame.Rect(x0 + i * LEVEL_SLOT_W + 2, LEVEL_BAR_TOP + 2, LEVEL_SLOT_W - 4, 22)
                        if r.collidepoint(mx, my):
                            current_level = min(100, max(1, lo + i))
                            break
                else:
                    for i, j in enumerate(squadron):
                        if math.hypot((j.x - cam_x) - mx, (j.y - cam_y) - my) < 30:
                            active_jet_idx = i
                            SFX.snd_switch.play()
                            break

        cur_jet = squadron[active_jet_idx]

        # Gentle Camera Parallax (0.015 for realistic stratospheric floating)
        cam_x += ((cur_jet.x - SCREEN_W * 0.5) - cam_x) * 0.015
        cam_y += ((cur_jet.y - SCREEN_H * 0.5) - cam_y) * 0.015
        cam_x = max(0, min(country.world_w - SCREEN_W, cam_x))
        cam_y = max(0, min(country.world_h - SCREEN_H, cam_y))

        keys = pygame.key.get_pressed()

        # Update Squadron with Current Level Speed
        for idx, jet in enumerate(squadron):
            jet_speed = speed_factor
            if idx == active_jet_idx:
                steer_x = (1 if keys[pygame.K_RIGHT] or keys[pygame.K_d] else 0) - (1 if keys[pygame.K_LEFT] or keys[pygame.K_a] else 0)
                steer_y = (1 if keys[pygame.K_DOWN] or keys[pygame.K_s] else 0) - (1 if keys[pygame.K_UP] or keys[pygame.K_w] else 0)
                if steer_x or steer_y:
                    target_h = math.atan2(steer_y, steer_x)
                    diff = (target_h - jet.heading + math.pi) % (2 * math.pi) - math.pi
                    jet.heading += max(-0.035, min(0.035, diff))
            else:
                lead_off_x = cur_jet.x + ((idx % 5) - 2) * 130
                lead_off_y = cur_jet.y + ((idx // 5) * 2 - 1) * 90
                want_h = math.atan2(lead_off_y - jet.y, lead_off_x - jet.x)
                diff = (want_h - jet.heading + math.pi) % (2 * math.pi) - math.pi
                jet.heading += max(-0.025, min(0.025, diff))

            jet.x += math.cos(jet.heading) * jet_speed
            jet.y += math.sin(jet.heading) * jet_speed
            jet.x = max(100, min(country.world_w - 100, jet.x))
            jet.y = max(100, min(country.world_h - 100, jet.y))
            jet.trajectory.record(jet.x, jet.y)

        # Update Bombs
        for b in dropped_bombs[:]:
            b.update()
            if b.altitude <= 0:
                dropped_bombs.remove(b)
                blasts.append([b.x, b.y, 0])
                SFX.snd_explode.play()

        # Update Missiles
        for m in active_missiles[:]:
            m.update(cur_jet.x, cur_jet.y)
            if math.hypot(m.x - cur_jet.x, m.y - cur_jet.y) < 22:
                active_missiles.remove(m)
                cur_jet.hp = max(0, cur_jet.hp - 60)
                blasts.append([m.x, m.y, 0])
                SFX.snd_explode.play()

        # 1. Render Continent Map
        country.draw(screen, cam_x, cam_y, SCREEN_W, SCREEN_H)

        # 2. Render Bombs Plunging Downward
        for b in dropped_bombs:
            b.draw(screen, cam_x, cam_y)

        # 3. Render Climbing SAM Missiles
        for m in active_missiles:
            m.draw(screen, cam_x, cam_y)

        # 4. Render 10 Squadron Jets
        for idx, jet in enumerate(squadron):
            jet.trajectory.draw(screen, cam_x, cam_y)
            model = draw_jet_model_topdown(jet.get_paint())
            rot = pygame.transform.rotate(model, -math.degrees(jet.heading))
            sx, sy = int(jet.x - cam_x), int(jet.y - cam_y)
            screen.blit(rot, rot.get_rect(center=(sx, sy)))

            if idx == active_jet_idx:
                pygame.draw.circle(screen, (0, 230, 255), (sx, sy), 26, 1)
                tag = font.render(f"[{jet.callsign}]", True, (0, 230, 255))
                screen.blit(tag, (sx - tag.get_width() // 2, sy - 34))

        # Explosions
        for bl in blasts[:]:
            bl[2] += 1
            if bl[2] > 20:
                blasts.remove(bl)
            else:
                pygame.draw.circle(screen, (255, 140, 30), (int(bl[0] - cam_x), int(bl[1] - cam_y)), bl[2] * 2)

        # Minimap (Top Right)
        map_w, map_h = 240, 68
        rx, ry = SCREEN_W - map_w - 20, 20
        pygame.draw.rect(screen, (10, 16, 26), (rx, ry, map_w, map_h), border_radius=4)
        pygame.draw.rect(screen, (0, 200, 255), (rx, ry, map_w, map_h), 1, border_radius=4)

        for s in country.sam_sites:
            bx = rx + int((s["x"] / country.world_w) * map_w)
            by = ry + int((s["y"] / country.world_h) * map_h)
            pygame.draw.circle(screen, (0, 200, 140), (bx, by), 2)

        cam_bx = rx + int((cam_x / country.world_w) * map_w)
        cam_by = ry + int((cam_y / country.world_h) * map_h)
        pygame.draw.rect(screen, (255, 215, 60), (cam_bx, cam_by, max(4, int((SCREEN_W / country.world_w) * map_w)), max(4, int((SCREEN_H / country.world_h) * map_h))), 1)
        screen.blit(font.render("COUNTRY RADAR (35,000 FT)", True, (0, 200, 255)), (rx + 4, ry + 4))

        # Level Strip (Bottom of Screen)
        pygame.draw.rect(screen, (10, 14, 22), (0, LEVEL_BAR_TOP, SCREEN_W, SCREEN_H - LEVEL_BAR_TOP))
        screen.blit(font.render("[P] PREV", True, (180, 190, 210)), (20, LEVEL_BAR_TOP + 6))
        screen.blit(font.render("NEXT [N]", True, (180, 190, 210)), (SCREEN_W - 85, LEVEL_BAR_TOP + 6))

        lo = max(1, current_level - 5)
        x0 = SCREEN_W // 2 - (11 * LEVEL_SLOT_W) // 2
        for i in range(11):
            lvl = lo + i
            if lvl <= 100:
                r = pygame.Rect(x0 + i * LEVEL_SLOT_W + 2, LEVEL_BAR_TOP + 2, LEVEL_SLOT_W - 4, 22)
                cur = lvl == current_level
                pygame.draw.rect(screen, (255, 140, 0) if cur else (26, 32, 48), r, border_radius=3)
                pygame.draw.rect(screen, (255, 220, 100) if cur else (70, 85, 110), r, 1, border_radius=3)
                lbl = font.render(str(lvl), True, (20, 20, 20) if cur else (220, 225, 240))
                screen.blit(lbl, lbl.get_rect(center=r.center))

        # Command HUD
        hud_title = f"STRATOSPHERE LEVEL {current_level}/100 | SPEED: {speed_factor:.2f} px/f"
        screen.blit(big_font.render(hud_title, True, (255, 215, 80)), (20, 20))
        status_txt = f"ACTIVE PILOT: {cur_jet.callsign} [TAB: Switch Jet 1-10] | SQUADRON: 10 CAP READY"
        screen.blit(font.render(status_txt, True, (200, 225, 245)), (20, 44))
        ctrl_txt = "[TAB] Switch Plane  |  [W/A/S/D] Fly  |  [SPACE] Drop Bomb  |  [M] SAM Launch  |  [N/P] Level 1-100"
        screen.blit(font.render(ctrl_txt, True, (160, 200, 230)), (20, 64))

        pygame.display.flip()
        clock.tick(60)
        await asyncio.sleep(0)

    pygame.quit()

if __name__ == "__main__":
    asyncio.run(main())
