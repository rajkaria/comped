#!/usr/bin/env python3
"""Generate each Play's main.ts and deps.toml from the single source already in the repo.

DESCRIPTION.md is the registry copy, PARAMETERS.json the parameter table, and STEPS below the DAG.
The frontmatter shape is copied from two live registry archives read on 2026-09-04
(modiqo/hello 0.2.2, dotisacat/playoffs-standings 0.2.5); see docs/research/ROTE-FORMAT.md.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HANDLE = "rajkaria"
ROTE_VERSION = "0.79.0"
VERSION = "0.1.5"

# One reading is one step: the read_* steps are parallel roots, everything else depends on the merge.
# argv addresses the bundled core through @resource{...}, which resolves to <package>/resources/<path>.
CLI = "@resource{comped_core/cli.py}"
# The one step that talks to the network lives outside the core, so the core stays verifiably offline.
POST = "@resource{post_score.py}"


def read(only, dir_param, extra=()):
    return ["python3", CLI, "ledger", "--only", only, "--{0}".format(dir_param.replace("_", "-")), "$" + dir_param,
            "--days-back", "$days_back", "--out-dir", "$out_dir"] + list(extra)


REDACT = ["--redact", "$redact"]
SUBAGENTS = ["--include-subagents", "$include_subagents"]

STEPS = {
    "session-ledger": [
        ("read_claude", read("claude-code", "claude_dir", SUBAGENTS + REDACT), [], 120000),
        ("read_codex", read("codex", "codex_dir", REDACT), [], 120000),
        ("read_pi", read("pi", "pi_dir", REDACT), [], 60000),
        ("read_opencode", read("opencode", "opencode_dir", REDACT), [], 60000),
        ("merge_ledger", ["python3", CLI, "merge", "--out-dir", "$out_dir"],
         ["read_claude", "read_codex", "read_pi", "read_opencode"], 60000),
        ("summarize", ["python3", CLI, "summary", "--out-dir", "$out_dir"], ["merge_ledger"], 30000),
    ],
    "comped": [
        ("read_claude", read("claude-code", "claude_dir", SUBAGENTS + REDACT), [], 120000),
        ("read_codex", read("codex", "codex_dir", REDACT), [], 120000),
        ("read_pi", read("pi", "pi_dir", REDACT), [], 60000),
        ("read_opencode", read("opencode", "opencode_dir", REDACT), [], 60000),
        ("merge_ledger", ["python3", CLI, "merge", "--out-dir", "$out_dir"],
         ["read_claude", "read_codex", "read_pi", "read_opencode"], 60000),
        ("price_ledger", ["python3", CLI, "price", "--out-dir", "$out_dir", "--plan", "$plan",
                          "--rates-path", "$rates_path", "--days-back", "$days_back"], ["merge_ledger"], 60000),
        ("find_repeats", ["python3", CLI, "repeats", "--out-dir", "$out_dir",
                          "--repeat-threshold", "$repeat_threshold", "--handle", "$handle"], ["price_ledger"], 60000),
        ("render_card", ["python3", CLI, "card", "--out-dir", "$out_dir", "--card-theme", "$card_theme"],
         ["find_repeats"], 60000),
        ("post_score", ["python3", POST, "--out-dir", "$out_dir", "--leaderboard", "$leaderboard", "--handle", "$handle"],
         ["render_card"], 30000),
    ],
    "wrong-turns": [
        ("read_claude", read("claude-code", "claude_dir", SUBAGENTS + ["--redact", "true"]), [], 120000),
        ("read_codex", read("codex", "codex_dir", ["--redact", "true"]), [], 120000),
        ("merge_ledger", ["python3", CLI, "merge", "--out-dir", "$out_dir"], ["read_claude", "read_codex"], 60000),
        ("classify_turns", ["python3", CLI, "wrongturns", "--out-dir", "$out_dir",
                            "--min-recurrence", "$min_recurrence", "--show-snippets", "$show_snippets"],
         ["merge_ledger"], 60000),
        ("draft_rules", ["python3", CLI, "rules", "--out-dir", "$out_dir", "--rules-target", "$rules_target"],
         ["classify_turns"], 30000),
    ],
}

TAGS = {
    "session-ledger": ["domain-agent-operations", "job-session-ledger", "job-token-accounting", "audience-developers",
                       "effect-read-only", "tool-claude-code", "tool-codex"],
    "comped": ["domain-agent-operations", "job-agent-cost-review", "job-repeat-ask-detection", "audience-developers",
               "effect-read-only", "tool-claude-code", "tool-codex"],
    "wrong-turns": ["domain-agent-operations", "job-mistake-review", "job-rule-drafting", "audience-developers",
                    "effect-read-only", "tool-claude-code", "tool-codex"],
}

OUTPUT_SCHEMA = {
    "session-ledger": ["records", "humans", "tools", "sources"],
    "comped": ["total_usd", "multiplier", "per_model", "repeats", "written", "leaderboard"],
    "wrong-turns": ["classes", "written"],
}


# The presentation plane: deprivileged, reads recorded step observations only. Each Play's last
# step already prints its human-readable block followed by one JSON line, so the body splits that
# stdout rather than re-deriving anything.
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

/** A harness whose log directory is absent warns and exits 0. Surface those, once, by name. */
function absencesOf(entries: Array<{{ label: string; step: ReturnType<typeof ctx.step> }}>): string[] {{
  const notes: string[] = [];
  for (const {{ label, step }} of entries) {{
    const o = step.outcome;
    if (o.status !== "completed" && o.status !== "restored") {{ notes.push(`${{label}}: not run`); continue; }}
    const body = o.output.body;
    if (!isProcessExecBody(body)) continue;
    const parsed = split(body.stdout?.text ?? "").json as {{ warning?: string }};
    if (typeof parsed.warning === "string") notes.push(`${{label}}: ${{parsed.warning}}`);
  }}
  return notes;
}}

if (ctx.run.status === "failed") {{
  out.human("The run failed before it could produce a result; the step evidence is in the runner report above.");
  out.summary("run failed");
  out.result({{ run_id: ctx.run.run_id, ok: false }});
}} else {{
  const final = split(stdoutOf("{last}", ctx.requireAvailable(stepName("{last}"))));
  const notes = absencesOf([
{reads}
  ]);
{render}
}}
"""

RENDER = {'session-ledger': '  const j = final.json as Record<string, any>;\n  out.human([`LEDGER`, final.human, notes.length ? `\\nNot read: ${notes.join("; ")}` : ""].join("\\n"));\n  out.summary(`${j.records ?? 0} usage records, ${j.human_typed ?? 0} typed messages, ${j.tools ?? 0} tool calls across ${j.sessions ?? 0} sessions`);\n  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });', 'comped': '  const j = final.json as Record<string, any>;\n  // The poster never fails the run: read whatever it printed, and say nothing if it printed nothing.\n  const post = ctx.step(stepName("post_score")).outcome;\n  const r = ((post.status === "completed" || post.status === "restored") && isProcessExecBody(post.output.body)\n    ? split(post.output.body.stdout?.text ?? "").json : {}) as Record<string, any>;\n  const board = r.posted === true && r.rank ? `Leaderboard: #${r.rank} of ${r.of} \u00b7 ${r.url}`\n    : r.posted === true ? `Leaderboard: posted${r.reason ? ` (${r.reason})` : ""} \u00b7 ${r.url ?? "https://gotcomped.com/leaderboard.html"}`\n    : r.skipped === true ? "Leaderboard: skipped (leaderboard=false)"\n    : typeof r.warning === "string" ? `Leaderboard: not posted (${r.warning})` : "";\n  out.human([final.human, board, notes.length ? `Not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\\n"));\n  const mult = j.multiplier === null || j.multiplier === undefined ? "list price only" : `${Number(j.multiplier).toFixed(1)}x vs ${j.plan}${j.plan_source === "auto" ? " (inferred)" : ""}`;\n  out.summary(`$${Number(j.total_usd ?? 0).toFixed(2)} comped over ${ctx.params.days_back} days, ${mult}, ${j.repeats ?? 0} repeat offenders${j.detected ? ` \u00b7 ${j.detected}` : ""}${r.rank ? ` \u00b7 #${r.rank} of ${r.of} on the leaderboard` : ""}`);\n  out.result({ run_id: ctx.run.run_id, ...j, leaderboard: r, absences: notes });', 'wrong-turns': '  const j = final.json as Record<string, any>;\n  out.human([final.human, notes.length ? `Not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\\n"));\n  out.summary(`${j.classes ?? 0} recurring mistake classes; drafted rules written, nothing applied`);\n  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });'}
LAST = {'session-ledger': 'summarize', 'comped': 'render_card', 'wrong-turns': 'draft_rules'}
READS = {'session-ledger': '    { label: "read_claude", step: ctx.step(stepName("read_claude")) },\n    { label: "read_codex", step: ctx.step(stepName("read_codex")) },\n    { label: "read_pi", step: ctx.step(stepName("read_pi")) },\n    { label: "read_opencode", step: ctx.step(stepName("read_opencode")) },', 'comped': '    { label: "read_claude", step: ctx.step(stepName("read_claude")) },\n    { label: "read_codex", step: ctx.step(stepName("read_codex")) },\n    { label: "read_pi", step: ctx.step(stepName("read_pi")) },\n    { label: "read_opencode", step: ctx.step(stepName("read_opencode")) },', 'wrong-turns': '    { label: "read_claude", step: ctx.step(stepName("read_claude")) },\n    { label: "read_codex", step: ctx.step(stepName("read_codex")) },'}

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


def yaml_scalar(v):
    """Single-quoted YAML scalar, the form the registry archives use for descriptions and defaults."""
    return "'{0}'".format(str(v).replace("'", "''"))


def frontmatter(slug: str, desc: str, params: list) -> str:
    L = ["name: {0}".format(slug), "description: {0}".format(yaml_scalar(desc)),
         "version: {0}".format(yaml_scalar(VERSION)),
         "source_url: https://play.modiqo.ai/{0}/{1}".format(HANDLE, slug),
         "metadata:",
         "  version: {0}".format(yaml_scalar(VERSION)),
         "  rote_version: {0}".format(yaml_scalar(ROTE_VERSION)),
         "  status: released", "  kind: atomic",
         "  flow_type: parallel",
         "  execution_model: steps_with_presentation",
         "  requires_endpoints: []",
         "  requires_sessions: false",
         "  license: MIT",
         "  discoverability:", "    tags:"]
    L += ["    - {0}".format(t) for t in TAGS[slug]]
    # The quality rubric reads top-level `tags` and `discoverability` as well as the copies under
    # metadata; the live registry archives carry all three, so carry all three.
    L += ["tags:"] + ["- {0}".format(t) for t in TAGS[slug]]
    L += ["discoverability:", "  tags:"] + ["  - {0}".format(t) for t in TAGS[slug]]
    L += ["output:", "  schema:", "    type: object", "    properties:"]
    L += ["      {0}:\n        type: object".format(k) if k in ("per_model", "repeats", "written", "classes", "sources", "leaderboard")
          else "      {0}:\n        type: string".format(k) for k in OUTPUT_SCHEMA[slug]]
    fx = ROOT / "docs" / "plays" / slug / "PRESENTATION_FIXTURES.json"
    if fx.is_file():
        # Representative completed observations, captured from a real run by tools/build_fixtures.py.
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
    for name, argv, deps, timeout in STEPS[slug]:
        L += ["  {0}:".format(name), "    type: process.exec", "    timeout_ms: {0}".format(timeout)]
        if deps:
            L += ["    depends_on:"] + ["    - {0}".format(d) for d in deps]
        L += ["    argv:"] + ["    - {0}".format(yaml_scalar(a)) for a in argv]
    return "\n".join(L)


def main():
    for slug in ("session-ledger", "comped", "wrong-turns"):
        d = ROOT / "plays" / slug
        src = ROOT / "docs" / "plays" / slug
        desc = (src / "DESCRIPTION.md").read_text(encoding="utf-8").strip()
        params = json.loads((src / "PARAMETERS.json").read_text(encoding="utf-8"))
        fm = frontmatter(slug, desc, params)
        body = "\n".join(" * " + line if line else " *" for line in fm.splitlines())
        program = BODY.format(last=LAST[slug], reads=READS[slug], render=RENDER[slug])
        (d / "main.ts").write_text(
            "#!/usr/bin/env -S rote play run\n/**\n * @rote-frontmatter\n * ---\n"
            + body + "\n * ---\n */\n" + program, encoding="utf-8")
        (d / "deps.toml").write_text(DEPS, encoding="utf-8")
        print("{0}: main.ts + deps.toml, {1} steps".format(slug, len(STEPS[slug])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
