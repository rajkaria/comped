# Steps - photo-debt

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

| step | depends on | command |
|---|---|---|
| `read_photos` | root | `python3 resources/daily_core/cli.py photos-read --source photos --library $library --out-dir <out_dir> --demo <demo>` |
| `read_folder` | root | `python3 resources/daily_core/cli.py photos-read --source folder --root $root --out-dir <out_dir> --demo <demo>` |
| `report` | `read_photos`, `read_folder` | `python3 resources/daily_core/cli.py photos-report --burst-window $burst_window --screenshot-days $screenshot_days --top $top --hash-dupes $hash_dupes --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/photo-debt.md`
- `out_dir/photo-debt.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no adapters, no network, no credentials.
License: MIT.
