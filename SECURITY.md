# Security policy

## Report a vulnerability

Do not open a public issue. Use
[GitHub's private vulnerability reporting](https://github.com/kshanxs/shipkit/security/advisories/new)
and include the affected skill or script, the commit, the steps to reproduce and the impact.

## Supported versions

Security fixes go to the `main` branch.

## In scope

- Scripts, hooks and the installer in this repository running unintended commands, or writing
  outside the paths they should touch.
- Skill instructions that lead an agent to expose secrets or to act against a production system
  when the skill says it will not.

Vulnerabilities in a project that uses shipkit, or in a coding agent itself, belong with that
project or vendor.
