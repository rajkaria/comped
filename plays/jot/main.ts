#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: jot
 * description: 'A thought arrives while you are doing something else. `note=''ring the dentist''` and it is in your notes, timestamped, and you are back to what you were doing. No app to open, no window to find, no place to decide on.
 *
 * It appends `- 14:22 ring the dentist` to one Markdown file inside your vault — plain Markdown, so Obsidian, Logseq, a text editor or `cat` all read it the same way — and mirrors the capture to its own log, so the count and the streak survive you moving the vault. The same note twice within a minute is refused, because the second one is a slip of the hand rather than a second thought. An hour later the same words are a new thought and are captured.
 *
 * Leave `vault_dir` empty and it writes to the log only, touching nothing in your notes at all.
 *
 * - Reads: its own log, and the one inbox file inside `vault_dir` to count what is sitting there. Not the rest of your vault.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, asserted by a test on every commit. What you capture here stays on the machine.
 * - Writes: one appended line to `~/.rote-micro/jot.jsonl` and one appended line to `<vault_dir>/<inbox>`. Both are appends: nothing in your notes is deleted, truncated or rewritten in place, and no other file in the vault is opened for writing. The exact path written is printed in the output.
 * - Runs cold: set `demo=true` to read a bundled fourteen-day log copied to a temporary folder. Your own log and vault are not opened.
 *
 * See also: `vault-pulse`, which measures the vault this one fills — orphans, broken links, and the notes you never went back to. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/jot
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
 *     - domain-personal-productivity
 *     - job-quick-capture
 *     - job-notes-inbox
 *     - audience-everyone
 *     - effect-local-write
 *     - tool-obsidian
 *     - tool-markdown
 * tags:
 * - domain-personal-productivity
 * - job-quick-capture
 * - job-notes-inbox
 * - audience-everyone
 * - effect-local-write
 * - tool-obsidian
 * - tool-markdown
 * discoverability:
 *   tags:
 *   - domain-personal-productivity
 *   - job-quick-capture
 *   - job-notes-inbox
 *   - audience-everyone
 *   - effect-local-write
 *   - tool-obsidian
 *   - tool-markdown
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       today:
 *         type: integer
 *       week:
 *         type: integer
 *       inbox_lines:
 *         type: integer
 *       streak:
 *         type: integer
 *       longest_streak:
 *         type: integer
 *       captured:
 *         type: integer
 * presentation_fixtures:
 *   record: resources/presentation-fixtures/record/fixture.yaml
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: note
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'One line, captured now. Leave it empty to read the inbox back without adding to it.'
 *   example: 'ring the dentist'
 * - name: vault_dir
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Your Obsidian vault or any folder of Markdown. Empty keeps the capture in the log only and writes nothing to your notes.'
 *   example: '~/Notes'
 * - name: inbox
 *   param_type: string
 *   required: false
 *   default: 'Inbox.md'
 *   description: 'The one file inside vault_dir this Play appends to. Created with a heading if it does not exist.'
 *   example: 'Inbox.md'
 * - name: state_dir
 *   param_type: string
 *   required: false
 *   default: '~/.rote-micro'
 *   description: 'The one directory this Play writes to. One append-only JSONL file per stream; nothing is ever deleted or rewritten in place.'
 *   example: '~/.rote-micro'
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
 *   record:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'jot'
 *     - 'record'
 *     - '--note'
 *     - '$note'
 *     - '--vault-dir'
 *     - '$vault_dir'
 *     - '--inbox'
 *     - '$inbox'
 *     - '--state-dir'
 *     - '$state_dir'
 *     - '--now'
 *     - '$now'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - record
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'jot'
 *     - 'report'
 *     - '--vault-dir'
 *     - '$vault_dir'
 *     - '--inbox'
 *     - '$inbox'
 *     - '--state-dir'
 *     - '$state_dir'
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
    { label: "record", step: ctx.step(stepName("record")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.today ?? 0} captured today · ${j.inbox_lines ?? 0} sitting in the inbox`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
