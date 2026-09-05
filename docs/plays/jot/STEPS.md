# Steps - jot

Two steps. `record` appends one line to the log and `report` reads the log back, and the state file is what they share.
Each step is one stdlib-only Python command that prints a human block and then exactly one
JSON object as its last line. Nothing to report is an expected absence: the step says so,
exits 0, and the run completes.

| step | depends on | command |
|---|---|---|
| `record` | root | `python3 resources/micro_core/cli.py jot record --note $note --vault-dir $vault_dir --inbox $inbox --state-dir $state_dir --now $now --demo $demo` |
| `report` | `record` | `python3 resources/micro_core/cli.py jot report --vault-dir $vault_dir --inbox $inbox --state-dir $state_dir --tz $tz --now $now --demo $demo` |

Outputs:

- one JSON object on each step's stdout
- `$state_dir/<stream>.jsonl` — appended to, never rewritten
- `$vault_dir/$inbox` — one appended line

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
