# Steps - vault-pulse

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one stdlib-only Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and the run
continues.

| step | depends on | command |
|---|---|---|
| `read_vault` | root | `python3 resources/daily_core/cli.py notes-read --vault $vault --out-dir <out_dir> --demo <demo>` |
| `report` | `read_vault` | `python3 resources/daily_core/cli.py notes-report --stale-days $stale_days --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/vault-pulse.md`
- `out_dir/vault-pulse.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
