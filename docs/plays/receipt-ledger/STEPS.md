# Steps - receipt-ledger

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one stdlib-only Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and the run
continues.

| step | depends on | command |
|---|---|---|
| `read_files` | root | `python3 resources/daily_core/cli.py receipts-read --source files --receipts-dir $receipts_dir --out-dir <out_dir> --demo <demo>` |
| `read_mail` | root | `python3 resources/daily_core/cli.py receipts-read --source mail --mail-dir $mail_dir --out-dir <out_dir> --demo <demo>` |
| `report` | `read_files`, `read_mail` | `python3 resources/daily_core/cli.py receipts-report --months-back $months_back --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/receipt-ledger.md`
- `out_dir/receipt-ledger.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
