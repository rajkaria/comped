#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: is-it-secret
 * description: 'Run this on anything you are about to paste into a chat, an agent, an issue or a screenshot. It tells you what is in there that should not leave your machine, and hands back the same text with those parts replaced, ready to paste.
 *
 * It knows the literal shapes: AWS access key ids, GitHub tokens including fine-grained ones, Slack, Stripe live keys, Google, OpenAI, Anthropic, Twilio, SendGrid, npm and PyPI tokens, PEM and OpenSSH private key blocks, SSH public keys, JWTs, and connection strings carrying a password. On top of those it reads assignments: a name that says secret, token, password or api_key whose value is at least twelve characters and random enough — measured as Shannon entropy, not guessed — is reported too.
 *
 * Precision is the whole product, because a checker that cries wolf gets turned off within a week and then it is protecting nothing. So `API_KEY=your-key-here` is not a finding. Neither is `${GITHUB_TOKEN}`, `$MY_VAR`, `<your-secret>`, `changeme`, a value made of one repeated character, Stripe''s own `sk_test_` keys, or AWS''s documented `AKIAIOSFODNN7EXAMPLE`. Every one of those exclusions has its own test.
 *
 * The verdict is one of three words. `safe` means paste it. `redact` means there are things to take out first, and the redacted copy is printed for you. `do-not-paste` means at least one of them is a live credential shape.
 *
 * - Reads: the text you pass, or the file or folder at `path` (up to 200 files, 2 MB each). Nothing else.
 * - Never reads: any credential store, keychain or token file of its own accord. It reads only what you point it at.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. The thing that finds your secrets is the last thing that should have a network stack, and it does not have one.
 * - Writes nothing. The redacted copy is printed, never saved.
 * - Never prints what it found. Every finding is masked to its first four and last two characters plus a length, in the human block and in the JSON alike, and a test asserts that the original value appears in neither.
 * - Runs cold: set `demo=true` to scan a bundled synthetic `.env` with nothing configured.
 *
 * See also: `safe-to-commit`, which runs the same detectors over your staged files before the commit, and `whatis`, which peels the thing rather than judging it. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/is-it-secret
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
 *     - domain-security
 *     - job-secret-detection
 *     - job-paste-safety
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-dotenv
 *     - tool-git
 * tags:
 * - domain-security
 * - job-secret-detection
 * - job-paste-safety
 * - audience-everyone
 * - effect-read-only
 * - tool-dotenv
 * - tool-git
 * discoverability:
 *   tags:
 *   - domain-security
 *   - job-secret-detection
 *   - job-paste-safety
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-dotenv
 *   - tool-git
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       verdict:
 *         type: string
 *       findings:
 *         type: object
 *       counts:
 *         type: object
 *       redacted:
 *         type: string
 *       source:
 *         type: string
 *       bytes:
 *         type: integer
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: text
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'The snippet you are about to paste into a chat, an agent or an issue. Nothing leaves this machine.'
 *   example: 'PASTE=whatever-you-were-about-to-send'
 * - name: path
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Read instead of text. A folder is read up to 200 files deep.'
 *   example: './.env'
 * - name: strict
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true also flags an assignment whose name says secret and whose value is random enough to be one. false keeps only the literal key shapes.'
 *   example: 'true'
 * - name: show
 *   param_type: string
 *   required: false
 *   default: 'redacted'
 *   description: 'redacted prints your text back with every finding replaced, ready to paste. none prints the findings only.'
 *   example: 'redacted'
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
 *     - 'secret'
 *     - 'report'
 *     - '--text'
 *     - '$text'
 *     - '--path'
 *     - '$path'
 *     - '--strict'
 *     - '$strict'
 *     - '--show'
 *     - '$show'
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
  out.summary(`${j.verdict === "safe" ? "nothing to redact" : `${(j.findings ?? []).length} to redact — ${j.verdict}`}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
