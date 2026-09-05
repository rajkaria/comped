#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: punch
 * description: 'Type one line saying what you are doing. That is the whole interaction, and it takes two seconds. Do it five or ten times a day and the Play starts answering a question your calendar cannot: not where the time went, but how many times the day was broken.
 *
 * A punch whose topic differs from the one before it is a context switch. The report gives you today''s punches with their times, how many switches there were, how long the block you are currently in has run, the longest block you managed today, a sparkline of the last fortnight, and the streak of days you have kept it up. Pass `tag=api` and the tag is the topic, so "fixing the parser" and "back on the API" count as the same thread rather than as a switch.
 *
 * The number worth sharing here is the switch count, and low is good — which makes it a stranger leaderboard than most, and a more honest one. Nothing here judges you for the number; it just tells you what it was, from what you typed.
 *
 * - Reads: only its own log, at `state_dir/punch.jsonl`. It does not read your calendar, your editor, your shell history or your machine.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. Nothing you type here leaves the machine.
 * - Writes: one appended line to `~/.rote-micro/punch.jsonl` (or wherever you point `state_dir`), and nothing else, ever. Appends only: nothing is deleted, truncated or rewritten in place, so the log is always something you can read yourself.
 * - A corrupt or half-written line costs itself and nothing else; the rest of the log still reports.
 * - Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log is not opened.
 *
 * See also: `jot` for capturing a thought rather than a state, `streak` for the days rather than the hours, and `since-last`, which answers the same "what just happened" question about files. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.1'
 * source_url: https://play.modiqo.ai/rajkaria/punch
 * metadata:
 *   version: '0.1.1'
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
 *     - domain-personal-productivity
 *     - job-time-tracking
 *     - job-context-switch-audit
 *     - audience-everyone
 *     - effect-local-write
 *     - tool-jsonl
 * tags:
 * - domain-personal-productivity
 * - job-time-tracking
 * - job-context-switch-audit
 * - audience-everyone
 * - effect-local-write
 * - tool-jsonl
 * discoverability:
 *   tags:
 *   - domain-personal-productivity
 *   - job-time-tracking
 *   - job-context-switch-audit
 *   - audience-everyone
 *   - effect-local-write
 *   - tool-jsonl
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       punches:
 *         type: integer
 *       switches:
 *         type: integer
 *       current_block_min:
 *         type: integer
 *       longest_block_min:
 *         type: integer
 *       streak:
 *         type: integer
 *       longest_streak:
 *         type: integer
 *       shape:
 *         type: string
 *       topics:
 *         type: object
 * presentation_fixtures:
 *   record: resources/presentation-fixtures/record/fixture.yaml
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: note
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'One line, written now. Leave it empty to read the day back without adding to it.'
 *   example: 'back on the API'
 * - name: tag
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Optional. When given it is the topic instead of the note, so two differently worded punches on the same thing are not counted as a switch.'
 *   example: 'api'
 * - name: state_dir
 *   param_type: string
 *   required: false
 *   default: '~/.rote-micro'
 *   description: 'The one directory this Play writes to. One append-only JSONL file per stream; nothing is ever deleted or rewritten in place.'
 *   example: '~/.rote-micro'
 * - name: days_back
 *   param_type: integer
 *   required: false
 *   default: '14'
 *   description: 'How many days the sparkline covers.'
 *   example: '14'
 * - name: tz
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Empty uses the machine''s zone. A day boundary is a place, not a fact: this decides when today starts.'
 *   example: 'Asia/Kolkata'
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
 *   record:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'punch'
 *     - 'record'
 *     - '--note'
 *     - '$note'
 *     - '--tag'
 *     - '$tag'
 *     - '--state-dir'
 *     - '$state_dir'
 *     - '--now'
 *     - '$now'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - record
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'punch'
 *     - 'report'
 *     - '--state-dir'
 *     - '$state_dir'
 *     - '--days-back'
 *     - '$days_back'
 *     - '--tz'
 *     - '$tz'
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
    { label: "record", step: ctx.step(stepName("record")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.switches ?? 0} switch(es) today · longest block ${j.longest_block_min ?? 0} min · ${j.streak ?? 0}-day streak`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
