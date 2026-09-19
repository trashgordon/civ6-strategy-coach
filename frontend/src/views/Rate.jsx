// Blind A/B rating: two plans for one brief, which setting wrote which kept hidden until
// you've picked. The eval says whether a plan is correct; this is how we learn whether
// it's any good.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { DISPLAY, T } from "../theme";
import { Markdown } from "../markdown";
import { Button, Empty, ErrorNote, Panel, Tag } from "../components/ui";

function setupLine(brief) {
  const cfg = brief.config || {};
  const bits = [
    brief.civ || "Coach picks the civ",
    brief.primary_focus, brief.city_philosophy, brief.posture,
    cfg.ruleset, cfg.difficulty, cfg.gameSpeed && `${cfg.gameSpeed} speed`,
    cfg.mapType && `${cfg.mapType}${cfg.mapSize ? ` · ${cfg.mapSize}` : ""}`,
  ];
  return bits.filter((b) => b && b !== "No preference");
}

function Verdict({ onPick, disabled }) {
  const [note, setNote] = useState("");
  const pick = (side) => onPick(side, note);

  useEffect(() => {
    // 1 / 2 / T from the keyboard, unless you're typing a note.
    function onKey(e) {
      if (disabled || e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === "1") pick("left");
      if (e.key === "2") pick("right");
      if (e.key.toLowerCase() === "t") pick("tie");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div
      style={{
        position: "sticky", bottom: "calc(env(safe-area-inset-bottom, 0px) + 0.75rem)",
        background: T.panel, border: `1px solid ${T.line}`, borderRadius: "8px",
        padding: "0.8rem", display: "flex", flexWrap: "wrap", gap: "0.6rem",
        alignItems: "center", boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
      }}
    >
      <Button onClick={() => pick("left")} disabled={disabled}>Plan 1 is better</Button>
      <Button variant="ghost" onClick={() => pick("tie")} disabled={disabled}>About the same</Button>
      <Button onClick={() => pick("right")} disabled={disabled}>Plan 2 is better</Button>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Why? (optional)"
        aria-label="Why you picked it"
        style={{
          flex: "1 1 12rem", minWidth: 0, background: T.raised, color: T.text,
          border: `1px solid ${T.line}`, borderRadius: "6px", padding: "0.55rem 0.7rem",
          fontSize: "0.9rem",
        }}
      />
      <span style={{ color: T.muted, fontSize: "0.75rem" }}>Keys: 1 · T · 2</span>
    </div>
  );
}

function Summary({ summary }) {
  if (!summary.length) return null;
  const cell = { padding: "0.45rem 0.6rem", borderBottom: `1px solid ${T.line}`, fontSize: "0.85rem", textAlign: "left" };
  return (
    <Panel title="Results so far">
      <div className="compare-scroll">
        <table style={{ borderCollapse: "collapse", width: "100%", fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr style={{ color: T.muted }}>
              {["Experiment", "Setting", "Wins", "Ties", "Rated", "Verdict"].map((h) => (
                <th key={h} style={{ ...cell, fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {summary.map((s) => {
              const decided = s.a_wins + s.b_wins;
              const verdict = s.p_value == null
                ? "Nothing decided yet"
                : s.p_value < 0.05
                  ? `A real difference (p = ${s.p_value.toFixed(3)})`
                  : `Could still be chance (p = ${s.p_value.toFixed(2)}, ${decided} decided)`;
              return [
                <tr key={`${s.experiment}-a`}>
                  <td style={cell} rowSpan={2}><strong>{s.experiment}</strong></td>
                  <td style={cell}>A · {s.label_a}</td>
                  <td style={cell}>{s.a_wins}</td>
                  <td style={cell} rowSpan={2}>{s.ties}</td>
                  <td style={cell} rowSpan={2}>{s.pairs - s.unrated}/{s.pairs}</td>
                  <td style={cell} rowSpan={2}>{verdict}</td>
                </tr>,
                <tr key={`${s.experiment}-b`}>
                  <td style={cell}>B · {s.label_b}</td>
                  <td style={cell}>{s.b_wins}</td>
                </tr>,
              ];
            })}
          </tbody>
        </table>
      </div>
      <p style={{ color: T.muted, fontSize: "0.8rem", margin: "0.7rem 0 0", lineHeight: 1.5 }}>
        Ties don't count either way. With few pairs rated, even a lopsided split can be chance
        — the p-value says how likely it would be if the two settings were equally good.
      </p>
    </Panel>
  );
}

export default function Rate() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [revealed, setRevealed] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError("");
    setRevealed(null);
    try {
      setData(await api.ratings());
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function pick(side, note) {
    if (!data?.next || revealed || saving) return;
    setSaving(true);
    try {
      setRevealed({ ...(await api.rate(data.next.id, side, note)), side });
      setData({ ...data, summary: (await api.ratings()).summary });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!data) return null;

  const pair = data.next;
  if (!pair) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <Panel>
          <Empty>
            Nothing left to rate. Pair up two eval runs to compare two settings, then rate them here:
            <br />
            <code style={{ color: T.text }}>python -m evals.pairs make RUN_A RUN_B -e name</code>
          </Empty>
        </Panel>
        <Summary summary={data.summary} />
      </div>
    );
  }

  const label = (side) => revealed && (side === "left" ? revealed.left_label : revealed.right_label);
  const picked = (side) => revealed && revealed.side === side;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <Panel
        title={`Which plan is better? · ${pair.experiment}`}
        right={<Tag>{pair.brief_id}</Tag>}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.6rem" }}>
          {setupLine(pair.brief).map((b) => <Tag key={b} tone="brass">{b}</Tag>)}
        </div>
        {pair.brief.playstyle_text && (
          <blockquote style={{ margin: 0, color: T.muted, fontStyle: "italic", fontSize: "0.9rem" }}>
            “{pair.brief.playstyle_text}”
          </blockquote>
        )}
        <p style={{ color: T.muted, fontSize: "0.8rem", margin: "0.6rem 0 0" }}>
          Judge the strategy, not the polish: would you rather play Plan 1 or Plan 2? Which setting
          wrote which stays hidden until you've picked.
        </p>
      </Panel>

      {revealed && (
        <Panel style={{ borderColor: T.accent }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.8rem", justifyContent: "space-between" }}>
            <span>
              {revealed.winner_label
                ? <>You picked <strong>{revealed.winner_label}</strong>.</>
                : <>A tie between <strong>{revealed.left_label}</strong> and <strong>{revealed.right_label}</strong>.</>}
            </span>
            <Button onClick={load}>Next pair</Button>
          </div>
        </Panel>
      )}

      <div className="rate-grid">
        {["left", "right"].map((side, i) => (
          <div key={side} style={{ minWidth: 0 }}>
            <h3
              style={{
                fontFamily: DISPLAY, margin: "0 0 0.6rem", fontSize: "1.1rem",
                color: picked(side) ? T.accent : T.text,
              }}
            >
              Plan {i + 1}
              {label(side) && <span style={{ color: T.muted, fontWeight: 400, fontSize: "0.85rem" }}> · {label(side)}</span>}
            </h3>
            <Markdown text={pair[side]} layout="sections" buildId={`rate-${pair.id}-${side}`} />
          </div>
        ))}
      </div>

      {!revealed && <Verdict onPick={pick} disabled={saving} />}
      <Summary summary={data.summary} />
    </div>
  );
}
