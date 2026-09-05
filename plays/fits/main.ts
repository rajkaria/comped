#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: fits
 * description: 'Before you paste forty kilobytes into an agent: will it fit, and what will it cost. Point it at text or at a file and it answers both, plus the things nobody bothers to count — bytes, lines, words, and what the text actually looks like.
 *
 * The bytes, lines and words are facts. The token count is not, and this Play refuses to pretend otherwise. The standard library has no tokenizer, so the count comes from a stated character-class model — ASCII prose at roughly four characters per token, punctuation-dense code nearer three, CJK at about one token per character — and it is printed as a RANGE with a band of ±15%, widened to ±25% when the text is mostly non-ASCII. The method travels in the same output as the number, so nobody has to guess how much to trust it. A single confident figure would have been easier to read and worse to rely on.
 *
 * The money is real, though: the cost comes from the same maintained price table the `comped` Play prices a month with, so the rates are the ones actually charged, and a model the table does not know is named in the output instead of being priced at zero.
 *
 * - Reads: the text you pass, or the file or folder at `path` (up to 200 files, 2 MB each). Nothing else.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. The price table is a JSON file bundled inside the Play; nothing is fetched at run time.
 * - Writes nothing. No state, no cache, no output file.
 * - Runs cold: set `demo=true` to measure a bundled 40 KB document with nothing configured.
 *
 * See also: `last-turn`, which prices the turn that actually happened, and `budget-left`, which tells you what today has left in it. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.1'
 * source_url: https://play.modiqo.ai/rajkaria/fits
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
 *     - domain-agent-operations
 *     - job-context-sizing
 *     - job-cost-estimation
 *     - audience-developers
 *     - effect-read-only
 *     - tool-claude-code
 *     - tool-codex
 * tags:
 * - domain-agent-operations
 * - job-context-sizing
 * - job-cost-estimation
 * - audience-developers
 * - effect-read-only
 * - tool-claude-code
 * - tool-codex
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-context-sizing
 *   - job-cost-estimation
 *   - audience-developers
 *   - effect-read-only
 *   - tool-claude-code
 *   - tool-codex
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       bytes:
 *         type: integer
 *       chars:
 *         type: integer
 *       lines:
 *         type: integer
 *       words:
 *         type: integer
 *       tokens_low:
 *         type: integer
 *       tokens_mid:
 *         type: integer
 *       tokens_high:
 *         type: integer
 *       fits:
 *         type: boolean
 *       pct:
 *         type: integer
 *       window:
 *         type: integer
 *       costs:
 *         type: object
 *       method:
 *         type: string
 *       source:
 *         type: string
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: text
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'The text to measure. Leave it empty and set path instead to measure a file or a folder.'
 *   example: 'the text you are about to paste'
 * - name: path
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Measured instead of text. A folder is read up to 200 files deep and totalled.'
 *   example: './src/main.py'
 * - name: window
 *   param_type: integer
 *   required: false
 *   default: '200000'
 *   description: 'The window you are aiming at, in tokens. The percentage and the headroom are measured against this.'
 *   example: '200000'
 * - name: models
 *   param_type: string
 *   required: false
 *   default: 'claude-opus-5,claude-sonnet-5,claude-haiku-4-5'
 *   description: 'Comma-separated. A model the price table does not know is named in the output rather than priced at zero.'
 *   example: 'claude-opus-5,claude-sonnet-5'
 * - name: rates_path
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Empty uses the price table bundled with the Play. Point it at your own JSON to price with different rates.'
 *   example: '~/prices.json'
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
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'fits'
 *     - 'report'
 *     - '--text'
 *     - '$text'
 *     - '--path'
 *     - '$path'
 *     - '--window'
 *     - '$window'
 *     - '--models'
 *     - '$models'
 *     - '--rates-path'
 *     - '$rates_path'
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
  out.summary(`${j.tokens_low ?? 0}–${j.tokens_high ?? 0} tokens, ${j.pct ?? 0}% of the window${j.fits === false ? " — does not fit" : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
