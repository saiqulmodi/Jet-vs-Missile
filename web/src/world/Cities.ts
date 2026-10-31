// City positions from main.py:399-407 (drawn in Phase 3). Drones already patrol over them (main.py:1022-1024),
// and launchers keep clear of them (main.py:449, 468).
import { CITY_COUNT, WORLD_H_PX, WORLD_W_PX } from '../config';

export interface CityPx {
  x: number; // main.py map px
  y: number;
  r: number;
}

export function makeCities(rand: () => number): CityPx[] {
  const out: CityPx[] = [];
  const gap = (WORLD_W_PX - 2600) / (CITY_COUNT - 1); // main.py:401
  for (let i = 0; i < CITY_COUNT; i++) {
    const x = 1500 + i * gap + (rand() * 360 - 180); // main.py:403
    const y = 1000 + rand() * (WORLD_H_PX - 550 - 1000); // main.py:404
    const r = 150 + Math.floor(rand() * 101); // main.py:405
    out.push({ x, y, r });
  }
  return out;
}
