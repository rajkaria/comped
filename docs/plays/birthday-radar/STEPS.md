# Steps - birthday-radar

One source is one step, so the reads are parallel roots and the report depends on all of them.
Every step is one stdlib-only Python command that prints a human block and then exactly one JSON object as its
last line. A source this machine does not have is an expected absence: the step names it, exits 0, and the run
continues.

| step | depends on | command |
|---|---|---|
| `read_contacts` | root | `python3 resources/daily_core/cli.py contacts-read --source addressbook --out-dir <out_dir> --demo <demo>` |
| `read_vcards` | root | `python3 resources/daily_core/cli.py contacts-read --source vcard --vcard-dir $vcard_dir --out-dir <out_dir> --demo <demo>` |
| `read_csv` | root | `python3 resources/daily_core/cli.py contacts-read --source csv --csv-path $csv_path --out-dir <out_dir> --demo <demo>` |
| `report` | `read_contacts`, `read_vcards`, `read_csv` | `python3 resources/daily_core/cli.py contacts-report --horizon $horizon --redact $redact --out-dir <out_dir> --demo <demo>` |

Outputs:

- `out_dir/birthday-radar.md`
- `out_dir/birthday-radar.json`
- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
