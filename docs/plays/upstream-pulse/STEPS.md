# Steps - upstream-pulse

The steps form a chain: each one leaves a file behind for the next, and the report depends on the readings.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

`fetch_registry` is the only step in this package that opens a connection. It asks the public registries about the packages `read_lockfiles` found and writes their answers into `out_dir`; with `demo=true` it opens nothing at all. Every other step is offline by construction.

| step | depends on | command |
|---|---|---|
| `read_lockfiles` | root | `python3 resources/daily_core/cli.py upstream-read --source lockfiles --root $root --out-dir <out_dir> --demo <demo>` |
| `fetch_registry` | `read_lockfiles` | `python3 resources/fetch/registry_partial.py --max-packages $max_packages --cache-hours $cache_hours --out-dir <out_dir> --demo <demo>` |
| `read_registry` | `fetch_registry` | `python3 resources/daily_core/cli.py upstream-read --source registry --root $root --out-dir <out_dir> --demo <demo>` |
| `report` | `read_lockfiles`, `read_registry` | `python3 resources/daily_core/cli.py upstream-report --root $root --dormant-days $dormant_days --cache-hours $cache_hours --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/upstream-pulse.md`
- `out_dir/upstream-pulse.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no adapters.
License: MIT.
