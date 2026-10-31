// The game's logo, as inline SVG (no image files). A radar-scope emblem with a sweeping beam; a delta jet
// climbs out of it while a missile chases it along a curling smoke trail and the jet's flares burst behind it;
// below, the name. Animated once on open (trail draws, missile flies, flares pop, letters rise), then it idles
// with a slow glow and the radar sweep.

export const LOGO_SVG = /* svg */ `
<svg class="logo" viewBox="0 0 640 460" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Jet vs Missile">
  <defs>
    <radialGradient id="lg-scope" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#0b2a44" stop-opacity="0.95"/>
      <stop offset="70%" stop-color="#06162a" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#020814" stop-opacity="0.6"/>
    </radialGradient>
    <linearGradient id="lg-sweep" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#00e6ff" stop-opacity="0"/>
      <stop offset="100%" stop-color="#00e6ff" stop-opacity="0.55"/>
    </linearGradient>
    <linearGradient id="lg-trail" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="45%" stop-color="#ffd2a0" stop-opacity="0.75"/>
      <stop offset="100%" stop-color="#ff7a1a" stop-opacity="1"/>
    </linearGradient>
    <linearGradient id="lg-jet" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#e9fbff"/>
      <stop offset="100%" stop-color="#7fb8cc"/>
    </linearGradient>
    <linearGradient id="lg-word1" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#9ff6ff"/>
      <stop offset="100%" stop-color="#00b8e6"/>
    </linearGradient>
    <linearGradient id="lg-word2" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#ffb070"/>
    </linearGradient>
    <filter id="lg-glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="lg-hot" x="-100%" y="-100%" width="300%" height="300%">
      <feGaussianBlur stdDeviation="6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="lg-clip"><circle cx="320" cy="170" r="128"/></clipPath>
  </defs>

  <!-- radar scope -->
  <g class="lg-scope">
    <circle cx="320" cy="170" r="128" fill="url(#lg-scope)"/>
    <circle cx="320" cy="170" r="128" fill="none" stroke="#00e6ff" stroke-width="3" class="lg-ring" filter="url(#lg-glow)"/>
    <circle cx="320" cy="170" r="88" fill="none" stroke="#00e6ff" stroke-opacity="0.25" stroke-width="1.5"/>
    <circle cx="320" cy="170" r="46" fill="none" stroke="#00e6ff" stroke-opacity="0.18" stroke-width="1.5"/>
    <path d="M192 170 H448 M320 42 V298" stroke="#00e6ff" stroke-opacity="0.15" stroke-width="1.5"/>
    <g clip-path="url(#lg-clip)">
      <path class="lg-sweep" d="M320 170 L448 170 A128 128 0 0 0 410 80 Z" fill="url(#lg-sweep)">
        <animateTransform attributeName="transform" type="rotate" from="0 320 170" to="-360 320 170" dur="4s" repeatCount="indefinite"/>
      </path>
    </g>
    <g stroke="#00e6ff" stroke-width="3" stroke-linecap="round" class="lg-ticks">
      <path d="M320 34 V48 M320 292 V306 M184 170 H198 M442 170 H456"/>
    </g>
  </g>

  <!-- missile smoke trail curling up toward the jet -->
  <path class="lg-trail" d="M150 330 C 170 250, 270 300, 268 226 S 300 150, 352 150"
        fill="none" stroke="url(#lg-trail)" stroke-width="7" stroke-linecap="round" pathLength="1"/>

  <!-- the missile rides the trail -->
  <g class="lg-missile" filter="url(#lg-glow)">
    <path d="M-15 -3.2 L9 -3.2 L16 0 L9 3.2 L-15 3.2 Z" fill="#f2f2ea"/>
    <path d="M-15 -3.2 L-20 -8 L-12 -3.2 Z M-15 3.2 L-20 8 L-12 3.2 Z" fill="#c8c8b8"/>
    <circle cx="-20" cy="0" r="5" fill="#ffb040" filter="url(#lg-hot)"/>
    <animateMotion dur="1.9s" begin="0.5s" fill="freeze" rotate="auto" keyPoints="0;0.93" keyTimes="0;1" calcMode="spline" keySplines="0.4 0 0.6 1"
                   path="M150 330 C 170 250, 270 300, 268 226 S 300 150, 352 150"/>
  </g>

  <!-- flares bursting behind the jet -->
  <g class="lg-flares" filter="url(#lg-hot)" fill="#fff6d8">
    <circle cx="372" cy="146" r="5"/><circle cx="356" cy="132" r="4"/><circle cx="388" cy="166" r="4"/>
    <circle cx="350" cy="160" r="3"/><circle cx="380" cy="128" r="3"/><circle cx="398" cy="148" r="3"/>
  </g>

  <!-- the jet climbing out of the scope -->
  <g class="lg-jet">
    <g transform="translate(430 96) rotate(48)">
      <path d="M0 -64 L7 -34 L9 -8 L48 22 L48 32 L9 22 L7 38 L21 50 L21 57 L0 51 L-21 57 L-21 50 L-7 38 L-9 22 L-48 32 L-48 22 L-9 -8 L-7 -34 Z"
            fill="url(#lg-jet)" stroke="#00e6ff" stroke-width="2" filter="url(#lg-glow)"/>
      <path d="M0 -40 L4 -24 L0 -16 L-4 -24 Z" fill="#1d2a3a"/>
      <circle cx="0" cy="60" r="7" fill="#ff8c28" filter="url(#lg-hot)" class="lg-burner"/>
    </g>
  </g>

  <!-- the name -->
  <g class="lg-word" font-family="'Arial Black', 'Segoe UI Black', Impact, sans-serif" font-weight="900" text-anchor="middle">
    <text class="lg-w1" x="196" y="402" font-size="74" fill="url(#lg-word1)" filter="url(#lg-glow)" transform="skewX(-10)" transform-origin="196 402">JET</text>
    <g class="lg-vs" transform="translate(318 380)">
      <path d="M-30 0 L0 -26 L30 0 L0 26 Z" fill="#ff7a1a" filter="url(#lg-hot)"/>
      <text x="0" y="9" font-size="26" fill="#140600">VS</text>
    </g>
    <text class="lg-w2" x="474" y="402" font-size="58" fill="url(#lg-word2)" filter="url(#lg-glow)" transform="skewX(-10)" transform-origin="474 402">MISSILE</text>
    <rect class="lg-underline" x="120" y="420" width="400" height="4" rx="2" fill="#00e6ff" opacity="0.8"/>
  </g>
</svg>`;

/** Small play / help icons (no words on the intro). */
export const PLAY_ICON = `<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="29" fill="none" stroke="currentColor" stroke-width="3"/><path d="M25 19 L47 32 L25 45 Z" fill="currentColor"/></svg>`;
export const HELP_ICON = `<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="29" fill="none" stroke="currentColor" stroke-width="3"/><path d="M24 25 a8 8 0 1 1 12 7 c-3 2 -4 3 -4 7" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="46" r="2.8" fill="currentColor"/></svg>`;
export const CLOSE_ICON = `<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M20 20 L44 44 M44 20 L20 44" stroke="currentColor" stroke-width="5" stroke-linecap="round"/></svg>`;
