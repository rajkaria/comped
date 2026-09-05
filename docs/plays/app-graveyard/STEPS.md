# Steps - app-graveyard

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one stdlib-only Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and the run
continues.

| step | depends on | command |
|---|---|---|
| `read_applications` | root | `python3 resources/daily_core/cli.py apps-read --source applications --app-dirs $app_dirs --out-dir <out_dir> --demo <demo>` |
| `read_casks` | root | `python3 resources/daily_core/cli.py apps-read --source casks --out-dir <out_dir> --demo <demo>` |
| `report` | `read_applications`, `read_casks` | `python3 resources/daily_core/cli.py apps-report --unused-days $unused_days --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/app-graveyard.md`
- `out_dir/app-graveyard.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
