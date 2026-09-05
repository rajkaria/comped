#!/usr/bin/env python3
"""Generate main.ts, deps.toml and STEPS.md for the twelve micro Plays from docs/plays.

DESCRIPTION.md is the registry copy and PARAMETERS.json the parameter table; both are hand-written
source. _micro-spec.json is the DAG, the tags, the output schema and the one-line summary. The
frontmatter shape matches the nine Plays already published from this repository.

A Play that remembers is two steps, record then report. A Play that is a pure function is one
report step: giving it a second would mean inventing a scratch file for the halves to talk
through, and a Play that claims to write nothing should not write a file to prove it.
"""
import io
import json
import pathlib
import sys
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HANDLE = "rajkaria"
ROTE_VERSION = "0.80.0"
VERSION = "0.1.0"
CLI = "@resource{micro_core/cli.py}"
DEMO_NOW = "2026-09-05T12:00:00Z"
SPEC = json.loads((ROOT / "docs" / "plays" / "_micro-spec.json").read_text(encoding="utf-8"))
SLUGS = list(SPEC)
# Only these three need a price table, so only these three carry a second core.
PRICED = ("fits", "last-turn", "budget-left")
INTEGERS = {"punches", "switches", "current_block_min", "longest_block_min", "streak", "longest_streak",
            "bytes", "chars", "lines", "words", "tokens_low", "tokens_mid", "tokens_high", "pct",
            "window", "depth_reached", "today", "week", "inbox_lines", "captured", "input", "output",
            "cache_read", "cache_write", "cache_pct", "turns_today", "turns", "lines_added",
            "lines_removed", "files", "staged", "average_interval_min"}
BOOLEANS = {"fits", "valid", "over", "priced", "first_run", "truncated"}
OBJECTS = {"layers", "costs", "topics", "by_tag", "currencies", "habits", "fires", "findings",
           "counts", "created", "modified", "deleted", "biggest", "sensitive_changed", "written",
           "debug", "oversized", "env_files", "from_worktree", "models"}

DEPS = """schema_version = 1

[[tools]]
id = "python3"
command = "python3"
required = true

[[tools.install]]
manager = "brew"
package = "python@3"

[[tools.install]]
manager = "apt"
package = "python3"

[[tools.install]]
manager = "system"
notes = "Any Python 3.9+ on PATH. Every step is one stdlib-only script; no pip install, no node, no network."
"""

BODY = r"""
// Presentation plane: deprivileged; imports ONLY the presentation SDK; owns no effects.
const {{ FlowOutput, isProcessExecBody, loadPresentationContext, stepName }} =
  await import("__ROTE_PRESENTATION_SDK__");

const out = new FlowOutput();
const ctx = await loadPresentationContext();

/** Read one process.exec step's stdout, refusing anything that is not a clean, complete capture. */
function stdoutOf(label: string, step: {{ body: unknown }}): string {{
  if (!isProcessExecBody(step.body)) throw new Error(`${{label}} did not record a process.exec observation`);
  const exit = step.body.status.exit;
  if (exit.kind !== "code" || exit.code !== 0) {{
    throw new Error(`${{label}} failed: ${{step.body.stderr?.text ?? "no stderr captured"}}`);
  }}
  const s = step.body.stdout;
  // Truncation is the cause, an unparseable tail only its symptom: check it before parsing.
  if (s?.truncated === true) throw new Error(`${{label}} stdout was truncated at ${{s.bytes ?? "?"}} bytes`);
  if (s?.text === undefined) throw new Error(`${{label}} captured no stdout`);
  return s.text;
}}

/** Every step prints one JSON object as its last line; everything above it is for a human. */
function split(text: string): {{ human: string; json: Record<string, unknown> }} {{
  const lines = text.split("\n");
  let i = lines.length - 1;
  while (i >= 0 && lines[i].trim() === "") i--;
  try {{
    return {{ human: lines.slice(0, i).join("\n").trimEnd(), json: JSON.parse(lines[i]) }};
  }} catch {{
    return {{ human: text.trimEnd(), json: {{}} }};
  }}
}}

/** A source this machine does not have warns and exits 0. Surface those, once, by name. */
function absencesOf(entries: Array<{{ label: string; step: ReturnType<typeof ctx.step> }}>): string[] {{
  const notes: string[] = [];
  for (const {{ label, step }} of entries) {{
    const o = step.outcome;
    if (o.status !== "completed" && o.status !== "restored") {{ notes.push(`${{label}}: not run`); continue; }}
    if (!isProcessExecBody(o.output.body)) continue;
    const parsed = split(o.output.body.stdout?.text ?? "").json as {{ warning?: string }};
    if (typeof parsed.warning === "string") notes.push(`${{label}}: ${{parsed.warning}}`);
  }}
  return notes;
}}

if (ctx.run.status === "failed") {{
  out.human("The run failed before it could produce a result; the step evidence is in the runner report above.");
  out.summary("run failed");
  out.result({{ run_id: ctx.run.run_id, ok: false }});
}} else {{
  const final = split(stdoutOf("report", ctx.requireAvailable(stepName("report"))));
  const j = final.json as Record<string, any>;
  const notes = absencesOf([
{reads}
  ]);
  out.human([final.human, notes.length ? `Could not read: ${{notes.join("; ")}}` : ""].filter(Boolean).join("\n"));
  out.summary({summary});
  out.result({{ run_id: ctx.run.run_id, ...j, absences: notes }});
}}
"""



def yaml_scalar(v):
    return "'{0}'".format(str(v).replace("'", "''"))


def kind_of(key):
    if key in INTEGERS:
        return "integer"
    if key in BOOLEANS:
        return "boolean"
    return "object" if key in OBJECTS else "string"


def full_argv(argv):
    """Every step also takes the clock and the demo switch, so both are appended once, here."""
    return ["python3", CLI] + list(argv) + ["--now", "$now", "--demo", "$demo"]


def frontmatter(slug, desc, params):
    spec = SPEC[slug]
    tags = spec["tags"]
    L = ["name: {0}".format(slug), "description: {0}".format(yaml_scalar(desc)),
         "version: {0}".format(yaml_scalar(VERSION)),
         "source_url: https://play.modiqo.ai/{0}/{1}".format(HANDLE, slug),
         "metadata:",
         "  version: {0}".format(yaml_scalar(VERSION)),
         "  rote_version: {0}".format(yaml_scalar(ROTE_VERSION)),
         "  status: released", "  kind: atomic",
         "  flow_type: sequential",
         "  execution_model: steps_with_presentation",
         "  requires_endpoints: []",
         "  requires_sessions: false",
         "  license: MIT",
         "  discoverability:", "    tags:"]
    L += ["    - {0}".format(t) for t in tags]
    L += ["tags:"] + ["- {0}".format(t) for t in tags]
    L += ["discoverability:", "  tags:"] + ["  - {0}".format(t) for t in tags]
    L += ["output:", "  schema:", "    type: object", "    properties:"]
    for key in spec["outputs"]:
        L += ["      {0}:\n        type: {1}".format(key, kind_of(key))]
    fx = ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json"
    if fx.is_file():
        L += ["presentation_fixtures:"]
        L += ["  {0}: {1}".format(k, v) for k, v in sorted(json.loads(fx.read_text()).items())]
    L += ["parameters:"]
    for p in params:
        L += ["- name: {0}".format(p["name"]),
              "  param_type: {0}".format("integer" if p["type"] == "integer" else "string"),
              "  required: false",
              "  default: {0}".format(yaml_scalar(p["default"])),
              "  description: {0}".format(yaml_scalar(p["description"])),
              "  example: {0}".format(yaml_scalar(p["example"]))]
    L += ["steps:"]
    for name, argv, deps, timeout in spec["steps"]:
        L += ["  {0}:".format(name), "    type: process.exec", "    timeout_ms: {0}".format(timeout)]
        if deps:
            L += ["    depends_on:"] + ["    - {0}".format(d) for d in deps]
        L += ["    argv:"] + ["    - {0}".format(yaml_scalar(a)) for a in full_argv(argv)]
    return "\n".join(L)


def steps_doc(slug, params):
    """STEPS.md is generated: a hand-maintained copy of the DAG is a copy that goes stale."""
    spec = SPEC[slug]
    writers = [p["name"] for p in params if p["name"] in ("state_dir", "vault_dir")]
    rows = []
    for name, argv, deps, _timeout in spec["steps"]:
        cmd = " ".join(["python3", "resources/micro_core/cli.py"] + list(argv) + ["--now", "$now",
                                                                                 "--demo", "$demo"])
        rows.append("| `{0}` | {1} | `{2}` |".format(
            name, ", ".join("`{0}`".format(d) for d in deps) if deps else "root", cmd))
    shape = ("One step. This Play is a pure function: text goes in, the answer comes out, and nothing "
             "is kept between runs." if len(spec["steps"]) == 1 else
             "Two steps. `record` appends one line to the log and `report` reads the log back, and the "
             "state file is what they share.")
    return "\n".join([
        "# Steps - {0}".format(slug), "",
        shape,
        "Each step is one stdlib-only Python command that prints a human block and then exactly one",
        "JSON object as its last line. Nothing to report is an expected absence: the step says so,",
        "exits 0, and the run completes.", "",
        "| step | depends on | command |", "|---|---|---|"] + rows + ["", "Outputs:", ""] +
        ["- one JSON object on each step's stdout"] +
        (["- `{0}` — appended to, never rewritten".format(
            "$state_dir/<stream>.jsonl") ] if "state_dir" in writers else []) +
        (["- `$vault_dir/$inbox` — one appended line"] if "vault_dir" in writers else []) +
        ["", "Requirements: `python3` (>= 3.9). No pip installs, no node, no network, no credentials.",
         "License: MIT.", ""])


def presentation_fixtures(slug):
    """Capture each step's real demo output, so the presentation plane is developed against truth."""
    from micro_core import cli
    spec = SPEC[slug]
    dst = ROOT / "plays" / slug / "resources" / "presentation-fixtures"
    index = {}
    for name, argv, _deps, timeout in spec["steps"]:
        # On a demo run the fixture supplies the input, so a flag whose value is a parameter
        # placeholder is dropped WITH its flag — a bare --text with nothing after it is an error,
        # not a default.
        call, i = [], 0
        argv = list(argv)
        while i < len(argv):
            if argv[i].startswith("--") and i + 1 < len(argv) and argv[i + 1].startswith("$"):
                i += 2
                continue
            call.append(argv[i])
            i += 1
        call += ["--demo", "true", "--now", DEMO_NOW]
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(call)
        out = buf.getvalue()
        d = dst / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "stdout.txt").write_text(out, encoding="utf-8")
        (d / "stderr.txt").write_text("", encoding="utf-8")
        (d / "fixture.yaml").write_text("\n".join([
            "schema_version: 1", "kind: process.exec", "status:", "  exit:", "    kind: code",
            "    code: 0", "  duration_ms: 40", "  timeout_ms: {0}".format(timeout),
            "stdout: resources/presentation-fixtures/{0}/stdout.txt".format(name),
            "stderr: resources/presentation-fixtures/{0}/stderr.txt".format(name), ""]), encoding="utf-8")
        index[name] = "resources/presentation-fixtures/{0}/fixture.yaml".format(name)
    (ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json").write_text(
        json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main():
    for slug in SLUGS:
        src = ROOT / "docs" / "plays" / slug
        dst = ROOT / "plays" / slug
        dst.mkdir(parents=True, exist_ok=True)
        params = json.loads((src / "PARAMETERS.json").read_text(encoding="utf-8"))
        presentation_fixtures(slug)
        desc = (src / "DESCRIPTION.md").read_text(encoding="utf-8").strip()
        fm = frontmatter(slug, desc, params)
        body = "\n".join(" * " + line if line else " *" for line in fm.splitlines())
        reads = ",\n".join(
            '    {{ label: "{0}", step: ctx.step(stepName("{0}")) }}'.format(name)
            for name, _a, deps, _t in SPEC[slug]["steps"] if not deps and name != "report")
        program = BODY.format(reads=reads, summary=SPEC[slug]["summary"])
        (dst / "main.ts").write_text(
            "#!/usr/bin/env -S rote play run\n/**\n * @rote-frontmatter\n * ---\n"
            + body + "\n * ---\n */\n" + program, encoding="utf-8")
        (dst / "deps.toml").write_text(DEPS, encoding="utf-8")
        (src / "STEPS.md").write_text(steps_doc(slug, params), encoding="utf-8")
        print("{0}: main.ts + deps.toml + STEPS.md, {1} step(s)".format(slug, len(SPEC[slug]["steps"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
