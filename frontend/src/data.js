// Field lists and defaults, lifted from the prototype so the form matches the game's
// own setup screen.

export const CIVS = [
  "America", "Arabia", "Australia", "Aztec", "Babylon", "Brazil", "Byzantium", "Canada",
  "China", "Cree", "Egypt", "England", "Ethiopia", "France", "Gaul", "Georgia",
  "Germany", "Gran Colombia", "Greece", "Hungary", "Inca", "India", "Indonesia", "Japan",
  "Khmer", "Kongo", "Korea", "Macedon", "Mali", "Maori", "Mapuche", "Maya",
  "Mongolia", "Netherlands", "Norway", "Ottoman", "Persia", "Phoenicia", "Poland", "Rome",
  "Russia", "Scotland", "Scythia", "Spain", "Sumeria", "Sweden", "Vietnam", "Zulu",
];

export const MODES = [
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

// The persona's default setup — Gathering Storm, Prince, Pangaea, and the two modes
// that are actually on.
export const DEFAULT_CONFIG = {
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

export const NO_PREFERENCE = "No preference";

export const CITY_PHILOSOPHIES = ["Tall", "Wide", NO_PREFERENCE];
export const PRIMARY_FOCUSES = [
  "Culture", "Science", "Domination", "Religion", "Diplomacy", NO_PREFERENCE,
];
export const POSTURES = [
  "Aggressive / militaristic", "Introverted / peaceful", NO_PREFERENCE,
];

export const SETUP_FIELDS = [
  { key: "ruleset", label: "Ruleset", options: ["Vanilla", "Rise & Fall", "Gathering Storm"] },
  { key: "difficulty", label: "Difficulty", options: ["Settler", "Chieftain", "Warlord", "Prince", "King", "Emperor", "Immortal", "Deity"] },
  { key: "gameSpeed", label: "Game speed", options: ["Online", "Quick", "Standard", "Epic", "Marathon"] },
  { key: "mapType", label: "Map type", options: ["Continents", "Pangaea", "Fractal", "Archipelago", "Inland Sea", "Highlands", "Terra Incognita", "Small Continents", "Lakes", "Shuffle"] },
  { key: "mapSize", label: "Map size", options: ["Duel", "Tiny", "Small", "Standard", "Large", "Huge"] },
  { key: "cityStates", label: "City-states", number: { min: 0, max: 24 } },
  { key: "disasterIntensity", label: "Disaster intensity", number: { min: 0, max: 4 } },
  { key: "resources", label: "Resources", options: ["Sparse", "Standard", "Abundant"] },
  { key: "worldAge", label: "World age", options: ["Old", "New"] },
  { key: "startPosition", label: "Start position", options: ["Standard", "Balanced", "Legendary"] },
  { key: "temperature", label: "Temperature", options: ["Hot", "Standard", "Cold"] },
  { key: "rainfall", label: "Rainfall", options: ["Arid", "Standard", "Wet"] },
  { key: "seaLevel", label: "Sea level", options: ["Low", "Standard", "High"] },
];


// "Surprise me" picks a definite build, so No preference is deliberately excluded —
// a randomiser that shrugs isn't a surprise.
function pick(options) {
  const real = options.filter((o) => o !== NO_PREFERENCE);
  return real[Math.floor(Math.random() * real.length)];
}

export function randomBuildStyle() {
  return {
    civ: pick(CIVS),
    cityPhilosophy: pick(CITY_PHILOSOPHIES),
    primaryFocus: pick(PRIMARY_FOCUSES),
    posture: pick(POSTURES),
  };
}
