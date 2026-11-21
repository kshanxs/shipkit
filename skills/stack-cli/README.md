# stack-cli

**Group:** Build · **Commands:** `/cli`, `/shell`

Conventions and a test workflow for command-line tools, shell scripts, provisioners, infrastructure code and small libraries: safe re-runs, dry runs, honest exit codes, data on stdout, no hardcoded users or machines, and tests in a throwaway `HOME` with stubbed commands.

## When to use it

Adding or changing a CLI, a script, an installer, a service unit, infrastructure code or a library.

## Example

In Claude Code:

```
/cli add a --dry-run flag to the installer
```

In Cursor, Codex or Trae, name it in the message: `@cli add a --dry-run flag to the installer`.
