"""Rebuild the game's database for one ruleset, just far enough to read the tech tree.

The expansions don't only add rows — Gathering Storm deletes base-game prerequisites
(Cartography no longer needs Shipbuilding) and rewrites others. Reading every XML file
in one pile, the way the name extractor does, would merge three different trees into
one wrong one. So this applies each file's <Row>, <Replace>, <Update> and <Delete>
operations in the order the game does, using the `.modinfo` files to decide which files
a ruleset loads.

Only the handful of tables the tree needs are kept, and game modes (Heroes, Secret
Societies, ...) and scenarios are left out: they're opt-in setups, not the ruleset.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# The app's ruleset labels -> (the game's ruleset id, its game core, its player list).
RULESETS = {
    "Vanilla": ("RULESET_STANDARD", "Base", "StandardPlayers"),
    "Rise & Fall": ("RULESET_EXPANSION_1", "Expansion1", "Expansion1_Players"),
    "Gathering Storm": ("RULESET_EXPANSION_2", "Expansion2", "Expansion2_Players"),
}
DEFAULT_RULESET = "Gathering Storm"

# Table -> the columns that identify a row, for <Replace>.
TABLE_KEYS = {
    "Technologies": ("TechnologyType",),
    "TechnologyPrereqs": ("Technology", "PrereqTech"),
    "Civics": ("CivicType",),
    "CivicPrereqs": ("Civic", "PrereqCivic"),
    "Units": ("UnitType",),
    "UnitReplaces": ("CivUniqueUnitType",),
    "Buildings": ("BuildingType",),
    "BuildingReplaces": ("CivUniqueBuildingType",),
    "Districts": ("DistrictType",),
    "DistrictReplaces": ("CivUniqueDistrictType",),
    "Improvements": ("ImprovementType",),
    "Policies": ("PolicyType",),
    "Governments": ("GovernmentType",),
    "Civilizations": ("CivilizationType",),
    "CivilizationTraits": ("CivilizationType", "TraitType"),
    "CivilizationLeaders": ("CivilizationType", "LeaderType"),
    "LeaderTraits": ("LeaderType", "TraitType"),
    "Eras": ("EraType",),
}


@dataclass
class Database:
    tables: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    def rows(self, table: str) -> list[dict[str, str]]:
        return self.tables.get(table, [])


# ------------------------------------------------------------------ applying one file


def _values(element: ET.Element) -> dict[str, str]:
    """A row written as attributes, child elements, or both. `<Description/>` is ''."""
    values = dict(element.attrib)
    for child in element:
        values[child.tag] = (child.text or "").strip()
    return values


def _matches(row: dict[str, str], where: dict[str, str]) -> bool:
    return all(row.get(k) == v for k, v in where.items())


def apply_xml(db: Database, content: str) -> None:
    """Apply one gameplay XML file. Unparseable files are skipped, as the game would."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return
    for table in root:
        keys = TABLE_KEYS.get(table.tag)
        if keys is None:
            continue
        rows = db.tables.setdefault(table.tag, [])
        for op in table:
            if op.tag == "Row":
                row = _values(op)
                key = {k: row.get(k) for k in keys}
                # A duplicate key is an error in the game, which keeps the first row.
                if not any(_matches(r, key) for r in rows):
                    rows.append(row)
            elif op.tag == "Replace":
                row = _values(op)
                key = {k: row.get(k) for k in keys}
                rows[:] = [r for r in rows if not _matches(r, key)]
                rows.append(row)
            elif op.tag == "Delete":
                where = _values(op)
                rows[:] = [r for r in rows if not _matches(r, where)]
            elif op.tag == "Update":
                where_el, set_el = op.find("Where"), op.find("Set")
                if where_el is None or set_el is None:
                    continue
                where, changes = _values(where_el), _values(set_el)
                for row in rows:
                    if _matches(row, where):
                        row.update(changes)


# ------------------------------------------------------------- which files, what order


def _criterion_met(element: ET.Element, ruleset: str, installed_mods: set[str]) -> bool:
    ruleset_id, game_core, players = RULESETS[ruleset]
    text = (element.text or "").strip()
    listed = [part.strip() for part in text.split(",") if part.strip()]
    if element.tag == "RuleSetInUse":
        return ruleset_id in listed
    if element.tag == "GameCoreInUse":
        return text == game_core
    if element.tag == "LeaderPlayable":
        # "Players:Expansion2_Players::LEADER_KUPE" — playable in this ruleset's list.
        return any(entry.split("::")[0].endswith(f":{players}") for entry in listed)
    if element.tag == "ModInUse":
        return text.upper() in installed_mods
    # Game modes (ConfigurationValueMatches) and anything unrecognised: not the ruleset.
    return False


def _criteria(modinfo: ET.Element, ruleset: str, installed_mods: set[str]) -> dict[str, bool]:
    met = {}
    for criteria in modinfo.iter("Criteria"):
        results = [_criterion_met(c, ruleset, installed_mods) for c in criteria]
        if not results:
            met[criteria.get("id", "")] = True
        elif criteria.get("any") == "1":
            met[criteria.get("id", "")] = any(results)
        else:
            met[criteria.get("id", "")] = all(results)
    return met


def _is_optional_content(path: Path) -> bool:
    """Scenarios and the tutorial aren't part of any ruleset."""
    return any("Scenario" in part or "Tutorial" in part for part in path.parts)


def _parse_modinfo(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_text(errors="ignore"))
    except (OSError, ET.ParseError):
        return None


def load_order(assets: Path, ruleset: str) -> list[Path]:
    """Every gameplay XML file the ruleset loads, in the order it loads them."""
    base = sorted((assets / "Base" / "Assets" / "Gameplay" / "Data").glob("*.xml"))

    modinfos = [
        (path, parsed)
        for path in sorted((assets / "DLC").glob("*/*.modinfo"))
        if not _is_optional_content(path.relative_to(assets))
        and (parsed := _parse_modinfo(path)) is not None
    ]
    installed = {(parsed.get("id") or "").upper() for _, parsed in modinfos}

    staged: list[tuple[int, int, int, Path]] = []
    for mod_index, (path, modinfo) in enumerate(modinfos):
        met = _criteria(modinfo, ruleset, installed)
        for action in modinfo.iter("UpdateDatabase"):
            criteria = action.get("criteria")
            if criteria and not met.get(criteria, False):
                continue
            order = action.findtext("Properties/LoadOrder") or "0"
            try:
                load_order_value = int(order.strip())
            except ValueError:
                load_order_value = 0
            for file_el in action.findall("File"):
                name = (file_el.text or "").strip()
                if not name.lower().endswith(".xml"):
                    continue
                # Within one action, higher Priority loads first.
                priority = int(file_el.get("Priority", "0") or 0)
                staged.append((load_order_value, mod_index, -priority, path.parent / name))
    staged.sort(key=lambda item: item[:3])
    return base + [path for *_, path in staged if path.is_file()]


def load(assets: Path, ruleset: str) -> Database:
    db = Database()
    for path in load_order(assets, ruleset):
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        # Cheap filter: most files touch none of our tables.
        if not re.search(r"<(" + "|".join(TABLE_KEYS) + r")>", content):
            continue
        apply_xml(db, content)
    return db
