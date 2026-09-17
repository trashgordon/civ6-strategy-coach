// What the archive is actually worth: whether these builds win.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { SERIF, T } from "../theme";
import { Empty, ErrorNote, Panel, WinRate } from "../components/ui";

function Figure({ label, value, hint }) {
  return (
    <div style={{ minWidth: "7rem" }}>
      <div
        style={{
          fontFamily: SERIF, color: T.parchment, fontSize: "1.6rem",
          fontVariantNumeric: "tabular-nums", lineHeight: 1.1,
        }}
      >
        {value}
      </div>
      <div style={{ color: T.parchmentDim, fontSize: "0.75rem", marginTop: "0.2rem" }}>
        {label}
      </div>
      {hint && (
        <div style={{ color: T.brassDim, fontSize: "0.7rem", marginTop: "0.1rem" }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function DimensionTable({ label, entries }) {
  if (!entries.length) return null;
  const cell = {
    padding: "0.4rem 0.6rem",
    borderBottom: `1px solid ${T.border}`,
    fontSize: "0.85rem",
    textAlign: "left",
  };
  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h3
        style={{
          fontFamily: SERIF, color: T.brass, fontSize: "1rem",
          fontWeight: 400, margin: "0 0 0.4rem",
        }}
      >
        {label}
      </h3>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <tbody>
          {entries.map((e) => (
            <tr key={e.value}>
              <td style={{ ...cell, color: T.parchment }}>{e.value}</td>
              <td style={{ ...cell, textAlign: "right", whiteSpace: "nowrap" }}>
                <WinRate won={e.won} lost={e.lost} rate={e.win_rate} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Stats({ refreshKey }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setStats(await api.stats());
      setError(null);
    } catch (e) {
      setError(e.message || "Couldn't load your stats.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  if (error) return <ErrorNote message={error} onRetry={load} />;
  if (!stats) return null;

  const { overall, by_dimension: byDimension, victories } = stats;
  const decided = overall.won + overall.lost;

  if (!decided && !overall.abandoned) {
    return (
      <Panel style={{ padding: "1.5rem" }}>
        <Empty>
          No results logged yet. Open a build in the Archive and record how the game
          actually went — once a few are in, this is where the patterns show up.
        </Empty>
      </Panel>
    );
  }

  const dimensions = Object.entries(byDimension).filter(
    ([, d]) => d.entries.length > 0
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <Panel title="Record">
        <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap" }}>
          <Figure
            label="Win rate"
            value={overall.win_rate === null ? "—" : `${Math.round(overall.win_rate * 100)}%`}
            hint={`${overall.won}–${overall.lost} decided`}
          />
          <Figure label="Won" value={overall.won} />
          <Figure label="Lost" value={overall.lost} />
          <Figure label="Abandoned" value={overall.abandoned} />
          <Figure
            label="Not recorded"
            value={overall.unrecorded}
            hint={overall.unrecorded ? "log these to sharpen the numbers" : null}
          />
          {stats.mean_winning_turn && (
            <Figure
              label="Avg winning turn"
              value={stats.mean_winning_turn}
              hint={stats.fastest_win_turn ? `fastest T${stats.fastest_win_turn}` : null}
            />
          )}
        </div>

        {decided > 0 && decided < 5 && (
          <p
            style={{
              color: T.brassDim, fontSize: "0.78rem", lineHeight: 1.6,
              margin: "1rem 0 0",
            }}
          >
            Only {decided} decided {decided === 1 ? "game" : "games"} so far — read these
            as a tally, not a trend.
          </p>
        )}
      </Panel>

      {victories.length > 0 && (
        <Panel title="Victories by type">
          <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
            {victories.map((v) => (
              <Figure key={v.victory_type} label={v.victory_type} value={v.count} />
            ))}
          </div>
        </Panel>
      )}

      {dimensions.length > 0 && (
        <Panel title="What actually wins">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(16rem, 1fr))",
              gap: "0 2rem",
            }}
          >
            {dimensions.map(([key, d]) => (
              <DimensionTable key={key} label={d.label} entries={d.entries} />
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
