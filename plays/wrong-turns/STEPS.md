# Steps - wrong-turns

One reading is one step, so the reads are parallel roots and everything downstream depends on the merge.
Every step is a shell command; each prints one JSON object on stdout. A missing log directory is an
expected absence: the step prints `{"ok":true,"warning":...}` and exits 0.

| step | depends on | command |
|---|---|---|
| `read_claude` | root | `python3 resources/comped_core/cli.py ledger --only claude-code --claude-dir <claude_dir> --days-back <days_back> --out-dir <out_dir> --include-subagents <include_subagents> --redact true` |
| `read_codex` | root | `python3 resources/comped_core/cli.py ledger --only codex --codex-dir <codex_dir> --days-back <days_back> --out-dir <out_dir> --redact true` |
| `merge_ledger` | read_claude, read_codex | `python3 resources/comped_core/cli.py merge --out-dir <out_dir>` |
| `classify_turns` | merge_ledger | `python3 resources/comped_core/cli.py wrongturns --out-dir <out_dir> --min-recurrence <min_recurrence> --show-snippets <show_snippets>` |
| `draft_rules` | classify_turns | `python3 resources/comped_core/cli.py rules --out-dir <out_dir> --rules-target <rules_target>` |

Outputs:

- `out_dir/wrong-turns-report.md`
- `out_dir/wrong-turns-rules.md`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
