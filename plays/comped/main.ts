#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: comped
 * description: 'Every coding session on this machine wrote down exactly what it consumed, and none of it is readable by hand. This reads all of it: Claude Code including the subagent transcripts in subdirectories, where four in ten usage lines are streaming duplicates that must be collapsed before pricing, Codex, whose counters are cumulative and need differencing, and Pi. You get one card: the API list-price equivalent of the last N days per model, the multiplier against the plan you actually pay for, your cache-read share, and how all of it moved since your last run. Under it, the jobs you have asked your agent for three or more times, each with its repeat cost and the exact play settle command to capture it. Then what those repeats would have cost as Plays, at Modiqo''s stated 98% and at a conservative 80%. Prices come from a bundled table that names its source and as-of date; a model the table does not know is reported as tokens and never priced by guess. You do not tell it what you run: the model ids in your own logs name the providers behind them -- Claude, GPT/Codex, Kimi, GLM, DeepSeek, Gemini, Grok, Qwen -- and every subscription those providers sell is priced on the card at once, the least flattering one marked as assumed, so you read your row instead of typing it. It refuses to open your OAuth files to find the tier, and the card says plainly that list price is not a bill. Read-only and no credentials. Writes a Markdown report, an SVG card, a PNG when the machine can render one, and a small baseline for next run''s delta, all under the folder you choose. Then, unless you say leaderboard=false, it posts the score to the gotcomped.com leaderboard and prints your rank: that is the one thing this Play ever sends, and the exact payload is saved next to the card so you can read it. Point claude_dir at resources/fixtures/claude to see a full run on synthetic logs before you run it on your own.
 *
 * - Reads: session logs under the four configured directories. Nothing else.
 * - Never reads: `~/.claude.json`, `~/.codex/auth.json`, any credential, keychain or token file. Which AI you run is inferred from the model ids already in those logs; the plan tier is never read from your account.
 * - Never sends from the core: reading, pricing and rendering make no network calls. Verifiable: `comped_core` imports no `urllib`, `http`, `socket`, `subprocess` (except the PNG renderer, which is invoked with a fixed argv and no shell). The one step that talks to the network is `comped`''s `post_score`, a separate short script that sends your score to the gotcomped.com leaderboard after the card is written and nothing before; `leaderboard=false` skips it, and a failed post never fails the run.
 * - Writes: only under `out_dir`. Every written path is listed in the report.
 * - Message text: truncated to 120 chars and hashed by default. `redact=false` keeps full text locally, never in the card.
 *
 * See also: `session-ledger` (the normalized ledger this reads) and `wrong-turns` (recurring mistakes, with drafted rules). Docs, the full methodology and a worked example: https://gotcomped.com'
 * version: '0.1.4'
 * source_url: https://play.modiqo.ai/rajkaria/comped
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
 *     - job-agent-cost-review
 *     - job-repeat-ask-detection
 *     - audience-developers
 *     - effect-read-only
 *     - tool-claude-code
 *     - tool-codex
 * tags:
 * - domain-agent-operations
 * - job-agent-cost-review
 * - job-repeat-ask-detection
 * - audience-developers
 * - effect-read-only
 * - tool-claude-code
 * - tool-codex
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-agent-cost-review
 *   - job-repeat-ask-detection
 *   - audience-developers
 *   - effect-read-only
 *   - tool-claude-code
 *   - tool-codex
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       total_usd:
 *         type: string
 *       multiplier:
 *         type: string
 *       per_model:
 *         type: object
 *       repeats:
 *         type: object
 *       written:
 *         type: object
 *       leaderboard:
 *         type: object
 * presentation_fixtures:
 *   find_repeats: resources/presentation-fixtures/find_repeats/fixture.yaml
 *   merge_ledger: resources/presentation-fixtures/merge_ledger/fixture.yaml
 *   price_ledger: resources/presentation-fixtures/price_ledger/fixture.yaml
 *   read_claude: resources/presentation-fixtures/read_claude/fixture.yaml
 *   read_codex: resources/presentation-fixtures/read_codex/fixture.yaml
 *   read_opencode: resources/presentation-fixtures/read_opencode/fixture.yaml
 *   read_pi: resources/presentation-fixtures/read_pi/fixture.yaml
 *   render_card: resources/presentation-fixtures/render_card/fixture.yaml
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
 * - name: plan
 *   param_type: string
 *   required: false
 *   default: 'auto'
 *   description: 'Leave it. auto reads the model ids already in your logs, names the providers behind them (Claude, GPT/Codex, Kimi, GLM, DeepSeek, Gemini, Grok, Qwen and the rest) and prices every tier those providers sell, marking the least flattering one as assumed -- you read your own row instead of typing it. Override with a comma-separated list of ids, or usd:<amount> for a subscription this table does not carry. This Play never opens your OAuth files to find out.'
 *   example: 'auto'
 * - name: repeat_threshold
 *   param_type: integer
 *   required: false
 *   default: '3'
 *   description: 'Minimum asks for a repeat offender; also needs 2 sessions and 2 days.'
 *   example: '3'
 * - name: rates_path
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Path to a prices.json that replaces the bundled table.'
 *   example: ''
 * - name: handle
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Your name on the gotcomped.com leaderboard, and in the /play settle command. Blank posts anonymously (anon-xxxx). gotcomped.com/run.sh fills in your rote handle.'
 *   example: 'priya'
 * - name: card_theme
 *   param_type: string
 *   required: false
 *   default: 'dark'
 *   description: 'dark or light.'
 *   example: 'dark'
 * - name: leaderboard
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true posts your score to gotcomped.com after the card is written and prints your rank: the multiplier, tier, list-price total, plan, detected providers, days, and your handle. Nothing else, ever; the exact payload is saved to out_dir/comped-rank.json. false sends nothing, and the run is then entirely offline.'
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
 *   price_ledger:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - merge_ledger
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'price'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--plan'
 *     - '$plan'
 *     - '--rates-path'
 *     - '$rates_path'
 *     - '--days-back'
 *     - '$days_back'
 *   find_repeats:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - price_ledger
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'repeats'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--repeat-threshold'
 *     - '$repeat_threshold'
 *     - '--handle'
 *     - '$handle'
 *   render_card:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - find_repeats
 *     argv:
 *     - 'python3'
 *     - '@resource{comped_core/cli.py}'
 *     - 'card'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--card-theme'
 *     - '$card_theme'
 *   post_score:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - render_card
 *     argv:
 *     - 'python3'
 *     - '@resource{post_score.py}'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--leaderboard'
 *     - '$leaderboard'
 *     - '--handle'
 *     - '$handle'
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
  const final = split(stdoutOf("render_card", ctx.requireAvailable(stepName("render_card"))));
  const notes = absencesOf([
    { label: "read_claude", step: ctx.step(stepName("read_claude")) },
    { label: "read_codex", step: ctx.step(stepName("read_codex")) },
    { label: "read_pi", step: ctx.step(stepName("read_pi")) },
    { label: "read_opencode", step: ctx.step(stepName("read_opencode")) },
  ]);
  const j = final.json as Record<string, any>;
  // The poster never fails the run: read whatever it printed, and say nothing if it printed nothing.
  const post = ctx.step(stepName("post_score")).outcome;
  const r = ((post.status === "completed" || post.status === "restored") && isProcessExecBody(post.output.body)
    ? split(post.output.body.stdout?.text ?? "").json : {}) as Record<string, any>;
  const board = r.posted === true && r.rank ? `Leaderboard: #${r.rank} of ${r.of} · ${r.url}`
    : r.posted === true ? `Leaderboard: posted${r.reason ? ` (${r.reason})` : ""} · ${r.url ?? "https://gotcomped.com/leaderboard.html"}`
    : r.skipped === true ? "Leaderboard: skipped (leaderboard=false)"
    : typeof r.warning === "string" ? `Leaderboard: not posted (${r.warning})` : "";
  out.human([final.human, board, notes.length ? `Not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  const mult = j.multiplier === null || j.multiplier === undefined ? "list price only" : `${Number(j.multiplier).toFixed(1)}x vs ${j.plan}${j.plan_source === "auto" ? " (inferred)" : ""}`;
  out.summary(`$${Number(j.total_usd ?? 0).toFixed(2)} comped over ${ctx.params.days_back} days, ${mult}, ${j.repeats ?? 0} repeat offenders${j.detected ? ` · ${j.detected}` : ""}${r.rank ? ` · #${r.rank} of ${r.of} on the leaderboard` : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, leaderboard: r, absences: notes });
}
