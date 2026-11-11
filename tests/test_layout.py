"""The repository's shape: every skill has its SKILL.md (with frontmatter that matches its folder),
a README, a router entry and commands; the root README lists every skill; nothing project-specific
from the pack's origin leaks into a public file."""

from __future__ import annotations

import re
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = sorted(p.parent for p in (REPO / "skills").glob("*/SKILL.md"))
EXPECTED = {
    "stack-backend", "stack-web", "stack-native", "wire-api", "seedbed", "fanout", "harden", "bug-sweep",
    "load-sim", "perf-watch", "triage-report", "ship-check", "docsync", "feature-map", "open-loops", "handoff", "switchboard",
    "kit-build", "kit-break", "kit-flow", "kit-feature", "autopilot", "profile",
}  # fmt: skip


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path}: no frontmatter"
    out = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip('"')
    return out


class Layout(unittest.TestCase):
    def test_the_skills_and_kits_are_there(self) -> None:
        self.assertEqual({p.name for p in SKILLS}, EXPECTED)

    def test_each_skill_has_frontmatter_a_readme_and_no_broken_reference_links(self) -> None:
        for skill in SKILLS:
            meta = frontmatter(skill / "SKILL.md")
            self.assertEqual(meta.get("name"), skill.name)
            self.assertGreater(len(meta.get("description", "")), 80, skill.name)
            self.assertLess(len(meta.get("description", "")), 1024, skill.name)
            self.assertTrue((skill / "README.md").exists(), skill.name)
            for doc in [skill / "SKILL.md", *(p for p in skill.glob("references/*.md") if ".example" not in p.name)]:
                prose = re.sub(r"```.*?```", "", doc.read_text(encoding="utf-8"), flags=re.S)
                for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", prose):
                    if target.startswith(("http", "mailto")) or "<" in target:
                        continue
                    self.assertTrue((doc.parent / target).exists(), f"{doc}: {target}")

    def test_the_router_knows_every_skill_and_its_commands_are_shipped(self) -> None:
        table = tomllib.loads((REPO / "skills/switchboard/skills.toml").read_text())
        self.assertEqual(set(table), EXPECTED)
        for name, entry in table.items():
            for short in entry["short"]:
                command = REPO / "skills/switchboard/commands" / f"{short}.md"
                self.assertIn(f"`{name}`", command.read_text(), short)

    def test_the_root_readme_lists_every_skill_and_command(self) -> None:
        readme = (REPO / "README.md").read_text()
        table = tomllib.loads((REPO / "skills/switchboard/skills.toml").read_text())
        for name, entry in table.items():
            self.assertIn(f"[{name}](skills/{name}/)", readme)
            self.assertIn(f"`/{entry['short'][0]}`", readme)
        for group in ("Build", "Break & Test", "Docs & Flow", "Kits"):
            self.assertIn(f"### {group}", readme)

    def test_scripts_are_standard_library_python(self) -> None:
        allowed_third_party = set()
        for script in REPO.glob("skills/*/scripts/*.py"):
            imports = re.findall(r"^(?:from|import) ([a-zA-Z_]+)", script.read_text(), re.M)
            local = {p.stem for p in script.parent.glob("*.py")}
            for name in imports:
                if name in local or name == "__future__":
                    continue
                self.assertTrue(__import__("importlib.util").util.find_spec(name) is not None or name in allowed_third_party, f"{script.name}: {name}")


class Public(unittest.TestCase):
    """The pack came out of one private product. Its name may appear once, in the README's roadmap line."""

    # Built from pieces so this file does not match its own search.
    PATTERN = re.compile("|".join(["zy" + "ralum", "lu" + "me", "sch" + "ool", "notion" + r"\.so"]), re.I)

    def tracked(self) -> list[Path]:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO, capture_output=True, text=True).stdout
        return [REPO / line for line in out.splitlines() if (REPO / line).is_file()]

    def test_nothing_but_the_roadmap_line_names_the_origin(self) -> None:
        hits = []
        for path in self.tracked():
            if path.suffix in (".png", ".jpg", ".lock") or path.name == "uv.lock":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if self.PATTERN.search(line):
                    hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:80]}")
        roadmap = [h for h in hits if h.startswith("README.md:") and "Roadmap" in h]
        self.assertEqual(len(roadmap), 1, hits)
        self.assertEqual([h for h in hits if h not in roadmap], [])

    def test_no_home_paths_hostnames_or_key_shapes(self) -> None:
        bad = re.compile(r"/home/[a-z]+/|/Users/[A-Za-z]+/|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY")
        for path in self.tracked():
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertIsNone(bad.search(text), f"{path.relative_to(REPO)}: {bad.search(text) and bad.search(text).group(0)}")


if __name__ == "__main__":
    unittest.main()
