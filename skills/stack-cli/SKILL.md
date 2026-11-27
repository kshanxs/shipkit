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

## Services an installer sets up

- A systemd user unit runs with a minimal `PATH` that usually lacks `~/.local/bin`: set
  `Environment=PATH=...` in the unit when the service calls tools installed there, or a status page
  silently shows "none found" instead of failing. That line replaces systemd's default `PATH`, so
  write the full standard list after the extra folders (`/usr/local/sbin:/usr/local/bin:/usr/sbin:
  /usr/bin:/sbin:/bin`), or tools in sbin (`iw`, `ip`, `ethtool`) go missing. Build it from one
  shared value for every unit the installer writes, and test the rendered unit.
- A script a service, cron or ssh command may run must not assume an interactive `PATH`: look in
  `/usr/local/sbin`, `/usr/sbin` and `/sbin` too (append them when missing) before reporting a tool
  as not installed.
- User units stop at logout unless lingering is on (`loginctl show-user $USER -p Linger`); check it
  and tell the user the one command that turns it on, rather than running sudo for them.
- A reverse proxy in front of a local service (for example `tailscale serve`) makes every request
  arrive from 127.0.0.1, so "local requests only" checks in that service stop protecting anything.
  Publish only the paths clients need, and never the admin API.
- An upstream that hashes or rewrites its own config on start (a plaintext key replaced by its hash)
  owns that file afterwards: write it once, never overwrite it on re-install, and keep the plaintext
  value the tool itself needs in a separate mode-600 file.
- A queue an API pops on read (each record handed out once) needs exactly one persistent reader that
  stores what it takes; document it, so nobody drains it by hand while debugging.
- Updating a pinned dependency automatically: back up its state, move, health-check, and move back
  on failure, recording the outcome where the user will see it. Test the rollback for real by moving
  to a version known to fail the check.

## Libraries

Keep the public API small and named. Do not print, exit or change global state from library code.
State the supported runtime versions. A breaking change needs a major version and a changelog line.

## Running unattended

Timers, cron jobs and scripts that reach other hosts over ssh or look up new DNS names fail silently.
Read [the unattended rules](references/unattended.md): a timer needs `OnCalendar=` to keep a next run
(check `systemctl --user list-timers`), ssh connections are reused and backed off on resets, and a new
name is checked against its authoritative server before anyone resolves it through a cache.

## Test it

Run tests against a throwaway `HOME`, with stubs at the front of `PATH` for anything that reaches
the network or changes the system (`git push`, `apt-get`, `systemctl`, `sudo`, `curl`).
A script that reads fixed paths (`/sys`, `/proc`, `/usr/sbin/<tool>`) needs a root-prefix override
(for example `SYSROOT=...`) so tests can point it at fixtures instead.

| Case | Must hold |
|---|---|
| Fresh machine | Works with an empty `HOME` and no config |
| Second run | Reports no change, and files are identical |
| `--dry-run` | Changes nothing |
| Path with spaces, odd username | Still works |
| Missing tool, unsupported OS | A clear message and a non-zero exit |
| Failure halfway | Non-zero exit, nothing half-written, and a re-run recovers |
| `--json` | `json.loads(stdout)` succeeds on every path, including errors and skipped items |
| Minimal `PATH` (`env -i HOME=$HOME PATH=/usr/bin:/bin`) | Same results as from a login shell: the way a service, cron or ssh runs it |

Checks, when the tools are present (say which were not):

```bash
bash -n script.sh
shellcheck script.sh
python3 -m compileall -q scripts
```

**Gate:** the tests and checks must pass before the next kit step. Then `/break` attacks the change
with [the tooling attacks](../harden/references/tooling_attacks.md).
