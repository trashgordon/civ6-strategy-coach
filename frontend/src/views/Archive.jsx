// Browse, search and filter saved builds, newest first. Selecting one loads the full
// plan (the list endpoint leaves plan bodies out so the list stays cheap).
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Markdown } from "../markdown";
import { SERIF, T } from "../theme";
import {
  Button, Empty, ErrorNote, Panel, Select, Tag, TextInput, UnverifiedNames,
  UsageNote, formatDate,
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
        {build.civ && <Tag tone="brass">{build.civ}</Tag>}
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

export default function Archive({ focusBuildId, onFocusConsumed, refreshKey }) {
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
                  <div style={{ display: "flex", gap: "0.5rem" }}>
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
                {selected.usage && (
                  <>
                    <UsageNote usage={selected.usage} />
                    <span style={{ color: T.border }}>·</span>
                  </>
                )}
                {[
                  selected.civ,
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

            <div style={{ maxWidth: "44rem" }}>
              <UnverifiedNames names={selected.unverified_names} />
              <Markdown text={selected.generated_plan} />
            </div>
          </article>
        )}
      </Panel>
    </div>
  );
}
