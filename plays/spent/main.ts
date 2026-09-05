#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: spent
 * description: '`entry=''320 lunch #food''`. That is the interaction. Three or four of those a day and you have a spend log that owes nothing to a bank, an app, a login or an export.
 *
 * It reads an amount with or without a currency symbol, a label, and an optional #tag, and it keeps money in decimal arithmetic from end to end — never a float, because a float is how a total quietly becomes 4907.999999999999. The report gives you today, this month, the top categories with their share, the daily average, and — if you set a budget — where the month lands at the current rate.
 *
 * Currencies are totalled apart and never converted. A made-up exchange rate would make one clean number out of two honest ones, so a month with rupees and dollars in it reports both.
 *
 * - Reads: only its own log, at `state_dir/spent.jsonl`. It does not read your bank, your mail, your receipts or your files.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step, and it could not connect to a bank if it wanted to.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
 * - Writes: one appended line to `~/.rote-micro/spent.jsonl` (or wherever you point `state_dir`), and nothing else, ever. Appends only: nothing is deleted, truncated or rewritten in place.
 * - An entry it cannot read an amount out of is refused with a message that says how to write it, and the run still exits cleanly.
 * - Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log is not opened.
 *
 * See also: `receipt-ledger`, which totals the receipt files already on your disk — a different axis on the same question. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/spent
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
 *     - domain-personal-finance
 *     - job-spend-tracking
 *     - job-budget-check
 *     - audience-everyone
 *     - effect-local-write
 *     - tool-jsonl
 * tags:
 * - domain-personal-finance
 * - job-spend-tracking
 * - job-budget-check
 * - audience-everyone
 * - effect-local-write
 * - tool-jsonl
 * discoverability:
 *   tags:
 *   - domain-personal-finance
 *   - job-spend-tracking
 *   - job-budget-check
 *   - audience-everyone
 *   - effect-local-write
 *   - tool-jsonl
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       currency:
 *         type: string
 *       today:
 *         type: integer
 *       month:
 *         type: string
 *       avg_per_day:
 *         type: string
 *       projection:
 *         type: string
 *       budget:
 *         type: string
 *       over:
 *         type: boolean
 *       by_tag:
 *         type: object
 *       currencies:
 *         type: object
 * presentation_fixtures:
 *   record: resources/presentation-fixtures/record/fixture.yaml
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: entry
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Amount first, then what it was for, and an optional #tag. A leading symbol sets the currency. Leave it empty to read the month back without adding to it.'
 *   example: '320 lunch #food'
 * - name: currency
 *   param_type: string
 *   required: false
 *   default: 'USD'
 *   description: 'Used when the entry carries no symbol. Currencies are totalled apart, never converted, because a made-up exchange rate is worse than two honest numbers.'
 *   example: 'INR'
 * - name: budget
 *   param_type: string
 *   required: false
 *   default: '0'
 *   description: 'Optional. When set, the report projects the month at the current rate and says whether that lands over.'
 *   example: '6000'
 * - name: state_dir
 *   param_type: string
 *   required: false
 *   default: '~/.rote-micro'
 *   description: 'The one directory this Play writes to. One append-only JSONL file per stream; nothing is ever deleted or rewritten in place.'
 *   example: '~/.rote-micro'
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
 *     - 'spent'
 *     - 'record'
 *     - '--entry'
 *     - '$entry'
 *     - '--currency'
 *     - '$currency'
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
 *     - 'spent'
 *     - 'report'
 *     - '--state-dir'
 *     - '$state_dir'
 *     - '--budget'
 *     - '$budget'
 *     - '--currency'
 *     - '$currency'
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
  out.summary(`${j.month ?? 0} ${j.currency ?? ""} this month${j.over ? ", on pace to go over" : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
