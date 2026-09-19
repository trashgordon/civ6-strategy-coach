"""The tech and civic trees: in the prompt, and as a check on the plan's paths.

The name whitelist can say "Construction" is a real tech; it can't say that
"**Mathematics → Construction** for Ancient Walls/Colosseum" is wrong twice over (walls
come from Masonry, the Colosseum from a civic). The tree can, because it knows what
each tech and civic needs and what it unlocks. Three checks, all in the Tech Path and
Civic Path sections, all deliberately narrow so a warning means something:

1. A path lists something out of order: Education before Writing.
2. A path lists the other tree's item: Civil Service (a civic) in the tech path.
3. A path credits an unlock to the wrong tech or civic: "Civil Service for Classical
   Republic" — Classical Republic comes from Political Philosophy.

Like the rest of the grounding, all of this is a silent no-op without `data/facts/`.
"""

import json
import re
import unicodedata
from functools import lru_cache

from .ruleset import DEFAULT_RULESET, RULESETS

TREES = ("technologies", "civics")
_TREE_LABEL = {"technologies": "tech", "civics": "civic"}
_SECTION_TREE = {"tech path": "technologies", "civic path": "civics"}


@lru_cache(maxsize=1)
def _load() -> dict:
    from . import facts  # at call time: facts imports this module, and tests repoint it

    path = facts.facts_dir() / "tree.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def reload() -> None:
    _load.cache_clear()
    _index.cache_clear()


def for_ruleset(ruleset: str | None) -> dict:
    """The tree for a ruleset label, falling back to Gathering Storm. {} when absent."""
    data = _load()
    if not data:
        return {}
    label = ruleset if ruleset in RULESETS else DEFAULT_RULESET
    return data.get(label) or {}


# ------------------------------------------------------------------------------ prompt


def prompt_section(ruleset: str | None) -> str:
    tree = for_ruleset(ruleset)
    if not tree:
        return ""
    label = ruleset if ruleset in RULESETS else DEFAULT_RULESET
    unlocks: dict[str, list[str]] = {}
    for item in tree.get("unlocks", []):
        shown = f"{item['name']} [{item['civ']} only]" if item.get("civ") else item["name"]
        unlocks.setdefault(item["by"], []).append(shown)

    lines = [
        f"The tech and civic trees for {label}. Each line is: name (era) ← what it needs "
        "→ what it unlocks. Order a path so every item comes after what it needs; put "
        "only technologies in the Tech Path and only civics in the Civic Path; and when "
        "you say a tech or civic is for something, it must be the one that unlocks it "
        "here. Items marked [X only] are that civ's uniques.",
    ]
    for bucket, heading in (("technologies", "Technologies"), ("civics", "Civics")):
        lines.append(f"{heading}:")
        entries = sorted(tree.get(bucket, {}).items(), key=lambda kv: (kv[1].get("cost", 0), kv[0]))
        for name, info in entries:
            line = f"- {name} ({info.get('era', '')})"
            if info.get("needs"):
                line += " ← " + ", ".join(info["needs"])
            if unlocks.get(name):
                line += " → " + ", ".join(unlocks[name])
            lines.append(line)

    wonders = tree.get("wonders", {})
    if wonders:
        lines.append(
            "Wonders — what each actually does and where it can be built, with its "
            "production cost and what unlocks it. Describe a wonder only as written here, "
            "and respect its placement rule when you say where to build it:"
        )
        for name, info in sorted(wonders.items(), key=lambda kv: (kv[1].get("cost", 0), kv[0])):
            lines.append(f"- {name} ({info.get('by', '')}, {info.get('cost', 0)} production): {info['effect']}")
    return "\n".join(lines)


# -------------------------------------------------------------------------- validation


def _plain(text: str) -> str:
    """Strip accents and markdown emphasis, keeping case and (near enough) length."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("**", "").replace("`", "")
    return re.sub(r"\s&\s", " and ", text)  # "Drama & Poetry"


def _name_pattern(names: dict[str, str]) -> re.Pattern | None:
    if not names:
        return None
    alternatives = sorted(names, key=len, reverse=True)
    return re.compile(
        r"(?<![\w-])(" + "|".join(re.escape(a) for a in alternatives) + r")(?![\w-])",
        flags=re.IGNORECASE,
    )


def _variants(name: str) -> set[str]:
    """How a name shows up in prose: "Legions", "Crossbowmen", "Hansa's"."""
    plain = _plain(name)
    forms = {plain, plain + "s", plain + "es", plain + "'s"}
    if plain.endswith("man"):
        forms.add(plain[:-3] + "men")
    return {f.lower() for f in forms}


@lru_cache(maxsize=8)
def _index(ruleset: str) -> dict:
    tree = for_ruleset(ruleset)
    tree_names: dict[str, tuple[str, str]] = {}   # variant -> (canonical, bucket)
    for bucket in TREES:
        for name in tree.get(bucket, {}):
            for variant in _variants(name):
                tree_names.setdefault(variant, (name, bucket))
    unlock_names: dict[str, dict] = {}
    for item in tree.get("unlocks", []):
        for variant in _variants(item["name"]):
            # A name that's also a tech or civic is ambiguous; leave it to the tree.
            if variant not in tree_names:
                unlock_names.setdefault(variant, item)

    needs: dict[str, set[str]] = {}

    def ancestors(name: str, bucket: str) -> set[str]:
        key = f"{bucket}:{name}"
        if key not in needs:
            needs[key] = set()
            direct = tree.get(bucket, {}).get(name, {}).get("needs", [])
            found = set(direct)
            for parent in direct:
                found |= ancestors(parent, bucket)
            needs[key] = found
        return needs[key]

    all_ancestors = {
        (name, bucket): ancestors(name, bucket)
        for bucket in TREES for name in tree.get(bucket, {})
    }
    return {
        "tree_names": tree_names,
        "tree_pattern": _name_pattern(tree_names),
        "unlock_names": unlock_names,
        "unlock_pattern": _name_pattern(unlock_names),
        "ancestors": all_ancestors,
    }


def _found(pattern: re.Pattern | None, lookup: dict, text: str) -> list[tuple[int, int, object]]:
    """(start, end, entry) for each capitalised name in `text`."""
    if pattern is None:
        return []
    hits = []
    for match in pattern.finditer(text):
        # Game names are capitalised; "under construction" is not the tech.
        if not match.group(0)[0].isupper():
            continue
        entry = lookup.get(match.group(0).lower())
        if entry is not None:
            hits.append((match.start(), match.end(), entry))
    return hits


def _sections(plan: str) -> dict[str, str]:
    """{"tech path": body, "civic path": body} for whichever the plan has."""
    out = {}
    for match in re.finditer(r"^##\s+(.+?)\s*$", plan, flags=re.MULTILINE):
        heading = match.group(1).strip().lower()
        if heading in _SECTION_TREE:
            rest = plan[match.end():]
            end = re.search(r"^##\s+", rest, flags=re.MULTILINE)
            out[heading] = rest[: end.start()] if end else rest
    return out


_ARROW = re.compile(r"\s*(?:→|->|➜|»)\s*")
_SENTENCE = re.compile(r"(?<=[.!?;])\s+")
_CLAUSE = re.compile(r",?\s+then\s+|;\s*")
_LIST_GLUE = re.compile(r"^\s*(?:/|,|&|and|or)\s*$", flags=re.IGNORECASE)
_CONNECTIVE = re.compile(r"\b(?:for|unlocks?|unlocking|to unlock|gets? you|gives? you)\b", re.I)
_SPAN_END = re.compile(r"[.;:()—–]|,\s|\bthen\b")
_SPAN_WORDS = 8
_KEEPS_PAYING = {"district", "building", "improvement"}
_WAITING = re.compile(r"\b(?:hold|holding|wait|waiting|save|saving)\s*$", re.IGNORECASE)


# "for Seowon buffs", "for farm-adjacent Seowon prep": about a bonus, not the unlock.
_NOT_AN_UNLOCK = re.compile(
    r"^\W*(?:buffs?|prep|synergy|synergies|adjacency|adjacencies|bonus(?:es)?|boosts?"
    r"|stacking|yields?|output|eurekas?|inspirations?)\b",
    flags=re.IGNORECASE,
)
_LEAD_WORDS = 2  # "for the Agoge", "for early Legions" — not "for defensive walls and X"


def _claimed_unlocks(span: str, index: dict) -> list[dict]:
    """The unlockables a "for …"/"unlocks …" span is actually about.

    Only names that open the span (after a word or two), plus any listed straight after
    them — "for Ancient Walls/Colosseum" — and only when what follows isn't a bonus.
    """
    hits = _found(index["unlock_pattern"], index["unlock_names"], span)
    if not hits or len(span[: hits[0][0]].split()) > _LEAD_WORDS:
        return []
    group = _group(span, hits)
    if _NOT_AN_UNLOCK.match(span[group[-1][1]:]):
        return []
    return [item for *_, item in group]


def _group(text: str, hits: list, from_end: bool = False) -> list:
    """The run of names at one end of a chain segment: "Steel/Industrialization"."""
    if not hits:
        return []
    ordered = hits[::-1] if from_end else hits
    group = [ordered[0]]
    for hit in ordered[1:]:
        a, b = (hit, group[-1]) if from_end else (group[-1], hit)
        if not _LIST_GLUE.match(text[a[1]:b[0]]):
            break
        group.append(hit)
    return group[::-1] if from_end else group


def _chains(line: str, index: dict) -> list[list[list[tuple[str, str]]]]:
    """Each arrow chain in a line, as ranks of (name, bucket)."""
    chains = []
    for sentence in _SENTENCE.split(line):
        segments = _ARROW.split(sentence)
        if len(segments) < 2:
            continue
        ranks = []
        for i, segment in enumerate(segments):
            hits = _found(index["tree_pattern"], index["tree_names"], segment)
            group = _group(segment, hits, from_end=(i == 0))
            if group:
                ranks.append([entry for *_, entry in group])
        if len(ranks) >= 2:
            chains.append(ranks)
    return chains


def path_issues(plan: str, ruleset: str | None) -> list[str]:
    """Plain-language problems with the plan's paths. Empty when the tree is absent."""
    if not plan or not for_ruleset(ruleset):
        return []
    index = _index(ruleset if ruleset in RULESETS else DEFAULT_RULESET)
    issues: list[str] = []

    def report(message: str) -> None:
        if message not in issues:
            issues.append(message)

    for heading, body in _sections(_plain(plan)).items():
        bucket = _SECTION_TREE[heading]
        other = "civics" if bucket == "technologies" else "technologies"
        for line in body.splitlines():
            for ranks in _chains(line, index):
                flat = [(name, b) for rank in ranks for name, b in rank]
                for name, b in flat:
                    if b == other:
                        report(
                            f"{name} is a {_TREE_LABEL[other]}, but it's listed in the "
                            f"{heading.split()[0]} path."
                        )
                for i, earlier in enumerate(ranks):
                    for later in ranks[i + 1:]:
                        for name, b in earlier:
                            for then, b2 in later:
                                if b == b2 and then in index["ancestors"].get((name, b), ()):
                                    report(f"{name} comes before {then}, but {name} needs {then} first.")

            for clause in _CLAUSE.split(line):
                for connective in _CONNECTIVE.finditer(clause):
                    before = clause[: connective.start()]
                    # The claim belongs to the chain step it's written in: in
                    # "… → Urbanization → into Modern civics for X", nothing in the
                    # step "into Modern civics" is said to unlock X.
                    step = _ARROW.split(before)[-1]
                    if not _found(index["tree_pattern"], index["tree_names"], step):
                        continue
                    # "hold for Merchant Republic" is waiting for it, not unlocking it.
                    if _WAITING.search(before):
                        continue
                    sources = {
                        entry[0]
                        for *_, entry in _found(
                            index["tree_pattern"], index["tree_names"], clause[: connective.start()]
                        )
                    }
                    if not sources:
                        continue
                    span = clause[connective.end():]
                    stop = _SPAN_END.search(span)
                    span = span[: stop.start()] if stop else span
                    span = " ".join(span.split()[:_SPAN_WORDS])
                    for item in _claimed_unlocks(span, index):
                        bucket_of_unlock = "technologies" if item["tree"] == "technology" else "civics"
                        # "Economics for Commercial Hub snowball" isn't a claim that
                        # Economics unlocks it: Currency comes first, and hubs keep
                        # paying off. A government or card is a one-off unlock, though,
                        # so "Civil Service for Classical Republic" is still wrong.
                        already_have = item["kind"] in _KEEPS_PAYING and any(
                            item["by"] in index["ancestors"].get((source, bucket_of_unlock), ())
                            for source in sources
                        )
                        if item["by"] not in sources and not already_have:
                            credited = " or ".join(sorted(sources))
                            report(
                                f"{item['name']} is unlocked by {item['by']} "
                                f"({'tech' if item['tree'] == 'technology' else 'civic'}), "
                                f"not {credited}."
                            )
    return issues
