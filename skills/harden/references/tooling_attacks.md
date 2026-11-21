# Tooling attacks

For a CLI, a script, an installer, infrastructure code or a library. Each attack is one test
against the real command, in a throwaway `HOME` with anything that reaches the network or changes
the system replaced by a stub. Never run these against a real machine's configuration.

| Area | Attack | Must hold |
|---|---|---|
| Input | Spaces, quotes, `$(...)`, a leading `-`, newlines and unicode in names and paths | Treated as data; nothing is executed |
| Paths | Empty value, `/`, `..`, a symlink to somewhere else | Refused or contained; nothing outside the target changes |
| Re-run | Run twice, then compare every file | The second run changes nothing |
| Interruption | Kill it halfway, or make a step fail | Non-zero exit, no half-written file, and a re-run recovers |
| Concurrency | Two runs at once (a timer and a person) | A lock, or a result as if they ran in turn |
| Existing work | Uncommitted changes, a user's own file where a link must go | Never overwritten; left alone or backed up |
| Dry run | `--dry-run` on every path | Nothing changes, and no network write |
| Environment | Empty `HOME`, no `PATH` tools, another username, no terminal, an unusual locale | Works, or stops with a clear message |
| Platform | An unsupported OS or package manager, an old runtime | A clear message and a non-zero exit |
| Privilege | Run as root and as a user | User files stay owned by the user; nothing world-writable |
| Secrets | Look in arguments, logs, output and files written | No secret appears; secret files are mode 600 |
| Dependencies | The network is down, a command fails, a download is corrupt | Fails closed; nothing partial is installed |
| Output | `--json` on success, error and skipped paths | stdout is valid JSON, and the exit code is honest |
