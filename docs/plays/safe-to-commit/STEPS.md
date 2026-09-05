# Steps - safe-to-commit

One step. This Play is a pure function: text goes in, the answer comes out, and nothing is kept between runs.
Each step is one stdlib-only Python command that prints a human block and then exactly one
JSON object as its last line. Nothing to report is an expected absence: the step says so,
exits 0, and the run completes.

| step | depends on | command |
|---|---|---|
| `report` | root | `python3 resources/micro_core/cli.py staged report --repo $repo --max-file-kb $max_file_kb --strict $strict --now $now --demo $demo` |

Outputs:

- one JSON object on each step's stdout

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
