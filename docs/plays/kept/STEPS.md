# Steps - kept

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

| step | depends on | command |
|---|---|---|
| `read_agent` | root | `python3 resources/daily_core/cli.py kept-read --source agent --claude-dir $claude_dir --codex-dir $codex_dir --pi-dir $pi_dir --out-dir <out_dir> --demo <demo>` |
| `read_git` | root | `python3 resources/daily_core/cli.py kept-read --source git --root $root --max-repos $max_repos --out-dir <out_dir> --demo <demo>` |
| `report` | `read_agent`, `read_git` | `python3 resources/daily_core/cli.py kept-report --grace-minutes $grace_minutes --min-lines $min_lines --max-blame-files $max_blame_files --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/kept.md`
- `out_dir/kept.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). `git` for a real run. No pip installs, no node, no adapters, no network, no credentials.
License: MIT.
