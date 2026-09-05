#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: cron-when
 * description: 'You have a cron expression and a suspicion. This tells you what it says in English, the next five times it actually fires — in your zone and in UTC, side by side — how often that works out to be, and whether the clocks are going to ruin it.
 *
 * Two things most cron readers get wrong, and this one does not. When both day-of-month and day-of-week are restricted, a day matches if EITHER matches: `0 0 13 * 5` is the thirteenth AND every Friday, not Friday the thirteenth. And a schedule pinned to an hour that a zone skips does not fire that day at all — `30 1 * * *` in Europe/London simply does not happen on the morning the clocks go forward — so that day is not offered as a fire, and the warning says which day and why. The other side of the same coin, an hour that happens twice when the clocks go back, is reported too.
 *
 * Ranges, lists, steps, wrapping ranges like `22-2`, three-letter month and day names, Sunday as both 0 and 7, and the macros `@daily`, `@hourly`, `@weekly`, `@monthly`, `@yearly` and `@midnight` all read the way cron reads them. An expression that is not valid gets a message naming the field that is wrong, and the run still exits cleanly.
 *
 * - Reads: the expression you pass, and the system time-zone database. No files, no directories.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
 * - Writes nothing. No state, no cache, no output file.
 * - Runs cold: set `demo=true` to read a bundled expression with nothing configured.
 *
 * See also: `whatis`, which recognises a cron expression among everything else it recognises. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/cron-when
 * metadata:
 *   version: '0.1.0'
 *   rote_version: '0.80.0'
 *   status: released
 *   kind: atomic
 *   flow_type: sequential
 *   execution_model: steps_with_presentation
 *   requires_endpoints: []
 *   requires_sessions: false
 *   license: MIT
 *   discoverability:
 *     tags:
 *     - domain-developer-tooling
 *     - job-schedule-review
 *     - job-timezone-check
 *     - audience-developers
 *     - effect-read-only
 *     - tool-cron
 * tags:
 * - domain-developer-tooling
 * - job-schedule-review
 * - job-timezone-check
 * - audience-developers
 * - effect-read-only
 * - tool-cron
 * discoverability:
 *   tags:
 *   - domain-developer-tooling
 *   - job-schedule-review
 *   - job-timezone-check
 *   - audience-developers
 *   - effect-read-only
 *   - tool-cron
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       valid:
 *         type: boolean
 *       expr:
 *         type: string
 *       english:
 *         type: string
 *       zone:
 *         type: string
 *       fires:
 *         type: object
 *       average_interval_min:
 *         type: integer
 *       dst_warning:
 *         type: string
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: expr
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Five fields, or a macro like @daily. Ranges, lists, steps and three-letter names all read the way cron reads them.'
 *   example: '30 9 * * 1-5'
 * - name: tz
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Empty uses the machine''s zone. This is the zone whose clock changes decide whether a run is skipped or doubled.'
 *   example: 'Europe/London'
 * - name: count
 *   param_type: integer
 *   required: false
 *   default: '5'
 *   description: 'How many upcoming fires to print, each in your zone and in UTC.'
 *   example: '5'
 * - name: demo
 *   param_type: string
 *   required: false
 *   default: 'false'
 *   description: 'true runs the whole Play against bundled synthetic input, so a first run needs nothing configured and touches nothing of yours.'
 *   example: 'false'
 * - name: now
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Empty reads the real clock. An ISO-8601 instant makes the run reproducible, which is how the tests and the demo produce the same bytes on every machine.'
 *   example: '2026-09-05T14:22:03Z'
 * steps:
 *   report:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'cron'
 *     - 'report'
 *     - '--expr'
 *     - '$expr'
 *     - '--tz'
 *     - '$tz'
 *     - '--count'
 *     - '$count'
 *     - '--now'
 *     - '$now'
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

  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.valid === false ? `not a cron expression: ${j.error}` : `${j.english} — next ${(j.fires ?? [{}])[0]?.local ?? "never"}${j.dst_warning ? " ⚠ clock change" : ""}`}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
