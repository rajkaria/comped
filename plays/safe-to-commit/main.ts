#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: safe-to-commit
 * description: 'The last thing between a live credential and permanent git history is you, at the moment you type commit. This reads what is actually staged and tells you what is in it: credentials, an `.env` that should not be tracked, leftover debugging, and files large enough that you will regret them for the life of the repository.
 *
 * It does not run git. The index format is public and stable, so `.git/index` is parsed directly for the staged paths and their blob ids, and the blobs are read out of `.git/objects` with zlib — which means this keeps the same promise every other Play here keeps: no subprocess, no shell, nothing executed. Where a staged blob lives in a packfile rather than a loose object, the working-tree copy is read instead and the output names the files that happened to, so you know which lines were read from where. A version 4 index, whose paths are prefix-compressed, is declined by name rather than mis-parsed.
 *
 * The credential detectors are the same ones `is-it-secret` uses, with the same exclusions, so `API_KEY=your-key-here` is not a finding here either. The debug detectors are deliberately narrow: `print(` counts in a `.py` file under `src/` and not in one under `scripts/`, where printing is the job; `console.log` counts only in JavaScript and TypeScript; a Go `fmt.Println` does not count in a main package. A pre-commit check that cries about everything gets bypassed within a week, and then it is protecting nothing.
 *
 * The verdict is one of four words: `clean`, `review` (something is worth a look), `do-not-commit` (a live credential shape is staged), or `nothing-staged`.
 *
 * - Reads: `.git/index` and the loose objects for the staged paths, plus the working-tree copy of any staged file whose blob is packed. Nothing outside `repo`.
 * - Never reads: your git credentials, `~/.gitconfig` secrets, any keychain or token file. It reads what you staged and nothing else.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. This is the check that reads your secrets; it is also the one with no network stack.
 * - Writes nothing. It does not stage, unstage, commit, amend or modify anything. It reads and reports.
 * - Never prints what it found. Every credential is masked to its first four and last two characters plus a length, and a test asserts the original never appears in the output.
 * - Runs cold: set `demo=true` to read a bundled synthetic repository — a real index and real loose objects, written byte by byte, with a fake key staged in it.
 *
 * See also: `is-it-secret` for the same detectors over a paste, and `since-last` for what changed whether or not you staged it. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.1'
 * source_url: https://play.modiqo.ai/rajkaria/safe-to-commit
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
 *     - domain-security
 *     - job-precommit-check
 *     - job-secret-detection
 *     - audience-developers
 *     - effect-read-only
 *     - tool-git
 * tags:
 * - domain-security
 * - job-precommit-check
 * - job-secret-detection
 * - audience-developers
 * - effect-read-only
 * - tool-git
 * discoverability:
 *   tags:
 *   - domain-security
 *   - job-precommit-check
 *   - job-secret-detection
 *   - audience-developers
 *   - effect-read-only
 *   - tool-git
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       verdict:
 *         type: string
 *       files:
 *         type: integer
 *       findings:
 *         type: object
 *       debug:
 *         type: object
 *       oversized:
 *         type: object
 *       env_files:
 *         type: object
 *       from_worktree:
 *         type: object
 *       staged:
 *         type: integer
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: repo
 *   param_type: string
 *   required: false
 *   default: '.'
 *   description: 'The working copy whose staged set is read, straight out of .git/index. No git process is started.'
 *   example: '~/code/my-project'
 * - name: max_file_kb
 *   param_type: integer
 *   required: false
 *   default: '512'
 *   description: 'A staged file bigger than this is called out before it goes into history, where it stays for ever.'
 *   example: '512'
 * - name: strict
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true also flags an assignment whose name says secret and whose value is random enough to be one.'
 *   example: 'true'
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
 *     - 'staged'
 *     - 'report'
 *     - '--repo'
 *     - '$repo'
 *     - '--max-file-kb'
 *     - '$max_file_kb'
 *     - '--strict'
 *     - '$strict'
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
  out.summary(`${j.staged ?? 0} staged file(s) — ${j.verdict ?? "unknown"}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
