# Steps - what-grew

The steps form a chain: each one leaves a file behind for the next, and the report depends on the readings.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

| step | depends on | command |
|---|---|---|
| `read_home` | root | `python3 resources/daily_core/cli.py grew-read --source home --root $root --depth $depth --floor-bytes $floor_bytes --out-dir <out_dir> --demo <demo>` |
| `report` | `read_home` | `python3 resources/daily_core/cli.py grew-report --since $since --keep-baselines $keep_baselines --write-baseline $write_baseline --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/what-grew.md`
- `out_dir/what-grew.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no adapters, no network, no credentials.
License: MIT.
