// Every colour is a CSS variable, defined once per theme in styles.css. Components
// never hold a literal colour, which is what lets the light/dark toggle repaint the
// whole app without a re-render.
export const T = {
  ground: "var(--ground)",
  bar: "var(--bar)",
  panel: "var(--panel)",
  raised: "var(--raised)",
  line: "var(--line)",
  text: "var(--text)",
  muted: "var(--muted)",
  accent: "var(--accent)",
  onAccent: "var(--on-accent)",
  accentSoft: "var(--accent-soft)",
  warn: "var(--warn)",
  warnSoft: "var(--warn-soft)",
  danger: "var(--danger)",
  dangerSoft: "var(--danger-soft)",
  ok: "var(--ok)",
  // Yields — semantic, and separate from the accent.
  science: "var(--y-science)",
  culture: "var(--y-culture)",
  faith: "var(--y-faith)",
  gold: "var(--y-gold)",
  production: "var(--y-production)",

  // Names from the original navy-and-brass theme, pointed at the new tokens so every
  // component keeps rendering sensibly.
  bg: "var(--ground)",
  bgHero: "var(--bar)",
  panelAlt: "var(--raised)",
  border: "var(--line)",
  brass: "var(--accent)",
  brassDim: "var(--muted)",
  parchment: "var(--text)",
  parchmentDim: "var(--muted)",
  rust: "var(--accent)",
};

// A condensed display face for labels and headings, its regular sibling for text —
// the pairing strategy-game interfaces use, and both self-hosted.
export const DISPLAY = '"Barlow Semi Condensed", "Arial Narrow", system-ui, sans-serif';
export const SANS = '"Barlow", system-ui, -apple-system, "Segoe UI", sans-serif';
// Headings were set in a serif before; they're the display face now.
export const SERIF = DISPLAY;
