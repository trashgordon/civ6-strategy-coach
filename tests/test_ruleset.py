"""Rebuilding one ruleset's tech tree from the game's XML, the way the game loads it."""

import textwrap

from backend import extract_gamedata, ruleset


def _xml(body: str) -> str:
    return f"<GameInfo>{textwrap.dedent(body)}</GameInfo>"


def _prereqs(db, tech):
    return sorted(r["PrereqTech"] for r in db.rows("TechnologyPrereqs") if r["Technology"] == tech)


# --------------------------------------------------------------------- applying files


def test_rows_deletes_updates_and_replaces_apply_in_order():
    db = ruleset.Database()
    ruleset.apply_xml(db, _xml("""
        <Technologies>
          <Row TechnologyType="TECH_A" Cost="25"/>
          <Row><TechnologyType>TECH_B</TechnologyType><Cost>50</Cost></Row>
        </Technologies>
        <TechnologyPrereqs>
          <Row Technology="TECH_B" PrereqTech="TECH_A"/>
          <Row Technology="TECH_B" PrereqTech="TECH_OLD"/>
        </TechnologyPrereqs>
    """))
    ruleset.apply_xml(db, _xml("""
        <TechnologyPrereqs><Delete Technology="TECH_B" PrereqTech="TECH_OLD"/></TechnologyPrereqs>
        <Technologies>
          <Update><Where TechnologyType="TECH_A"/><Set><Cost>30</Cost></Set></Update>
          <Replace TechnologyType="TECH_B" Cost="99"/>
        </Technologies>
    """))
    costs = {r["TechnologyType"]: r["Cost"] for r in db.rows("Technologies")}
    assert costs == {"TECH_A": "30", "TECH_B": "99"}
    assert _prereqs(db, "TECH_B") == ["TECH_A"]


def test_a_duplicate_row_keeps_the_first_as_the_game_does():
    db = ruleset.Database()
    ruleset.apply_xml(db, _xml("""
        <Technologies>
          <Row TechnologyType="TECH_A" Cost="25"/>
          <Row TechnologyType="TECH_A" Cost="999"/>
        </Technologies>
    """))
    assert [r["Cost"] for r in db.rows("Technologies")] == ["25"]


def test_unparseable_files_and_unknown_tables_are_ignored():
    db = ruleset.Database()
    ruleset.apply_xml(db, "<GameInfo><Technologies><Row")
    ruleset.apply_xml(db, _xml('<Agendas><Row AgendaType="X"/></Agendas>'))
    assert db.tables == {}


# ------------------------------------------------------------- which files, what order


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _install(tmp_path):
    """Base game plus an expansion that rewrites a prerequisite, a scenario and a mode."""
    assets = tmp_path / "Assets"
    _write(assets / "Base/Assets/Gameplay/Data/Technologies.xml", _xml("""
        <Technologies>
          <Row TechnologyType="TECH_SHIPBUILDING"/><Row TechnologyType="TECH_CARTOGRAPHY"/>
        </Technologies>
        <TechnologyPrereqs>
          <Row Technology="TECH_CARTOGRAPHY" PrereqTech="TECH_SHIPBUILDING"/>
        </TechnologyPrereqs>
    """))
    _write(assets / "DLC/Expansion2/Expansion2.modinfo", """<Mod id="XP2">
      <ActionCriteria>
        <Criteria id="Expansion2"><GameCoreInUse>Expansion2</GameCoreInUse></Criteria>
        <Criteria id="Mode"><ConfigurationValueMatches><Group>Game</Group></ConfigurationValueMatches></Criteria>
      </ActionCriteria>
      <InGameActions>
        <UpdateDatabase id="Remove" criteria="Expansion2">
          <Properties><LoadOrder>-100</LoadOrder></Properties>
          <File Priority="1">Data/Remove.xml</File>
        </UpdateDatabase>
        <UpdateDatabase id="Content" criteria="Expansion2"><File>Data/Techs.xml</File></UpdateDatabase>
        <UpdateDatabase id="Heroes" criteria="Mode"><File>Data/Mode.xml</File></UpdateDatabase>
      </InGameActions></Mod>""")
    _write(assets / "DLC/Expansion2/Data/Remove.xml", _xml("""
        <TechnologyPrereqs>
          <Delete Technology="TECH_CARTOGRAPHY" PrereqTech="TECH_SHIPBUILDING"/>
        </TechnologyPrereqs>"""))
    _write(assets / "DLC/Expansion2/Data/Techs.xml", _xml("""
        <Technologies><Row TechnologyType="TECH_BUTTRESS"/></Technologies>
        <TechnologyPrereqs><Row Technology="TECH_CARTOGRAPHY" PrereqTech="TECH_BUTTRESS"/></TechnologyPrereqs>"""))
    _write(assets / "DLC/Expansion2/Data/Mode.xml", _xml(
        '<Technologies><Row TechnologyType="TECH_HERO_MODE"/></Technologies>'))
    _write(assets / "DLC/VikingsScenario/VikingsScenario.modinfo", """<Mod id="VS">
      <InGameActions><UpdateDatabase id="S"><File>Data/S.xml</File></UpdateDatabase></InGameActions></Mod>""")
    _write(assets / "DLC/VikingsScenario/Data/S.xml", _xml(
        '<Technologies><Row TechnologyType="TECH_SCENARIO"/></Technologies>'))
    return assets


def test_each_ruleset_gets_its_own_tree(tmp_path):
    assets = _install(tmp_path)
    vanilla = ruleset.load(assets, "Vanilla")
    storm = ruleset.load(assets, "Gathering Storm")
    assert _prereqs(vanilla, "TECH_CARTOGRAPHY") == ["TECH_SHIPBUILDING"]
    assert _prereqs(storm, "TECH_CARTOGRAPHY") == ["TECH_BUTTRESS"]


def test_scenarios_and_game_modes_are_not_part_of_a_ruleset(tmp_path):
    storm = ruleset.load(_install(tmp_path), "Gathering Storm")
    techs = {r["TechnologyType"] for r in storm.rows("Technologies")}
    assert "TECH_SCENARIO" not in techs
    assert "TECH_HERO_MODE" not in techs
    assert "TECH_BUTTRESS" in techs


def test_a_lower_load_order_runs_first(tmp_path):
    order = ruleset.load_order(_install(tmp_path), "Gathering Storm")
    names = [p.name for p in order]
    assert names.index("Remove.xml") < names.index("Techs.xml")


# ------------------------------------------------------------------- building the tree


def test_the_tree_carries_prerequisites_unlocks_and_whose_uniques_they_are():
    db = ruleset.Database()
    ruleset.apply_xml(db, _xml("""
        <Technologies>
          <Row TechnologyType="TECH_BRONZE" Name="LOC_BRONZE" Cost="50" EraType="ERA_ANCIENT"/>
          <Row TechnologyType="TECH_IRON" Name="LOC_IRON" Cost="80" EraType="ERA_ANCIENT"/>
          <Row TechnologyType="TECH_FUTURE" Name="LOC_FUTURE" Cost="9" Repeatable="true"/>
        </Technologies>
        <TechnologyPrereqs><Row Technology="TECH_IRON" PrereqTech="TECH_BRONZE"/></TechnologyPrereqs>
        <Civics><Row CivicType="CIVIC_GAMES" Name="LOC_GAMES" Cost="110" EraType="ERA_CLASSICAL"/></Civics>
        <Units>
          <Row UnitType="UNIT_SWORDSMAN" Name="LOC_SWORDSMAN" PrereqTech="TECH_IRON"/>
          <Row UnitType="UNIT_LEGION" Name="LOC_LEGION" TraitType="TRAIT_ROME_LEGION"/>
          <Row UnitType="UNIT_RIDER" Name="LOC_RIDER" PrereqTech="TECH_IRON" TraitType="TRAIT_LEADER_RIDER"/>
          <Row UnitType="UNIT_CS" Name="LOC_CS" PrereqTech="TECH_IRON" TraitType="MINOR_TRAIT"/>
        </Units>
        <UnitReplaces><Row CivUniqueUnitType="UNIT_LEGION" ReplacesUnitType="UNIT_SWORDSMAN"/></UnitReplaces>
        <Buildings>
          <Row BuildingType="BUILDING_COLOSSEUM" Name="LOC_COLOSSEUM" PrereqCivic="CIVIC_GAMES" IsWonder="true"/>
        </Buildings>
        <Civilizations>
          <Row CivilizationType="CIV_ROME" Name="LOC_ROME" StartingCivilizationLevelType="CIVILIZATION_LEVEL_FULL_CIV"/>
          <Row CivilizationType="CIV_AMERICA" Name="LOC_AMERICA" StartingCivilizationLevelType="CIVILIZATION_LEVEL_FULL_CIV"/>
        </Civilizations>
        <CivilizationTraits><Row CivilizationType="CIV_ROME" TraitType="TRAIT_ROME_LEGION"/></CivilizationTraits>
        <CivilizationLeaders><Row CivilizationType="CIV_AMERICA" LeaderType="LEADER_TEDDY"/></CivilizationLeaders>
        <LeaderTraits><Row LeaderType="LEADER_TEDDY" TraitType="TRAIT_LEADER_RIDER"/></LeaderTraits>
    """))
    names = {
        "LOC_BRONZE": "Bronze Working", "LOC_IRON": "Iron Working", "LOC_FUTURE": "Future Tech",
        "LOC_GAMES": "Games and Recreation", "LOC_SWORDSMAN": "Swordsman", "LOC_LEGION": "Legion",
        "LOC_RIDER": "Rough Rider", "LOC_CS": "City-State Unit", "LOC_COLOSSEUM": "Colosseum",
        "LOC_ROME": "Rome", "LOC_AMERICA": "America",
    }
    tree = extract_gamedata._tree(db, names)

    assert tree["technologies"]["Iron Working"] == {"era": "Ancient", "cost": 80, "needs": ["Bronze Working"]}
    assert "Future Tech" not in tree["technologies"]
    unlocks = {u["name"]: u for u in tree["unlocks"]}
    # A unique with no prerequisite of its own inherits the one it replaces.
    assert unlocks["Legion"] == {"name": "Legion", "kind": "unit", "by": "Iron Working",
                                 "tree": "technology", "civ": "Rome"}
    assert unlocks["Rough Rider"]["civ"] == "America"        # via the leader's trait
    assert unlocks["Colosseum"]["kind"] == "wonder"
    assert unlocks["Colosseum"]["tree"] == "civic"
    assert "City-State Unit" not in unlocks                  # not a major civ's
