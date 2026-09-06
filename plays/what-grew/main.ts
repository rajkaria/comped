#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: what-grew
 * description: 'Something ate 40 GB and nothing will tell you what. Every disk tool answers the wrong question: they show what is big, and what is big is mostly what was always big. The useful question is what *moved*, and nothing can answer it without having looked before. So this Play is built around a baseline rather than a scan — one bounded walk records a directory-size snapshot, and every run after that says what changed.
 *
 * It walks the tree you name with `os.scandir`, reading directory entries and `stat` results. It opens no file it measures. Sizes are on-disk sizes wherever the filesystem exposes them, so APFS clones and sparse files do not inflate the total; the apparent total is printed alongside so the gap is visible rather than silently chosen for you.
 *
 * Four rules the report keeps. The first run has nothing to compare against and says exactly that: it records the baseline and tells you when to come back, rather than printing a zero delta as though the disk had stood still. Growth and shrinkage are reported in separate classes — newly appeared, grew in place, shrank in place, deleted — because a folder that vanished is not the same event as a folder that got smaller, and merging them loses the only fact worth having. The reclaim figure counts regenerable bytes only, caches and build output a command can rebuild, and is kept strictly apart from data nobody can regenerate, because a headline that mixes the two is an invitation to delete the wrong thing. And nothing is ever deleted, moved or opened.
 *
 * You get the total, the folders that moved most in each direction with their names, free space, the net change since the baseline you chose, and how many past baselines are being kept.
 *
 * - Reads: directory entries and `stat` results under `root`. No file it measures is ever opened.
 * - Never reads: file contents of any kind, and no credential, keychain, token or password file. This Play needs no account and has no login step.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. No folder name leaves this machine.
 * - Writes: only inside `out_dir`, which is created if missing — the report, and the baselines the next run compares against. Every written path is listed in the run output. Nothing under `root` is modified.
 * - Degrades, never fails: a folder that cannot be read is reported by name with the reason and the run still completes. A walk that hits its own entry or time bound says so and reports its totals as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against a bundled synthetic tree that already carries two baselines, so the comparison has something to show on the very first run.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/what-grew
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
 *     - job-disk-reclaim
 *     - job-storage-trend
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-finder
 * tags:
 * - domain-personal-computing
 * - job-disk-reclaim
 * - job-storage-trend
 * - audience-everyone
 * - effect-read-only
 * - tool-finder
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-disk-reclaim
 *   - job-storage-trend
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-finder
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       total_bytes:
 *         type: integer
 *       reclaim_bytes:
 *         type: integer
 *       dirs_named:
 *         type: integer
 *       files:
 *         type: integer
 *       free_bytes:
 *         type: integer
 *       net_bytes:
 *         type: integer
 *       first_run:
 *         type: boolean
 *       baselines_held:
 *         type: integer
 * presentation_fixtures:
 *   read_home: resources/presentation-fixtures/read_home/fixture.yaml
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
 *   description: 'true runs the whole Play against a bundled synthetic folder tree with two retained baselines, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '~'
 *   description: 'The tree to measure. Every folder under it is sized; no file it measures is ever opened.'
 *   example: '~'
 * - name: depth
 *   param_type: integer
 *   required: false
 *   default: '4'
 *   description: 'How deep to name folders. Everything below the depth is still counted, and rolled into its parent.'
 *   example: '4'
 * - name: floor_bytes
 *   param_type: integer
 *   required: false
 *   default: '16777216'
 *   description: 'Folders below this size are counted but not named, so the table is the folders that matter rather than every folder there is.'
 *   example: '16777216'
 * - name: since
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Which retained baseline to diff against: last, first, a number of runs back, 7d/2w/3m, or a date. Empty means the most recent one.'
 *   example: 'last'
 * - name: keep_baselines
 *   param_type: integer
 *   required: false
 *   default: '10'
 *   description: 'How many past measurements to retain under out_dir. They are what make the second run say what moved.'
 *   example: '10'
 * - name: write_baseline
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true records this measurement for the next run to compare against. false reports and records nothing.'
 *   example: 'true'
 * steps:
 *   read_home:
 *     type: process.exec
 *     timeout_ms: 420000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'grew-read'
 *     - '--source'
 *     - 'home'
 *     - '--root'
 *     - '$root'
 *     - '--depth'
 *     - '$depth'
 *     - '--floor-bytes'
 *     - '$floor_bytes'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - read_home
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'grew-report'
 *     - '--since'
 *     - '$since'
 *     - '--keep-baselines'
 *     - '$keep_baselines'
 *     - '--write-baseline'
 *     - '$write_baseline'
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
    { label: "read_home", step: ctx.step(stepName("read_home")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${Math.round((j.total_bytes ?? 0) / 1e8) / 10} GB across ${j.dirs_named ?? 0} named folders${j.first_run ? "; first run, so there is nothing to compare it with yet" : `, net ${Math.round((j.net_bytes ?? 0) / 1e8) / 10} GB since the baseline`}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
