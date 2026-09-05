# Steps - tab-debt

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one stdlib-only Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and the run
continues.

| step | depends on | command |
|---|---|---|
| `read_chromium` | root | `python3 resources/daily_core/cli.py tabs-read --source chromium --out-dir <out_dir> --demo <demo>` |
| `read_firefox` | root | `python3 resources/daily_core/cli.py tabs-read --source firefox --out-dir <out_dir> --demo <demo>` |
| `read_safari` | root | `python3 resources/daily_core/cli.py tabs-read --source safari --out-dir <out_dir> --demo <demo>` |
| `read_arc` | root | `python3 resources/daily_core/cli.py tabs-read --source arc --out-dir <out_dir> --demo <demo>` |
| `report` | `read_chromium`, `read_firefox`, `read_safari`, `read_arc` | `python3 resources/daily_core/cli.py tabs-report --keep-path $keep_path --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/tab-debt.md`
- `out_dir/tab-debt.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
