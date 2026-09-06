# Steps - standing-cost

The steps form a chain: each one leaves a file behind for the next, and the report depends on the readings.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

`fetch_calendar` is the only step in this package that opens a connection. It reads the calendar window and writes the normalised events into `out_dir`; with `demo=true` it reads no environment variable and opens nothing at all. Every other step is offline by construction.

| step | depends on | command |
|---|---|---|
| `fetch_calendar` | root | `python3 resources/fetch/calendar_partial.py --partial $partial --calendar-id $calendar_id --days $days --token-env $token_env --out-dir <out_dir> --demo <demo>` |
| `read_calendar` | `fetch_calendar` | `python3 resources/daily_core/cli.py standingcost-read --source calendar --partial $partial --out-dir <out_dir> --demo <demo>` |
| `report` | `read_calendar` | `python3 resources/daily_core/cli.py standingcost-report --source calendar --partial $partial --days $days --focus-block-minutes $focus_block_minutes --currency $currency --hourly-rate $hourly_rate --self $owner_address --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/standing-cost.md`
- `out_dir/standing-cost.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no adapters.
License: MIT.
