#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: app-graveyard
 * description: 'macOS records the last time you opened every application and never shows you the list. This asks Spotlight for those dates, measures each bundle on disk, and turns "what can I delete" into a list with evidence on every row.
 *
 * It also answers a question nobody thinks to ask. Sixteen bytes into an application''s executable is the list of architectures it ships, and on an Apple silicon machine an app with no arm64 slice runs under translation every single time you open it. Reading that needs no tools and runs no code: the header is just read. Apps still shipping Intel-only are listed with their sizes.
 *
 * The report gives the applications unopened past your threshold, sorted by what they cost you in disk, the ones with no recorded opening at all, the total that would come back, anything installed twice under the same bundle identifier, and your Homebrew casks including superseded versions still on disk and casks whose application is no longer anywhere.
 *
 * Every date says where it came from. Spotlight answers for most applications; where it has no record the file access time is used instead and the row is labelled as such, because the two are not the same measurement and mixing them silently would make the whole list untrustworthy. A bundle too large to walk inside the per-app file cap has its size reported as a lower bound and is counted.
 *
 * - Reads: only the locations listed above. Nothing else on your disk is opened.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/app-graveyard
 * metadata:
 *   version: '0.1.0'
 *   rote_version: '0.79.0'
 *   status: released
 *   kind: atomic
 *   flow_type: parallel
 *   execution_model: steps_with_presentation
 *   requires_endpoints: []
 *   requires_sessions: false
 *   license: MIT
 *   discoverability:
 *     tags:
 *     - domain-personal-computing
 *     - job-disk-reclaim
 *     - job-application-audit
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-spotlight
 *     - tool-homebrew
 * tags:
 * - domain-personal-computing
 * - job-disk-reclaim
 * - job-application-audit
 * - audience-everyone
 * - effect-read-only
 * - tool-spotlight
 * - tool-homebrew
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-disk-reclaim
 *   - job-application-audit
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-spotlight
 *   - tool-homebrew
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       apps:
 *         type: integer
 *       bytes:
 *         type: integer
 *       unused:
 *         type: integer
 *       never_used:
 *         type: integer
 *       reclaimable:
 *         type: integer
 *       intel_only:
 *         type: integer
 *       casks:
 *         type: integer
 * presentation_fixtures:
 *   read_applications: resources/presentation-fixtures/read_applications/fixture.yaml
 *   read_casks: resources/presentation-fixtures/read_casks/fixture.yaml
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
 *   description: 'true runs against a bundled synthetic set of applications and casks.'
 *   example: 'false'
 * - name: unused_days
 *   param_type: integer
 *   required: false
 *   default: '180'
 *   description: 'An application unopened for this many days is counted as unused.'
 *   example: '180'
 * - name: app_dirs
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Comma-separated override. Empty means /Applications, ~/Applications and /Applications/Utilities.'
 *   example: ''
 * steps:
 *   read_applications:
 *     type: process.exec
 *     timeout_ms: 180000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'apps-read'
 *     - '--source'
 *     - 'applications'
 *     - '--app-dirs'
 *     - '$app_dirs'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_casks:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'apps-read'
 *     - '--source'
 *     - 'casks'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - read_applications
 *     - read_casks
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'apps-report'
 *     - '--unused-days'
 *     - '$unused_days'
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
    { label: "read_applications", step: ctx.step(stepName("read_applications")) },
    { label: "read_casks", step: ctx.step(stepName("read_casks")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${(j.unused ?? 0) + (j.never_used ?? 0)} of ${j.apps ?? 0} applications unopened, ${Math.round((j.reclaimable ?? 0) / 1e8) / 10} GB reclaimable${j.intel_only ? `, ${j.intel_only} still Intel-only` : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
