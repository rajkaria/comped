#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: session-ledger
 * description: 'Every agent harness on this machine keeps a transcript, each in its own shape, and none of them agree on what a token record looks like. Claude Code writes one line per content block so four in ten usage lines are duplicates of the same API call, and buries subagent spend in a subdirectory. Codex writes cumulative counters that have to be differenced. Pi and OpenCode have their own layouts. This reads all of them and emits one deduplicated ledger: usage records with uncached input, cache write, cache read, output and reasoning tokens per model per turn; the human messages that started each turn; and every tool call with whether it errored. Nothing is priced, nothing is judged, and message text is truncated and hashed unless you ask for it. It is the file the other session Plays should be reading instead of each re-parsing the logs, and it says which sources it found, which it could not read, and why. Read-only, no credentials, no network. Writes one JSONL and one summary JSON under the folder you choose. Point it at resources/fixtures to see a full run on synthetic logs first.
 *
 * - Reads: session logs under the four configured directories. Nothing else.
 * - Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Which AI you run is inferred from the model ids already in those logs; the plan tier is never read from your account.
 * - Never sends: no network calls of any kind. Verifiable: the core imports no `urllib`, `http`, `socket`, `subprocess` (except the PNG renderer, which is invoked with a fixed argv and no shell).
 * - Writes: only under `out_dir`. Every written path is listed in the report.
 * - Message text: truncated to 120 chars and hashed by default. `redact=false` keeps full text locally, never in the card.
 *
 * See also: `comped` (prices this ledger and finds your repeat asks) and `wrong-turns` (recurring mistakes, with drafted rules). Docs, the full methodology and a worked example: https://gotcomped.com'
 * version: '0.1.3'
 * source_url: https://play.modiqo.ai/rajkaria/session-ledger
 * metadata:
 *   version: '0.1.3'
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
 *     - job-session-ledger
 *     - job-token-accounting
 *     - audience-developers
 *     - effect-read-only
 *     - tool-claude-code
 *     - tool-codex
 * tags:
 * - domain-agent-operations
 * - job-session-ledger
 * - job-token-accounting
 * - audience-developers
 * - effect-read-only
 * - tool-claude-code
 * - tool-codex
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-session-ledger
 *   - job-token-accounting
 *   - audience-developers
 *   - effect-read-only
 *   - tool-claude-code
 *   - tool-codex
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       records:
 *         type: string
 *       humans:
 *         type: string
 *       tools:
 *         type: string
 *       sources:
 *         type: object
 * presentation_fixtures:
 *   merge_ledger: resources/presentation-fixtures/merge_ledger/fixture.yaml
 *   read_claude: resources/presentation-fixtures/read_claude/fixture.yaml
 *   read_codex: resources/presentation-fixtures/read_codex/fixture.yaml
 *   read_opencode: resources/presentation-fixtures/read_opencode/fixture.yaml
 *   read_pi: resources/presentation-fixtures/read_pi/fixture.yaml
 *   summarize: resources/presentation-fixtures/summarize/fixture.yaml
 * parameters:
 * - name: days_back
 *   param_type: integer
 *   required: false
 *   default: '30'
 *   description: 'Filter on each record''s own timestamp.'
 *   example: '30'
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
 * - name: pi_dir
 *   param_type: string
 *   required: false
 *   default: '~/.pi/agent/sessions'
 *   description: 'Best-effort adapter; the source note says so.'
 *   example: 'resources/fixtures/pi'
 * - name: opencode_dir
 *   param_type: string
 *   required: false
 *   default: '~/.local/share/opencode/storage'
 *   description: 'Best-effort adapter; the source note says so.'
 *   example: 'resources/fixtures/opencode/storage'
 * - name: include_subagents
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'Claude Code subagent transcripts. true or false.'
 *   example: 'true'
 * - name: redact
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true stores a 120-character truncation plus sha256; false keeps full text locally, never in a card.'
 *   example: 'true'
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
 *     - '$redact'
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
 *     - '$redact'
 *   read_pi:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'ledger'
 *     - '--only'
 *     - 'pi'
 *     - '--pi-dir'
 *     - '$pi_dir'
 *     - '--days-back'
 *     - '$days_back'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--redact'
 *     - '$redact'
 *   read_opencode:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'ledger'
 *     - '--only'
 *     - 'opencode'
 *     - '--opencode-dir'
 *     - '$opencode_dir'
 *     - '--days-back'
 *     - '$days_back'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--redact'
 *     - '$redact'
 *   merge_ledger:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - read_claude
 *     - read_codex
 *     - read_pi
 *     - read_opencode
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'merge'
 *     - '--out-dir'
 *     - '$out_dir'
 *   summarize:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - merge_ledger
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'summary'
 *     - '--out-dir'
 *     - '$out_dir'
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
  const final = split(stdoutOf("summarize", ctx.requireAvailable(stepName("summarize"))));
  const notes = absencesOf([
    { label: "read_claude", step: ctx.step(stepName("read_claude")) },
    { label: "read_codex", step: ctx.step(stepName("read_codex")) },
    { label: "read_pi", step: ctx.step(stepName("read_pi")) },
    { label: "read_opencode", step: ctx.step(stepName("read_opencode")) },
  ]);
  const j = final.json as Record<string, any>;
  out.human([`LEDGER`, final.human, notes.length ? `\nNot read: ${notes.join("; ")}` : ""].join("\n"));
  out.summary(`${j.records ?? 0} usage records, ${j.human_typed ?? 0} typed messages, ${j.tools ?? 0} tool calls across ${j.sessions ?? 0} sessions`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
