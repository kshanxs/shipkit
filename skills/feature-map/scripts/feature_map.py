#!/usr/bin/env python3
"""
The feature map: check it, count it, and hold the pricing page to it.

    python3 feature_map.py            # check
    python3 feature_map.py --write    # check, and rewrite the counts table and the generated catalog
    python3 feature_map.py --list     # every feature: tier, status, name
    python3 feature_map.py --list --status Planned --plan Pro

Configured by the [feature_map] table of shipkit.toml (all optional):

    [feature_map]
    catalog = "docs/feature_catalog.md"      # the map
    tiers = ["Free", "Pro", "Enterprise"]   # plan names, cheapest first (the generic SaaS default)
    specs_dir = "docs/features"              # every spec here must be linked from the map
    comparison = "apps/web/src/pricing.ts"   # optional: a file with `export const COMPARISON = [...]`
    catalog_out = "apps/web/src/catalog.ts"  # optional: generated public catalog (.ts or .json)

The map is the part of the catalog between `<!-- tree:start -->` and
`<!-- tree:end -->`. Inside it:

    ## Pro: collaborate and automate        a tier, or another group of features
    ### Billing                             an area
    - **Online payments** · Partly · [Billing](features/billing.md)   a feature
      - Card checkout and invoices · Built                            a sub-feature
      - Refunds and reconciliation · Planned

A line is `name · status`, then anything else (links, a date, a note) after a
further ` · `. A feature's name is bold; a sub-feature's is not. A group whose
heading starts with a tier name is that tier; any other group (such as
"Plan to be decided") holds features without one.

Checks:
  format     a line in the map is not a heading, a feature or a sub-feature
  status     a status is not one of the tracker's words
  rollup     a feature's status does not follow from its sub-features
  names      two features share a name
  specs      a specification under specs_dir is not linked from the map
  counts     the counts table is not what the map adds up to (--write fixes it)
  site       the comparison table disagrees with the map: a row the map does not have,
             a row in the wrong tier, a feature that is not built shown as included,
             or a built one shown as coming soon
  catalog    the generated catalog is not what the map's tiers hold (--write fixes it)

Exit status is 1 when anything is reported. SHIPKIT_ROOT points the script at another tree.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def project_root() -> Path:
    """SHIPKIT_ROOT, else the nearest folder up from here holding shipkit.toml, else the git root, else here."""
    if os.environ.get("SHIPKIT_ROOT"):
        return Path(os.environ["SHIPKIT_ROOT"]).resolve()
    here = Path.cwd().resolve()
    for marker in ("shipkit.toml", ".git"):
        for folder in (here, *here.parents):
            if (folder / marker).exists():
                return folder
    return here


ROOT = project_root()


def _config() -> dict:
    path = ROOT / "shipkit.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


_CFG = _config()
_DOCS = _CFG.get("docsync", {}).get("docs_dir", "docs")
_FM = _CFG.get("feature_map", {})
CATALOG = Path(_FM.get("catalog", f"{_DOCS}/feature_catalog.md"))
SPECS = Path(_FM.get("specs_dir", _CFG.get("docsync", {}).get("features_dir", f"{_DOCS}/features")))
PRICING_TS = Path(_FM["comparison"]) if _FM.get("comparison") else None
CATALOG_TS = Path(_FM["catalog_out"]) if _FM.get("catalog_out") else None

PLANS = tuple(_FM.get("tiers", ("Free", "Pro", "Enterprise")))
# The tracker's status words, sorted by what is left to do.
DONE = ("Built",)
NEEDS_WORK = ("Partly", "Backend only", "Frontend only", "In progress")
NOT_STARTED = ("Next", "Planned", "Coming soon")
STATUSES = DONE + NEEDS_WORK + NOT_STARTED

TREE = re.compile(r"<!-- tree:start -->\n(.*?)<!-- tree:end -->", re.S)
COUNTS = re.compile(r"(<!-- counts:start -->\n).*?(<!-- counts:end -->)", re.S)
LINE = re.compile(r"^(?P<indent> *)- (?P<name>.+?) · (?P<status>[^·]+?)(?: · (?P<rest>.*))?$")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


@dataclass
class Node:
    name: str
    status: str
    line: int
    group: str
    area: str
    rest: str = ""
    children: list["Node"] = field(default_factory=list)

    @property
    def plan(self) -> str | None:
        return next((plan for plan in PLANS if self.group.startswith(plan)), None)


def parse(text: str) -> tuple[list[Node], list[str]]:
    """The features of the tree, each with its sub-features, and what is wrong with its lines."""
    match = TREE.search(text)
    if not match:
        return [], [f"{CATALOG}: no `<!-- tree:start -->` … `<!-- tree:end -->` block"]
    first_line = text[: match.start(1)].count("\n") + 1
    features: list[Node] = []
    problems: list[str] = []
    group = area = ""
    for offset, raw in enumerate(match.group(1).splitlines()):
        number = first_line + offset
        if not raw.strip():
            continue
        if raw.startswith("## "):
            group, area = raw[3:].strip(), ""
            continue
        if raw.startswith("### "):
            area = raw[4:].strip()
            continue
        found = LINE.match(raw)
        if not found or not group:
            problems.append(f"{CATALOG}:{number}: format: not a heading, a feature or a sub-feature: {raw.strip()[:70]}")
            continue
        name, status, depth = found["name"].strip(), found["status"].strip(), len(found["indent"])
        bold = name.startswith("**") and name.endswith("**")
        if status not in STATUSES:
            problems.append(f"{CATALOG}:{number}: status: `{status}` is not one of {', '.join(STATUSES)}")
        node = Node(name.strip("*"), status, number, group, area, found["rest"] or "")
        if depth == 0 and bold:
            features.append(node)
        elif depth == 2 and not bold and features and features[-1].group == group:
            features[-1].children.append(node)
        else:
            problems.append(f"{CATALOG}:{number}: format: a feature is `- **Name** · Status`; a sub-feature is indented two spaces and not bold")
    return features, problems


def rollup(children: list[Node]) -> set[str]:
    """The statuses a feature may carry, given its sub-features."""
    statuses = {child.status for child in children}
    if statuses <= set(DONE):
        return set(DONE)
    if statuses <= set(NOT_STARTED):
        return set(NOT_STARTED)
    return set(NEEDS_WORK)


def check_tree(features: list[Node]) -> list[str]:
    problems = []
    seen: dict[str, int] = {}
    for feature in features:
        key = feature.name.lower()
        if key in seen:
            problems.append(f"{CATALOG}:{feature.line}: names: `{feature.name}` is also on line {seen[key]}")
        seen[key] = feature.line
        if feature.children and feature.status in STATUSES and feature.status not in rollup(feature.children):
            allowed = " or ".join(sorted(rollup(feature.children)))
            problems.append(f"{CATALOG}:{feature.line}: rollup: `{feature.name}` is {feature.status}, but its sub-features make it {allowed}")
    return problems


def check_specs(text: str) -> list[str]:
    """Every specification is reachable from the tree, so no feature is left without a plan or a place."""
    match = TREE.search(text)
    linked = {(CATALOG.parent / target).as_posix() for target in LINK.findall(match.group(1))} if match else set()
    specs = sorted((ROOT / SPECS).glob("*.md"))
    return [
        f"{CATALOG}: specs: {path.relative_to(ROOT).as_posix()} is not linked from the tree"
        for path in specs
        if path.name != "README.md" and os.path.normpath(path.relative_to(ROOT).as_posix()) not in {os.path.normpath(x) for x in linked}
    ]


def bucket(status: str) -> str:
    return "Built" if status in DONE else "Needs work" if status in NEEDS_WORK else "Not started"


def counts_table(features: list[Node]) -> str:
    groups = list(dict.fromkeys(feature.group for feature in features))
    rows = ["| Group | Features | Built | Needs work | Not started |", "|---|---|---|---|---|"]
    totals = [0, 0, 0, 0]
    for group in groups:
        mine = [feature for feature in features if feature.group == group]
        tally = [len(mine)] + [sum(bucket(f.status) == name for f in mine) for name in ("Built", "Needs work", "Not started")]
        totals = [a + b for a, b in zip(totals, tally)]
        rows.append(f"| {group.split(':')[0]} | {' | '.join(map(str, tally))} |")
    rows.append(f"| **All** | {' | '.join(f'**{n}**' for n in totals)} |")
    return "\n".join(rows) + "\n"


def check_counts(text: str, features: list[Node]) -> list[str]:
    match = COUNTS.search(text)
    if not match:
        return [f"{CATALOG}: counts: no `<!-- counts:start -->` … `<!-- counts:end -->` block"]
    current = text[match.end(1) : match.start(2)]
    return [] if current == counts_table(features) else [f"{CATALOG}: counts: the table is out of date; run feature_map.py --write"]


def comparison_rows(source: str) -> list[tuple[int, str, list[str]]]:
    """(line, feature, [one value per tier]) for each row of COMPARISON in the comparison file."""
    start = source.find("export const COMPARISON")
    if start < 0:
        return []
    end = source.find("\n]\n", start)
    rows = []
    for found in re.finditer(r"\[\s*'((?:[^'\\]|\\.)+)'\s*,([^\]\[]+)\]", source[start:end]):
        values = [value.strip().strip("'") for value in found.group(2).split(",") if value.strip()]
        if len(values) == len(PLANS):
            rows.append((source[: start + found.start()].count("\n") + 1, found.group(1).replace("\\'", "'"), values))
    return rows


def check_site(features: list[Node]) -> list[str]:
    if PRICING_TS is None or not (ROOT / PRICING_TS).exists():
        return []
    path = ROOT / PRICING_TS
    nodes: dict[str, tuple[Node, str | None]] = {}
    for feature in features:
        nodes[feature.name.lower()] = (feature, feature.plan)
        for child in feature.children:
            nodes.setdefault(child.name.lower(), (child, feature.plan))
    problems = []
    for line, label, values in comparison_rows(path.read_text(encoding="utf-8")):
        where = f"{PRICING_TS}:{line}: site: `{label}`"
        if label.lower() not in nodes or nodes[label.lower()][1] is None:
            problems.append(f"{where} is not a feature of a plan in the tree; use the tree's name for it")
            continue
        node, plan = nodes[label.lower()]
        first = PLANS.index(plan)
        if any(value != "no" for value in values[:first]) or any(value == "no" for value in values[first:]):
            problems.append(f"{where} is in {plan} in the tree, so it is `no` before {plan} and included from it on")
        elif node.status in NOT_STARTED and any(value != "COMING_SOON" for value in values[first:]):
            problems.append(f"{where} is {node.status} in the tree, so the page may only say COMING_SOON")
        elif node.status not in NOT_STARTED and "COMING_SOON" in values:
            problems.append(f"{where} is {node.status} in the tree, so the page should not say COMING_SOON")
    return problems


# What a customer is told for each of the tracker's words.
CUSTOMER_STATUS = {"Built": "built", **{word: "under_development" for word in NEEDS_WORK}, **{word: "coming_soon" for word in NOT_STARTED}}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def ts_string(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def catalog_items(features: list[Node]) -> list[dict]:
    """The features of the tiers, as customers are shown them: no notes, links or untiered features."""
    items = []
    for feature in features:
        if feature.status not in CUSTOMER_STATUS or not feature.plan:
            continue
        fid = slug(feature.name)
        items.append({
            "id": fid,
            "title": feature.name,
            "plan": slug(feature.plan),
            "category": feature.area,
            "status": CUSTOMER_STATUS[feature.status],
            "subfeatures": [
                {"id": f"{fid}--{slug(c.name)}", "title": c.name, "status": CUSTOMER_STATUS.get(c.status, "coming_soon")}
                for c in feature.children
            ],
        })
    return items


def catalog_source(features: list[Node], suffix: str = ".ts") -> str:
    """The generated catalog for the tiers: TypeScript, or JSON when the output ends in .json."""
    items = catalog_items(features)
    if suffix == ".json":
        return json.dumps({"generated_by": "feature_map.py --write", "catalog": items}, indent=2, ensure_ascii=False) + "\n"
    plans = " | ".join(f"'{slug(p)}'" for p in PLANS)
    header = (
        "/**\n"
        " * Every feature of the tiers and the sub-features under it: what the\n"
        " * pricing page and the roadmap page show customers.\n"
        " *\n"
        f" * Generated by feature_map.py --write from {CATALOG.as_posix()}. Do not\n"
        " * edit it by hand: change the map and run the script. Notes and links in the\n"
        " * map are for the team and are left out, as is any feature outside a tier.\n"
        " */\n\n"
        "export type FeatureStatus = 'built' | 'under_development' | 'coming_soon'\n"
        f"export type CatalogPlan = {plans}\n\n"
        "export interface Subfeature {\n  id: string\n  title: string\n  status: FeatureStatus\n}\n\n"
        "export interface Feature {\n  id: string\n  title: string\n  plan: CatalogPlan\n"
        "  /** The area of the map the feature sits under, such as Billing or Search. */\n"
        "  category: string\n  status: FeatureStatus\n  subfeatures: Subfeature[]\n}\n\n"
        "export const CATALOG: Feature[] = [\n"
    )
    lines = []
    for item in items:
        subs = ", ".join(
            f"{{ id: {ts_string(sub['id'])}, title: {ts_string(sub['title'])}, status: '{sub['status']}' }}" for sub in item["subfeatures"]
        )
        lines.append(
            f"  {{ id: {ts_string(item['id'])}, title: {ts_string(item['title'])}, plan: '{item['plan']}', category: {ts_string(item['category'])}, "
            f"status: '{item['status']}', subfeatures: [{subs}] }},"
        )
    return header + "\n".join(lines) + "\n]\n"


def check_catalog(features: list[Node]) -> list[str]:
    if CATALOG_TS is None:
        return []
    path = ROOT / CATALOG_TS
    if not path.parent.exists():
        return []
    if not path.exists() or path.read_text(encoding="utf-8") != catalog_source(features, CATALOG_TS.suffix):
        return [f"{CATALOG_TS}: catalog: {CATALOG_TS} is out of date; run feature_map.py --write"]
    return []


def listing(features: list[Node], status: str | None, plan: str | None) -> str:
    lines = []
    for feature in features:
        if plan and feature.plan != plan:
            continue
        rows = [(feature, "")] + [(child, "  ") for child in feature.children]
        for node, indent in rows:
            if status is None or node.status == status:
                lines.append(f"{feature.group.split(':')[0]:<24} {node.status:<14} {indent}{node.name}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="rewrite the counts table and catalogData.ts from the tree")
    parser.add_argument("--list", action="store_true", help="print every feature and sub-feature")
    parser.add_argument("--status", choices=STATUSES, help="with --list: only this status")
    parser.add_argument("--plan", choices=PLANS, help="with --list: only this plan")
    args = parser.parse_args()

    path = ROOT / CATALOG
    if not path.exists():
        print(f"{CATALOG} is missing")
        return 1
    text = path.read_text(encoding="utf-8")
    features, problems = parse(text)

    if args.list:
        print(listing(features, args.status, args.plan))
        return 0
    if args.write and COUNTS.search(text):
        text = COUNTS.sub(lambda m: m.group(1) + counts_table(features) + m.group(2), text)
        path.write_text(text, encoding="utf-8")
    if args.write and CATALOG_TS is not None and (ROOT / CATALOG_TS).parent.exists():
        (ROOT / CATALOG_TS).write_text(catalog_source(features, CATALOG_TS.suffix), encoding="utf-8")

    problems += check_tree(features) + check_specs(text) + check_counts(text, features) + check_site(features) + check_catalog(features)
    for problem in problems:
        print(problem)
    print(f"feature map: {len(features)} features, {sum(len(f.children) for f in features)} sub-features, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
