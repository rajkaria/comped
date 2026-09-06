#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: photo-debt
 * description: 'A photo library only ever grows. The shutter fires ten times to get one usable frame, every screenshot lands next to the family album, and the same image arrives again from a message, an AirDrop and a download. None of that is visible in the Photos app, which is organised by date and by face rather than by waste, so the honest number — how much of this is not really photographs — has never been on screen.
 *
 * It reads the Photos library''s own database, through a copy opened read-only so the library is never touched, and a folder of loose images alongside it. What it reads is file metadata: name, size, dates, dimensions. For duplicate confirmation it hashes bytes; no image is ever decoded, displayed, uploaded or moved.
 *
 * Three separate claims, each carrying its own confidence and never added together without saying which is which. Files whose bytes are byte-for-byte identical: a fact. Extra frames from a burst, inferred from capture time, dimensions and file name: an inference. Screenshots old enough to have served their purpose: a judgement, and you set the age. You get all three with their own totals, the largest groups by name, and how much disk each class would give back.
 *
 * Two things this deliberately does not do. It never deletes, moves or renames anything: the output is a list to review, and every removal stays a decision you make in the Photos app, where there is an undo. And it never compares images by content similarity — the standard library decodes neither JPEG nor HEIC, an imaging package would break the stdlib-only promise, and shelling out to a converter would break the no-child-process promise. So "duplicate" here always means identical bytes, and "near-duplicate" always means metadata, never pixels.
 *
 * - Reads: the Photos library database (through a read-only copy) and file metadata under the image folder you name. Candidate duplicates are hashed. Nothing else on your disk is opened.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. It reads no face, place or person data, and no image is decoded.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. No photo, thumbnail or hash leaves this machine.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output. Nothing in your library or your image folder is ever modified.
 * - Degrades, never fails: a library this machine does not have, or one that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against a bundled synthetic library and image folder with nothing configured, before you point it at your own machine.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/photo-debt
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
 *     - job-photo-library-audit
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-photos
 * tags:
 * - domain-personal-computing
 * - job-disk-reclaim
 * - job-photo-library-audit
 * - audience-everyone
 * - effect-read-only
 * - tool-photos
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-disk-reclaim
 *   - job-photo-library-audit
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-photos
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       assets:
 *         type: integer
 *       bytes:
 *         type: integer
 *       duplicates:
 *         type: integer
 *       reclaimable:
 *         type: integer
 *       screenshots:
 *         type: integer
 *       burst_siblings:
 *         type: integer
 * presentation_fixtures:
 *   read_folder: resources/presentation-fixtures/read_folder/fixture.yaml
 *   read_photos: resources/presentation-fixtures/read_photos/fixture.yaml
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
 *   description: 'true runs the whole Play against a bundled synthetic photo library and image folder, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: library
 *   param_type: string
 *   required: false
 *   default: '~/Pictures/Photos Library.photoslibrary'
 *   description: 'The Photos library to read. Its database is copied and opened read-only; the library itself is never modified and no image is opened.'
 *   example: '~/Pictures/Photos Library.photoslibrary'
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '~/Pictures'
 *   description: 'A folder of loose images to read alongside the library. Only file metadata is read.'
 *   example: '~/Pictures'
 * - name: burst_window
 *   param_type: integer
 *   required: false
 *   default: '2'
 *   description: 'Seconds. Photos taken within this of each other are treated as one burst, which is what separates nine tries at one picture from nine pictures.'
 *   example: '2'
 * - name: screenshot_days
 *   param_type: integer
 *   required: false
 *   default: '90'
 *   description: 'A screenshot older than this is counted as debt: it was made to be looked at once.'
 *   example: '90'
 * - name: top
 *   param_type: integer
 *   required: false
 *   default: '5'
 *   description: 'How many groups to name on the card. The totals are over everything, not just the rows shown.'
 *   example: '5'
 * - name: hash_dupes
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true reads candidate files to confirm a duplicate by content. false compares size and date only, which is faster and less certain.'
 *   example: 'true'
 * steps:
 *   read_photos:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'photos-read'
 *     - '--source'
 *     - 'photos'
 *     - '--library'
 *     - '$library'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_folder:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'photos-read'
 *     - '--source'
 *     - 'folder'
 *     - '--root'
 *     - '$root'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 300000
 *     depends_on:
 *     - read_photos
 *     - read_folder
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'photos-report'
 *     - '--burst-window'
 *     - '$burst_window'
 *     - '--screenshot-days'
 *     - '$screenshot_days'
 *     - '--top'
 *     - '$top'
 *     - '--hash-dupes'
 *     - '$hash_dupes'
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
    { label: "read_photos", step: ctx.step(stepName("read_photos")) },
    { label: "read_folder", step: ctx.step(stepName("read_folder")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.assets ?? 0} photos taking ${Math.round((j.bytes ?? 0) / 1e8) / 10} GB, ${j.duplicates ?? 0} duplicate group(s), ${Math.round((j.reclaimable ?? 0) / 1e8) / 10} GB reclaimable`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
