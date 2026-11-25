---
name: stack-cli
description: "Conventions and test workflow for command-line tools, shell scripts, provisioners, infrastructure code and small libraries: safe re-runs, dry runs, exit codes, data on stdout and messages on stderr, quoting, temp files, atomic writes, privileges, secrets, OS and package-manager detection, and testing in a throwaway HOME with stubbed commands. Use when adding or changing a CLI, a shell or Python script, an installer, a systemd unit, a cron job, Ansible, Terraform or a library; and when the user says 'CLI', 'script', 'shell', 'bash', 'installer', 'provision', 'dotfiles', 'systemd' or 'shellcheck'."
---

# CLI tools, scripts and infrastructure

Find the entry points first: `bin/`, `scripts/`, `[project.scripts]`, the `bin` field of
`package.json`, `Makefile`, installers and units. The project's README and code win over this file.

## The rules

| Rule | What it means |
|---|---|
| Safe to run twice | A second run changes nothing and reports that. Check before changing; never append the same line again |
| Show before changing | Anything that changes a machine offers `--dry-run`, which changes nothing |
| Never destroy by default | Back up what you replace. Deleting data needs an explicit flag; refuse an empty or root path |
| Data on stdout | Results go to stdout, messages to stderr. With `--json`, stdout is one valid JSON document and nothing else |
| Honest exit codes | `0` worked, non-zero failed, `2` wrong usage. A partial failure is a failure. A pipeline fails when any part fails |
| No one's machine in the code | No hardcoded user, home, hostname, IP, repository owner or token. Detect it, or read a flag, environment variable or config |
| Detect the platform | Read `/etc/os-release` and `uname`; check `command -v`. Stop with a clear message on what is not supported |
| Least privilege | Run as the user. Ask for root only for the step that needs it, and write user files as that user |
| Secrets stay out | Not in arguments (`ps` shows them), logs, shell history or the repository. Read them from the environment or a mode-600 file |
| Writes are atomic | Write a temp file in the same folder, then rename. An interrupted run leaves the old file whole |

## Shell

```bash
#!/usr/bin/env bash
set -euo pipefail
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
```

- Quote every expansion: `"$path"`, `"${items[@]}"`. Use `--` before user-supplied paths.
- Guard deletion: `rm -rf "${dir:?}/cache"`.
- Under `set -e`, an assignment takes the exit status of its command substitution, so
  `state="ok$([ "$x" = true ] && echo ', extra')"` ends the script, with no message, when the test is false.
  Give it a fallback (`&& echo ', extra' || true`) or use an `if`. The opposite trap: `local v="$(cmd)"`
  hides a failing `cmd`, so declare with `local v` first, then assign.
- macOS ships BSD tools and an old bash: `sed -i`, `readlink -f`, `date -d` and `grep -P` differ.
  Avoid them in portable scripts, or check the platform first.
- Never pipe a download into a shell without saying so. Download to a file over HTTPS, then run it.

## Python and Node tools

- Use the argument parser for `--help` and usage errors. State the minimum runtime and check it at
  start with a one-line message, not a traceback.
- Prefer the standard library in a tool that must run before anything is installed.
- Pass commands as a list, never a shell string built from input.

## Libraries

Keep the public API small and named. Do not print, exit or change global state from library code.
State the supported runtime versions. A breaking change needs a major version and a changelog line.

## Test it

Run tests against a throwaway `HOME`, with stubs at the front of `PATH` for anything that reaches
the network or changes the system (`git push`, `apt-get`, `systemctl`, `sudo`, `curl`).

| Case | Must hold |
|---|---|
| Fresh machine | Works with an empty `HOME` and no config |
| Second run | Reports no change, and files are identical |
| `--dry-run` | Changes nothing |
| Path with spaces, odd username | Still works |
| Missing tool, unsupported OS | A clear message and a non-zero exit |
| Failure halfway | Non-zero exit, nothing half-written, and a re-run recovers |
| `--json` | `json.loads(stdout)` succeeds on every path, including errors and skipped items |

Checks, when the tools are present (say which were not):

```bash
bash -n script.sh
shellcheck script.sh
python3 -m compileall -q scripts
```

**Gate:** the tests and checks must pass before the next kit step. Then `/break` attacks the change
with [the tooling attacks](../harden/references/tooling_attacks.md).
