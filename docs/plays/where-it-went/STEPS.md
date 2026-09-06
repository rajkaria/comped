# Steps - where-it-went

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

| step | depends on | command |
|---|---|---|
| `read_chromium` | root | `python3 resources/daily_core/cli.py history-read --source chromium --days $days --out-dir <out_dir> --demo <demo>` |
| `read_firefox` | root | `python3 resources/daily_core/cli.py history-read --source firefox --days $days --out-dir <out_dir> --demo <demo>` |
| `read_safari` | root | `python3 resources/daily_core/cli.py history-read --source safari --days $days --out-dir <out_dir> --demo <demo>` |
| `report` | `read_chromium`, `read_firefox`, `read_safari` | `python3 resources/daily_core/cli.py history-report --days $days --gap-minutes $gap_minutes --top $top --tz $tz --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/where-it-went.md`
- `out_dir/where-it-went.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no adapters, no network, no credentials.
License: MIT.
