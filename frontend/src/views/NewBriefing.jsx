// Config form on the left, the coach's dossier on the right — the prototype's
// two-column layout, now posting to our own backend.
import { useState } from "react";
import { api } from "../api";
import {
  CITY_PHILOSOPHIES, CIVS, DEFAULT_CONFIG, MODES, NO_PREFERENCE,
  POSTURES, PRIMARY_FOCUSES, SETUP_FIELDS,
} from "../data";
import { Markdown } from "../markdown";
import { SERIF, T } from "../theme";
import {
  Button, Empty, ErrorNote, FieldRow, NumberInput, Panel, Select, Thinking,
  UnverifiedNames, UsageNote,
} from "../components/ui";

export default function NewBriefing({ onSaved, onOpenArchive }) {
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [civ, setCiv] = useState("");
  const [cityPhilosophy, setCityPhilosophy] = useState(NO_PREFERENCE);
  const [primaryFocus, setPrimaryFocus] = useState(NO_PREFERENCE);
  const [posture, setPosture] = useState(NO_PREFERENCE);
  const [playstyle, setPlaystyle] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [build, setBuild] = useState(null);

  function updateConfig(key, value) {
    setConfig((c) => ({ ...c, [key]: value }));
  }
  function toggleMode(key) {
    setConfig((c) => ({ ...c, modes: { ...c.modes, [key]: !c.modes[key] } }));
  }

  async function generate() {
    setLoading(true);
    setError(null);
    setBuild(null);
    try {
      const saved = await api.generate({
        config,
        civ,
        city_philosophy: cityPhilosophy,
        primary_focus: primaryFocus,
        posture,
        playstyle_text: playstyle,
      });
      setBuild(saved);
      onSaved?.(saved);
    } catch (e) {
      setError(e.message || "Something went wrong drafting the strategy.");
    } finally {
      setLoading(false);
    }
  }

  const activeModeCount = Object.values(config.modes).filter(Boolean).length;

  return (
    <div className="briefing-grid">
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <Panel
          title="Game setup"
          right={
            <Button
              variant="ghost"
              onClick={() => setConfig(DEFAULT_CONFIG)}
              style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem" }}
            >
              Reset
            </Button>
          }
        >
          {SETUP_FIELDS.map((field) => (
            <FieldRow key={field.key} label={field.label}>
              {field.number ? (
                <NumberInput
                  ariaLabel={field.label}
                  value={config[field.key]}
                  min={field.number.min}
                  max={field.number.max}
                  onChange={(v) => updateConfig(field.key, v)}
                />
              ) : (
                <Select
                  ariaLabel={field.label}
                  value={config[field.key]}
                  options={field.options}
                  onChange={(v) => updateConfig(field.key, v)}
                />
              )}
            </FieldRow>
          ))}

          <h3
            style={{
              fontFamily: SERIF, color: T.brass, fontSize: "1.05rem",
              marginTop: "1.5rem", marginBottom: "0.6rem", fontWeight: 400,
            }}
          >
            Game modes {activeModeCount ? `(${activeModeCount} on)` : ""}
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {MODES.map((mode) => (
              <label
                key={mode.key}
                style={{
                  display: "flex", alignItems: "center", gap: "0.5rem",
                  fontSize: "0.85rem", color: T.parchmentDim, cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={config.modes[mode.key]}
                  onChange={() => toggleMode(mode.key)}
                  style={{ accentColor: T.brass }}
                />
                {mode.label}
              </label>
            ))}
          </div>
        </Panel>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <Panel title="The build you're after">
          <FieldRow label="Civilization">
            <Select
              ariaLabel="Civilization"
              value={civ}
              options={CIVS}
              placeholder="No preference — coach's pick"
              onChange={setCiv}
              style={{ minWidth: "14rem" }}
            />
          </FieldRow>
          <FieldRow label="City philosophy">
            <Select
              ariaLabel="City philosophy"
              value={cityPhilosophy}
              options={CITY_PHILOSOPHIES}
              onChange={setCityPhilosophy}
              style={{ minWidth: "14rem" }}
            />
          </FieldRow>
          <FieldRow label="Primary focus">
            <Select
              ariaLabel="Primary focus"
              value={primaryFocus}
              options={PRIMARY_FOCUSES}
              onChange={setPrimaryFocus}
              style={{ minWidth: "14rem" }}
            />
          </FieldRow>
          <FieldRow label="Posture">
            <Select
              ariaLabel="Posture"
              value={posture}
              options={POSTURES}
              onChange={setPosture}
              style={{ minWidth: "14rem" }}
            />
          </FieldRow>

          <label
            htmlFor="playstyle"
            style={{
              display: "block", fontFamily: SERIF, color: T.brass,
              fontSize: "1.05rem", marginTop: "1.25rem", marginBottom: "0.5rem",
            }}
          >
            How do you want to play?
          </label>
          <textarea
            id="playstyle"
            value={playstyle}
            maxLength={4000}
            onChange={(e) => setPlaystyle(e.target.value)}
            placeholder="A vibe, a victory type, a challenge — e.g. 'few cities, big wonders, culture win' or 'go wide and crush people militarily.'"
            style={{
              width: "100%", minHeight: "7rem", background: T.panelAlt,
              color: T.parchment, border: `1px solid ${T.border}`,
              borderRadius: "3px", padding: "0.65rem", fontSize: "0.9rem",
              resize: "vertical", lineHeight: 1.5,
            }}
          />
          <p
            style={{
              color: T.parchmentDim, fontSize: "0.75rem",
              margin: "0.5rem 0 0.75rem", lineHeight: 1.5,
            }}
          >
            The dropdowns are coarse hints. If this box disagrees with them, this box wins.
          </p>
          <Button onClick={generate} disabled={loading} style={{ width: "100%" }}>
            {loading ? "Drafting the plan..." : "Draft the strategy"}
          </Button>
        </Panel>

        <Panel style={{ minHeight: "14rem", padding: "1.5rem" }}>
          {loading && <Thinking label="The coach is studying the board" />}

          {!loading && error && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <ErrorNote message={error} onRetry={generate} />
            </div>
          )}

          {!loading && !error && !build && (
            <Empty>
              The board is set. Describe your build and the coach will draft your plan.
            </Empty>
          )}

          {!loading && build && (
            <article>
              <header
                style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "baseline", gap: "1rem", flexWrap: "wrap",
                  marginBottom: "0.5rem", borderBottom: `1px solid ${T.border}`,
                  paddingBottom: "0.75rem",
                }}
              >
                <div>
                  <h2
                    style={{
                      fontFamily: SERIF, color: T.parchment,
                      fontSize: "1.3rem", margin: 0,
                    }}
                  >
                    {build.title}
                  </h2>
                  <p
                    style={{
                      color: T.parchmentDim, fontSize: "0.78rem",
                      margin: "0.3rem 0 0",
                    }}
                  >
                    Saved to your archive — rename or delete it there.
                  </p>
                  <UsageNote usage={build.usage} style={{ display: "block", marginTop: "0.3rem" }} />
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <Button variant="ghost" onClick={() => onOpenArchive?.(build.id)}>
                    Open in archive
                  </Button>
                  <Button variant="ghost" onClick={() => setBuild(null)}>
                    New briefing
                  </Button>
                </div>
              </header>
              <div style={{ maxWidth: "44rem" }}>
                <UnverifiedNames names={build.unverified_names} />
                <Markdown text={build.generated_plan} />
              </div>
            </article>
          )}
        </Panel>
      </div>
    </div>
  );
}
