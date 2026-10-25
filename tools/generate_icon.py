import pygame
import math
from pathlib import Path

def generate_tactical_icon(out_path="icons/icon.png"):
    pygame.init()
    size = 512
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    
    # Tactical dark navy background with circular radar sweep
    surface.fill((8, 14, 24))
    center = (size // 2, size // 2)
    
    # Concentric radar rings and crosshairs
    for r in (220, 160, 100, 45):
        pygame.draw.circle(surface, (24, 52, 80), center, r, 2)
    pygame.draw.line(surface, (24, 52, 80), (0, size // 2), (size, size // 2), 2)
    pygame.draw.line(surface, (24, 52, 80), (size // 2, 0), (size // 2, size), 2)
    
    # Glowing ballistic trajectory arc (neon orange flame track)
    pts = [(40 + i * 5, int(420 - math.sin(i * 0.038) * 250)) for i in range(86)]
    if len(pts) > 1:
        pygame.draw.lines(surface, (255, 90, 20), False, pts, 6)
        pygame.draw.lines(surface, (255, 230, 120), False, pts, 2)
        
    # Stealth Interceptor silhouette (Electric Cyan outline)
    jet_poly = [
        (390, 160), (330, 205), (210, 215), (130, 330), (155, 345), 
        (250, 265), (220, 390), (255, 380), (295, 295), (370, 275), 
        (440, 205), (470, 150)
    ]
    pygame.draw.polygon(surface, (20, 30, 45), jet_poly)
    pygame.draw.polygon(surface, (0, 230, 255), jet_poly, 4)
    
    # Missile warhead terminal intercept point
    pygame.draw.circle(surface, (255, 255, 255), (390, 160), 9)
    pygame.draw.circle(surface, (255, 60, 50), (390, 160), 18, 3)
    pygame.draw.circle(surface, (255, 210, 60), (390, 160), 28, 1)
    
    # Shield border with beveled corners
    pygame.draw.rect(surface, (0, 210, 255), (10, 10, size - 20, size - 20), 6, border_radius=36)
    
    Path("icons").mkdir(exist_ok=True)
    pygame.image.save(surface, out_path)
    print(f"Tactical App Icon generated at {out_path}")

if __name__ == "__main__":
    generate_tactical_icon()
