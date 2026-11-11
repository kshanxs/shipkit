#!/usr/bin/env python3
"""Claude Code Stop hook: do not finish while the documentation contract is broken.

Reads the hook's JSON from stdin. When the checks report errors it prints a
`block` decision, which sends the errors back to the agent so it can fix them.
It blocks at most once per stop: if the agent is already continuing because of
this hook (`stop_hook_active`), it lets the session end, so a problem the agent
cannot fix (someone else's uncommitted change, say) never traps it.

It also names the open questions (the open-loops skill's register) that this
change set touches when the register itself did not change, once for each set
of changes, so an answer or a changed behaviour is not left out of the register.

Configured in .claude/settings.json (install.sh --hooks adds it). Never exits
non-zero: a broken hook must not break a session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LIMIT = 25  # problems shown; the rest are counted
HERE = Path(__file__).resolve().parent


def decide(payload: dict, errors: dict[str, list[str]], questions: list[str] | None = None) -> dict | None:
    """The hook's answer: a block decision, or None to let the session end."""
    if payload.get("stop_hook_active"):
        return None
    problems = [f"[{name}] {problem}" for name, found in errors.items() for problem in found]
    questions = questions or []
    if not problems and not questions:
        return None
    lines: list[str] = []
    if problems:
        shown = problems[:LIMIT]
        more = len(problems) - len(shown)
        lines += [
            "The documentation contract (the docsync skill) is not met:",
            "",
            *[f"- {problem}" for problem in shown],
            *([f"- and {more} more"] if more else []),
            "",
            "Fix these before finishing: add the changelog line, document the feature, set the status "
            "line or the plan queue entry, then run "
            f"`python3 {HERE / 'check_docs.py'} --changed`. "
            "If a problem comes from a change that is not yours, do not touch it; say so in your reply.",
        ]
    if questions:
        shown = questions[:LIMIT]
        more = len(questions) - len(shown)
        lines += [
            *([""] if lines else []),
            "This change touches open questions, and the open questions register did not change:",
            "",
            *[f"- {question}" for question in shown],
            *([f"- and {more} more"] if more else []),
            "",
            "For each, see whether the user answered it, or whether its Today line or its implications no "
            "longer match the code; update the register and run "
            "`open_loops.py --write` (the open-loops skill). "
            "If none is affected, carry on.",
        ]
    return {"decision": "block", "reason": "\n".join(lines)}


def open_question_reminders() -> list[str]:
    """The open questions this change set touches, from the open-questions skill; none if it is absent."""
    try:
        script = HERE.parents[1] / "open-loops" / "scripts"
        if not (script / "open_loops.py").exists():
            return []
        sys.path.insert(0, str(script))
        import open_loops

        return open_loops.remind_once()
    except Exception as error:  # noqa: BLE001  (the reminder is advice; it must not stop the contract's check)
        print(f"open questions reminder skipped: {error}", file=sys.stderr)
        return []


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        sys.path.insert(0, str(HERE))
        import check_docs

        errors, _, _ = check_docs.run(changed=True)
        questions = [] if payload.get("stop_hook_active") else open_question_reminders()
        answer = decide(payload, errors, questions)
        if answer:
            print(json.dumps(answer))
    except Exception as error:  # noqa: BLE001  (a hook failure must never end a session badly)
        print(f"docsync stop hook skipped: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
