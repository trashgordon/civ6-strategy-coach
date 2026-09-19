// Everything you choose sits in the left column; the plan gets the whole right side.
import { useState } from "react";
import { api } from "../api";
import {
  CITY_PHILOSOPHIES, CIVS, DEFAULT_CONFIG, MODES, NO_PREFERENCE,
  POSTURES, PRIMARY_FOCUSES, SETUP_FIELDS, randomBuildStyle,
} from "../data";
import { Markdown } from "../markdown";
import { DISPLAY, T } from "../theme";
import {
  Button, Empty, ErrorNote, FieldLabel, NumberInput, Panel, Segmented, Select, Thinking,
  ToggleChip, TreeIssues, UnverifiedNames, UsageNote,
} from "../components/ui";

// Short labels for the segmented controls. The values stay the full strings the
// backend and the prompt expect.
const PHILOSOPHY_OPTIONS = [
  { value: "Tall", label: "Tall" },
  { value: "Wide", label: "Wide" },
  { value: NO_PREFERENCE, label: "Any", title: "No preference" },
];
const FOCUS_OPTIONS = [
  { value: "Science", label: "Science" },
  { value: "Culture", label: "Culture" },
  { value: "Domination", label: "Domination" },
  { value: "Religion", label: "Religion" },
  { value: "Diplomacy", label: "Diplomacy" },
  { value: NO_PREFERENCE, label: "Any", title: "No preference" },
];
const POSTURE_OPTIONS = [
  { value: "Introverted / peaceful", label: "Peaceful" },
  { value: "Aggressive / militaristic", label: "Aggressive" },
  { value: NO_PREFERENCE, label: "Any", title: "No preference" },
];

// The setup most people never change, summarised on one line while collapsed.
function setupSummary(config) {
  const on = MODES.filter((m) => config.modes[m.key]).length;
  return [
    config.ruleset, config.difficulty, `${config.mapType} · ${config.mapSize}`,
    `${config.gameSpeed} speed`, `${config.cityStates} city-states`,
    on ? `${on} mode${on === 1 ? "" : "s"}` : null,
  ].filter(Boolean).join(" · ");
}

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

  function surpriseMe() {
    const roll = randomBuildStyle();
    setCiv(roll.civ);
    setCityPhilosophy(roll.cityPhilosophy);
    setPrimaryFocus(roll.primaryFocus);
    setPosture(roll.posture);
  }

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

  const [setupOpen, setSetupOpen] = useState(false);

  return (
    <div className="briefing-grid">
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <Panel
          title="Your build"
          right={
            <Button
              variant="ghost"
              onClick={surpriseMe}
              style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem" }}
            >
              🎲 Surprise me
            </Button>
          }
        >
          <div style={{ display: "grid", gap: "0.95rem" }}>
            <div>
              <FieldLabel htmlFor="civ">Civilization</FieldLabel>
              <Select id="civ" value={civ} options={CIVS} placeholder="Coach's pick" onChange={setCiv} />
            </div>
            <div>
              <FieldLabel>Cities</FieldLabel>
              <Segmented name="philosophy" ariaLabel="City philosophy" value={cityPhilosophy}
                options={PHILOSOPHY_OPTIONS} onChange={setCityPhilosophy} />
            </div>
            <div>
              <FieldLabel>Focus</FieldLabel>
              <Segmented name="focus" ariaLabel="Primary focus" value={primaryFocus}
                options={FOCUS_OPTIONS} columns={3} onChange={setPrimaryFocus} />
            </div>
            <div>
              <FieldLabel>Posture</FieldLabel>
              <Segmented name="posture" ariaLabel="Posture" value={posture}
                options={POSTURE_OPTIONS} onChange={setPosture} />
            </div>
            <div>
              <FieldLabel htmlFor="playstyle">How do you want to play?</FieldLabel>
              <textarea
                id="playstyle"
                value={playstyle}
                maxLength={4000}
                onChange={(e) => setPlaystyle(e.target.value)}
                placeholder="A vibe, a victory type, a challenge — 'few cities, big wonders, culture win'."
                style={{
                  width: "100%", minHeight: "5.5rem", background: T.raised, color: T.text,
                  border: `1px solid ${T.line}`, borderRadius: "5px", padding: "0.6rem",
                  fontSize: "0.92rem", resize: "vertical", lineHeight: 1.5,
                }}
              />
              <p style={{ color: T.muted, fontSize: "0.74rem", margin: "0.35rem 0 0", lineHeight: 1.45 }}>
                The choices above are coarse hints. If this box disagrees with them, this box wins.
              </p>
            </div>
            <Button onClick={generate} disabled={loading} style={{ width: "100%", padding: "0.7rem" }}>
              {loading ? "Drafting…" : "Draft the strategy"}
            </Button>
          </div>
        </Panel>

        <Panel
          title="Game setup"
          right={
            <div style={{ display: "flex", gap: "0.4rem" }}>
              {setupOpen && (
                <Button variant="ghost" onClick={() => setConfig(DEFAULT_CONFIG)}
                  style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem" }}>
                  Reset
                </Button>
              )}
              <Button variant="ghost" onClick={() => setSetupOpen((o) => !o)}
                style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem" }}
                aria-expanded={setupOpen}>
                {setupOpen ? "Done" : "Edit"}
              </Button>
            </div>
          }
        >
          {!setupOpen ? (
            <p style={{ margin: 0, color: T.text, fontSize: "0.86rem", lineHeight: 1.55 }}>
              {setupSummary(config)}
            </p>
          ) : (
            <div style={{ display: "grid", gap: "1rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.7rem" }}>
                {SETUP_FIELDS.map((field) => (
                  <div key={field.key}>
                    <FieldLabel htmlFor={`setup-${field.key}`}>{field.label}</FieldLabel>
                    {field.number ? (
                      <NumberInput id={`setup-${field.key}`} value={config[field.key]}
                        min={field.number.min} max={field.number.max}
                        onChange={(v) => updateConfig(field.key, v)} />
                    ) : (
                      <Select id={`setup-${field.key}`} value={config[field.key]}
                        options={field.options} onChange={(v) => updateConfig(field.key, v)} />
                    )}
                  </div>
                ))}
              </div>
              <div>
                <FieldLabel>Game modes</FieldLabel>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                  {MODES.map((mode) => (
                    <ToggleChip key={mode.key} id={`mode-${mode.key}`}
                      checked={config.modes[mode.key]} onChange={() => toggleMode(mode.key)}>
                      {mode.label.replace(/ Mode$/, "")}
                    </ToggleChip>
                  ))}
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", minWidth: 0 }}>
        {loading && (
          <Panel><Thinking label="The coach is studying the board" /></Panel>
        )}

        {!loading && error && <ErrorNote message={error} onRetry={generate} />}

        {!loading && !error && !build && (
          <Panel>
            <Empty>
              Set your build on the left and draft a strategy. The plan lands here — twelve
              sections, with a Playbook you can tick off mid-game.
            </Empty>
          </Panel>
        )}

        {!loading && build && (
          <article style={{ display: "grid", gap: "0.9rem" }}>
            <header
              style={{
                display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                gap: "0.75rem", flexWrap: "wrap",
              }}
            >
              <div>
                <h2 style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: "1.55rem", margin: 0, color: T.text }}>
                  {build.title}
                </h2>
                <div style={{ color: T.muted, fontSize: "0.78rem", marginTop: "0.2rem" }}>
                  Saved to your archive ·{" "}
                  <UsageNote usage={build.usage} />
                </div>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <Button variant="ghost" onClick={() => onOpenArchive?.(build.id)}>Open in archive</Button>
                <Button variant="ghost" onClick={() => setBuild(null)}>New briefing</Button>
              </div>
            </header>
            <UnverifiedNames names={build.unverified_names} />
            <TreeIssues issues={build.tree_issues} />
            <Markdown text={build.generated_plan} layout="sections" buildId={build.id} />
          </article>
        )}
      </div>
    </div>
  );
}
