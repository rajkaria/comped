#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: upstream-pulse
 * description: 'A vulnerability scanner tells you about the bugs somebody has already found and written down. This tells you about the packages where nobody is looking for them any more: the last release was three years ago, there is exactly one human who can publish, the repository is archived, and the thing sits in the code path that answers requests. None of that is a CVE. All of it is the shape of the next one.
 *
 * The Play is two programs on purpose, and the seam between them is a file. The local half parses every lockfile under a root you choose — npm, pip, poetry, uv, Cargo, Go — and builds the inventory and the dependency graph from files already on your disk, running no package manager and opening no network. The other half is one step that asks the public registries about the packages that inventory names, and writes their answers into `out_dir` as JSON. That step is the only part of this package that opens a connection and it is one short file you can read before you run it. `daily_core`, which does every judgement, imports no networking module at all and only ever reads that file.
 *
 * What goes out is a package name and its ecosystem, to that ecosystem''s own public registry, one request each. These registries take no key and are given none. Your versions, your paths, your lockfiles, your repository names and anything else about this machine stay here. Answers are cached under `out_dir` and reused for as long as you allow, and the card prints how old they are.
 *
 * Every checked package gets a dormancy grade A–F with every single input printed beside it, each with its own points and its own maximum — last release, release cadence, publishers, deprecation, repository state, licence, version drift. A reader who thinks a single publisher matters more than two years of silence can see both numbers, disagree with the weighting and redo the arithmetic. A bare score is an assertion; a score with its inputs is an argument. A package that was not looked up is reported as "not checked", never as healthy, because "we did not ask" must never read as "it is fine".
 *
 * - Reads: lockfiles and the manifests beside them under `root`, and the registry answers written into `out_dir`. Nothing else on your disk is opened, and no package manager, installer or build tool is run.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account, has no login step, and the registries it queries need no key. Private registry configuration is neither read nor used.
 * - Never sends: your versions, your lockfiles, your paths, your repository names or anything identifying this machine. One public GET per package name is the whole of it. `daily_core`, which makes every judgement, imports no `urllib`, `http`, `socket` or `ssl` at all, and a test in the repository asserts that on every commit.
 * - Writes: only inside `out_dir`, which is created if missing — the registry answers, their cache, the report, and a baseline so the next run can say what moved. Every written path is listed in the run output. Nothing under `root` is modified.
 * - Degrades, never fails: a machine with no network, a registry that refuses, a lockfile format that cannot be parsed and a package the registry does not know are each reported by name with the reason, and the run still completes. The inventory is reported in full either way, with the unchecked packages counted and named.
 * - Runs cold: set `demo=true` to run the whole Play against five bundled synthetic project trees and a bundled answer set. In that mode the registry step opens no connection at all, so a first run needs no network.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/upstream-pulse
 * metadata:
 *   version: '0.1.0'
 *   rote_version: '0.79.0'
 *   status: released
 *   kind: atomic
 *   flow_type: sequential
 *   execution_model: steps_with_presentation
 *   requires_endpoints: []
 *   requires_sessions: false
 *   license: MIT
 *   discoverability:
 *     tags:
 *     - domain-software-engineering
 *     - job-dependency-audit
 *     - job-supply-chain-review
 *     - audience-engineering-teams
 *     - effect-read-only
 *     - tool-npm
 *     - tool-pypi
 *     - tool-crates
 * tags:
 * - domain-software-engineering
 * - job-dependency-audit
 * - job-supply-chain-review
 * - audience-engineering-teams
 * - effect-read-only
 * - tool-npm
 * - tool-pypi
 * - tool-crates
 * discoverability:
 *   tags:
 *   - domain-software-engineering
 *   - job-dependency-audit
 *   - job-supply-chain-review
 *   - audience-engineering-teams
 *   - effect-read-only
 *   - tool-npm
 *   - tool-pypi
 *   - tool-crates
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       packages:
 *         type: integer
 *       direct:
 *         type: integer
 *       lockfiles:
 *         type: integer
 *       checked:
 *         type: integer
 *       unchecked:
 *         type: integer
 *       offline:
 *         type: boolean
 *       dormant:
 *         type: integer
 *       single_maintainer:
 *         type: integer
 *       deprecated:
 *         type: integer
 *       headline:
 *         type: integer
 * presentation_fixtures:
 *   fetch_registry: resources/presentation-fixtures/fetch_registry/fixture.yaml
 *   read_lockfiles: resources/presentation-fixtures/read_lockfiles/fixture.yaml
 *   read_registry: resources/presentation-fixtures/read_registry/fixture.yaml
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: out_dir
 *   param_type: string
 *   required: false
 *   default: '~/daily'
 *   description: 'Created if missing. Everything this Play writes goes here and nowhere else.'
 *   example: '~/daily'
 * - name: demo
 *   param_type: string
 *   required: false
 *   default: 'false'
 *   description: 'true runs the whole Play against five bundled synthetic project trees and a bundled registry answer set, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '~'
 *   description: 'Every lockfile under this folder is parsed. Nothing outside it is opened, and no package manager is run.'
 *   example: '~/Projects'
 * - name: max_packages
 *   param_type: integer
 *   required: false
 *   default: '120'
 *   description: 'The most packages to ask the registries about, direct dependencies first. Everything else is inventoried and reported as not checked, which is not the same as healthy.'
 *   example: '120'
 * - name: cache_hours
 *   param_type: integer
 *   required: false
 *   default: '24'
 *   description: 'How long a registry answer under out_dir may be reused before it is asked for again. The card prints how old the answers are.'
 *   example: '24'
 * - name: dormant_days
 *   param_type: integer
 *   required: false
 *   default: '730'
 *   description: 'A package with no release in this many days is called dormant. Two years is long enough that a maintained package would have shipped something.'
 *   example: '730'
 * steps:
 *   read_lockfiles:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'upstream-read'
 *     - '--source'
 *     - 'lockfiles'
 *     - '--root'
 *     - '$root'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   fetch_registry:
 *     type: process.exec
 *     timeout_ms: 420000
 *     depends_on:
 *     - read_lockfiles
 *     argv:
 *     - 'python3'
 *     - '@resource{fetch/registry_partial.py}'
 *     - '--max-packages'
 *     - '$max_packages'
 *     - '--cache-hours'
 *     - '$cache_hours'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_registry:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - fetch_registry
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'upstream-read'
 *     - '--source'
 *     - 'registry'
 *     - '--root'
 *     - '$root'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - read_lockfiles
 *     - read_registry
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'upstream-report'
 *     - '--root'
 *     - '$root'
 *     - '--dormant-days'
 *     - '$dormant_days'
 *     - '--cache-hours'
 *     - '$cache_hours'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 * ---
 */

// Presentation plane: deprivileged; imports ONLY the presentation SDK; owns no effects.
const { FlowOutput, isProcessExecBody, loadPresentationContext, stepName } =
  await import("__ROTE_PRESENTATION_SDK__");

const out = new FlowOutput();
const ctx = await loadPresentationContext();

/** Read one process.exec step's stdout, refusing anything that is not a clean, complete capture. */
function stdoutOf(label: string, step: { body: unknown }): string {
  if (!isProcessExecBody(step.body)) throw new Error(`${label} did not record a process.exec observation`);
  const exit = step.body.status.exit;
  if (exit.kind !== "code" || exit.code !== 0) {
    throw new Error(`${label} failed: ${step.body.stderr?.text ?? "no stderr captured"}`);
  }
  const s = step.body.stdout;
  // Truncation is the cause, an unparseable tail only its symptom: check it before parsing.
  if (s?.truncated === true) throw new Error(`${label} stdout was truncated at ${s.bytes ?? "?"} bytes`);
  if (s?.text === undefined) throw new Error(`${label} captured no stdout`);
  return s.text;
}

/** Every step prints one JSON object as its last line; everything above it is for a human. */
function split(text: string): { human: string; json: Record<string, unknown> } {
  const lines = text.split("\n");
  let i = lines.length - 1;
  while (i >= 0 && lines[i].trim() === "") i--;
  try {
    return { human: lines.slice(0, i).join("\n").trimEnd(), json: JSON.parse(lines[i]) };
  } catch {
    return { human: text.trimEnd(), json: {} };
  }
}

/** A source this machine does not have warns and exits 0. Surface those, once, by name. */
function absencesOf(entries: Array<{ label: string; step: ReturnType<typeof ctx.step> }>): string[] {
  const notes: string[] = [];
  for (const { label, step } of entries) {
    const o = step.outcome;
    if (o.status !== "completed" && o.status !== "restored") { notes.push(`${label}: not run`); continue; }
    if (!isProcessExecBody(o.output.body)) continue;
    const parsed = split(o.output.body.stdout?.text ?? "").json as { warning?: string };
    if (typeof parsed.warning === "string") notes.push(`${label}: ${parsed.warning}`);
  }
  return notes;
}

if (ctx.run.status === "failed") {
  out.human("The run failed before it could produce a result; the step evidence is in the runner report above.");
  out.summary("run failed");
  out.result({ run_id: ctx.run.run_id, ok: false });
} else {
  const final = split(stdoutOf("report", ctx.requireAvailable(stepName("report"))));
  const j = final.json as Record<string, any>;
  const notes = absencesOf([
    { label: "read_lockfiles", step: ctx.step(stepName("read_lockfiles")) },
    { label: "fetch_registry", step: ctx.step(stepName("fetch_registry")) },
    { label: "read_registry", step: ctx.step(stepName("read_registry")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.packages ?? 0} packages, ${j.checked ?? 0} checked, ${j.dormant ?? 0} dormant and ${j.single_maintainer ?? 0} with one publisher; ${j.headline ?? 0} are both and in the production path`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
