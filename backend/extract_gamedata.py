"""Extract canonical Civ VI names from your own game install.

    python -m backend.extract_gamedata

Writes JSON to `data/facts/`, which is gitignored — and must stay that way. The names
and descriptions are Firaxis/2K's copyrighted content, so this repo ships the extractor,
never the extracted data. Everyone runs it against the copy of the game they own, which
also means the output matches whichever DLC and patch they actually have.

Nothing here is required: with no facts on disk the app behaves exactly as before.
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import config

# Where the game usually lives, per platform. CIV6_PATH overrides all of it.
_CANDIDATE_ROOTS = [
    # macOS (Steam)
    "~/Library/Application Support/Steam/steamapps/common/Sid Meier's Civilization VI",
    # Windows (Steam / Epic)
    "C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization VI",
    "C:/Program Files/Epic Games/SidMeiersCivilizationVI",
    # Linux (Steam / Proton)
    "~/.steam/steam/steamapps/common/Sid Meier's Civilization VI",
    "~/.local/share/Steam/steamapps/common/Sid Meier's Civilization VI",
]

# <Row Tag="LOC_TECH_POTTERY_NAME"><Text>Pottery</Text></Row>
_LOC_ROW = re.compile(
    r'<Row\s+Tag="(LOC_[A-Z0-9_]+)"[^>]*>\s*<Text>(.*?)</Text>', re.DOTALL
)
_XML_ROW = re.compile(r"<Row\s+([^>]*?)/?>", re.DOTALL)
# <Row Type="CIVILIZATION_KUMASI" Name="CityStateCategory" Value="CULTURAL"/>
_COMMEMORATION_ROW = re.compile(r'<Row CommemorationType="([A-Z_]+)"([^>]*)/>')
_CITY_STATE_CATEGORY = re.compile(
    r'<Row\s+Type="(CIVILIZATION_[A-Z_]+)"\s+Name="CityStateCategory"\s+Value="([A-Z]+)"'
)
# Game text is full of [ICON_Culture] markup that means nothing to a model.
_ICON = re.compile(r"\[ICON_([A-Za-z]+)\]")
_BRACKETED = re.compile(r"\[[^\]]*\]")
_ATTR = re.compile(r'(\w+)="([^"]*)"')

# Table -> (the attribute holding the display-name key, output filename, label).
# Wonders are split out of Buildings by the IsWonder flag.
# Groups where naming the thing isn't enough — the coach makes claims about what it
# does, and recalling that from training is where the errors come from ("Corvée for
# settlers" when Corvée is +15% production toward ancient and classical wonders).
# A tuple, not a set: two tables can define rows that resolve to the same display
# name, so iteration order decides which effect wins and must be deterministic.
# Buildings and Improvements were dropped deliberately: ~5,300 cached tokens for
# effects the coach rarely reasons about, where policy cards and civ abilities are
# where the misattributions actually happened. Governor promotions stay.
_WITH_EFFECTS = (
    "Policies", "Beliefs", "Civics", "Technologies", "Governments", "Districts",
    "Governors", "GovernorPromotions",
)

_TABLES = [
    ("Technologies", "Name", "technologies", "Technologies"),
    ("Civics", "Name", "civics", "Civics"),
    ("Buildings", "Name", "buildings", "Buildings"),
    ("Districts", "Name", "districts", "Districts"),
    ("Policies", "Name", "policy_cards", "Policy cards"),
    ("Beliefs", "Name", "beliefs", "Religious beliefs"),
    ("Governments", "Name", "governments", "Governments"),
    ("Governors", "Name", "governors", "Governors"),
    ("GovernorPromotions", "Name", "governor_promotions", "Governor promotions"),
    ("Units", "Name", "units", "Units"),
    ("Improvements", "Name", "improvements", "Improvements"),
    ("Resources", "Name", "resources", "Resources"),
    ("Civilizations", "Name", "civilizations", "Civilizations"),
    ("Leaders", "Name", "leaders", "Leaders"),
    # Not for the prompt — these exist so validation doesn't flag an era, a yield or a
    # Great Person the coach legitimately named.
    ("Eras", "Name", "eras", "Eras"),
    ("Yields", "Name", "yields", "Yields"),
    ("Religions", "Name", "religions", "Religions"),
    ("GreatPersonIndividuals", "Name", "great_people", "Great People"),
    ("Projects", "Name", "projects", "Projects"),
    ("Features", "Name", "features", "Map features"),
    ("Terrains", "Name", "terrains", "Terrains"),
    ("BeliefClasses", "Name", "belief_classes", "Belief classes"),
]

# Some names only exist in the localization files, with no gameplay table carrying a
# Name attribute — civ and leader abilities ("Enuma Anu Enlil") are the big one.
_LOC_PREFIX_GROUPS = [
    ("LOC_TRAIT_", "_NAME", "abilities", "Civ & leader abilities"),
]


def find_install() -> Path | None:
    override = os.getenv("CIV6_PATH", "").strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_dir() else None
    for candidate in _CANDIDATE_ROOTS:
        path = Path(candidate).expanduser()
        if path.is_dir():
            return path
    return None


def _assets_dir(install: Path) -> Path | None:
    """The Assets tree, which sits inside the .app bundle on macOS."""
    for candidate in (
        install / "Civ6.app" / "Contents" / "Assets",
        install / "Sid Meier's Civilization VI.app" / "Contents" / "Assets",
        install / "Assets",
    ):
        if candidate.is_dir():
            return candidate
    # Fall back to hunting for it.
    for base in install.rglob("Assets"):
        if (base / "Base").is_dir():
            return base
    return None


def _load_localization(assets: Path) -> dict[str, set[str]]:
    """LOC_* key -> every English display text defined for it.

    Scenario DLC reuses base-game keys for different things: the Black Death scenario
    redefines LOC_GOVERNMENT_MONARCHY_NAME as "Catholic Monarchy". Resolving a key to one
    winner would silently drop "Monarchy" from the whitelist, so keep every variant —
    for "is this a real name?" the union is exactly what we want.
    """
    strings: dict[str, set[str]] = defaultdict(set)
    for path in assets.rglob("Text/en_US/*.xml"):
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for tag, value in _LOC_ROW.findall(content):
            value = value.strip()
            if value:
                strings[tag].add(value)
    return strings


def _collect_rows(assets: Path) -> dict[str, list[dict[str, str]]]:
    """{table name: [row attribute dicts]} across every gameplay XML file."""
    tables: dict[str, list[dict[str, str]]] = defaultdict(list)
    wanted = {name for name, *_ in _TABLES}
    for path in assets.rglob("*.xml"):
        if "Text" in path.parts:
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for table in wanted:
            # Only scan the slice of the file inside <Table>...</Table>.
            for block in re.findall(
                rf"<{table}>(.*?)</{table}>", content, flags=re.DOTALL
            ):
                for raw in _XML_ROW.findall(block):
                    tables[table].append(dict(_ATTR.findall(raw)))
    return tables


def _effects(
    rows: dict[str, list[dict[str, str]]],
    strings: dict[str, set[str]],
) -> dict[str, str]:
    """{display name: what it actually does}, for every table that carries one."""
    found: dict[str, str] = {}
    for table in _WITH_EFFECTS:
        for row in rows.get(table, []):
            name_key, desc_key = row.get("Name"), row.get("Description")
            if not name_key or not desc_key:
                continue
            # The canonical pairing shares a stem: LOC_POLICY_CORVEE_{NAME,DESCRIPTION}.
            # Scenario rows reuse a display name with an unrelated key, which is how
            # "Serfdom" ended up described as a farm bonus.
            if name_key.removesuffix("_NAME") != desc_key.removesuffix("_DESCRIPTION"):
                continue
            names = strings.get(name_key, set())
            descriptions = strings.get(desc_key, set())
            if not names or not descriptions:
                continue
            name = _clean(sorted(names)[0])
            # Prefer the fullest wording when a scenario redefines the key.
            effect = _clean_text(sorted(descriptions, key=len)[-1])
            if name and effect and len(effect) <= 300:
                found.setdefault(name, effect)

    # Civ and leader abilities live only in localization, paired by tag.
    for tag, values in strings.items():
        if not (tag.startswith("LOC_TRAIT_") and tag.endswith("_NAME")):
            continue
        description = strings.get(tag[: -len("_NAME")] + "_DESCRIPTION", set())
        if not description:
            continue
        name = _clean(sorted(values)[0]) if values else None
        effect = _clean_text(sorted(description, key=len)[-1])
        if name and effect and len(effect) <= 300:
            found.setdefault(name, effect)
    return found


def _clean_text(value: str) -> str:
    """Strip Civ's icon markup so a bonus reads as a sentence."""
    value = _ICON.sub(r"\1", value or "")
    value = _BRACKETED.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    # "[ICON_Production] Production" expands to "Production Production".
    return re.sub(r"\b(\w+) \1\b", r"\1", value, flags=re.IGNORECASE)


def _dedications(assets: Path, strings: dict[str, set[str]]) -> list[dict[str, str]]:
    """Dedications with the era they're available in and all three age bonuses.

    A dedication isn't a Golden Age feature — you pick one at every era change. In a
    Golden Age it gives the strong effect; in a Normal or Dark Age it instead earns era
    score toward the next one. Advice that only covers the Golden case is advice for a
    third of the situations.
    """
    rows: dict[str, dict[str, str]] = {}
    for path in assets.rglob("*.xml"):
        if "Text" in path.parts:
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for ctype, rest in _COMMEMORATION_ROW.findall(content):
            attrs = dict(_ATTR.findall(rest))
            if "CategoryDescription" in attrs:
                rows.setdefault(ctype, attrs)

    def text(key: str, name: str) -> str:
        values = strings.get(key or "", set())
        if not values:
            return ""
        cleaned = _clean_text(sorted(values, key=len)[-1])
        # Strip the "<Name> Golden Age:" / "<Name> Dedication Bonus:" prefix.
        return re.sub(
            rf"^{re.escape(name)}\s*(?:Golden Age|Dedication Bonus)\s*:\s*",
            "", cleaned,
        ).strip()

    def era(value: str) -> str:
        return (value or "").replace("ERA_", "").replace("_", " ").title()

    out = []
    for attrs in rows.values():
        name = _clean(
            sorted(strings.get(attrs["CategoryDescription"], {""}))[0]
        )
        if not name:
            continue
        entry = {
            "name": name,
            "eras": f"{era(attrs.get('MinimumGameEra'))}–{era(attrs.get('MaximumGameEra'))}".strip("–"),
            "golden": text(attrs.get("GoldenAgeBonusDescription", ""), name),
            "normal": text(attrs.get("NormalAgeBonusDescription", ""), name),
            "dark": text(attrs.get("DarkAgeBonusDescription", ""), name),
        }
        if entry["golden"] or entry["normal"]:
            out.append(entry)
    return sorted(out, key=lambda e: e["name"])


def _city_states(assets: Path, strings: dict[str, set[str]]) -> list[dict[str, str]]:
    """Every city-state with its category and suzerain bonus.

    This is the one fact group that isn't just a name: "send envoys for suzerain
    bonuses" is useless advice, while "Geneva, +15% science while at peace" is a plan.
    """
    categories: dict[str, str] = {}
    for path in assets.rglob("*.xml"):
        if "Text" in path.parts:
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for civ, value in _CITY_STATE_CATEGORY.findall(content):
            categories[civ] = value.title()

    found: dict[str, dict[str, str]] = {}
    for civ, category in categories.items():
        names = strings.get(f"LOC_{civ}_NAME", set())
        bonuses = strings.get(f"LOC_{civ}_BONUS", set())
        name = _clean(sorted(names)[0]) if names else None
        bonus = _clean_text(sorted(bonuses, key=len)[-1]) if bonuses else ""
        if name and bonus:
            found[name] = {"name": name, "category": category, "bonus": bonus}
    return [found[k] for k in sorted(found)]


def _clean(name: str) -> str | None:
    """Drop unresolved keys, icon markup, and anything that isn't a plain name."""
    if not name:
        return None
    name = name.strip()
    if not name or name.startswith("LOC_"):
        return None
    if "[" in name or "{" in name or len(name) > 60:
        return None
    return name


def extract() -> dict[str, list]:
    install = find_install()
    if install is None:
        raise FileNotFoundError(
            "Couldn't find a Civilization VI install. Set CIV6_PATH to the game folder."
        )
    assets = _assets_dir(install)
    if assets is None:
        raise FileNotFoundError(f"Found {install} but no Assets directory inside it.")

    strings = _load_localization(assets)
    rows = _collect_rows(assets)

    facts: dict[str, list] = {}
    for table, name_attr, out_name, _label in _TABLES:
        names: set[str] = set()
        wonders: set[str] = set()
        for row in rows.get(table, []):
            key = row.get(name_attr)
            if not key:
                continue
            for raw in strings.get(key, ()):
                value = _clean(raw)
                if value is None:
                    continue
                if table == "Buildings" and row.get("IsWonder") == "true":
                    wonders.add(value)
                else:
                    names.add(value)
        facts[out_name] = sorted(names)
        if table == "Buildings":
            facts["wonders"] = sorted(wonders)

    for prefix, suffix, out_name, _label in _LOC_PREFIX_GROUPS:
        harvested = {
            _clean(value)
            for tag, values in strings.items()
            if tag.startswith(prefix) and tag.endswith(suffix)
            for value in values
        }
        facts[out_name] = sorted(v for v in harvested if v)

    facts["city_states"] = _city_states(assets, strings)
    facts["dedication_bonuses"] = _dedications(assets, strings)
    facts["effects"] = _effects(rows, strings)

    # Golden Age dedications are the commemoration categories, named via LOC_MOMENT_*.
    dedications = {
        _clean(value)
        for tag, values in strings.items()
        if tag.startswith("LOC_MOMENT_CATEGORY_")
        and not tag.endswith(("_GOLDEN_AGE", "_NORMAL_AGE", "_DARK_AGE"))
        for value in values
    }
    facts["dedications"] = sorted(d for d in dedications if d)

    return facts


def facts_dir() -> Path:
    return config.facts_path()


def main() -> int:
    try:
        facts = extract()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        print(
            "\nThe app works without this — it just won't be able to check the coach's\n"
            "names against the real game data.",
            file=sys.stderr,
        )
        return 1

    out = facts_dir()
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, values in sorted(facts.items()):
        (out / f"{name}.json").write_text(json.dumps(values, indent=1, ensure_ascii=False))
        total += len(values)
        note = ""
        if name == "city_states":
            note = " (with suzerain bonuses)"
        elif name == "effects":
            note = " (what things actually do)"
        elif name == "dedication_bonuses":
            note = " (golden / normal / dark age)"
        print(f"  {name:22} {len(values):>5}{note}")
    print(f"\n  {'TOTAL':22} {total:>5} names -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
