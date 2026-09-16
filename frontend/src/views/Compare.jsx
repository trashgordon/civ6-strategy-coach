// Multi-select 2+ saved builds, then get the structured side-by-side table plus the
// coach's compare-and-contrast writeup.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Markdown } from "../markdown";
import { SERIF, T } from "../theme";
import {
  Button, Empty, ErrorNote, Panel, Thinking, UsageNote, formatDate,
} from "../components/ui";

const ROWS = [
  { key: "civ", label: "Civ" },
  { key: "primary_focus", label: "Primary focus" },
  { key: "posture", label: "Posture" },
  { key: "city_philosophy", label: "City philosophy" },
  { key: "ruleset", label: "Ruleset" },
  { key: "difficulty", label: "Difficulty" },
  { key: "map_type", label: "Map" },
];

const cellStyle = {
  padding: "0.6rem 0.75rem",
  borderBottom: `1px solid ${T.border}`,
  fontSize: "0.85rem",
  verticalAlign: "top",
  color: T.parchment,
};

const labelStyle = {
  ...cellStyle,
  color: T.parchmentDim,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.03em",
  whiteSpace: "nowrap",
};

function value(raw) {
  return raw && raw !== "No preference" ? raw : "—";
}

function CompareTable({ rows }) {
  return (
    <div className="compare-scroll">
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: "34rem" }}>
        <caption
          style={{
            captionSide: "top", textAlign: "left", fontFamily: SERIF,
            color: T.parchment, fontSize: "1.3rem", paddingBottom: "0.6rem",
          }}
        >
          Side by side
        </caption>
        <thead>
          <tr>
            <th style={{ ...labelStyle, textAlign: "left" }} scope="col">
              &nbsp;
            </th>
            {rows.map((row) => (
              <th
                key={row.id}
                scope="col"
                style={{
                  ...cellStyle, textAlign: "left", fontFamily: SERIF,
                  fontSize: "0.98rem", fontWeight: 400, color: T.parchment,
                  borderBottom: `1px solid ${T.brassDim}`,
                }}
              >
                {row.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((field) => (
            <tr key={field.key}>
              <th scope="row" style={{ ...labelStyle, textAlign: "left" }}>
                {field.label}
              </th>
              {rows.map((row) => (
                <td key={row.id} style={cellStyle}>
                  {value(row[field.key])}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <th scope="row" style={{ ...labelStyle, textAlign: "left" }}>
              Key techs / wonders
            </th>
            {rows.map((row) => (
              <td key={row.id} style={cellStyle}>
                {row.key_terms?.length ? (
                  <ul style={{ margin: 0, paddingLeft: "1.1rem", lineHeight: 1.6 }}>
                    {row.key_terms.map((term) => (
                      <li key={term}>{term}</li>
                    ))}
                  </ul>
                ) : (
                  "—"
                )}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default function Compare({ refreshKey, onCompared }) {
  const [builds, setBuilds] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [listError, setListError] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadList = useCallback(async () => {
    try {
      const body = await api.builds();
      setBuilds(body.builds);
      setListError(null);
    } catch (e) {
      setListError(e.message || "Couldn't load your archive.");
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList, refreshKey]);

  function toggle(id) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    );
  }

  async function runCompare() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.compare(selectedIds));
      onCompared?.();
    } catch (e) {
      setError(e.message || "Couldn't build that comparison.");
    } finally {
      setLoading(false);
    }
  }

  const enough = selectedIds.length >= 2;

  return (
    <div className="briefing-grid">
      <Panel
        title="Pick builds"
        right={
          <span style={{ color: T.parchmentDim, fontSize: "0.78rem" }}>
            {selectedIds.length} selected
          </span>
        }
      >
        {listError && <ErrorNote message={listError} onRetry={loadList} />}

        {!listError && builds.length < 2 && (
          <p style={{ color: T.parchmentDim, fontSize: "0.85rem", lineHeight: 1.6 }}>
            You need at least two saved builds to compare. Draft another strategy first.
          </p>
        )}

        <div style={{ maxHeight: "28rem", overflowY: "auto", margin: "0 -0.35rem" }}>
          {builds.map((build) => {
            const checked = selectedIds.includes(build.id);
            return (
              <label
                key={build.id}
                style={{
                  display: "flex", gap: "0.6rem", alignItems: "flex-start",
                  padding: "0.55rem 0.35rem", cursor: "pointer",
                  borderBottom: `1px solid ${T.border}`,
                  background: checked ? T.panelAlt : "transparent",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(build.id)}
                  style={{ accentColor: T.brass, marginTop: "0.2rem" }}
                />
                <span style={{ minWidth: 0 }}>
                  <span
                    style={{
                      display: "block", fontFamily: SERIF,
                      fontSize: "0.95rem", color: T.parchment,
                    }}
                  >
                    {build.title}
                  </span>
                  <span
                    style={{
                      display: "block", color: T.parchmentDim,
                      fontSize: "0.73rem", marginTop: "0.2rem",
                    }}
                  >
                    {formatDate(build.created_at)}
                  </span>
                </span>
              </label>
            );
          })}
        </div>

        <div
          style={{
            display: "flex", flexDirection: "column",
            gap: "0.5rem", marginTop: "1rem",
          }}
        >
          <Button onClick={runCompare} disabled={!enough || loading}>
            {loading ? "Comparing..." : "Compare selected"}
          </Button>
          {selectedIds.length > 0 && (
            <Button variant="ghost" onClick={() => setSelectedIds([])}>
              Clear selection
            </Button>
          )}
          {!enough && builds.length >= 2 && (
            <p style={{ color: T.parchmentDim, fontSize: "0.75rem", margin: 0 }}>
              Pick at least two (up to five).
            </p>
          )}
        </div>
      </Panel>

      <Panel style={{ minHeight: "16rem", padding: "1.5rem" }}>
        {loading && <Thinking label="The coach is laying the plans side by side" />}

        {!loading && error && <ErrorNote message={error} onRetry={runCompare} />}

        {!loading && !error && !result && (
          <Empty>
            Select two or more builds and the coach will tell you where they overlap,
            where they diverge, and which one to reach for when.
          </Empty>
        )}

        {!loading && result && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
            <CompareTable rows={result.rows} />
            <div style={{ maxWidth: "44rem" }}>
              <div
                style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "baseline", gap: "1rem", flexWrap: "wrap",
                  margin: "0 0 0.25rem",
                }}
              >
                <h3
                  style={{
                    fontFamily: SERIF, color: T.parchment, fontSize: "1.3rem",
                    margin: 0, fontWeight: 400,
                  }}
                >
                  The coach's read
                </h3>
                <UsageNote usage={result.usage} />
              </div>
              <Markdown text={result.writeup} />
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
