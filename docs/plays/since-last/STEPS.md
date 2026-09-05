# Steps - since-last

One step. This Play is a pure function: text goes in, the answer comes out, and nothing is kept between runs.
Each step is one stdlib-only Python command that prints a human block and then exactly one
JSON object as its last line. Nothing to report is an expected absence: the step says so,
exits 0, and the run completes.

| step | depends on | command |
|---|---|---|
| `report` | root | `python3 resources/micro_core/cli.py since-last report --root $root --state-dir $state_dir --ignore $ignore --max-files $max_files --watch-sensitive $watch_sensitive --tz $tz --now $now --demo $demo` |

Outputs:

- one JSON object on each step's stdout
- `$state_dir/<stream>.jsonl` — appended to, never rewritten

Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.
License: MIT.
