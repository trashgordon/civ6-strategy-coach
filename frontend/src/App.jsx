import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { DISPLAY, T } from "./theme";
import { Button, ErrorNote, ThemeToggle, formatCost } from "./components/ui";
import NewBriefing from "./views/NewBriefing";
import Archive from "./views/Archive";
import Compare from "./views/Compare";
import Stats from "./views/Stats";
import Rate from "./views/Rate";
import Login from "./views/Login";

const TABS = [
  { key: "new", label: "New briefing" },
  { key: "archive", label: "Archive" },
  { key: "compare", label: "Compare" },
  { key: "stats", label: "Stats" },
  { key: "rate", label: "Rate" },
];

function Tabs({ active, onChange }) {
  return (
    <nav style={{ display: "flex", gap: "0.2rem", flexWrap: "wrap" }} aria-label="Views">
      {TABS.map((tab) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            aria-current={selected ? "page" : undefined}
            style={{
              background: selected ? T.accent : "transparent",
              color: selected ? T.onAccent : T.muted,
              border: "none",
              borderRadius: "5px",
              padding: "0.45rem 0.85rem",
              fontFamily: DISPLAY,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.07em",
              fontSize: "0.8rem",
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
    <div style={{ minHeight: "100%", background: T.ground }}>
      <header
        style={{
          background: T.bar,
          borderBottom: `1px solid ${T.line}`,
          padding: "0.65rem clamp(1rem, 3vw, 1.5rem)",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <div
          style={{
            maxWidth: "80rem", margin: "0 auto", display: "flex",
            alignItems: "center", justifyContent: "space-between",
            gap: "0.75rem 1.25rem", flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", flexWrap: "wrap" }}>
            <h1
              style={{
                fontFamily: DISPLAY, fontWeight: 700, fontSize: "1rem", margin: 0,
                textTransform: "uppercase", letterSpacing: "0.12em", color: T.text,
                whiteSpace: "nowrap",
              }}
              title="Civilization VI build coach"
            >
              Briefing <span style={{ color: T.accent }}>Table</span>
            </h1>
            <Tabs active={tab} onChange={setTab} />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.9rem", flexWrap: "wrap" }}>
            <div
              style={{
                textAlign: "right", color: T.muted, fontSize: "0.74rem",
                lineHeight: 1.45, fontVariantNumeric: "tabular-nums",
              }}
            >
              <div>{meta.model.replace(/^[a-z_]+\//, "")}</div>
              {meta.missing_key && (
                <div style={{ color: T.danger }}>{meta.missing_key} not set</div>
              )}
              {usage && usage.calls > 0 && (
                <div
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
                  {formatCost(usage.cost_usd)} · {usage.calls}{" "}
                  {usage.calls === 1 ? "call" : "calls"}
                </div>
              )}
            </div>
            <ThemeToggle />
            {meta.auth_required && (
              <Button
                variant="ghost"
                style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
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
      </header>

      <main style={{ maxWidth: "80rem", margin: "0 auto", padding: "1.25rem clamp(1rem, 3vw, 1.5rem)" }}>
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
            onOutcomeLogged={() => setRefreshKey((k) => k + 1)}
          />
        )}
        {tab === "stats" && <Stats refreshKey={refreshKey} />}
        {tab === "rate" && <Rate />}
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
          maxWidth: "80rem", margin: "0 auto",
          padding: "0 clamp(1rem, 3vw, 1.5rem) 2rem", color: T.muted, fontSize: "0.72rem",
          lineHeight: 1.6,
        }}
      >
        Unofficial fan tool — not affiliated with Firaxis Games or 2K.
      </footer>
    </div>
  );
}
