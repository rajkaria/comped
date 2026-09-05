#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: wrong-turns
 * description: 'Rote asks you to keep one wrong turn in every Play as proof a human was steering. Your logs already hold hundreds. This reads Claude Code and Codex transcripts and finds three kinds: tool calls that returned an error, the message where you corrected the agent, and reverts. It groups them into recurring mistake classes by tool and error signature, counts how often each recurred across sessions and days, prices what the recovery cost in tokens, and shows one redacted line of evidence per class. For every class that recurred three or more times it drafts the rule that would have prevented it, in a block you can paste into CLAUDE.md or AGENTS.md, and labels each draft with the confidence of the signal behind it: tool errors are high, phrase-detected corrections are medium, and it never upgrades a guess. It writes the draft next to the report and never edits your rules files. Read-only, no credentials, no network, python3 only. Point claude_dir at resources/fixtures/claude to see a full run on synthetic logs first.
 *
 * - Reads: session logs under the four configured directories. Nothing else.
 * - Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Which AI you run is inferred from the model ids already in those logs; the plan tier is never read from your account.
 * - Never sends from the core: reading, pricing and rendering make no network calls. Verifiable: `comped_core` imports no `urllib`, `http`, `socket`, `subprocess` (except the PNG renderer, which is invoked with a fixed argv and no shell). The one step that talks to the network is `comped`''s `post_score`, a separate short script that sends your score to the gotcomped.com leaderboard after the card is written and nothing before; `leaderboard=false` skips it, and a failed post never fails the run.
 * - Writes: only under `out_dir`. Every written path is listed in the report.
 * - Message text: truncated to 120 chars and hashed by default. `redact=false` keeps full text locally, never in the card.
 *
 * See also: `session-ledger` (the normalized ledger this reads) and `comped` (prices it and finds your repeat asks). Docs, the full methodology and a worked example: https://gotcomped.com'
 * version: '0.1.4'
 * source_url: https://play.modiqo.ai/rajkaria/wrong-turns
 * metadata:
 *   version: '0.1.4'
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
 *     - domain-agent-operations
 *     - job-mistake-review
 *     - job-rule-drafting
 *     - audience-developers
 *     - effect-read-only
 *     - tool-claude-code
 *     - tool-codex
 * tags:
 * - domain-agent-operations
 * - job-mistake-review
 * - job-rule-drafting
 * - audience-developers
 * - effect-read-only
 * - tool-claude-code
 * - tool-codex
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-mistake-review
 *   - job-rule-drafting
 *   - audience-developers
 *   - effect-read-only
 *   - tool-claude-code
 *   - tool-codex
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       classes:
 *         type: object
 *       written:
 *         type: object
 * presentation_fixtures:
 *   classify_turns: resources/presentation-fixtures/classify_turns/fixture.yaml
 *   draft_rules: resources/presentation-fixtures/draft_rules/fixture.yaml
 *   merge_ledger: resources/presentation-fixtures/merge_ledger/fixture.yaml
 *   read_claude: resources/presentation-fixtures/read_claude/fixture.yaml
 *   read_codex: resources/presentation-fixtures/read_codex/fixture.yaml
 * parameters:
 * - name: days_back
 *   param_type: integer
 *   required: false
 *   default: '14'
 *   description: 'Filter on each record''s own timestamp.'
 *   example: '14'
 * - name: out_dir
 *   param_type: string
 *   required: false
 *   default: '~/comped'
 *   description: 'Created if missing. Everything this Play writes goes here and nowhere else.'
 *   example: '~/comped'
 * - name: claude_dir
 *   param_type: string
 *   required: false
 *   default: '~/.claude/projects'
 *   description: 'Set to resources/fixtures/claude for a demo run on synthetic logs.'
 *   example: 'resources/fixtures/claude'
 * - name: codex_dir
 *   param_type: string
 *   required: false
 *   default: '~/.codex/sessions'
 *   description: 'Set to resources/fixtures/codex for a demo run on synthetic logs.'
 *   example: 'resources/fixtures/codex'
 * - name: include_subagents
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'Claude Code subagent transcripts. true or false.'
 *   example: 'true'
 * - name: min_recurrence
 *   param_type: integer
 *   required: false
 *   default: '3'
 *   description: 'How many times a mistake class must recur before it is reported; it also needs 2 sessions.'
 *   example: '3'
 * - name: show_snippets
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true shows one redacted evidence line per class; false replaces it with (snippets hidden).'
 *   example: 'true'
 * - name: rules_target
 *   param_type: string
 *   required: false
 *   default: 'both'
 *   description: 'claude, agents or both. Drafts only; nothing is ever written to your rules files.'
 *   example: 'both'
 * steps:
 *   read_claude:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'ledger'
 *     - '--only'
 *     - 'claude-code'
 *     - '--claude-dir'
 *     - '$claude_dir'
 *     - '--days-back'
 *     - '$days_back'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--include-subagents'
 *     - '$include_subagents'
 *     - '--redact'
 *     - 'true'
 *   read_codex:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'ledger'
 *     - '--only'
 *     - 'codex'
 *     - '--codex-dir'
 *     - '$codex_dir'
 *     - '--days-back'
 *     - '$days_back'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--redact'
 *     - 'true'
 *   merge_ledger:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - read_claude
 *     - read_codex
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'merge'
 *     - '--out-dir'
 *     - '$out_dir'
 *   classify_turns:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - merge_ledger
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'wrongturns'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--min-recurrence'
 *     - '$min_recurrence'
 *     - '--show-snippets'
 *     - '$show_snippets'
 *   draft_rules:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - classify_turns
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'rules'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--rules-target'
 *     - '$rules_target'
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

/** A harness whose log directory is absent warns and exits 0. Surface those, once, by name. */
function absencesOf(entries: Array<{ label: string; step: ReturnType<typeof ctx.step> }>): string[] {
  const notes: string[] = [];
  for (const { label, step } of entries) {
    const o = step.outcome;
    if (o.status !== "completed" && o.status !== "restored") { notes.push(`${label}: not run`); continue; }
    const body = o.output.body;
    if (!isProcessExecBody(body)) continue;
    const parsed = split(body.stdout?.text ?? "").json as { warning?: string };
    if (typeof parsed.warning === "string") notes.push(`${label}: ${parsed.warning}`);
  }
  return notes;
}

if (ctx.run.status === "failed") {
  out.human("The run failed before it could produce a result; the step evidence is in the runner report above.");
  out.summary("run failed");
  out.result({ run_id: ctx.run.run_id, ok: false });
} else {
  const final = split(stdoutOf("draft_rules", ctx.requireAvailable(stepName("draft_rules"))));
  const notes = absencesOf([
    { label: "read_claude", step: ctx.step(stepName("read_claude")) },
    { label: "read_codex", step: ctx.step(stepName("read_codex")) },
  ]);
  const j = final.json as Record<string, any>;
  out.human([final.human, notes.length ? `Not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.classes ?? 0} recurring mistake classes; drafted rules written, nothing applied`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
