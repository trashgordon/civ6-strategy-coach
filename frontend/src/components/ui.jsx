// Small shared pieces. Styling stays inline against the theme object, the way the
// prototype did it, so there's no CSS framework to learn.
import { T, SERIF, SANS } from "../theme";

export function Panel({ title, children, style, right }) {
  return (
    <section
      style={{
        background: T.panel,
        border: `1px solid ${T.border}`,
        borderRadius: "4px",
        padding: "1.25rem",
        ...style,
      }}
    >
      {(title || right) && (
        <header
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "0.75rem",
            marginBottom: "0.75rem",
          }}
        >
          {title && (
            <h2
              style={{
                fontFamily: SERIF,
                color: T.brass,
                fontSize: "1.05rem",
                margin: 0,
              }}
            >
              {title}
            </h2>
          )}
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
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "0.75rem",
        padding: "0.55rem 0",
        borderBottom: `1px solid ${T.border}`,
      }}
    >
      <span style={{ color: T.parchmentDim, fontSize: "0.85rem" }}>{label}</span>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

const controlStyle = {
  background: T.panelAlt,
  color: T.parchment,
  border: `1px solid ${T.border}`,
  borderRadius: "3px",
  padding: "0.3rem 0.5rem",
  fontSize: "0.85rem",
};

export function Select({ value, onChange, options, placeholder, style, ariaLabel }) {
  return (
    <select
      value={value}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      style={{ ...controlStyle, minWidth: "9rem", ...style }}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

export function NumberInput({ value, onChange, min, max, ariaLabel }) {
  return (
    <input
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
      style={{ ...controlStyle, width: "4.5rem" }}
    />
  );
}

export function TextInput({ value, onChange, placeholder, style, ariaLabel, onKeyDown }) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      style={{ ...controlStyle, padding: "0.45rem 0.6rem", ...style }}
    />
  );
}

export function Button({ children, onClick, disabled, variant = "primary", style, type }) {
  const variants = {
    primary: { background: disabled ? T.brassDim : T.rust, color: T.parchment, border: "none" },
    ghost: {
      background: "transparent",
      color: T.brassDim,
      border: `1px solid ${T.border}`,
    },
    solid: {
      background: T.panelAlt,
      color: T.parchment,
      border: `1px solid ${T.border}`,
    },
  };
  return (
    <button
      type={type || "button"}
      onClick={onClick}
      disabled={disabled}
      style={{
        borderRadius: "3px",
        padding: "0.5rem 0.9rem",
        fontFamily: SANS,
        fontWeight: variant === "primary" ? 600 : 500,
        fontSize: "0.85rem",
        cursor: disabled ? "default" : "pointer",
        opacity: disabled && variant !== "primary" ? 0.5 : 1,
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
      <p style={{ fontFamily: SERIF, color: T.parchment, fontSize: "1.05rem", margin: 0 }}>
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
      <div style={{ color: T.brassDim, fontSize: "1.2rem", marginBottom: "0.5rem" }}>◆</div>
      <p
        style={{
          color: T.parchmentDim,
          fontFamily: SERIF,
          fontSize: "1.05rem",
          maxWidth: "30rem",
          margin: "0 auto",
          lineHeight: 1.6,
        }}
      >
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
        border: `1px solid ${T.rust}`,
        background: "rgba(166, 82, 46, 0.12)",
        borderRadius: "3px",
        padding: "0.75rem 0.9rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
      }}
    >
      <span style={{ color: T.parchment, fontSize: "0.85rem", lineHeight: 1.5 }}>
        {message}
      </span>
      {onRetry && (
        <Button variant="solid" onClick={onRetry} style={{ flexShrink: 0 }}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Tag({ children, tone = "dim" }) {
  const colors = {
    dim: { color: T.parchmentDim, border: T.border },
    brass: { color: T.brass, border: T.brassDim },
  };
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "0.7rem",
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        padding: "0.15rem 0.45rem",
        borderRadius: "2px",
        border: `1px solid ${colors[tone].border}`,
        color: colors[tone].color,
        whiteSpace: "nowrap",
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
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
