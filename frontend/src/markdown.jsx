// The plan arrives as markdown. Two layouts:
//   "flow"     — one continuous column (the compare writeup)
//   "sections" — each "##" section as its own card, with the section-specific
//                treatments: yield chips, a turn track, a tickable Playbook.
import { useEffect, useState } from "react";
import { DISPLAY, SANS, T } from "./theme";
import { YieldChip } from "./components/ui";

function renderInline(text, keyBase) {
  // Bold first, then italics inside each non-bold run, so **bold** never gets eaten by
  // the single-asterisk pattern.
  const boldParts = text.split(/\*\*(.+?)\*\*/g);
  return boldParts.flatMap((part, i) => {
    if (i % 2 === 1) {
      return [
        <strong key={`${keyBase}-b${i}`} style={{ color: T.text, fontWeight: 600 }}>
          {part}
        </strong>,
      ];
    }
    return part.split(/(?<!\*)\*([^*\n]+)\*(?!\*)/g).map((piece, j) =>
      j % 2 === 1 ? <em key={`${keyBase}-i${i}-${j}`}>{piece}</em> : (
        <span key={`${keyBase}-t${i}-${j}`}>{piece}</span>
      )
    );
  });
}

const isTableLine = (line) => line.startsWith("|") && line.length > 1;

function parseCells(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

const isSeparatorRow = (cells) => cells.length > 0 && cells.every((c) => /^:?-{1,}:?$/.test(c));

// The block renderer: headers, lists, paragraphs, rules, tables.
function renderBlocks(text, prefix = "b") {
  const blocks = [];
  let listBuffer = [];
  let listType = null;
  let paraBuffer = [];
  let tableBuffer = [];

  function flushPara() {
    if (!paraBuffer.length) return;
    const key = `${prefix}-p${blocks.length}`;
    blocks.push(
      <p key={key} style={{ fontFamily: SANS, color: T.text, lineHeight: 1.6, margin: "0 0 0.6rem" }}>
        {renderInline(paraBuffer.join(" "), key)}
      </p>
    );
    paraBuffer = [];
  }

  function flushList() {
    if (!listBuffer.length) return;
    const Tag = listType === "ol" ? "ol" : "ul";
    const key = `${prefix}-l${blocks.length}`;
    blocks.push(
      <Tag key={key} style={{ margin: "0.3rem 0 0.7rem", paddingLeft: "1.2rem", color: T.text }}>
        {listBuffer.map((item, i) => (
          <li key={i} style={{ marginBottom: "0.3rem", lineHeight: 1.55 }}>
            {renderInline(item, `${key}-${i}`)}
          </li>
        ))}
      </Tag>
    );
    listBuffer = [];
    listType = null;
  }

  function flushTable() {
    if (!tableBuffer.length) return;
    const key = `${prefix}-t${blocks.length}`;
    const rows = tableBuffer.map(parseCells);
    tableBuffer = [];
    let header = null;
    let body = rows;
    if (rows.length > 1 && isSeparatorRow(rows[1])) {
      header = rows[0];
      body = rows.slice(2);
    }
    body = body.filter((cells) => !isSeparatorRow(cells));
    if (!header && !body.length) return;
    const cell = {
      padding: "0.45rem 0.6rem", borderBottom: `1px solid ${T.line}`, fontSize: "0.88rem",
      lineHeight: 1.5, textAlign: "left", verticalAlign: "top", color: T.text,
    };
    blocks.push(
      <div key={key} style={{ overflowX: "auto", margin: "0.5rem 0 0.9rem" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "20rem" }}>
          {header && (
            <thead>
              <tr>
                {header.map((h, i) => (
                  <th key={i} scope="col" style={{
                    ...cell, fontFamily: DISPLAY, fontWeight: 600, fontSize: "0.72rem",
                    textTransform: "uppercase", letterSpacing: "0.07em", color: T.muted,
                    borderBottom: `1px solid ${T.accent}`, whiteSpace: "nowrap",
                  }}>
                    {renderInline(h, `${key}-h${i}`)}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {body.map((cells, r) => (
              <tr key={r}>
                {cells.map((c, ci) => (
                  <td key={ci} style={{ ...cell, fontWeight: ci === 0 && header ? 600 : 400 }}>
                    {renderInline(c, `${key}-${r}-${ci}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function flush() {
    flushPara();
    flushList();
    flushTable();
  }

  text.split("\n").forEach((raw, idx) => {
    const trimmed = raw.trim();
    if (!trimmed) {
      flush();
      return;
    }
    if (isTableLine(trimmed)) {
      flushPara();
      flushList();
      tableBuffer.push(trimmed);
      return;
    }
    flushTable();

    if (/^-{3,}$/.test(trimmed)) {
      flush();
      blocks.push(<div key={`${prefix}-hr${idx}`} style={{ borderTop: `1px solid ${T.line}`, margin: "1rem 0" }} />);
      return;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.*)/);
    const ol = trimmed.match(/^\d+\.\s+(.*)/);
    const ul = trimmed.match(/^[-*]\s+(.*)/);

    if (heading) {
      flush();
      const level = heading[1].length;
      blocks.push(
        <h3 key={`${prefix}-h${idx}`} style={{
          fontFamily: DISPLAY, fontWeight: 700, color: T.text, margin: "1rem 0 0.4rem",
          fontSize: level === 3 ? "0.98rem" : "1.1rem",
        }}>
          {renderInline(heading[2], `${prefix}-h${idx}`)}
        </h3>
      );
    } else if (ol) {
      flushPara();
      if (listType !== "ol") flushList();
      listType = "ol";
      listBuffer.push(ol[1]);
    } else if (ul) {
      flushPara();
      if (listType !== "ul") flushList();
      listType = "ul";
      listBuffer.push(ul[1]);
    } else {
      flushList();
      paraBuffer.push(trimmed);
    }
  });

  flush();
  return blocks;
}

// ------------------------------------------------------------------ sections

// Chips only where the link is true: techs drive science, civics culture, religion faith.
const SECTION_YIELDS = {
  "Tech Path": { yieldKey: "science", label: "Science" },
  "Civic Path": { yieldKey: "culture", label: "Culture" },
  "Religious Beliefs": { yieldKey: "faith", label: "Faith" },
};

function splitSections(text) {
  const sections = [];
  let current = { title: null, body: [] };
  text.split("\n").forEach((line) => {
    const m = line.trim().match(/^##\s+(.+?)\s*$/);
    if (m) {
      if (current.title || current.body.join("").trim()) sections.push(current);
      current = { title: m[1], body: [] };
    } else {
      current.body.push(line);
    }
  });
  if (current.title || current.body.join("").trim()) sections.push(current);
  return sections.map((s) => ({ title: s.title, body: s.body.join("\n").trim() }));
}

function listItems(body) {
  return body
    .split("\n")
    .map((l) => l.trim().match(/^(?:[-*]|\d+[.)])\s+(.*)/))
    .filter(Boolean)
    .map((m) => m[1]);
}

const TURN = /\b(?:T|[Tt]urns?\s*~?)\s*(\d{2,4})/;

// Benchmarks drawn to scale on one axis. The full text stays in the list below; the
// track exists so "am I on pace?" is answerable at a glance.
function TurnTrack({ body }) {
  const points = listItems(body)
    // "Off-pace if you're not suzerain by T100" is a warning, not a milestone.
    .filter((item) => !/off[- ]pace|behind|if you('re| are)? not/i.test(item))
    .map((item) => {
      const m = item.match(TURN);
      return m ? Number(m[1]) : null;
    })
    .filter((n) => n !== null)
    .sort((a, b) => a - b);
  if (points.length < 2) return null;

  const end = Math.ceil((points[points.length - 1] * 1.08) / 10) * 10;
  let lastPos = -100;
  let lastRow = 1;
  const ticks = points.map((turn) => {
    const pos = (turn / end) * 100;
    // Stagger labels that would sit on top of each other.
    const row = pos - lastPos < 7 ? 1 - lastRow : 0;
    lastPos = pos;
    lastRow = row;
    return { turn, pos, row };
  });

  return (
    <div aria-hidden="true" style={{ position: "relative", height: "3.4rem", margin: "0.4rem 0.5rem 0.9rem" }}>
      <div style={{ position: "absolute", left: 0, right: 0, top: "0.55rem", height: "4px", borderRadius: "2px", background: T.raised }} />
      {ticks.map((t) => (
        <div key={t.turn} style={{
          position: "absolute", left: `${t.pos}%`, top: 0, transform: "translateX(-50%)",
          display: "grid", justifyItems: "center",
        }}>
          <i style={{ display: "block", width: "12px", height: "12px", borderRadius: "50%", marginTop: "0.25rem",
            background: T.panel, border: `2px solid ${T.accent}` }} />
          <span style={{
            fontSize: "0.72rem", color: T.muted, fontVariantNumeric: "tabular-nums",
            marginTop: t.row ? "1.15rem" : "0.2rem", whiteSpace: "nowrap",
          }}>
            T{t.turn}
          </span>
        </div>
      ))}
      <span style={{ position: "absolute", right: 0, top: "-0.15rem", fontSize: "0.66rem", color: T.muted }}>
        T{end}
      </span>
    </div>
  );
}

function loadChecked(key) {
  if (!key) return [];
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// The Playbook as a checklist. Ticks are remembered per build in this browser —
// they're a mid-game convenience, not something worth a server round-trip.
function Playbook({ body, buildId }) {
  const items = listItems(body);
  const key = buildId ? `playbook:${buildId}` : null;
  const [done, setDone] = useState(() => loadChecked(key));

  useEffect(() => {
    setDone(loadChecked(key));
  }, [key]);

  if (!items.length) return renderBlocks(body, "pb");

  function toggle(i) {
    setDone((prev) => {
      const next = prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i];
      try {
        if (key) localStorage.setItem(key, JSON.stringify(next));
      } catch {
        // Storage blocked — ticks still work for this session.
      }
      return next;
    });
  }

  return (
    <ul className="steps">
      {items.map((item, i) => {
        const id = `step-${buildId ?? "new"}-${i}`;
        return (
          <li key={i}>
            <label htmlFor={id}>
              <input type="checkbox" id={id} checked={done.includes(i)} onChange={() => toggle(i)} />
              <span>{renderInline(item, id)}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

function SectionCard({ title, body, buildId }) {
  const chip = SECTION_YIELDS[title];
  const isWarning = title === "What Goes Wrong";
  const isPlaybook = title === "The Playbook";
  const steps = isPlaybook ? listItems(body).length : 0;

  return (
    <section
      style={{
        background: T.panel,
        border: `1px solid ${T.line}`,
        // A severity stripe marks the one section about failure.
        borderLeft: isWarning ? `3px solid ${T.warn}` : `1px solid ${T.line}`,
        borderRadius: "8px",
        padding: "0.9rem 1rem 0.5rem",
      }}
    >
      {title && (
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem", marginBottom: "0.35rem" }}>
          <h3 style={{
            fontFamily: DISPLAY, fontWeight: 700, fontSize: "1.02rem", margin: 0,
            color: isWarning ? T.warn : T.text, letterSpacing: "0.01em",
          }}>
            {title}
          </h3>
          {chip && <YieldChip yieldKey={chip.yieldKey}>{chip.label}</YieldChip>}
          {isPlaybook && steps > 0 && <YieldChip yieldKey="accent">{steps} steps</YieldChip>}
        </header>
      )}
      {title === "Timing Benchmarks" && <TurnTrack body={body} />}
      {isPlaybook ? <Playbook body={body} buildId={buildId} /> : renderBlocks(body, title || "intro")}
    </section>
  );
}

export function Markdown({ text, layout = "flow", buildId }) {
  if (!text) return null;
  if (layout !== "sections") return <>{renderBlocks(text)}</>;
  return (
    <div style={{ display: "grid", gap: "0.75rem" }}>
      {splitSections(text).map((s, i) => (
        <SectionCard key={`${s.title}-${i}`} title={s.title} body={s.body} buildId={buildId} />
      ))}
    </div>
  );
}
