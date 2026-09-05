#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: desktop-clutter
 * description: 'The Desktop and the Downloads folder are append-only in practice. Things arrive, nothing leaves, and the Finder sorts by name so the oldest file in there is invisible. Every fact needed to fix that is already in the file system.
 *
 * This counts both folders, and the screenshot folder as well when you have moved it somewhere else, which it learns from the same preference macOS wrote when you changed it. You get the file count and total size, the oldest file with its date, an age histogram in both files and bytes, what the files actually are as screenshots, installers, archives, documents and media, and the biggest files with how long since each was touched.
 *
 * Duplicates are proven, not guessed. Files of the same size and type are only candidates; each cluster is then hashed and only files with identical contents are reported as duplicates, and the report states which test it applied. Set hash_duplicates=false for a faster pass, and the wording changes to say the contents were not compared, because a claim you cannot support should not read the same as one you can.
 *
 * It ends with a grade from A to F built from three things: how many files, how many of them are cold, and how many duplicate groups. It is the same formula on every machine, so the grade is comparable with someone else''s.
 *
 * Nothing is moved, renamed or deleted. Contents are read only to prove a duplicate.
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
 * source_url: https://play.modiqo.ai/rajkaria/desktop-clutter
 * metadata:
 *   version: '0.1.0'
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
 *     - domain-personal-computing
 *     - job-disk-reclaim
 *     - job-desktop-cleanup
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-finder
 * tags:
 * - domain-personal-computing
 * - job-disk-reclaim
 * - job-desktop-cleanup
 * - audience-everyone
 * - effect-read-only
 * - tool-finder
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-disk-reclaim
 *   - job-desktop-cleanup
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-finder
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       files:
 *         type: integer
 *       bytes:
 *         type: integer
 *       cold:
 *         type: integer
 *       screenshots:
 *         type: integer
 *       duplicates:
 *         type: integer
 *       reclaimable:
 *         type: integer
 *       grade:
 *         type: string
 * presentation_fixtures:
 *   read_desktop: resources/presentation-fixtures/read_desktop/fixture.yaml
 *   read_downloads: resources/presentation-fixtures/read_downloads/fixture.yaml
 *   read_screenshots: resources/presentation-fixtures/read_screenshots/fixture.yaml
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
 *   description: 'true runs against a bundled synthetic folder listing with real ages, so the card is the same on every machine.'
 *   example: 'false'
 * - name: cold_days
 *   param_type: integer
 *   required: false
 *   default: '90'
 *   description: 'A file untouched for this many days is counted as cold.'
 *   example: '90'
 * - name: hash_duplicates
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true hashes same-size candidates so only identical files are reported. false is faster and says so.'
 *   example: 'true'
 * - name: desktop_dir
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Override the Desktop location. Empty means ~/Desktop.'
 *   example: ''
 * - name: downloads_dir
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Override the Downloads location. Empty means ~/Downloads.'
 *   example: ''
 * steps:
 *   read_desktop:
 *     type: process.exec
 *     timeout_ms: 90000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'clutter-read'
 *     - '--source'
 *     - 'desktop'
 *     - '--desktop-dir'
 *     - '$desktop_dir'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_downloads:
 *     type: process.exec
 *     timeout_ms: 90000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'clutter-read'
 *     - '--source'
 *     - 'downloads'
 *     - '--downloads-dir'
 *     - '$downloads_dir'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_screenshots:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'clutter-read'
 *     - '--source'
 *     - 'screenshots'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - read_desktop
 *     - read_downloads
 *     - read_screenshots
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'clutter-report'
 *     - '--cold-days'
 *     - '$cold_days'
 *     - '--hash-duplicates'
 *     - '$hash_duplicates'
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
    { label: "read_desktop", step: ctx.step(stepName("read_desktop")) },
    { label: "read_downloads", step: ctx.step(stepName("read_downloads")) },
    { label: "read_screenshots", step: ctx.step(stepName("read_screenshots")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.files ?? 0} files on the Desktop and in Downloads, ${j.cold ?? 0} untouched, ${Math.round((j.reclaimable ?? 0) / 1e8) / 10} GB reclaimable, grade ${j.grade ?? "?"}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
