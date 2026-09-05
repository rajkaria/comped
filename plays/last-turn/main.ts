#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: last-turn
 * description: 'The turn just finished. What did it cost? Not this month, not this project — that one turn, ninety seconds ago. Model, tokens in, tokens out, how much of the input was cache, the dollars, and today''s running total underneath it.
 *
 * The reason this can run twenty times a day is that it does not read your history. It finds the most recently modified transcript under the directories you configure and reads the last 256 KB of it — a tail, not an accounting, and the output says exactly that so nobody mistakes a partial number for a total. `comped` is the Play that reads everything and prices a month; this is the one you can afford to run between turns.
 *
 * It reads Claude Code and Codex transcripts. Codex reports running totals rather than per-turn ones, so the turn is the difference between consecutive records, and a total that went down is treated as a new session rather than as a negative turn. Codex also names the model once at the top of the session, so when the file is long enough that the model would fall outside the tail, the head is read for that one fact. A record in a format this does not know is skipped and counted, and the count is in the output, so an unread format shows up as a number rather than as a silent zero.
 *
 * Prices come from the same maintained table `comped` uses. A model the table does not know is reported by name with its tokens and no dollar figure, because no number is better than a wrong one.
 *
 * - Reads: `*.jsonl` transcripts under `claude_dir` and `codex_dir`, tails only, up to three directories deep. Two directories that turn out to be the same directory are read once, not twice.
 * - Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Which model you ran is taken from the model ids already in the transcript; your plan and your account are never consulted.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. Your transcripts are read, priced and printed on this machine.
 * - Writes nothing. No state, no cache, no output file.
 * - No message text is read or printed. Only the usage blocks, the model ids and the timestamps are touched.
 * - Runs cold: set `demo=true` to read bundled synthetic transcripts with nothing configured.
 *
 * See also: `budget-left` for what today has left in it, `comped` for the month and the multiplier, and `session-ledger` for the normalized ledger underneath both. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/last-turn
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
 *     - domain-agent-operations
 *     - job-token-accounting
 *     - job-agent-cost-review
 *     - audience-developers
 *     - effect-read-only
 *     - tool-claude-code
 *     - tool-codex
 * tags:
 * - domain-agent-operations
 * - job-token-accounting
 * - job-agent-cost-review
 * - audience-developers
 * - effect-read-only
 * - tool-claude-code
 * - tool-codex
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-token-accounting
 *   - job-agent-cost-review
 *   - audience-developers
 *   - effect-read-only
 *   - tool-claude-code
 *   - tool-codex
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       model:
 *         type: string
 *       input:
 *         type: integer
 *       output:
 *         type: integer
 *       cache_read:
 *         type: integer
 *       cache_write:
 *         type: integer
 *       cache_pct:
 *         type: integer
 *       usd:
 *         type: string
 *       harness:
 *         type: string
 *       at:
 *         type: string
 *       today_usd:
 *         type: string
 *       turns_today:
 *         type: integer
 *       priced:
 *         type: boolean
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: claude_dir
 *   param_type: string
 *   required: false
 *   default: '~/.claude/projects'
 *   description: 'Where Claude Code keeps its session transcripts. Only the tail of the newest file is read.'
 *   example: '~/.claude/projects'
 * - name: codex_dir
 *   param_type: string
 *   required: false
 *   default: '~/.codex/sessions'
 *   description: 'Where Codex keeps its session transcripts. Only the tail of the newest file is read.'
 *   example: '~/.codex/sessions'
 * - name: rates_path
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Empty uses the price table bundled with the Play. Point it at your own JSON to price with different rates.'
 *   example: '~/prices.json'
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
 *   report:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'last-turn'
 *     - 'report'
 *     - '--claude-dir'
 *     - '$claude_dir'
 *     - '--codex-dir'
 *     - '$codex_dir'
 *     - '--rates-path'
 *     - '$rates_path'
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

  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`that turn: ${j.input ?? 0} in / ${j.output ?? 0} out · $${j.usd ?? 0} · $${j.today_usd ?? 0} today`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
