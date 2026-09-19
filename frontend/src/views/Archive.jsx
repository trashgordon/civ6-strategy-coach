// Browse, search and filter saved builds, newest first. Selecting one loads the full
// plan (the list endpoint leaves plan bodies out so the list stays cheap).
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Markdown } from "../markdown";
import { OUTCOMES, VICTORY_TYPES } from "../data";
import { SERIF, T } from "../theme";
import {
  Button, Empty, ErrorNote, NumberInput, OutcomeBadge, Panel, Select, Tag, TextInput,
  TreeIssues, UnverifiedNames, UsageNote, formatDate,
} from "../components/ui";

function BuildRow({ build, active, onSelect }) {
  const descriptors = [build.primary_focus, build.city_philosophy, build.posture]
    .filter((d) => d && d !== "No preference");

  return (
    <button
      onClick={() => onSelect(build.id)}
      aria-current={active ? "true" : undefined}
      style={{
        display: "block", width: "100%", textAlign: "left", cursor: "pointer",
        background: active ? T.panelAlt : "transparent",
        border: "none", borderLeft: `2px solid ${active ? T.brass : "transparent"}`,
        borderBottom: `1px solid ${T.border}`,
        padding: "0.7rem 0.8rem", color: T.parchment,
      }}
    >
      <div
        style={{
          display: "flex", justifyContent: "space-between",
          gap: "0.5rem", alignItems: "baseline",
        }}
      >
        <span style={{ fontFamily: SERIF, fontSize: "0.98rem" }}>{build.title}</span>
        <span style={{ display: "flex", gap: "0.3rem", flexShrink: 0 }}>
          <OutcomeBadge
            outcome={build.outcome}
            victoryType={build.victory_type}
            endTurn={build.end_turn}
          />
          {build.played_civ && <Tag tone="brass">{build.played_civ}</Tag>}
        </span>
      </div>
      <div
        style={{
          color: T.parchmentDim, fontSize: "0.75rem",
          marginTop: "0.3rem", lineHeight: 1.5,
        }}
      >
        {formatDate(build.created_at)}
        {descriptors.length > 0 && ` · ${descriptors.join(" · ")}`}
      </div>
    </button>
  );
}

export default function Archive({
  focusBuildId, onFocusConsumed, refreshKey, onCompareWith, onOutcomeLogged,
}) {
  const [builds, setBuilds] = useState([]);
  const [filters, setFilters] = useState({ civs: [], focuses: [] });
  const [query, setQuery] = useState("");
  const [civFilter, setCivFilter] = useState("");
  const [focusFilter, setFocusFilter] = useState("");

  const [selectedId, setSelectedId] = useState(focusBuildId || null);
  const [selected, setSelected] = useState(null);
  const [listError, setListError] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [loadingList, setLoadingList] = useState(true);

  const [renaming, setRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  // Campaign journal: edited as the game actually plays out, so it saves explicitly
  // rather than on every keystroke.
  const [notesOpen, setNotesOpen] = useState(false);
  const [draftNotes, setDraftNotes] = useState("");
  const [notesSaved, setNotesSaved] = useState(false);
  // How the game went. Saved explicitly, like the journal.
  const [outcomeOpen, setOutcomeOpen] = useState(false);
  const [draftOutcome, setDraftOutcome] = useState("");
  const [draftVictory, setDraftVictory] = useState("");
  const [draftTurn, setDraftTurn] = useState("");
  const [outcomeSaved, setOutcomeSaved] = useState(false);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      const body = await api.builds({ q: query, civ: civFilter, primaryFocus: focusFilter });
      setBuilds(body.builds);
      setFilters(body.filters);
      setListError(null);
    } catch (e) {
      setListError(e.message || "Couldn't load your archive.");
    } finally {
      setLoadingList(false);
    }
  }, [query, civFilter, focusFilter]);

  // Debounced so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(loadList, query ? 250 : 0);
    return () => clearTimeout(handle);
  }, [loadList, query, refreshKey]);

  useEffect(() => {
    if (focusBuildId) {
      setSelectedId(focusBuildId);
      onFocusConsumed?.();
    }
  }, [focusBuildId, onFocusConsumed]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    let cancelled = false;
    api
      .build(selectedId)
      .then((build) => {
        if (cancelled) return;
        setSelected(build);
        setDraftTitle(build.title);
        setDraftNotes(build.notes || "");
        setNotesOpen(Boolean(build.notes));
        setNotesSaved(false);
        setDraftOutcome(build.outcome || "");
        setDraftVictory(build.victory_type || "");
        setDraftTurn(build.end_turn ? String(build.end_turn) : "");
        setOutcomeOpen(Boolean(build.outcome));
        setOutcomeSaved(false);
        setDetailError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setSelected(null);
        setDetailError(e.message || "Couldn't load that build.");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  async function saveTitle() {
    const title = draftTitle.trim();
    if (!title || !selected) return;
    try {
      const updated = await api.rename(selected.id, title);
      setSelected(updated);
      setRenaming(false);
      loadList();
    } catch (e) {
      setDetailError(e.message || "Couldn't rename that build.");
    }
  }

  async function saveNotes() {
    if (!selected) return;
    try {
      const updated = await api.saveNotes(selected.id, draftNotes);
      setSelected(updated);
      setNotesSaved(true);
      setTimeout(() => setNotesSaved(false), 2000);
    } catch (e) {
      setDetailError(e.message || "Couldn't save those notes.");
    }
  }

  async function saveOutcome() {
    if (!selected) return;
    try {
      const updated = await api.saveOutcome(selected.id, {
        outcome: draftOutcome,
        // A loss or an abandoned game has no victory type to record.
        victoryType: draftOutcome === "won" ? draftVictory : "",
        endTurn: draftTurn,
      });
      setSelected(updated);
      setDraftVictory(updated.victory_type || "");
      setOutcomeSaved(true);
      setTimeout(() => setOutcomeSaved(false), 2000);
      loadList();
      onOutcomeLogged?.();
    } catch (e) {
      setDetailError(e.message || "Couldn't save that result.");
    }
  }

  async function deleteSelected() {
    if (!selected) return;
    const ok = window.confirm(`Delete "${selected.title}"? This can't be undone.`);
    if (!ok) return;
    try {
      await api.remove(selected.id);
      setSelectedId(null);
      setSelected(null);
      loadList();
    } catch (e) {
      setDetailError(e.message || "Couldn't delete that build.");
    }
  }

  const hasFilters = Boolean(query || civFilter || focusFilter);

  return (
    <div className="briefing-grid">
      <Panel title="Archive" style={{ padding: "1.25rem 0.75rem 0.5rem" }}>
        <div
          style={{
            display: "flex", flexDirection: "column",
            gap: "0.5rem", padding: "0 0.5rem 0.75rem",
          }}
        >
          <TextInput
            ariaLabel="Search saved builds"
            value={query}
            onChange={setQuery}
            placeholder="Search titles, civs, plans..."
            style={{ width: "100%" }}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Select
              ariaLabel="Filter by civ"
              value={civFilter}
              options={filters.civs}
              placeholder="Any civ"
              onChange={setCivFilter}
              style={{ flex: 1, minWidth: 0 }}
            />
            <Select
              ariaLabel="Filter by focus"
              value={focusFilter}
              options={filters.focuses}
              placeholder="Any focus"
              onChange={setFocusFilter}
              style={{ flex: 1, minWidth: 0 }}
            />
          </div>
          {hasFilters && (
            <Button
              variant="ghost"
              onClick={() => {
                setQuery("");
                setCivFilter("");
                setFocusFilter("");
              }}
            >
              Clear filters
            </Button>
          )}
        </div>

        {listError && (
          <div style={{ padding: "0 0.5rem 0.75rem" }}>
            <ErrorNote message={listError} onRetry={loadList} />
          </div>
        )}

        <div style={{ maxHeight: "34rem", overflowY: "auto" }}>
          {builds.map((build) => (
            <BuildRow
              key={build.id}
              build={build}
              active={build.id === selectedId}
              onSelect={setSelectedId}
            />
          ))}
          {!loadingList && !builds.length && !listError && (
            <p
              style={{
                color: T.parchmentDim, fontSize: "0.85rem",
                padding: "1rem 0.8rem", lineHeight: 1.6,
              }}
            >
              {hasFilters
                ? "Nothing matches those filters."
                : "No saved builds yet. Draft a strategy and it'll show up here."}
            </p>
          )}
        </div>
      </Panel>

      <Panel style={{ minHeight: "16rem", padding: "1.5rem" }}>
        {detailError && <ErrorNote message={detailError} />}

        {!selected && !detailError && (
          <Empty>Pick a build from the archive to read the full dossier.</Empty>
        )}

        {selected && (
          <article>
            <header
              style={{
                borderBottom: `1px solid ${T.border}`,
                paddingBottom: "0.75rem", marginBottom: "0.5rem",
              }}
            >
              <div
                style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "baseline", gap: "1rem", flexWrap: "wrap",
                }}
              >
                {renaming ? (
                  <div style={{ display: "flex", gap: "0.5rem", flex: "1 1 18rem" }}>
                    <TextInput
                      ariaLabel="Build title"
                      value={draftTitle}
                      onChange={setDraftTitle}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveTitle();
                        if (e.key === "Escape") {
                          setRenaming(false);
                          setDraftTitle(selected.title);
                        }
                      }}
                      style={{ flex: 1, minWidth: 0 }}
                    />
                    <Button variant="solid" onClick={saveTitle}>Save</Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setRenaming(false);
                        setDraftTitle(selected.title);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <h2
                    style={{
                      fontFamily: SERIF, color: T.parchment,
                      fontSize: "1.3rem", margin: 0,
                    }}
                  >
                    {selected.title}
                  </h2>
                )}

                {!renaming && (
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <Button
                      variant="ghost"
                      onClick={() => onCompareWith?.(selected.id)}
                    >
                      Compare with…
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setOutcomeOpen((open) => !open)}
                    >
                      {outcomeOpen
                        ? "Hide result"
                        : selected.outcome
                        ? "Result"
                        : "Log result"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setNotesOpen((open) => !open)}
                    >
                      {notesOpen ? "Hide notes" : selected.notes ? "Notes" : "Add notes"}
                    </Button>
                    <Button variant="ghost" onClick={() => setRenaming(true)}>
                      Rename
                    </Button>
                    <Button variant="ghost" onClick={deleteSelected}>
                      Delete
                    </Button>
                  </div>
                )}
              </div>

              <div
                style={{
                  display: "flex", gap: "0.4rem", flexWrap: "wrap",
                  marginTop: "0.6rem", alignItems: "center",
                }}
              >
                <span style={{ color: T.parchmentDim, fontSize: "0.78rem" }}>
                  {formatDate(selected.created_at)}
                </span>
                {selected.outcome && (
                  <OutcomeBadge
                    outcome={selected.outcome}
                    victoryType={selected.victory_type}
                    endTurn={selected.end_turn}
                  />
                )}
                {selected.usage && (
                  <>
                    <UsageNote usage={selected.usage} />
                    <span style={{ color: T.border }}>·</span>
                  </>
                )}
                {[
                  selected.played_civ,
                  selected.primary_focus,
                  selected.city_philosophy,
                  selected.posture,
                  selected.ruleset,
                  selected.difficulty,
                  selected.map_type,
                ]
                  .filter((v) => v && v !== "No preference")
                  .map((value, i) => (
                    <Tag key={`${value}-${i}`}>{value}</Tag>
                  ))}
              </div>

              {selected.playstyle_text && (
                <p
                  style={{
                    color: T.parchmentDim, fontSize: "0.85rem",
                    fontStyle: "italic", lineHeight: 1.6,
                    margin: "0.75rem 0 0", paddingLeft: "0.75rem",
                    borderLeft: `2px solid ${T.border}`,
                  }}
                >
                  “{selected.playstyle_text}”
                </p>
              )}
            </header>

            {outcomeOpen && (
              <div
                style={{
                  margin: "1rem 0 0", padding: "0.9rem", background: T.panelAlt,
                  border: `1px solid ${T.border}`, borderRadius: "3px",
                }}
              >
                <div
                  style={{
                    fontFamily: SERIF, color: T.brass,
                    fontSize: "0.95rem", marginBottom: "0.6rem",
                  }}
                >
                  How did it go?
                </div>
                <div
                  style={{
                    display: "flex", gap: "0.75rem",
                    flexWrap: "wrap", alignItems: "center",
                  }}
                >
                  <Select
                    ariaLabel="Result"
                    value={draftOutcome}
                    options={OUTCOMES.filter((o) => o.value)}
                    placeholder="Not recorded"
                    onChange={setDraftOutcome}
                    style={{ minWidth: "9rem" }}
                  />
                  {draftOutcome === "won" && (
                    <Select
                      ariaLabel="Victory type"
                      value={draftVictory}
                      options={VICTORY_TYPES}
                      placeholder="Victory type…"
                      onChange={setDraftVictory}
                      style={{ minWidth: "9rem" }}
                    />
                  )}
                  <label
                    style={{
                      display: "flex", alignItems: "center",
                      gap: "0.4rem", color: T.parchmentDim, fontSize: "0.82rem",
                    }}
                  >
                    Ended turn
                    <NumberInput
                      ariaLabel="End turn"
                      value={draftTurn === "" ? "" : Number(draftTurn)}
                      min={0}
                      max={5000}
                      onChange={(v) => setDraftTurn(v === 0 ? "" : String(v))}
                    />
                  </label>
                  <Button variant="solid" onClick={saveOutcome}>
                    Save result
                  </Button>
                  {outcomeSaved && (
                    <span style={{ color: T.brass, fontSize: "0.78rem" }}>Saved</span>
                  )}
                </div>
              </div>
            )}

            {notesOpen && (
              <div
                style={{
                  margin: "1rem 0 1.25rem",
                  padding: "0.9rem",
                  background: T.panelAlt,
                  border: `1px solid ${T.border}`,
                  borderRadius: "3px",
                }}
              >
                <label
                  htmlFor="campaign-notes"
                  style={{
                    display: "block", fontFamily: SERIF, color: T.brass,
                    fontSize: "0.95rem", marginBottom: "0.4rem",
                  }}
                >
                  Campaign journal
                </label>
                <textarea
                  id="campaign-notes"
                  value={draftNotes}
                  maxLength={20000}
                  onChange={(e) => setDraftNotes(e.target.value)}
                  placeholder="How it's actually going. e.g. 'Turn 40: forward-settled by Rome, going Encampment before Campus.'"
                  style={{
                    width: "100%", minHeight: "6rem", background: T.panel,
                    color: T.parchment, border: `1px solid ${T.border}`,
                    borderRadius: "3px", padding: "0.6rem", fontSize: "0.85rem",
                    resize: "vertical", lineHeight: 1.6,
                  }}
                />
                <div
                  style={{
                    display: "flex", alignItems: "center",
                    gap: "0.6rem", marginTop: "0.5rem",
                  }}
                >
                  <Button
                    variant="solid"
                    onClick={saveNotes}
                    disabled={draftNotes === (selected.notes || "")}
                  >
                    Save notes
                  </Button>
                  {notesSaved && (
                    <span style={{ color: T.brass, fontSize: "0.78rem" }}>Saved</span>
                  )}
                </div>
              </div>
            )}

            <div>
              <UnverifiedNames names={selected.unverified_names} />
              <TreeIssues issues={selected.tree_issues} />
              <Markdown text={selected.generated_plan} layout="sections" buildId={selected.id} />
            </div>
          </article>
        )}
      </Panel>
    </div>
  );
}
