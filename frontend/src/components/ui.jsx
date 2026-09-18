// Shared building blocks. Every colour comes from a CSS variable (see theme.js), so
// these repaint when the theme changes without re-rendering.
import { useEffect, useState } from "react";
import { DISPLAY, SANS, T } from "../theme";

const LABEL = {
  fontFamily: DISPLAY,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.09em",
  fontSize: "0.72rem",
  color: T.muted,
};

export function FieldLabel({ children, htmlFor, style }) {
  return (
    <label htmlFor={htmlFor} style={{ ...LABEL, display: "block", marginBottom: "0.35rem", ...style }}>
      {children}
    </label>
  );
}

export function Panel({ title, children, style, right }) {
  return (
    <section
      style={{
        background: T.panel,
        border: `1px solid ${T.line}`,
        borderRadius: "8px",
        padding: "1.1rem",
        ...style,
      }}
    >
      {(title || right) && (
        <header
          style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: "0.75rem", marginBottom: "0.9rem",
          }}
        >
          {title && <h2 style={{ ...LABEL, fontSize: "0.78rem", margin: 0 }}>{title}</h2>}
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function FieldRow({ label, children }) {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: "0.75rem", padding: "0.45rem 0", borderBottom: `1px solid ${T.line}`,
      }}
    >
      <span style={{ color: T.muted, fontSize: "0.85rem" }}>{label}</span>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

const control = {
  background: T.raised,
  color: T.text,
  border: `1px solid ${T.line}`,
  borderRadius: "5px",
  padding: "0.4rem 0.55rem",
  fontSize: "0.9rem",
  fontFamily: SANS,
};

export function Select({ value, onChange, options, placeholder, style, ariaLabel, id }) {
  return (
    <select
      id={id}
      value={value}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      style={{ ...control, width: "100%", ...style }}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => {
        const opt = typeof o === "string" ? { value: o, label: o } : o;
        return (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        );
      })}
    </select>
  );
}

export function NumberInput({ value, onChange, min, max, ariaLabel, id, style }) {
  return (
    <input
      id={id}
      type="number"
      min={min}
      max={max}
      value={value}
      aria-label={ariaLabel}
      onChange={(e) => {
        const next = Number(e.target.value);
        if (Number.isNaN(next)) return;
        onChange(Math.min(max, Math.max(min, next)));
      }}
      style={{ ...control, width: "100%", fontVariantNumeric: "tabular-nums", ...style }}
    />
  );
}

export function TextInput({ value, onChange, placeholder, style, ariaLabel, onKeyDown, id }) {
  return (
    <input
      id={id}
      type="text"
      value={value}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      style={{ ...control, ...style }}
    />
  );
}

// A choice among a few options, as one strip of radio buttons.
export function Segmented({ name, value, options, onChange, columns, ariaLabel }) {
  const opts = options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  return (
    <fieldset
      className="seg"
      aria-label={ariaLabel}
      style={{ gridTemplateColumns: `repeat(${columns || opts.length}, minmax(0, 1fr))` }}
    >
      {opts.map((o) => {
        const id = `${name}-${o.value.replace(/\W+/g, "-").toLowerCase()}`;
        return (
          <span key={o.value} style={{ display: "contents" }}>
            <input
              type="radio"
              id={id}
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
            />
            <label htmlFor={id} title={o.title || o.label}>
              {o.label}
            </label>
          </span>
        );
      })}
    </fieldset>
  );
}

export function ToggleChip({ id, checked, onChange, children }) {
  return (
    <label className="chip-toggle" htmlFor={id}>
      <input type="checkbox" id={id} checked={checked} onChange={onChange} />
      <span>{children}</span>
    </label>
  );
}

export function Button({ children, onClick, disabled, variant = "primary", style, type, ...rest }) {
  const variants = {
    primary: {
      background: T.accent,
      color: T.onAccent,
      border: "1px solid transparent",
      fontFamily: DISPLAY,
      fontWeight: 700,
      textTransform: "uppercase",
      letterSpacing: "0.08em",
    },
    ghost: {
      background: "transparent",
      color: T.muted,
      border: `1px solid ${T.line}`,
      fontFamily: SANS,
      fontWeight: 500,
    },
    solid: {
      background: T.raised,
      color: T.text,
      border: `1px solid ${T.line}`,
      fontFamily: SANS,
      fontWeight: 500,
    },
  };
  return (
    <button
      {...rest}
      type={type || "button"}
      onClick={onClick}
      disabled={disabled}
      style={{
        borderRadius: "5px",
        padding: "0.5rem 0.9rem",
        fontSize: "0.85rem",
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.55 : 1,
        ...variants[variant],
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function Thinking({ label }) {
  return (
    <div style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
      <p style={{ color: T.text, fontSize: "1rem", margin: 0 }}>
        {label}
        <span className="dot">.</span>
        <span className="dot">.</span>
        <span className="dot">.</span>
      </p>
    </div>
  );
}

export function Empty({ children }) {
  return (
    <div style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
      <p style={{ color: T.muted, fontSize: "0.95rem", maxWidth: "30rem", margin: "0 auto", lineHeight: 1.6 }}>
        {children}
      </p>
    </div>
  );
}

export function ErrorNote({ message, onRetry }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      style={{
        border: `1px solid ${T.danger}`,
        background: T.dangerSoft,
        borderRadius: "6px",
        padding: "0.7rem 0.9rem",
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem",
      }}
    >
      <span style={{ color: T.text, fontSize: "0.88rem", lineHeight: 1.5 }}>{message}</span>
      {onRetry && (
        <Button variant="solid" onClick={onRetry} style={{ flexShrink: 0 }}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Tag({ children, tone = "dim" }) {
  const accent = tone === "brass" || tone === "accent";
  return (
    <span
      style={{
        display: "inline-block",
        fontFamily: DISPLAY,
        fontWeight: 600,
        fontSize: "0.7rem",
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        padding: "0.15rem 0.45rem",
        borderRadius: "3px",
        background: accent ? T.accentSoft : T.raised,
        color: accent ? T.accent : T.muted,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

// A yield-coloured tag for a plan section: Tech Path drives science, and so on.
export function YieldChip({ yieldKey, children }) {
  const color = T[yieldKey] || T.muted;
  return (
    <span
      style={{
        fontFamily: DISPLAY, fontWeight: 700, fontSize: "0.68rem", letterSpacing: "0.07em",
        textTransform: "uppercase", padding: "0.12rem 0.45rem", borderRadius: "3px",
        color, background: `color-mix(in srgb, ${color} 15%, transparent)`, whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

export function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

// A single call lands around a cent or two, so 2dp would flatten every call to the
// same "$0.02". Stay at 4dp until the running total is actually into dollars.
export function formatCost(cost) {
  if (cost === null || cost === undefined) return null;
  if (cost === 0) return "free";
  if (cost < 1) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

export function formatTokens(count) {
  if (count === null || count === undefined) return null;
  return count.toLocaleString();
}

export function UsageNote({ usage, style }) {
  if (!usage) return null;
  const cost = formatCost(usage.cost_usd);
  const inTokens = formatTokens(usage.prompt_tokens);
  const outTokens = formatTokens(usage.completion_tokens);
  const parts = [];
  if (inTokens && outTokens) parts.push(`${inTokens} in / ${outTokens} out`);
  // A null cost means the model isn't in the pricing table — say so rather than "$0".
  parts.push(cost ?? "cost unknown");
  return (
    <span
      style={{ color: T.muted, fontSize: "0.76rem", fontVariantNumeric: "tabular-nums", ...style }}
      title={`${usage.model || "model"} — token usage and estimated cost`}
    >
      {parts.join(" · ")}
    </span>
  );
}

// Names the coach asserted that aren't in the player's installed game data.
export function UnverifiedNames({ names }) {
  if (!names || !names.length) return null;
  return (
    <div
      role="note"
      style={{
        border: `1px solid color-mix(in srgb, ${T.warn} 50%, transparent)`,
        background: T.warnSoft,
        borderRadius: "6px",
        padding: "0.6rem 0.85rem",
        margin: "0 0 1rem",
        fontSize: "0.85rem",
        lineHeight: 1.55,
        color: T.text,
      }}
    >
      <strong style={{ color: T.warn, fontWeight: 600 }}>⚠ Not found in your game data:</strong>{" "}
      {names.join(", ")}
      <div style={{ color: T.muted, marginTop: "0.2rem" }}>
        The coach may have misremembered the name. Check before hunting for it in-game.
      </div>
    </div>
  );
}

const OUTCOME_TONES = {
  won: { color: T.ok, label: "Won" },
  lost: { color: T.danger, label: "Lost" },
  abandoned: { color: T.muted, label: "Abandoned" },
};

export function OutcomeBadge({ outcome, victoryType, endTurn }) {
  const tone = OUTCOME_TONES[outcome];
  if (!tone) return null;
  const detail = [victoryType, endTurn ? `T${endTurn}` : null].filter(Boolean).join(" · ");
  return (
    <span
      style={{
        display: "inline-block", fontFamily: DISPLAY, fontWeight: 600, fontSize: "0.7rem",
        letterSpacing: "0.06em", textTransform: "uppercase", padding: "0.15rem 0.45rem",
        borderRadius: "3px", color: tone.color,
        background: `color-mix(in srgb, ${tone.color} 14%, transparent)`, whiteSpace: "nowrap",
      }}
    >
      {tone.label}
      {detail ? ` · ${detail}` : ""}
    </span>
  );
}

// Win rates are meaningless without the sample they came from, so the record is
// always shown and the percentage is secondary.
export function WinRate({ won, lost, rate }) {
  const decided = won + lost;
  if (!decided) return <span style={{ color: T.muted, fontSize: "0.8rem" }}>—</span>;
  return (
    <span style={{ fontVariantNumeric: "tabular-nums", fontSize: "0.88rem" }}>
      <span style={{ color: T.text }}>{won}–{lost}</span>
      <span style={{ color: T.muted, fontSize: "0.8rem" }}> ({Math.round((rate ?? 0) * 100)}%)</span>
    </span>
  );
}

// System / light / dark. "System" leaves the choice to the OS; the other two pin it,
// and index.html applies the saved choice before first paint.
const THEME_OPTIONS = [
  { value: "system", label: "Auto", title: "Follow your system setting" },
  { value: "light", label: "Light", title: "Light theme" },
  { value: "dark", label: "Dark", title: "Dark theme" },
];

function readTheme() {
  try {
    const saved = localStorage.getItem("theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    try {
      if (theme === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", theme);
    } catch {
      // Storage blocked — the choice still applies for this session.
    }
  }, [theme]);
  return (
    <div style={{ width: "11.5rem" }}>
      <Segmented
        name="theme"
        ariaLabel="Colour theme"
        value={theme}
        options={THEME_OPTIONS}
        onChange={setTheme}
      />
    </div>
  );
}
