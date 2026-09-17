import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { SANS, SERIF, T } from "./theme";
import { Button, ErrorNote, formatCost } from "./components/ui";
import NewBriefing from "./views/NewBriefing";
import Archive from "./views/Archive";
import Compare from "./views/Compare";
import Login from "./views/Login";

const TABS = [
  { key: "new", label: "New briefing" },
  { key: "archive", label: "Archive" },
  { key: "compare", label: "Compare" },
];

function Tabs({ active, onChange }) {
  return (
    <nav
      style={{ display: "flex", gap: "0.25rem", marginTop: "1.25rem" }}
      aria-label="Views"
    >
      {TABS.map((tab) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            aria-current={selected ? "page" : undefined}
            style={{
              background: selected ? T.panel : "transparent",
              color: selected ? T.parchment : T.parchmentDim,
              border: `1px solid ${selected ? T.border : "transparent"}`,
              borderBottom: `2px solid ${selected ? T.brass : "transparent"}`,
              borderRadius: "3px 3px 0 0",
              padding: "0.5rem 1rem",
              fontFamily: SANS,
              fontSize: "0.88rem",
              fontWeight: selected ? 600 : 400,
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState(null);
  const [usage, setUsage] = useState(null);
  const [tab, setTab] = useState("new");
  // Bumped whenever a build is saved or deleted, so the other tabs refetch.
  const [refreshKey, setRefreshKey] = useState(0);
  const [focusBuildId, setFocusBuildId] = useState(null);
  // Set by "Compare with…" in the archive, so the Compare tab opens with that build
  // already ticked instead of making you find it again.
  const [compareSeedId, setCompareSeedId] = useState(null);

  const loadMeta = useCallback(async () => {
    try {
      setMeta(await api.meta());
      setMetaError(null);
    } catch (e) {
      setMetaError(e.message || "Couldn't reach the server.");
    }
  }, []);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  // Lifetime spend, refreshed whenever a call is made.
  useEffect(() => {
    if (!meta || (meta.auth_required && !meta.authenticated)) return;
    api.usage().then(setUsage).catch(() => setUsage(null));
  }, [meta, refreshKey]);

  if (metaError) {
    return (
      <div style={{ maxWidth: "32rem", margin: "4rem auto", padding: "1.5rem" }}>
        <ErrorNote message={metaError} onRetry={loadMeta} />
      </div>
    );
  }

  if (!meta) return null;

  if (meta.auth_required && !meta.authenticated) {
    return <Login onAuthenticated={loadMeta} />;
  }

  function openInArchive(buildId) {
    setFocusBuildId(buildId);
    setTab("archive");
  }

  function compareWith(buildId) {
    setCompareSeedId(buildId);
    setTab("compare");
  }

  return (
    <div style={{ minHeight: "100%", background: T.bg }}>
      <header
        style={{
          background: T.bgHero,
          borderBottom: `1px solid ${T.border}`,
          padding: "2rem 1.5rem 0",
        }}
      >
        <div style={{ maxWidth: "76rem", margin: "0 auto" }}>
          <div
            style={{
              display: "flex", justifyContent: "space-between",
              alignItems: "flex-start", gap: "1rem", flexWrap: "wrap",
            }}
          >
            <div>
              <div
                style={{
                  display: "flex", alignItems: "center",
                  gap: "0.6rem", marginBottom: "0.4rem",
                }}
              >
                <span style={{ color: T.brass, fontSize: "0.95rem" }}>◆</span>
                <span
                  style={{
                    color: T.brassDim, fontSize: "0.75rem", letterSpacing: "0.04em",
                  }}
                >
                  Civilization VI build coach
                </span>
              </div>
              <h1
                style={{
                  fontFamily: SERIF, fontSize: "2rem",
                  color: T.parchment, margin: 0,
                }}
              >
                The Briefing Table
              </h1>
              <p
                style={{
                  color: T.parchmentDim, marginTop: "0.5rem",
                  maxWidth: "38rem", lineHeight: 1.6,
                }}
              >
                Set the table the way you actually play, tell the coach what you're
                after, and get a complete build plan back — civ, tech, civics, city
                layout, government, all of it.
              </p>
            </div>

            <div
              style={{
                textAlign: "right", color: T.parchmentDim,
                fontSize: "0.73rem", lineHeight: 1.7,
              }}
            >
              <div>{meta.model}</div>
              {meta.missing_key && (
                <div style={{ color: T.rust }}>{meta.missing_key} not set</div>
              )}
              {usage && usage.calls > 0 && (
                <div
                  style={{ fontVariantNumeric: "tabular-nums" }}
                  title={
                    `${usage.prompt_tokens.toLocaleString()} prompt + ` +
                    `${usage.completion_tokens.toLocaleString()} completion tokens` +
                    (usage.cache_read_tokens
                      ? ` — ${usage.cache_read_tokens.toLocaleString()} tokens served from cache`
                      : "") +
                    (usage.has_unpriced_calls
                      ? " — some calls used a model with no published price"
                      : "")
                  }
                >
                  {usage.has_unpriced_calls ? "≥ " : ""}
                  {formatCost(usage.cost_usd)} over {usage.calls}{" "}
                  {usage.calls === 1 ? "call" : "calls"}
                </div>
              )}
              {meta.auth_required && (
                <Button
                  variant="ghost"
                  style={{ marginTop: "0.4rem", padding: "0.25rem 0.55rem", fontSize: "0.73rem" }}
                  onClick={async () => {
                    await api.logout();
                    loadMeta();
                  }}
                >
                  Log out
                </Button>
              )}
            </div>
          </div>

          <Tabs active={tab} onChange={setTab} />
        </div>
      </header>

      <main style={{ maxWidth: "76rem", margin: "0 auto", padding: "1.5rem" }}>
        {tab === "new" && (
          <NewBriefing
            onSaved={() => setRefreshKey((k) => k + 1)}
            onOpenArchive={openInArchive}
          />
        )}
        {tab === "archive" && (
          <Archive
            refreshKey={refreshKey}
            focusBuildId={focusBuildId}
            onFocusConsumed={() => setFocusBuildId(null)}
            onCompareWith={compareWith}
          />
        )}
        {tab === "compare" && (
          <Compare
            refreshKey={refreshKey}
            seedBuildId={compareSeedId}
            onSeedConsumed={() => setCompareSeedId(null)}
            onCompared={() => setRefreshKey((k) => k + 1)}
          />
        )}
      </main>

      <footer
        style={{
          maxWidth: "76rem", margin: "0 auto",
          padding: "0 1.5rem 2rem", color: T.parchmentDim, fontSize: "0.72rem",
          lineHeight: 1.6,
        }}
      >
        Unofficial fan tool — not affiliated with Firaxis Games or 2K.
      </footer>
    </div>
  );
}
