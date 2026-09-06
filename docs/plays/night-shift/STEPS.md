# Steps - night-shift

The steps form a chain: each one leaves a file behind for the next, and the report depends on the readings.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

| step | depends on | command |
|---|---|---|
| `read_commits` | root | `python3 resources/daily_core/cli.py nightshift-read --source commits --root $root --days $days --emails $emails --out-dir <out_dir> --demo <demo>` |
| `report` | `read_commits` | `python3 resources/daily_core/cli.py nightshift-report --days $days --late-hour $late_hour --dawn-hour $dawn_hour --fixup-minutes $fixup_minutes --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/night-shift.md`
- `out_dir/night-shift.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). `git` for a real run. No pip installs, no node, no adapters, no network, no credentials.
License: MIT.
