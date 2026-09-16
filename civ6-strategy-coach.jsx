import { useState } from "react";

const T = {
  bg: "#101A28",
  bgHero: "#0B141F",
  panel: "#152233",
  panelAlt: "#1B2C40",
  border: "#2A3E54",
  brass: "#C7A542",
  brassDim: "#8B7A48",
  parchment: "#ECE4CE",
  parchmentDim: "#A9A08A",
  rust: "#A6522E",
};

const SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif';
const SANS = '"Inter", "Segoe UI", Helvetica, Arial, sans-serif';

const CIVS = [
  "America", "Arabia", "Australia", "Aztec", "Babylon", "Brazil", "Byzantium", "Canada",
  "China", "Cree", "Egypt", "England", "Ethiopia", "France", "Gaul", "Georgia",
  "Germany", "Gran Colombia", "Greece", "Hungary", "Inca", "India", "Indonesia", "Japan",
  "Khmer", "Kongo", "Korea", "Macedon", "Mali", "Maori", "Mapuche", "Maya",
  "Mongolia", "Netherlands", "Norway", "Ottoman", "Persia", "Phoenicia", "Poland", "Rome",
  "Russia", "Scotland", "Scythia", "Spain", "Sumeria", "Sweden", "Vietnam", "Zulu",
];

const MODES = [
  { key: "apocalypse", label: "Apocalypse Mode" },
  { key: "barbarianClans", label: "Barbarian Clans Mode" },
  { key: "dramaticAges", label: "Dramatic Ages Mode" },
  { key: "heroesLegends", label: "Heroes & Legends Mode" },
  { key: "monopolies", label: "Monopolies and Corporations Mode" },
  { key: "secretSocieties", label: "Secret Societies Mode" },
  { key: "sukritactOceans", label: "Sukritact's Oceans" },
  { key: "techCivicShuffle", label: "Tech and Civic Shuffle Mode" },
  { key: "zombieDefense", label: "Zombie Defense Mode" },
];

const DEFAULTS = {
  ruleset: "Gathering Storm",
  difficulty: "Prince",
  gameSpeed: "Standard",
  mapType: "Pangaea",
  mapSize: "Standard",
  cityStates: 12,
  disasterIntensity: 2,
  resources: "Abundant",
  worldAge: "New",
  startPosition: "Legendary",
  temperature: "Standard",
  rainfall: "Wet",
  seaLevel: "Standard",
  modes: {
    apocalypse: false,
    barbarianClans: false,
    dramaticAges: false,
    heroesLegends: false,
    monopolies: true,
    secretSocieties: false,
    sukritactOceans: true,
    techCivicShuffle: false,
    zombieDefense: false,
  },
};

const SYSTEM_PROMPT = `You are a former competitive Civilization VI player who went pro on the tournament circuit before becoming a coach. You know the tech tree, civic tree, civs, leaders, governors, wonders, and policy cards cold, and you're just as sharp on general strategy game theory (tempo, snowballing, opportunity cost, opponent-reading) as you are on Civ 6 specifics.

Talk like a coach, not a wiki: direct, opinionated, no padding. State the recommendation first, then justify briefly.

Given a game configuration, an optional civ preference, and a description of how the person wants to play, produce a build plan covering, in this order, using "##" headers:
1. Civ & Leader recommendation (or a fit-check if one was requested)
2. Tech path
3. Civic path
4. City & district layout
5. Government & policy cards
6. Golden Age dedication priorities
7. Religious beliefs (skip cleanly if not relevant to the build)
8. The Playbook — a tight bulleted cheat-sheet of the 5-8 things to actually do, in order

Be specific: name actual techs, civics, wonders, cards, and governors rather than describing them abstractly. Account for the stated ruleset, map type, difficulty, and active game modes when they actually change the right call. If you're not certain of an exact number or a current-patch detail, say so rather than inventing one.

Space is tight: keep the entire response under roughly 700 words total. Favor bullets over prose. If something has to be cut, protect the Playbook and the Civ/Tech/Civic sections over exhaustive detail in City Layout, Government, Golden Age, or Religion.`;

function buildUserPrompt(s, civ, playstyle) {
  const activeModes = MODES.filter((m) => s.modes[m.key]).map((m) => m.label);
  return [
    "Game configuration:",
    `- Ruleset: ${s.ruleset}`,
    `- Difficulty: ${s.difficulty}`,
    `- Game speed: ${s.gameSpeed}`,
    `- Map: ${s.mapType}, ${s.mapSize} size, ${s.seaLevel} sea level, ${s.temperature} temperature, ${s.rainfall} rainfall, ${s.worldAge} world age, ${s.startPosition} start position`,
    `- City-states: ${s.cityStates}`,
    `- Disaster intensity: ${s.disasterIntensity}`,
    `- Resources: ${s.resources}`,
    `- Game modes active: ${activeModes.length ? activeModes.join(", ") : "None"}`,
    "",
    `Civ preference: ${civ || "No preference — recommend the best fit."}`,
    "",
    `How I want to play: ${playstyle || "Not specified — recommend a strong, fun build for this configuration."}`,
    "",
    "Give me the full build plan.",
  ].join("\n");
}

function renderInline(text, keyBase) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <strong key={`${keyBase}-${i}`} style={{ color: T.brass }}>
        {part}
      </strong>
    ) : (
      <span key={`${keyBase}-${i}`}>{part}</span>
    )
  );
}

function renderMarkdown(text) {
  const lines = text.split("\n");
  const blocks = [];
  let listBuffer = [];
  let listType = null;

  function flushList() {
    if (!listBuffer.length) return;
    const Tag = listType === "ol" ? "ol" : "ul";
    blocks.push(
      <Tag
        key={`list-${blocks.length}`}
        style={{
          margin: "0.5rem 0 1rem 0",
          paddingLeft: "1.25rem",
          listStyleType: listType === "ol" ? "decimal" : "disc",
        }}
      >
        {listBuffer.map((item, i) => (
          <li key={i} style={{ marginBottom: "0.35rem", lineHeight: 1.6 }}>
            {renderInline(item, `li-${blocks.length}-${i}`)}
          </li>
        ))}
      </Tag>
    );
    listBuffer = [];
    listType = null;
  }

  lines.forEach((raw, idx) => {
    const trimmed = raw.trim();

    if (!trimmed) {
      flushList();
      return;
    }
    if (/^-{3,}$/.test(trimmed)) {
      flushList();
      blocks.push(
        <div key={`hr-${idx}`} style={{ borderTop: `1px solid ${T.border}`, margin: "1.25rem 0" }} />
      );
      return;
    }
    const h1 = trimmed.match(/^#\s+(.*)/);
    const h2 = trimmed.match(/^##\s+(.*)/);
    const h3 = trimmed.match(/^###\s+(.*)/);
    const ol = trimmed.match(/^\d+\.\s+(.*)/);
    const ul = trimmed.match(/^[-*]\s+(.*)/);

    if (h1) {
      flushList();
      blocks.push(
        <h1 key={idx} style={{ fontFamily: SERIF, color: T.parchment, fontSize: "1.6rem", marginTop: "1.5rem", marginBottom: "0.5rem" }}>
          {renderInline(h1[1], `h1-${idx}`)}
        </h1>
      );
    } else if (h2) {
      flushList();
      blocks.push(
        <h2
          key={idx}
          style={{
            fontFamily: SERIF,
            color: T.brass,
            fontSize: "1.25rem",
            marginTop: "1.5rem",
            marginBottom: "0.5rem",
            borderBottom: `1px solid ${T.border}`,
            paddingBottom: "0.35rem",
          }}
        >
          {renderInline(h2[1], `h2-${idx}`)}
        </h2>
      );
    } else if (h3) {
      flushList();
      blocks.push(
        <h3 key={idx} style={{ fontFamily: SANS, color: T.parchment, fontSize: "1.05rem", fontWeight: 600, marginTop: "1rem", marginBottom: "0.35rem" }}>
          {renderInline(h3[1], `h3-${idx}`)}
        </h3>
      );
    } else if (ol) {
      if (listType !== "ol") flushList();
      listType = "ol";
      listBuffer.push(ol[1]);
    } else if (ul) {
      if (listType !== "ul") flushList();
      listType = "ul";
      listBuffer.push(ul[1]);
    } else {
      flushList();
      blocks.push(
        <p key={idx} style={{ fontFamily: SANS, color: T.parchmentDim, lineHeight: 1.7, marginBottom: "0.5rem" }}>
          {renderInline(trimmed, `p-${idx}`)}
        </p>
      );
    }
  });
  flushList();
  return blocks;
}

function FieldRow({ label, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", padding: "0.55rem 0", borderBottom: `1px solid ${T.border}` }}>
      <span style={{ fontFamily: SANS, color: T.parchmentDim, fontSize: "0.85rem" }}>{label}</span>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      style={{
        background: T.panelAlt,
        color: T.parchment,
        border: `1px solid ${T.border}`,
        borderRadius: "3px",
        padding: "0.3rem 0.5rem",
        fontFamily: SANS,
        fontSize: "0.85rem",
        minWidth: "9rem",
      }}
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

export default function App() {
  const [settings, setSettings] = useState(DEFAULTS);
  const [civ, setCiv] = useState("");
  const [playstyle, setPlaystyle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [strategy, setStrategy] = useState(null);

  function updateSetting(key, value) {
    setSettings((s) => ({ ...s, [key]: value }));
  }
  function toggleMode(key) {
    setSettings((s) => ({ ...s, modes: { ...s.modes, [key]: !s.modes[key] } }));
  }

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setStrategy(null);
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 1000,
          system: SYSTEM_PROMPT,
          messages: [{ role: "user", content: buildUserPrompt(settings, civ, playstyle) }],
        }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      const text = (data.content || [])
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("\n");
      if (!text) throw new Error("The coach came back empty-handed. Try again.");
      setStrategy(text);
    } catch (e) {
      setError((e && e.message) || "Something went wrong drafting the strategy.");
    } finally {
      setLoading(false);
    }
  }

  const activeModeCount = Object.values(settings.modes).filter(Boolean).length;

  return (
    <div style={{ minHeight: "100%", background: T.bg, fontFamily: SANS, color: T.parchment }}>
      <style>{`
        @keyframes pulse-dot { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
        .dot { display: inline-block; animation: pulse-dot 1.4s infinite; }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        select:focus, textarea:focus, input:focus, button:focus-visible {
          outline: 2px solid ${T.brass}; outline-offset: 2px;
        }
      `}</style>

      <div style={{ background: T.bgHero, borderBottom: `1px solid ${T.border}`, padding: "2rem 1.5rem 1.5rem" }}>
        <div style={{ maxWidth: "72rem", margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.4rem" }}>
            <span style={{ color: T.brass, fontSize: "0.95rem" }}>◆</span>
            <span style={{ fontFamily: SANS, color: T.brassDim, fontSize: "0.75rem", letterSpacing: "0.04em" }}>
              Civilization VI build coach
            </span>
          </div>
          <h1 style={{ fontFamily: SERIF, fontSize: "2rem", color: T.parchment, margin: 0 }}>The Briefing Table</h1>
          <p style={{ color: T.parchmentDim, marginTop: "0.5rem", maxWidth: "38rem", lineHeight: 1.6 }}>
            Set the table the way you actually play, tell the coach what you're after, and get a complete build
            plan back — civ, tech, civics, city layout, government, all of it.
          </p>
        </div>
      </div>

      <div style={{ maxWidth: "72rem", margin: "0 auto", padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 20rem", minWidth: "18rem", background: T.panel, border: `1px solid ${T.border}`, borderRadius: "4px", padding: "1.25rem" }}>
            <h2 style={{ fontFamily: SERIF, color: T.brass, fontSize: "1.05rem", marginTop: 0, marginBottom: "0.75rem" }}>Game setup</h2>

            <FieldRow label="Ruleset">
              <Select value={settings.ruleset} onChange={(v) => updateSetting("ruleset", v)} options={["Vanilla", "Rise & Fall", "Gathering Storm"]} />
            </FieldRow>
            <FieldRow label="Difficulty">
              <Select value={settings.difficulty} onChange={(v) => updateSetting("difficulty", v)} options={["Settler", "Chieftain", "Warlord", "Prince", "King", "Emperor", "Immortal", "Deity"]} />
            </FieldRow>
            <FieldRow label="Game speed">
              <Select value={settings.gameSpeed} onChange={(v) => updateSetting("gameSpeed", v)} options={["Online", "Quick", "Standard", "Epic", "Marathon"]} />
            </FieldRow>
            <FieldRow label="Map type">
              <Select value={settings.mapType} onChange={(v) => updateSetting("mapType", v)} options={["Continents", "Pangaea", "Fractal", "Archipelago", "Inland Sea", "Highlands", "Terra Incognita", "Small Continents", "Lakes", "Shuffle"]} />
            </FieldRow>
            <FieldRow label="Map size">
              <Select value={settings.mapSize} onChange={(v) => updateSetting("mapSize", v)} options={["Duel", "Tiny", "Small", "Standard", "Large", "Huge"]} />
            </FieldRow>
            <FieldRow label="City-states">
              <input
                type="number" min={0} max={24} value={settings.cityStates}
                onChange={(e) => updateSetting("cityStates", Number(e.target.value))}
                style={{ background: T.panelAlt, color: T.parchment, border: `1px solid ${T.border}`, borderRadius: "3px", padding: "0.3rem 0.5rem", width: "4rem", fontFamily: SANS, fontSize: "0.85rem" }}
              />
            </FieldRow>
            <FieldRow label="Disaster intensity">
              <input
                type="number" min={0} max={4} value={settings.disasterIntensity}
                onChange={(e) => updateSetting("disasterIntensity", Number(e.target.value))}
                style={{ background: T.panelAlt, color: T.parchment, border: `1px solid ${T.border}`, borderRadius: "3px", padding: "0.3rem 0.5rem", width: "4rem", fontFamily: SANS, fontSize: "0.85rem" }}
              />
            </FieldRow>
            <FieldRow label="Resources">
              <Select value={settings.resources} onChange={(v) => updateSetting("resources", v)} options={["Sparse", "Standard", "Abundant"]} />
            </FieldRow>
            <FieldRow label="World age">
              <Select value={settings.worldAge} onChange={(v) => updateSetting("worldAge", v)} options={["Old", "New"]} />
            </FieldRow>
            <FieldRow label="Start position">
              <Select value={settings.startPosition} onChange={(v) => updateSetting("startPosition", v)} options={["Standard", "Balanced", "Legendary"]} />
            </FieldRow>
            <FieldRow label="Temperature">
              <Select value={settings.temperature} onChange={(v) => updateSetting("temperature", v)} options={["Hot", "Standard", "Cold"]} />
            </FieldRow>
            <FieldRow label="Rainfall">
              <Select value={settings.rainfall} onChange={(v) => updateSetting("rainfall", v)} options={["Arid", "Standard", "Wet"]} />
            </FieldRow>
            <FieldRow label="Sea level">
              <Select value={settings.seaLevel} onChange={(v) => updateSetting("seaLevel", v)} options={["Low", "Standard", "High"]} />
            </FieldRow>

            <h2 style={{ fontFamily: SERIF, color: T.brass, fontSize: "1.05rem", marginTop: "1.5rem", marginBottom: "0.6rem" }}>
              Game modes {activeModeCount ? `(${activeModeCount} on)` : ""}
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {MODES.map((m) => (
                <label key={m.key} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", color: T.parchmentDim, cursor: "pointer" }}>
                  <input type="checkbox" checked={settings.modes[m.key]} onChange={() => toggleMode(m.key)} style={{ accentColor: T.brass }} />
                  {m.label}
                </label>
              ))}
            </div>
          </div>

          <div style={{ flex: "1 1 20rem", minWidth: "18rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: "4px", padding: "1.25rem" }}>
              <h2 style={{ fontFamily: SERIF, color: T.brass, fontSize: "1.05rem", marginTop: 0, marginBottom: "0.75rem" }}>Civilization</h2>
              <select
                value={civ} onChange={(e) => setCiv(e.target.value)}
                style={{ width: "100%", background: T.panelAlt, color: T.parchment, border: `1px solid ${T.border}`, borderRadius: "3px", padding: "0.5rem 0.6rem", fontFamily: SANS, fontSize: "0.9rem" }}
              >
                <option value="">No preference — coach's pick</option>
                {CIVS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: "4px", padding: "1.25rem", display: "flex", flexDirection: "column", flex: 1 }}>
              <h2 style={{ fontFamily: SERIF, color: T.brass, fontSize: "1.05rem", marginTop: 0, marginBottom: "0.75rem" }}>How do you want to play?</h2>
              <textarea
                value={playstyle}
                onChange={(e) => setPlaystyle(e.target.value)}
                placeholder="A vibe, a victory type, a challenge — e.g. 'few cities, big wonders, culture win' or 'go wide and crush people militarily.'"
                style={{ flex: 1, minHeight: "8rem", background: T.panelAlt, color: T.parchment, border: `1px solid ${T.border}`, borderRadius: "3px", padding: "0.65rem", fontFamily: SANS, fontSize: "0.9rem", resize: "vertical", lineHeight: 1.5 }}
              />
              <button
                onClick={handleGenerate}
                disabled={loading}
                style={{ marginTop: "1rem", background: loading ? T.brassDim : T.rust, color: T.parchment, border: "none", borderRadius: "3px", padding: "0.65rem 1rem", fontFamily: SANS, fontWeight: 600, fontSize: "0.9rem", cursor: loading ? "default" : "pointer" }}
              >
                {loading ? "Drafting the plan..." : "Draft the strategy"}
              </button>
            </div>
          </div>
        </div>

        <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: "4px", padding: "1.5rem", minHeight: "12rem" }}>
          {!strategy && !loading && !error && (
            <div style={{ textAlign: "center", padding: "2rem 1rem" }}>
              <div style={{ color: T.brassDim, fontSize: "1.2rem", marginBottom: "0.5rem" }}>◆</div>
              <p style={{ color: T.parchmentDim, fontFamily: SERIF, fontSize: "1.05rem" }}>
                The board is set. Describe your build and the coach will draft your plan.
              </p>
            </div>
          )}

          {loading && (
            <div style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
              <p style={{ fontFamily: SERIF, color: T.parchment, fontSize: "1.05rem", marginBottom: "0.5rem" }}>
                The coach is studying the board<span className="dot">.</span><span className="dot">.</span><span className="dot">.</span>
              </p>
            </div>
          )}

          {error && (
            <div style={{ textAlign: "center", padding: "1.5rem 1rem" }}>
              <p style={{ color: T.rust, marginBottom: "1rem" }}>{error}</p>
              <button
                onClick={handleGenerate}
                style={{ background: T.panelAlt, color: T.parchment, border: `1px solid ${T.border}`, borderRadius: "3px", padding: "0.5rem 1rem", cursor: "pointer" }}
              >
                Try again
              </button>
            </div>
          )}

          {strategy && !loading && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem", borderBottom: `1px solid ${T.border}`, paddingBottom: "0.75rem" }}>
                <h2 style={{ fontFamily: SERIF, color: T.parchment, fontSize: "1.3rem", margin: 0 }}>Coach's dossier</h2>
                <button
                  onClick={() => { setStrategy(null); setError(null); }}
                  style={{ background: "transparent", color: T.brassDim, border: `1px solid ${T.border}`, borderRadius: "3px", padding: "0.35rem 0.7rem", fontSize: "0.8rem", cursor: "pointer" }}
                >
                  New briefing
                </button>
              </div>
              <div style={{ maxWidth: "42rem" }}>{renderMarkdown(strategy)}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
