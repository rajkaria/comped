# Steps - comped

One reading is one step, so the reads are parallel roots and everything downstream depends on the merge.
Every step is a shell command; each prints one JSON object on stdout. A missing log directory is an
expected absence: the step prints `{"ok":true,"warning":...}` and exits 0.

| step | depends on | command |
|---|---|---|
| `read_claude` | root | `python3 resources/comped_core/cli.py ledger --only claude-code --claude-dir <claude_dir> --days-back <days_back> --out-dir <out_dir> --include-subagents <include_subagents> --redact <redact>` |
| `read_codex` | root | `python3 resources/comped_core/cli.py ledger --only codex --codex-dir <codex_dir> --days-back <days_back> --out-dir <out_dir> --redact <redact>` |
| `read_pi` | root | `python3 resources/comped_core/cli.py ledger --only pi --pi-dir <pi_dir> --days-back <days_back> --out-dir <out_dir> --redact <redact>` |
| `read_opencode` | root | `python3 resources/comped_core/cli.py ledger --only opencode --opencode-dir <opencode_dir> --days-back <days_back> --out-dir <out_dir> --redact <redact>` |
| `merge_ledger` | read_claude, read_codex, read_pi, read_opencode | `python3 resources/comped_core/cli.py merge --out-dir <out_dir>` |
| `price_ledger` | merge_ledger | `python3 resources/comped_core/cli.py price --out-dir <out_dir> --plan <plan> --rates-path <rates_path> --days-back <days_back>` |
| `find_repeats` | price_ledger | `python3 resources/comped_core/cli.py repeats --out-dir <out_dir> --repeat-threshold <repeat_threshold> --handle <handle>` |
| `render_card` | find_repeats | `python3 resources/comped_core/cli.py card --out-dir <out_dir> --card-theme <card_theme>` |

Outputs:

- `out_dir/comped-report.md`
- `out_dir/comped-card.svg`
- `out_dir/comped-card.png` (only when the machine can render one)
- `out_dir/comped-baseline.json`
- `out_dir/comped-explain.txt`
- `out_dir/comped-share.txt`
- the terminal card on the last step's stdout, plus one JSON object

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
