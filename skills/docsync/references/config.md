# docsync: the `[docsync]` table of shipkit.toml

Every key is optional; these are the defaults. A check whose files do not exist is skipped.

```toml
[docsync]
docs_dir = "docs"
packages = ["apps/*", "packages/*", "services/*"]   # each matching folder keeps its own CHANGELOG.md;
                                                     # [] for a one-package repo (the root CHANGELOG.md covers the code)
tracker = "docs/feature_status.md"                  # rows `| 2.1 Name | Status | note |` and the code map `| \`path\` | [doc](...) |`
features_dir = "docs/features"                      # one spec per feature, each with a dated status line
code_roots = []                                     # folders whose sub-folders are features: ["apps/api/app", "apps/web/src/features"]
statuses = ["Built", "Partly built", "Backend only", "Frontend only", "In progress", "Next", "Planned", "Coming soon"]
bug_register = "docs/testing/bug_report.md"
attack_log = "docs/testing/attack_log.md"
attack_log_start = ""                               # a date: closed bugs "Found by ... attack" since then need an attack row
racing_markers = []                                 # names that mark a race test: ["racing_client", "all_read_before_any_writes"]
naming = "snake"                                    # docs file names: snake | kebab | lower | any
plans_dir = "docs/plans"                            # dated files (YYYY-MM-DD-title.md) live only here
plan_sources = []                                   # every spec must be linked from one: ["docs/feature_catalog.md"]
no_plan = []                                        # specs exempt from that: ["docs/features/admin/*"]
policy_pages = []                                   # globs: ["apps/web/src/legal/*Page.tsx"]
policy_stamp = ""                                   # the file holding the policies' last-updated date
pairs = []                                          # files that change together: [["apps/web/src/pricing.ts", "docs/pricing.md"]]
logs = ["docs/bugs_fixed_and_improvements.md"]      # history files, where retired terms are allowed
scratch_names = ["task.md", "todo.md", "tasks.md"]  # not allowed inside packages
emoji = true
matrix = true                                       # lint the harden skill's test matrix when it exists

[[docsync.stale]]                                   # retired names, prices or paths; allowed in the logs and in `allowed`
label = "retired plan price"
pattern = '\$49/seat'
allowed = ["docs/pricing_history.md"]
```

The generic SaaS example of a whole `shipkit.toml` is in the repository's
`shipkit.example.toml`.
