#!/usr/bin/env python3
"""Generate main.ts and deps.toml for the sixteen daily Plays from the single source in docs/plays.

DESCRIPTION.md is the registry copy, PARAMETERS.json the parameter table, and _daily-spec.json the
DAG, tags and output schema. The frontmatter shape matches the three comped Plays, which was in turn
copied from live registry archives; see docs/research/ROTE-FORMAT.md.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDLE = "rajkaria"
ROTE_VERSION = "0.79.0"
VERSION = "0.1.0"
CLI = "@resource{daily_core/cli.py}"
SPEC = json.loads((ROOT / "docs" / "plays" / "_daily-spec.json").read_text(encoding="utf-8"))
SLUGS = list(SPEC)

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

# The presentation plane is deprivileged: it reads recorded step observations and owns no effects.
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

SUMMARY = {
    "tab-debt": '`${j.tabs ?? 0} open tabs across ${j.browsers ?? 0} browser(s), '
                '${j.cold ?? 0} untouched for a week or more'
                '${j.oldest_days ? `, oldest last used ${j.oldest_days} days ago` : ""}`',
    "birthday-radar": '`${j.with_birthday ?? 0} of ${j.contacts ?? 0} contacts have a birthday'
                      '${j.next_in_days === null || j.next_in_days === undefined ? "; none is coming up" '
                      ': `; the next is in ${j.next_in_days} day(s)`}'
                      '${j.missing ? `, ${j.missing} have none recorded` : ""}`',
    "app-graveyard": '`${(j.unused ?? 0) + (j.never_used ?? 0)} of ${j.apps ?? 0} applications unopened, '
                     '${Math.round((j.reclaimable ?? 0) / 1e8) / 10} GB reclaimable'
                     '${j.intel_only ? `, ${j.intel_only} still Intel-only` : ""}`',
    "vault-pulse": '`${j.notes ?? 0} notes, ${j.words ?? 0} words, ${j.orphans ?? 0} orphans, '
                   '${j.broken_links ?? 0} links pointing at nothing, daily streak ${j.streak ?? 0}`',
    "desktop-clutter": '`${j.files ?? 0} files on the Desktop and in Downloads, ${j.cold ?? 0} untouched, '
                       '${Math.round((j.reclaimable ?? 0) / 1e8) / 10} GB reclaimable, grade ${j.grade ?? "?"}`',
    "receipt-ledger": '`${j.in_window ?? 0} receipts totalled from ${j.documents ?? 0} documents: '
                      '${(j.currencies ?? []).map((c: any) => `${c.total} ${c.currency}`).join(" · ") '
                      '|| "nothing inside the window"}`',
    "bus-factor": '`${j.tracked_files ?? 0} tracked files across ${j.repos ?? 0} repositor(y/ies), '
                  '${j.sole_files ?? 0} of them with a single author, truck factor '
                  '${j.truck_factor ?? "?"}`',
    "night-shift": '`${j.commits ?? 0} commits over ${j.days ?? 0} days, ${j.late ?? 0} of them '
                   'late and ${j.weekend ?? 0} at the weekend, longest run of days '
                   '${j.longest_streak ?? 0}`',
    "kept": '`${j.agent_alive ?? 0} of ${j.agent_ever ?? 0} agent-written lines are still in the '
            'file${j.survival === null || j.survival === undefined ? "" : ` (${j.survival}% of '
            'them)`}, across ${j.sessions ?? 0} session(s)`',
    "extension-reach": '`${j.extensions ?? 0} extensions across ${j.browsers ?? 0} browser(s), '
                       '${j.all_urls ?? 0} able to read every page, ${j.stale ?? 0} not updated '
                       'in a year`',
    "where-it-went": '`${j.visits ?? 0} page visits over ${j.days ?? 0} days across '
                     '${j.domains ?? 0} domains${j.categories ? `, sorted into ${j.categories} '
                     'categories` : ""}`',
    "photo-debt": '`${j.assets ?? 0} photos taking '
                  '${Math.round((j.bytes ?? 0) / 1e8) / 10} GB, ${j.duplicates ?? 0} duplicate '
                  'group(s), ${Math.round((j.reclaimable ?? 0) / 1e8) / 10} GB reclaimable`',
    "what-grew": '`${Math.round((j.total_bytes ?? 0) / 1e8) / 10} GB across ${j.dirs_named ?? 0} '
                 'named folders${j.first_run ? "; first run, so there is nothing to compare it '
                 'with yet" : `, net ${Math.round((j.net_bytes ?? 0) / 1e8) / 10} GB since the '
                 'baseline`}`',
    "standing-cost": '`${j.occurrences ?? 0} occurrences of ${j.series ?? 0} recurring series '
                     'cost ${j.recurring_person_hours ?? 0} person-hours'
                     '${j.rate_set ? "" : "; no hourly rate is set, so no money is claimed"}`',
    "reply-debt": '`${j.debt ?? 0} of ${j.considered ?? 0} threads are waiting on you, '
                  '${j.direct ?? 0} of them asked you directly, ${j.cold ?? 0} have gone cold`',
    "upstream-pulse": '`${j.packages ?? 0} packages, ${j.checked ?? 0} checked, '
                      '${j.dormant ?? 0} dormant and ${j.single_maintainer ?? 0} with one '
                      'publisher; ${j.headline ?? 0} are both and in the production path`',
}

# The output schema's JSON types. Everything not named here is a string, which is what the
# free-text `verdict` and `grade` fields are.
NUMBER = ("person_hours", "recurring_person_hours", "silent_person_hours")
BOOLEAN = ("first_run", "offline", "rate_set")
OBJECT = ("currencies",)
INTEGER = (
    "tabs", "windows", "cold", "duplicates", "oldest_days", "browsers", "contacts",
    "with_birthday", "upcoming", "today", "next_in_days", "missing", "apps", "bytes", "unused",
    "never_used", "reclaimable", "intel_only", "casks", "notes", "words", "orphans",
    "broken_links", "write_only", "streak", "todo", "files", "screenshots", "documents",
    "priced", "in_window", "vendors", "recurring",
    # the ten pulse Plays
    "repos", "tracked_files", "tracked_lines", "sole_files", "authors", "truck_factor",
    "stale_sole_files", "commits", "days", "late", "weekend", "longest_streak", "agent_ever",
    "agent_alive", "human_ever", "human_alive", "survival", "sessions", "extensions", "installs",
    "all_urls", "blanket", "stale", "visits", "domains", "unique_urls", "categories", "assets",
    "burst_siblings", "total_bytes", "reclaim_bytes", "dirs_named", "free_bytes", "net_bytes",
    "baselines_held", "events_read", "occurrences", "cancelled", "series", "people",
    "threads_seen", "considered", "debt", "direct", "implied", "fyi", "excluded", "packages",
    "lockfiles", "checked", "unchecked", "dormant", "single_maintainer", "deprecated",
    "headline",
)


def output_type(key: str) -> str:
    for names, kind in ((OBJECT, "object"), (NUMBER, "number"), (BOOLEAN, "boolean"),
                        (INTEGER, "integer")):
        if key in names:
            return kind
    return "string"


def step_argv(step) -> list:
    """The full argv of one step: the shared CLI, or the packaged script the step names instead.

    A five-element step carries `{"resource": "<relpath>"}`, which is how the three network-backed
    Plays address their own fetcher -- the one file in each of those packages that opens a
    connection. Everything else is `daily_core/cli.py`, and both forms end with the same
    `--out-dir`/`--demo` pair so a step is always readable on its own.
    """
    argv, options = step[1], (step[4] if len(step) > 4 else {})
    script = "@resource{{{0}}}".format(options["resource"]) if options.get("resource") else CLI
    return ["python3", script] + list(argv) + ["--out-dir", "$out_dir", "--demo", "$demo"]


def yaml_scalar(v):
    return "'{0}'".format(str(v).replace("'", "''"))


def flow_type(steps: list) -> str:
    """`parallel` when the DAG has a layer wider than one step, `sequential` when it is a chain.

    rote runs a layer together and treats it as a barrier, so what the registry is being told here
    is a fact about the graph, not about how many steps there happen to be.
    """
    depth = {}
    for step in steps:
        name, deps = step[0], step[2]
        depth[name] = 1 + max([depth.get(d, 0) for d in deps] or [0])
    widths = {}
    for d in depth.values():
        widths[d] = widths.get(d, 0) + 1
    return "parallel" if max(widths.values()) > 1 else "sequential"


def frontmatter(slug: str, desc: str, params: list) -> str:
    spec = SPEC[slug]
    tags = spec["tags"]
    L = ["name: {0}".format(slug), "description: {0}".format(yaml_scalar(desc)),
         "version: {0}".format(yaml_scalar(VERSION)),
         "source_url: https://play.modiqo.ai/{0}/{1}".format(HANDLE, slug),
         "metadata:",
         "  version: {0}".format(yaml_scalar(VERSION)),
         "  rote_version: {0}".format(yaml_scalar(ROTE_VERSION)),
         "  status: released", "  kind: atomic",
         "  flow_type: {0}".format(flow_type(spec["steps"])),
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
        L += ["      {0}:\n        type: {1}".format(key, output_type(key))]
    fx = ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json"
    if fx.is_file():
        # Representative completed observations, captured from a real demo run by build_fixtures.py.
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
    for step in spec["steps"]:
        name, _argv, deps, timeout = step[0], step[1], step[2], step[3]
        full = step_argv(step)
        L += ["  {0}:".format(name), "    type: process.exec", "    timeout_ms: {0}".format(timeout)]
        if deps:
            L += ["    depends_on:"] + ["    - {0}".format(d) for d in deps]
        L += ["    argv:"] + ["    - {0}".format(yaml_scalar(a)) for a in full]
    return "\n".join(L)


def main() -> int:
    for slug in SLUGS:
        src = ROOT / "docs" / "plays" / slug
        dst = ROOT / "plays" / slug
        dst.mkdir(parents=True, exist_ok=True)
        desc = (src / "DESCRIPTION.md").read_text(encoding="utf-8").strip()
        params = json.loads((src / "PARAMETERS.json").read_text(encoding="utf-8"))
        fm = frontmatter(slug, desc, params)
        body = "\n".join(" * " + line if line else " *" for line in fm.splitlines())
        # Every step but the report: each of them prints its own `warning` when the
        # source it owns is absent, and the body surfaces those by name under the card.
        reads = ",\n".join(
            '    {{ label: "{0}", step: ctx.step(stepName("{0}")) }}'.format(step[0])
            for step in SPEC[slug]["steps"] if step[0] != "report")
        program = BODY.format(reads=reads, summary=SUMMARY[slug])
        (dst / "main.ts").write_text(
            "#!/usr/bin/env -S rote play run\n/**\n * @rote-frontmatter\n * ---\n"
            + body + "\n * ---\n */\n" + program, encoding="utf-8")
        (dst / "deps.toml").write_text(DEPS, encoding="utf-8")
        print("{0}: main.ts + deps.toml, {1} steps".format(slug, len(SPEC[slug]["steps"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
