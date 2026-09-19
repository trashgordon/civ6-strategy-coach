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

from . import config, ruleset

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
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

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
    ("GovernorPromotionSets", "", "_governor_promotion_sets", "internal"),
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
    ("LOC_ALLIANCE_", "", "alliances", "Alliance types", r" Alliance$"),
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


def _governor_kits(
    rows: dict[str, list[dict[str, str]]],
    strings: dict[str, set[str]],
    effects: dict[str, str],
) -> list[dict]:
    """Each governor with the promotions that are actually theirs.

    Injected as a flat list of 70 promotions, the model can't tell which governor a
    promotion belongs to, so it hedged — "take the promotion that boosts Great Person
    points" instead of naming Grants. The game links them; this carries the link.
    """
    # GovernorType -> display name, from the rows that carry a Name.
    names: dict[str, str] = {}
    for row in rows.get("Governors", []):
        gtype, key = row.get("GovernorType"), row.get("Name")
        if gtype and key:
            values = strings.get(key, set())
            if values:
                cleaned = _clean(sorted(values)[0])
                if cleaned:
                    names.setdefault(gtype, cleaned)

    # GovernorPromotionType -> display name.
    promo_names: dict[str, str] = {}
    for row in rows.get("GovernorPromotions", []):
        ptype, key = row.get("GovernorPromotionType"), row.get("Name")
        if ptype and key:
            values = strings.get(key, set())
            if values:
                cleaned = _clean(sorted(values)[0])
                if cleaned:
                    promo_names.setdefault(ptype, cleaned)

    grouped: dict[str, list[str]] = {}
    for row in rows.get("GovernorPromotionSets", []):
        gtype, ptype = row.get("GovernorType"), row.get("GovernorPromotion")
        if not gtype or not ptype:
            continue
        name = promo_names.get(ptype)
        if name:
            grouped.setdefault(gtype, [])
            if name not in grouped[gtype]:
                grouped[gtype].append(name)

    kits = []
    for gtype, promotions in grouped.items():
        governor = names.get(gtype)
        if not governor:
            continue
        kits.append(
            {
                "governor": governor,
                "promotions": [
                    {"name": n, "effect": effects.get(n, "")} for n in promotions
                ],
            }
        )
    return sorted(kits, key=lambda k: k["governor"])


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


def _display_names(assets: Path) -> dict[str, str]:
    """LOC_* key -> the one name a player sees, ignoring scenario rewrites.

    Unlike the validation whitelist, the tree has to say *which* name is right, so
    "Catholic Monarchy" (Black Death scenario) must not stand in for Monarchy.
    """
    names: dict[str, set[str]] = defaultdict(set)
    for path in assets.rglob("Text/en_US/*.xml"):
        if ruleset._is_optional_content(path.relative_to(assets)):
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        for tag, value in _LOC_ROW.findall(content):
            if value.strip():
                names[tag].add(value.strip())
    return {tag: sorted(values, key=lambda v: (len(v), v))[0] for tag, values in names.items()}


# Gameplay table -> (its type column, what the tree calls it).
_UNLOCKABLES = (
    ("Districts", "DistrictType", "district"),
    ("Buildings", "BuildingType", "building"),
    ("Improvements", "ImprovementType", "improvement"),
    ("Units", "UnitType", "unit"),
    ("Governments", "GovernmentType", "government"),
    ("Policies", "PolicyType", "policy card"),
)
_REPLACES = {
    "Districts": ("DistrictReplaces", "CivUniqueDistrictType", "ReplacesDistrictType"),
    "Buildings": ("BuildingReplaces", "CivUniqueBuildingType", "ReplacesBuildingType"),
    "Units": ("UnitReplaces", "CivUniqueUnitType", "ReplacesUnitType"),
}


def _tree(db: "ruleset.Database", names: dict[str, str]) -> dict:
    """One ruleset's techs and civics — era, cost, prerequisites — and what each unlocks."""

    def name(key: str | None) -> str | None:
        return _clean(names.get(key or "", "")) if key else None

    def era(key: str | None) -> str:
        return (key or "").removeprefix("ERA_").replace("_", " ").title()

    out: dict = {"technologies": {}, "civics": {}, "unlocks": [], "wonders": {}}
    type_names: dict[str, str] = {}
    for table, type_col, prereq_table, item_col, prereq_col, bucket in (
        ("Technologies", "TechnologyType", "TechnologyPrereqs", "Technology", "PrereqTech", "technologies"),
        ("Civics", "CivicType", "CivicPrereqs", "Civic", "PrereqCivic", "civics"),
    ):
        for row in db.rows(table):
            display = name(row.get("Name"))
            if display:
                type_names[row[type_col]] = display
        for row in db.rows(table):
            display = type_names.get(row[type_col])
            if not display or row.get("Repeatable") == "true":
                continue  # Future Tech / Future Civic repeat; there's no path to plan
            needs = sorted(
                type_names[r[prereq_col]]
                for r in db.rows(prereq_table)
                if r.get(item_col) == row[type_col] and r.get(prereq_col) in type_names
            )
            try:
                cost = int(row.get("Cost") or 0)
            except ValueError:
                cost = 0
            out[bucket][display] = {"era": era(row.get("EraType")), "cost": cost, "needs": needs}

    # Which major civ owns a unique, via its civ trait or its leader's trait.
    majors = {
        row["CivilizationType"]: name(row.get("Name"))
        for row in db.rows("Civilizations")
        if row.get("StartingCivilizationLevelType") == "CIVILIZATION_LEVEL_FULL_CIV"
    }
    trait_civ: dict[str, str] = {}
    for row in db.rows("CivilizationTraits"):
        if majors.get(row.get("CivilizationType")):
            trait_civ[row["TraitType"]] = majors[row["CivilizationType"]]
    leader_civ = {
        row["LeaderType"]: majors[row["CivilizationType"]]
        for row in db.rows("CivilizationLeaders")
        if majors.get(row.get("CivilizationType"))
    }
    for row in db.rows("LeaderTraits"):
        if row.get("LeaderType") in leader_civ:
            trait_civ.setdefault(row["TraitType"], leader_civ[row["LeaderType"]])

    seen: set[tuple[str, str]] = set()
    for table, type_col, kind in _UNLOCKABLES:
        rows = {row[type_col]: row for row in db.rows(table) if row.get(type_col)}
        replaces = {}
        if table in _REPLACES:
            rep_table, unique_col, base_col = _REPLACES[table]
            replaces = {r[unique_col]: r.get(base_col) for r in db.rows(rep_table)}
        for type_key, row in rows.items():
            trait = row.get("TraitType")
            civ = trait_civ.get(trait or "", "")
            if trait and not civ:
                continue  # a city-state's, a barbarian's, or a game mode's
            source = row
            if not (row.get("PrereqTech") or row.get("PrereqCivic")) and type_key in replaces:
                source = rows.get(replaces[type_key]) or row  # a unique inherits its unlock
            tech, civic = source.get("PrereqTech"), source.get("PrereqCivic")
            by = type_names.get(tech or "") or type_names.get(civic or "")
            display = name(row.get("Name"))
            if not by or not display or (display, civ) in seen:
                continue
            seen.add((display, civ))
            entry_kind = "wonder" if table == "Buildings" and row.get("IsWonder") == "true" else kind
            out["unlocks"].append({
                "name": display, "kind": entry_kind, "by": by,
                "tree": "technology" if type_names.get(tech or "") else "civic",
                "civ": civ,
            })
    out["unlocks"].sort(key=lambda u: (u["by"], u["kind"], u["name"]))

    # What each wonder does, as this ruleset describes it (the expansions rewrite some
    # descriptions), with its cost. The text includes the placement rule — "Must be
    # built on Desert or Floodplains without Hills" — which the coach otherwise guesses.
    unlocked_by = {u["name"]: u["by"] for u in out["unlocks"] if u["kind"] == "wonder"}
    for row in db.rows("Buildings"):
        if row.get("IsWonder") != "true":
            continue
        display = name(row.get("Name"))
        effect = _clean_text(names.get(row.get("Description") or "", ""))
        if not display or not effect or display not in unlocked_by:
            continue  # no way to build it in this ruleset
        try:
            cost = int(row.get("Cost") or 0)
        except ValueError:
            cost = 0
        out["wonders"][display] = {"effect": effect, "cost": cost, "by": unlocked_by[display]}
    return out


def _trees(assets: Path) -> dict[str, dict]:
    names = _display_names(assets)
    return {label: _tree(ruleset.load(assets, label), names) for label in ruleset.RULESETS}


def _game_speeds(assets: Path, names: dict[str, str]) -> dict[str, int]:
    """{"Marathon": 300, ...}: each speed's cost multiplier, as a percentage of Standard.

    The coach is told to scale its turn benchmarks to the speed but not by how much, and
    it under-scaled Marathon to about 2-2.5x. The game says 3x; this is where it says so.
    """
    import xml.etree.ElementTree as ET

    path = assets / "Base" / "Assets" / "Gameplay" / "Data" / "GameSpeeds.xml"
    try:
        root = ET.fromstring(path.read_text(errors="ignore"))
    except (OSError, ET.ParseError):
        return {}
    speeds = {}
    for row in root.iterfind("GameSpeeds/Row"):
        values = {**row.attrib, **{c.tag: (c.text or "").strip() for c in row}}
        name = _clean(names.get(values.get("Name", ""), ""))
        try:
            multiplier = int(values.get("CostMultiplier", ""))
        except ValueError:
            continue
        if name:
            speeds[name] = multiplier
    return speeds


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

    for group in _LOC_PREFIX_GROUPS:
        prefix, suffix, out_name = group[0], group[1], group[2]
        # Optional 5th element: a pattern the value itself must match.
        value_pattern = re.compile(group[4]) if len(group) > 4 else None
        harvested = {
            _clean(value)
            for tag, values in strings.items()
            if tag.startswith(prefix) and tag.endswith(suffix)
            for value in values
            if value_pattern is None or value_pattern.search(value)
        }
        facts[out_name] = sorted(v for v in harvested if v)

    facts["city_states"] = _city_states(assets, strings)
    facts["dedication_bonuses"] = _dedications(assets, strings)
    facts["effects"] = _effects(rows, strings)
    facts["governor_kits"] = _governor_kits(rows, strings, facts["effects"])
    # Per ruleset: the expansions rewrite the tree, so one merged tree would be wrong.
    facts["tree"] = _trees(assets)
    facts["game_speeds"] = _game_speeds(assets, _display_names(assets))
    # A scan-only table; it exists to build governor_kits, not to be listed.
    facts.pop("_governor_promotion_sets", None)

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
        elif name == "tree":
            note = " rulesets (tech & civic prerequisites, unlocks)"
        print(f"  {name:22} {len(values):>5}{note}")
    print(f"\n  {'TOTAL':22} {total:>5} names -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
