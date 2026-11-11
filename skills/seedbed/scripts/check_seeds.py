#!/usr/bin/env python3
"""Check that the seed catalogue, the seed code, the demo personas, the client-side stores and the
data map agree. Standard library only (Python 3.11+).

    python3 check_seeds.py            # static checks
    python3 check_seeds.py --run      # and the seed tests named in the config
    python3 check_seeds.py --changed  # and warn when a schema changed without its seed
    python3 check_seeds.py --init     # write a starter seedbed.toml (the generic SaaS example)

The scenario config is `seedbed.toml` at the project root, or the path in `[seedbed] config` of
shipkit.toml. references/seedbed.example.toml is the generic SaaS example with every key
explained. Exit status 1 when a check reports an error; warnings do not fail.
SHIPKIT_ROOT points the script at another tree.

Checks
  catalogue  a module the catalogue names is seeded by nothing; the seed fills a module the catalogue
             does not name; a scenario has no implementation, or an implementation no scenario; a
             scenario needs a module that does not exist
  personas   a persona is declared twice, has a login that does not match `id_pattern`, or a
             required persona is missing
  retired    a path listed under [retired] exists again
  map        a client-side store table (Dexie `.stores({...})`, or the tables listed in the config)
             is not named in the data map
  roles      a role document has no data-access section
  tests      (--run) a seed test command fails
  changed    (--changed, warning) a file matching [changed] shapes changed and no seed file or the
             data map did
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    """SHIPKIT_ROOT, else the nearest folder up from here holding shipkit.toml, else the git root, else here."""
    if os.environ.get("SHIPKIT_ROOT"):
        return Path(os.environ["SHIPKIT_ROOT"]).resolve()
    here = Path.cwd().resolve()
    for marker in ("shipkit.toml", "seedbed.toml", ".git"):
        for folder in (here, *here.parents):
            if (folder / marker).exists():
                return folder
    return here


ROOT = project_root()


class Report:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def error(self, check: str, message: str) -> None:
        self.errors.append((check, message))

    def warn(self, check: str, message: str) -> None:
        self.warnings.append((check, message))


def config_path() -> Path:
    shipkit = ROOT / "shipkit.toml"
    if shipkit.is_file():
        configured = tomllib.loads(shipkit.read_text(encoding="utf-8")).get("seedbed", {}).get("config")
        if configured:
            return ROOT / configured
    return ROOT / "seedbed.toml"


def load_config() -> dict | None:
    path = config_path()
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def read(path: str) -> str | None:
    file = ROOT / path
    return file.read_text(encoding="utf-8") if file.is_file() else None


def block(text: str, opener: str) -> str:
    """The text between the brace or bracket that ends `opener` and its match."""
    start = text.find(opener)
    if start < 0:
        return ""
    index = start + len(opener) - 1
    pairs = {"{": "}", "[": "]", "(": ")"}
    close = pairs[text[index]]
    depth = 0
    for position in range(index, len(text)):
        if text[position] == text[index]:
            depth += 1
        elif text[position] == close:
            depth -= 1
            if depth == 0:
                return text[index + 1 : position]
    return ""


def keys(body: str) -> set[str]:
    """Property names at the start of a line: `name: ...` or `name!: ...`."""
    return set(re.findall(r"(?m)^\s*([a-z_][a-z0-9_]*)\s*[!?]?:", body))


def dexie_tables(text: str) -> set[str]:
    """Every table named in any `.stores({ ... })` of a Dexie class."""
    tables: set[str] = set()
    for match in re.finditer(r"\.stores\(\{", text):
        tables |= keys(block(text[match.start() :], ".stores({"))
    return tables


def found_in(files: list[str], pattern: str) -> tuple[set[str], list[str]]:
    """Every first group of `pattern` across the files, and the files that are missing."""
    regex = re.compile(pattern, re.M)
    hits: set[str] = set()
    missing = []
    for path in files:
        text = read(path)
        if text is None:
            missing.append(path)
            continue
        hits |= {m.group(1) for m in regex.finditer(text)}
    return hits, missing


def check_catalogue(cfg: dict, report: Report) -> None:
    """The catalogue names modules and scenarios. Each must be something the seed makes, and back."""
    catalogue = cfg.get("catalogue", {})
    seed = cfg.get("seed", {})
    modules = list(catalogue.get("modules", []))
    scenarios: dict[str, str] = dict(catalogue.get("scenarios", {}))
    if not modules and not scenarios:
        return
    if modules:
        used, missing = found_in(seed.get("files", []), seed.get("module_marker", r'wants\("([a-z_]+)"\)'))
        for path in missing:
            report.error("catalogue", f"{path} is missing (listed under [seed] files)")
        if not missing:
            for module in modules:
                if module not in used:
                    report.error("catalogue", f"module `{module}` is in the catalogue and nothing seeds it ({', '.join(seed.get('files', []))})")
            for module in sorted(used - set(modules)):
                report.error("catalogue", f"the seed fills `{module}`, which is not a module of the catalogue")
    if scenarios:
        staged, missing = found_in(seed.get("scenario_files", []), seed.get("scenario_marker", r"^def scenario_([a-z_]+)\("))
        for path in missing:
            report.error("catalogue", f"{path} is missing (listed under [seed] scenario_files)")
        if not missing:
            for scenario in scenarios:
                if scenario not in staged:
                    report.error("catalogue", f"scenario `{scenario}` is in the catalogue and has no implementation")
            for scenario in sorted(staged - set(scenarios)):
                report.error("catalogue", f"the seed stages `{scenario}`, which is not a scenario of the catalogue")
        for scenario, needs in scenarios.items():
            if needs and needs not in modules:
                report.error("catalogue", f"scenario `{scenario}` needs module `{needs}`, which is not in the catalogue")


def check_personas(cfg: dict, report: Report) -> None:
    personas = cfg.get("personas", {})
    if not personas:
        return
    declared: list[tuple[str, str]] = [(p["slug"], p.get("login", "")) for p in personas.get("list", [])]
    if personas.get("file"):
        text = read(personas["file"])
        if text is None:
            report.error("personas", f"{personas['file']} is missing")
            return
        pattern = re.compile(personas.get("pattern", r'Persona\(\s*"([a-z-]+)"\s*,\s*"([^"]+)"'))
        declared += [(m.group(1), m.group(2) if m.lastindex and m.lastindex > 1 else "") for m in pattern.finditer(text)]
    slugs = [slug for slug, _ in declared]
    for slug in sorted({s for s in slugs if slugs.count(s) > 1}):
        report.error("personas", f"persona `{slug}` is declared twice")
    id_pattern = personas.get("id_pattern")
    if id_pattern:
        for slug, login in declared:
            if not re.fullmatch(id_pattern, login):
                report.error("personas", f"persona `{slug}` has the login {login!r}, which does not match {id_pattern}")
    for slug in personas.get("required", []):
        if slug not in slugs:
            report.error("personas", f"the demo offers `{slug}`, which is not a declared persona")


def check_retired(cfg: dict, report: Report) -> None:
    for item in cfg.get("retired", {}).get("paths", []):
        path, why = (item["path"], item.get("why", "")) if isinstance(item, dict) else (item, "")
        if (ROOT / path).exists():
            report.error("retired", f"{path} exists again{': ' + why if why else ''}")


def check_map(cfg: dict, report: Report) -> None:
    data_map = cfg.get("map", {})
    if not data_map.get("file"):
        return
    text = read(data_map["file"])
    if text is None:
        report.error("map", f"{data_map['file']} is missing")
        return
    named = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", text))
    internal = set(data_map.get("internal", ["meta"]))
    for store in data_map.get("stores", []):
        tables = set(store.get("tables", []))
        if store.get("path"):
            source = read(store["path"])
            if source is None:
                continue
            tables |= dexie_tables(source)
        label = store.get("label", "Store table")
        for table in sorted(tables - internal - named):
            report.error("map", f"{label} `{table}` ({store.get('path', 'config')}) is not named in {data_map['file']}")


def check_roles(cfg: dict, report: Report) -> None:
    roles = cfg.get("roles", {})
    if not roles.get("dir"):
        return
    folder = ROOT / roles["dir"]
    section = roles.get("section", "## Data and API Access")
    if not folder.is_dir():
        report.error("roles", f"{roles['dir']}/ is missing")
        return
    skip = set(roles.get("skip", ["README.md"])) | {Path(cfg.get("map", {}).get("file", "")).name}
    for page in sorted(folder.glob("*.md")):
        if page.name in skip:
            continue
        if section not in page.read_text(encoding="utf-8"):
            report.error("roles", f"{roles['dir']}/{page.name} has no \"{section.lstrip('#').strip()}\" section")


def changed_files() -> list[str]:
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line[3:].split(" -> ")[-1].strip('"') for line in output.splitlines() if len(line) > 3]


def check_changed(cfg: dict, report: Report) -> None:
    shapes = cfg.get("changed", {}).get("shapes", [])
    if not shapes:
        return
    files = changed_files()
    touched = [f for f in files if any(re.fullmatch(p, f) for p in shapes)]
    if not touched:
        return
    seed = cfg.get("seed", {})
    seeds = set(seed.get("files", [])) | set(seed.get("scenario_files", []))
    if seeds and not any(f in seeds for f in files):
        report.warn("changed", f"{', '.join(touched)} changed and the seed did not ({', '.join(sorted(seeds))}). Seed the new shape, or say why none is needed.")
    data_map = cfg.get("map", {}).get("file")
    if data_map and data_map not in files:
        report.warn("changed", f"{', '.join(touched)} changed and {data_map} did not. Check the entity's entry.")


def run_tests(cfg: dict, report: Report) -> None:
    for test in cfg.get("tests", []):
        folder = ROOT / test.get("cwd", ".")
        needs = test.get("needs")
        if needs and not (folder / needs).exists():
            report.warn("tests", f"{test.get('cwd', '.')}: {needs} is not there (dependencies not installed); `{test['command']}` did not run")
            continue
        try:
            result = subprocess.run(["sh", "-c", test["command"]], cwd=folder, capture_output=True, text=True, timeout=test.get("timeout", 900))
        except (OSError, subprocess.TimeoutExpired) as problem:
            report.error("tests", f"could not run `{test['command']}`: {problem}")
            continue
        if result.returncode != 0:
            tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-25:])
            report.error("tests", f"`{test['command']}` failed\n{tail}")


def run_checks(report: Report) -> None:
    cfg = load_config()
    if cfg is None:
        report.error("config", f"no scenario config at {config_path()}; start one with check_seeds.py --init")
        return
    check_catalogue(cfg, report)
    check_personas(cfg, report)
    check_retired(cfg, report)
    check_map(cfg, report)
    check_roles(cfg, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="also run the seed tests named under [[tests]]")
    parser.add_argument("--changed", action="store_true", help="also warn when a schema changed and no seed did")
    parser.add_argument("--init", action="store_true", help="write a starter seedbed.toml (the generic SaaS example) if none exists")
    args = parser.parse_args(argv)

    if args.init:
        target = config_path()
        if target.exists():
            print(f"{target} exists; nothing written")
            return 0
        shutil.copy(SKILL / "references" / "seedbed.example.toml", target)
        print(f"wrote {target}; edit it to name your modules, seed files and personas")
        return 0

    if load_config() is None:
        print(f"seedbed: no scenario config yet ({os.path.relpath(config_path(), ROOT)}); nothing to check. Start one with check_seeds.py --init")
        return 0
    report = Report()
    run_checks(report)
    cfg = load_config() or {}
    if args.changed:
        check_changed(cfg, report)
    if args.run:
        run_tests(cfg, report)
    for check, message in report.errors:
        print(f"ERROR [{check}] {message}")
    for check, message in report.warnings:
        print(f"warning [{check}] {message}")
    print(f"{len(report.errors)} errors, {len(report.warnings)} warnings")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
