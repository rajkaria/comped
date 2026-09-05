#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: since-last
 * description: 'An agent has been working. What did it touch? Not what it said it did — what actually moved on disk since the last time you asked.
 *
 * The first run notes the tree and says so, rather than claiming every file in your repository is new. Every run after that gives you what was created, what changed, what was deleted, the line counts that went with it, and the biggest single change. A file whose timestamp moved but whose bytes did not is not reported as modified, because that is noise and noise is what makes a check like this stop being read.
 *
 * The other half is the question people actually have, and it is answered without opening anything: `~/.ssh`, `~/.aws`, `~/.config`, `~/.gnupg`, `~/.claude`, `~/.codex` and `~/Library/LaunchAgents` are checked by directory timestamp alone. The Play can tell you something under `~/.ssh` changed while it was working, and it can tell you that having read not one byte of what is in there.
 *
 * The walk is bounded and says when it hit the bound, so a partial answer is reported as a lower bound and never as a complete one. `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, `target` and their friends are skipped by default; add your own with `ignore`.
 *
 * - Reads: file names, sizes, timestamps and line counts under `root`; file contents only far enough to count newlines and to notice a NUL byte, which makes a file binary and its line count unreported rather than invented. The sensitive directories are read by timestamp only.
 * - Never reads: any credential, keychain or token file. It notices that `~/.ssh` changed; it never looks inside it.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. Your file names never leave the machine.
 * - Writes: one snapshot file per watched folder under `state_dir`, and nothing else, ever. Nothing in `root` is modified, moved or deleted — this Play has no way to change your tree, only to describe it.
 * - Runs cold: set `demo=true` to compare a bundled tree against a bundled earlier snapshot, in a temporary folder. Your own state is not touched.
 *
 * See also: `safe-to-commit`, which reads what is staged rather than what changed, and `last-turn`, which prices the turn that did the changing. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/since-last
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
 *     - job-change-review
 *     - job-blast-radius
 *     - audience-developers
 *     - effect-local-write
 *     - tool-filesystem
 * tags:
 * - domain-agent-operations
 * - job-change-review
 * - job-blast-radius
 * - audience-developers
 * - effect-local-write
 * - tool-filesystem
 * discoverability:
 *   tags:
 *   - domain-agent-operations
 *   - job-change-review
 *   - job-blast-radius
 *   - audience-developers
 *   - effect-local-write
 *   - tool-filesystem
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       first_run:
 *         type: boolean
 *       created:
 *         type: object
 *       modified:
 *         type: object
 *       deleted:
 *         type: object
 *       lines_added:
 *         type: integer
 *       lines_removed:
 *         type: integer
 *       biggest:
 *         type: object
 *       sensitive_changed:
 *         type: object
 *       files:
 *         type: integer
 *       truncated:
 *         type: boolean
 *       written:
 *         type: object
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '.'
 *   description: 'The tree whose changes you want. Compared against the snapshot from the last time you asked about this same folder.'
 *   example: '~/code/my-project'
 * - name: state_dir
 *   param_type: string
 *   required: false
 *   default: '~/.rote-micro'
 *   description: 'The one directory this Play writes to. One append-only JSONL file per stream; nothing is ever deleted or rewritten in place.'
 *   example: '~/.rote-micro'
 * - name: ignore
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Comma-separated, added to the built-in list (.git, node_modules, __pycache__, .venv, dist, build and friends).'
 *   example: 'coverage,tmp'
 * - name: max_files
 *   param_type: integer
 *   required: false
 *   default: '20000'
 *   description: 'The walk stops here and says so, so a partial answer is never reported as a complete one.'
 *   example: '20000'
 * - name: watch_sensitive
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true also notices whether ~/.ssh, ~/.aws, ~/.config, ~/.gnupg or LaunchAgents changed — by directory timestamp alone, never by reading what is in them.'
 *   example: 'true'
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
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'since-last'
 *     - 'report'
 *     - '--root'
 *     - '$root'
 *     - '--state-dir'
 *     - '$state_dir'
 *     - '--ignore'
 *     - '$ignore'
 *     - '--max-files'
 *     - '$max_files'
 *     - '--watch-sensitive'
 *     - '$watch_sensitive'
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
  out.summary(`${j.first_run ? `first look: ${j.files ?? 0} files noted` : `${(j.created ?? []).length + (j.modified ?? []).length + (j.deleted ?? []).length} file(s) touched · +${j.lines_added ?? 0}/−${j.lines_removed ?? 0} lines${(j.sensitive_changed ?? []).length ? " ⚠ something outside the tree moved" : ""}`}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
