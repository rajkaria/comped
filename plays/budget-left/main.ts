#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: budget-left
 * description: 'You set a number you are willing to spend on agents today. This tells you how much of it is gone, how fast you are burning it, and whether you are going to hit the cap before the day ends.
 *
 * Today''s spend is priced from the transcripts the agents already write, by tail, the same way `last-turn` does it, so it is cheap enough to check between tasks. The burn rate is measured from your first turn of the day rather than from midnight, because an hour you were not working is not an hour you were spending. The crossing time is only ever printed when the crossing happens today: "about 16:40" for a moment eighteen days away would read as this afternoon and mean nothing, so instead it says the cap is not today''s problem at this rate.
 *
 * A day with nothing billed says so, rather than dividing by zero and inventing a rate.
 *
 * - Reads: `*.jsonl` transcripts under `claude_dir` and `codex_dir`, tails only, up to three directories deep. Only files touched in the last two days are opened at all.
 * - Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Your plan, your invoice and your account balance are never consulted — this is arithmetic over your own logs, not a billing integration.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit.
 * - Writes nothing. The budget is a parameter, not a stored setting; nothing is kept between runs.
 * - No message text is read or printed. Only usage blocks, model ids and timestamps.
 * - Runs cold: set `demo=true` to read bundled synthetic transcripts with nothing configured.
 *
 * See also: `last-turn` for the turn that just finished, and `comped` for what the month actually came to. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.1'
 * source_url: https://play.modiqo.ai/rajkaria/budget-left
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
 *     - job-budget-check
 *     - job-agent-cost-review
 *     - audience-developers
 *     - effect-read-only
 *     - tool-claude-code
 *     - tool-codex
 * tags:
 * - domain-agent-operations
 * - job-budget-check
 * - job-agent-cost-review
 * - audience-developers
 * - effect-read-only
 * - tool-claude-code
 * - tool-codex
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-budget-check
 *   - job-agent-cost-review
 *   - audience-developers
 *   - effect-read-only
 *   - tool-claude-code
 *   - tool-codex
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       spent:
 *         type: string
 *       budget:
 *         type: string
 *       pct:
 *         type: integer
 *       burn_per_hour:
 *         type: string
 *       exhausted_at:
 *         type: string
 *       verdict:
 *         type: string
 *       turns:
 *         type: integer
 *       models:
 *         type: object
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: daily_budget
 *   param_type: string
 *   required: false
 *   default: '10'
 *   description: 'What you are willing to spend on agents today, in dollars. The burn rate is measured against it.'
 *   example: '15'
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
 *     - 'budget'
 *     - 'report'
 *     - '--daily-budget'
 *     - '$daily_budget'
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
  out.summary(`$${j.spent ?? 0} of $${j.budget ?? 0} today · ${j.pct ?? 0}%${j.exhausted_at ? ` · cap about ${j.exhausted_at}` : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
