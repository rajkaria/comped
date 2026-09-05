#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: vault-pulse
 * description: 'A notes folder only grows. Nothing in the editor ever says which notes are load-bearing and which were written once and never opened again, so the answer is usually a feeling. Both facts are in the files: the links give the graph, the timestamps give the habit.
 *
 * This reads a markdown folder, finds your Obsidian vault on its own if you do not name one, and builds the link graph from wiki links and relative markdown links together. Out of that come the notes nothing points at and that point nowhere, the notes that have inbound links but no outbound ones, the links that point at a note which does not exist, and the notes everything else points at.
 *
 * Then the habit. Notes never edited after the minute they were created, notes under thirty words, notes untouched past your threshold, the count of new notes per week for the last sixteen weeks, your daily-note streak with the longest run you have ever managed, and every unchecked box in the vault with the number of notes holding them.
 *
 * One caveat is built in rather than left for you to discover. If every note carries the same creation time, which is what a fresh clone or a restored backup looks like, the never-edited count is meaningless and the Play says so instead of reporting a confident hundred per cent.
 *
 * Nothing is written inside the vault. The report goes to your output folder.
 *
 * - Reads: only the locations listed above. Nothing else on your disk is opened.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: a source this machine does not have, or that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against bundled synthetic fixtures with nothing configured, before you point it at your own machine.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/vault-pulse
 * metadata:
 *   version: '0.1.0'
 *   rote_version: '0.79.0'
 *   status: released
 *   kind: atomic
 *   flow_type: sequential
 *   execution_model: steps_with_presentation
 *   requires_endpoints: []
 *   requires_sessions: false
 *   license: MIT
 *   discoverability:
 *     tags:
 *     - domain-personal-computing
 *     - job-notes-audit
 *     - job-knowledge-hygiene
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-obsidian
 *     - tool-markdown
 * tags:
 * - domain-personal-computing
 * - job-notes-audit
 * - job-knowledge-hygiene
 * - audience-everyone
 * - effect-read-only
 * - tool-obsidian
 * - tool-markdown
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-notes-audit
 *   - job-knowledge-hygiene
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-obsidian
 *   - tool-markdown
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       notes:
 *         type: integer
 *       words:
 *         type: integer
 *       orphans:
 *         type: integer
 *       broken_links:
 *         type: integer
 *       write_only:
 *         type: integer
 *       streak:
 *         type: integer
 *       todo:
 *         type: integer
 * presentation_fixtures:
 *   read_vault: resources/presentation-fixtures/read_vault/fixture.yaml
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: out_dir
 *   param_type: string
 *   required: false
 *   default: '~/daily'
 *   description: 'Created if missing. Everything this Play writes goes here and nowhere else.'
 *   example: '~/daily'
 * - name: demo
 *   param_type: string
 *   required: false
 *   default: 'false'
 *   description: 'true runs against a bundled synthetic vault with orphans, a broken link and a daily-note streak.'
 *   example: 'false'
 * - name: vault
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Leave empty to find an Obsidian vault automatically, then fall back to ~/Documents/Notes and ~/Documents.'
 *   example: ''
 * - name: stale_days
 *   param_type: integer
 *   required: false
 *   default: '180'
 *   description: 'A note untouched for this many days is counted as stale.'
 *   example: '180'
 * steps:
 *   read_vault:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'notes-read'
 *     - '--vault'
 *     - '$vault'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - read_vault
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'notes-report'
 *     - '--stale-days'
 *     - '$stale_days'
 *     - '--out-dir'
 *     - '$out_dir'
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
    { label: "read_vault", step: ctx.step(stepName("read_vault")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.notes ?? 0} notes, ${j.words ?? 0} words, ${j.orphans ?? 0} orphans, ${j.broken_links ?? 0} links pointing at nothing, daily streak ${j.streak ?? 0}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
