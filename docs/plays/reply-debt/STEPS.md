# Steps - reply-debt

The steps form a chain: each one leaves a file behind for the next, and the report depends on the readings.
Every step is one Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and
the run continues.

`fetch_mail` is the only step in this package that opens a connection. It reads message headers and snippets and writes them into `out_dir`; with `demo=true` it reads no environment variable and opens nothing at all. Every other step is offline by construction.

| step | depends on | command |
|---|---|---|
| `fetch_mail` | root | `python3 resources/fetch/mail_partial.py --partial $out_dir/.reply-debt-mail.json --days $days --max-threads $max_threads --query=$query --token-env $token_env --out-dir <out_dir> --demo <demo>` |
| `read_mail` | `fetch_mail` | `python3 resources/daily_core/cli.py replydebt-read --source mail --partial $out_dir/.reply-debt-mail.json --out-dir <out_dir> --demo <demo>` |
| `report` | `read_mail` | `python3 resources/daily_core/cli.py replydebt-report --min-age-days $min_age_days --cold-days $cold_days --me $me --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/reply-debt.md`
- `out_dir/reply-debt.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no adapters.
License: MIT.
