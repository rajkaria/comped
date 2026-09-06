# Steps - bus-factor

The steps form a chain: each one leaves a file behind for the next, and the report depends on the readings.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

| step | depends on | command |
|---|---|---|
| `read_git` | root | `python3 resources/daily_core/cli.py busfactor-read --source git --root $root --max-repos $max_repos --out-dir <out_dir> --demo <demo>` |
| `report` | `read_git` | `python3 resources/daily_core/cli.py busfactor-report --departed-days $departed_days --stale-days $stale_days --threshold $threshold --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/bus-factor.md`
- `out_dir/bus-factor.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). `git` for a real run. No pip installs, no node, no adapters, no network, no credentials.
License: MIT.
