---
name: ship-check
description: "A read-only launch-readiness audit: pins the branch and head SHA, reads the docs and the code against a configurable checklist (operator capabilities, onboarding flows, privacy and the regulations you name, security, backups and recovery, observability, delivery, supply chain, operations, pricing), marks each item DONE, PARTIAL, MISSING or UNKNOWN with a file path as evidence, and ends with the launch blockers and the top five must-haves. It never builds or fixes anything. Use when asked whether the project is ready to launch, ship, deploy or go live, for a readiness audit or report, or for the launch blockers."
---

# Ship check: launch readiness

A read-only audit. It never builds or fixes anything, and every finding stays plan-only until the
owner picks what goes to the builder. `$SK` is the skills folder this skill is installed in.

## The checklist

What the audit covers is configuration, not this file: `ship-check.toml` at the project root (or
the path in `[ship_check] checklist` of `shipkit.toml`); without one, the generic SaaS checklist in
[references/checklist.example.toml](references/checklist.example.toml) is used.

```bash
C="python3 $SK/ship-check/scripts/ship_check.py"
$C init                                   # copy the generic SaaS checklist to ship-check.toml, then make it yours
$C scaffold --out ship-check-report.md    # the report's skeleton: every item UNKNOWN, with files to read for each
$C check ship-check-report.md             # every status a word, every DONE/PARTIAL/PRESENT a real path, the SHA, the top five
```

Make the checklist yours before the first audit: name the regulations that apply (GDPR, CCPA,
HIPAA, PCI DSS, SOC 2, a national data-protection law) in the privacy group's `note` and items; list
the operator console's capabilities; list the onboarding flows in the order a customer meets them;
list the pricing facts your plans have.

## 0. Pin the target

- Audit the active branch (or the one named) at its head SHA; the scaffold writes both at the top.
- Note which fixes are not on the deploy branch yet (`[target] deploy_branch`).

## 1. Read the sources

The checklist's `[sources]`: the tracker, the open questions, the bug register, the deployment and
infrastructure docs, CI workflows, security code, legal pages and pricing. **Documents can be
stale: confirm every claim in the code.** When a document says built or not built, check the code
and flag the stale document.

## 2. The report

1. **Operator capabilities** (support, audited support access, uptime and health, configuration and
   feature flags, suspend or offboard, billing operations, audit): PRESENT, PARTIAL or MISSING, with
   a path.
2. **Onboarding flows**, in the order a customer meets them, plus developer and test accounts:
   compare each with common practice and name each gap.
3. **Status checklist**: each item DONE, PARTIAL, MISSING or UNKNOWN, one line of evidence and a
   path, grouped as the checklist groups them.
4. **Pricing**: exact values with paths (plans, per-seat or usage prices, minimums, tiers, tax,
   trial and grace days, provider fees, unit economics). Flag stale documents.
5. **Bugs and risks**: open bugs and in-flight pull requests; then a numbered list of **launch
   blockers**, then other risks, then unknowns.

End with the **top five must-haves before launch**. Start nothing; wait for the owner to pick.

## Rules

- Every claim gets a file path, with a line number where you have one. What you could not verify is
  UNKNOWN; never guess. `ship_check.py check` refuses a DONE, PARTIAL or PRESENT with no path, and a
  path that does not exist.
- Keep it short and plain; status words in capitals.
- If a channel cuts off long messages, send the report in numbered parts (sections 1 to 3, then 4
  and 5). Large reports go in a file or a document; the chat gets the link and the top five
  blockers.
- Deliver to whoever asked. Do not post the report anywhere else.
