#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: streak
 * description: '`did=water`. One word, several times a day, and the Play keeps the only part of habit tracking that ever changes anyone''s behaviour: how long the run is, and which day you keep dropping it.
 *
 * Each habit gets its current streak, its longest ever, a grid of the last twenty-one days, and — once there is enough history to say it honestly — the weekday you miss most often. Marking the same habit twice in one day is one day; the log keeps both marks, the streak counts the day.
 *
 * Today not being marked yet does not end your streak. The day is not over, and a tracker that resets at midnight punishes you for checking it in the morning.
 *
 * - Reads: only its own log, at `state_dir/streak.jsonl`. Nothing else on the machine.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
 * - Writes: one appended line to `~/.rote-micro/streak.jsonl` (or wherever you point `state_dir`), and nothing else, ever. Appends only: nothing is deleted, truncated or rewritten in place.
 * - The missed-weekday reading is withheld until there are at least fourteen days of history and one weekday is clearly worse than the others, because a pattern read from four days is not a pattern.
 * - Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log is not opened.
 *
 * See also: `punch` for the hours inside a day, and `jot` for the thoughts. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.1'
 * source_url: https://play.modiqo.ai/rajkaria/streak
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
 *     - job-habit-tracking
 *     - job-streak-review
 *     - audience-everyone
 *     - effect-local-write
 *     - tool-jsonl
 * tags:
 * - domain-personal-productivity
 * - job-habit-tracking
 * - job-streak-review
 * - audience-everyone
 * - effect-local-write
 * - tool-jsonl
 * discoverability:
 *   tags:
 *   - domain-personal-productivity
 *   - job-habit-tracking
 *   - job-streak-review
 *   - audience-everyone
 *   - effect-local-write
 *   - tool-jsonl
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       habits:
 *         type: object
 *       best:
 *         type: string
 *       window:
 *         type: integer
 * presentation_fixtures:
 *   record: resources/presentation-fixtures/record/fixture.yaml
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: did
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'The habit you are marking, one word. Leave it empty to read the streaks back without marking anything.'
 *   example: 'water'
 * - name: state_dir
 *   param_type: string
 *   required: false
 *   default: '~/.rote-micro'
 *   description: 'The one directory this Play writes to. One append-only JSONL file per stream; nothing is ever deleted or rewritten in place.'
 *   example: '~/.rote-micro'
 * - name: window
 *   param_type: integer
 *   required: false
 *   default: '21'
 *   description: 'How many days the grid shows, and the window the missed-weekday reading is taken over.'
 *   example: '21'
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
 *     - 'streak'
 *     - 'record'
 *     - '--did'
 *     - '$did'
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
 *     - 'streak'
 *     - 'report'
 *     - '--state-dir'
 *     - '$state_dir'
 *     - '--window'
 *     - '$window'
 *     - '--did'
 *     - '$did'
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
  out.summary(`${j.best ?? "nothing"}: ${(j.habits ?? [{}])[0]?.current ?? 0}-day streak, longest ${(j.habits ?? [{}])[0]?.longest ?? 0}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
