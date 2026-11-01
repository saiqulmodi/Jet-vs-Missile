// Game analytics, only through the shared Stratos page script (owner's rule, C:\Users\saiqu\GAME_ANALYTICS_RULE.md,
// 31-Oct-2026): one game = one flight, from take-off (level_start) until the jet you fly goes down (game_over with
// the seconds it lasted); the next flight starts the next game. game_open / play_time come from the Stratos script
// itself. No personal data. Never breaks the game: does nothing when Stratos is not there (local, GitHub Pages,
// offline).

type StratosLike = { track: (name: string, details?: Record<string, unknown>) => void };

function track(name: string, details: Record<string, unknown>): void {
  try {
    const w = window as unknown as { Stratos?: StratosLike; parent?: { Stratos?: StratosLike } };
    const S = w.Stratos || (w.parent && w.parent !== (window as unknown) ? w.parent.Stratos : undefined);
    if (S) S.track(name, details);
  } catch {
    // never let analytics break the game
  }
}

let startedAt = 0;

/** a flight begins (take-off / a new jet takes over) */
export function flightStart(level: number): void {
  startedAt = Date.now();
  track('level_start', { level });
}

/** the jet you fly is down: that game is over */
export function flightEnd(score = 0): void {
  if (!startedAt) return;
  const seconds = Math.round((Date.now() - startedAt) / 1000);
  startedAt = 0;
  track('game_over', { seconds, score });
}
