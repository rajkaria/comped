# Steps - desktop-clutter

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one stdlib-only Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and the run
continues.

| step | depends on | command |
|---|---|---|
| `read_desktop` | root | `python3 resources/daily_core/cli.py clutter-read --source desktop --desktop-dir $desktop_dir --out-dir <out_dir> --demo <demo>` |
| `read_downloads` | root | `python3 resources/daily_core/cli.py clutter-read --source downloads --downloads-dir $downloads_dir --out-dir <out_dir> --demo <demo>` |
| `read_screenshots` | root | `python3 resources/daily_core/cli.py clutter-read --source screenshots --out-dir <out_dir> --demo <demo>` |
| `report` | `read_desktop`, `read_downloads`, `read_screenshots` | `python3 resources/daily_core/cli.py clutter-report --cold-days $cold_days --hash-duplicates $hash_duplicates --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/desktop-clutter.md`
- `out_dir/desktop-clutter.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
