#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: bus-factor
 * description: 'Every team knows some of its code has exactly one author left and nobody knows which files those are. The facts that settle it are already in the repository — who wrote which line, when they last committed anything, and whether a second person has ever been in the file — so this reads them and does the arithmetic nobody does by hand.
 *
 * Every git repository under a root you choose, read through one fixed, read-only `git` command line. A file''s authors come from its whole history rather than from blame on the current text, because a person who wrote a file and was then edited over still knows it and blame has already forgotten them. Ownership is measured in lines written, which is the only size git gives without opening a working-tree file, so every count on the card says "lines written" and never "lines". Bots, vendored trees, generated code and lock files are excluded by name, and both the count kept and the count excluded are printed, because an exclusion you cannot see is an exclusion you cannot check.
 *
 * You get the number of files with a single author, the largest cluster of them in one directory with the name attached, whether that name has committed anywhere in the last year, the truck factor, and the files that are both sole-authored and untouched — the ones where the knowledge and the attention have both gone. The truck factor is computed greedily, largest owner first, which makes it an upper bound on the true minimum; the card says so, because a number that can only be wrong in one direction is worth more than one that could be wrong in either.
 *
 * Author names and addresses are reduced to initials unless you turn redaction off, and no address is printed in full on the card either way.
 *
 * - Reads: git repositories under `root`, through `git log`, `git blame` and their read-only siblings. No working-tree file is opened and nothing outside `root` is looked at.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. The git commands it will run are an allow-list that contains nothing able to change a repository — no commit, no checkout, no fetch, no clean.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: a repository with no commits, a missing git, a directory that cannot be read, and a shallow clone are each reported by name with the reason, and the run still completes. A shallow clone is reported as a lower bound, because a truncated history is exactly that. A scan that hits its own repository or time bound says so.
 * - Runs cold: set `demo=true` to run the whole Play against three bundled synthetic repositories with nothing configured, before you point it at your own.
 *
 * Requires python3 3.9 or newer, and `git` for a real run. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/bus-factor
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
 *     - domain-software-engineering
 *     - job-code-ownership-audit
 *     - job-risk-review
 *     - audience-engineering-teams
 *     - effect-read-only
 *     - tool-git
 * tags:
 * - domain-software-engineering
 * - job-code-ownership-audit
 * - job-risk-review
 * - audience-engineering-teams
 * - effect-read-only
 * - tool-git
 * discoverability:
 *   tags:
 *   - domain-software-engineering
 *   - job-code-ownership-audit
 *   - job-risk-review
 *   - audience-engineering-teams
 *   - effect-read-only
 *   - tool-git
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       repos:
 *         type: integer
 *       tracked_files:
 *         type: integer
 *       tracked_lines:
 *         type: integer
 *       sole_files:
 *         type: integer
 *       authors:
 *         type: integer
 *       truck_factor:
 *         type: integer
 *       stale_sole_files:
 *         type: integer
 *       verdict:
 *         type: string
 * presentation_fixtures:
 *   read_git: resources/presentation-fixtures/read_git/fixture.yaml
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
 *   description: 'true runs the whole Play against three bundled synthetic repositories, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '~'
 *   description: 'Every git repository under this folder is read, up to max_repos. Nothing outside it is opened.'
 *   example: '~/Projects'
 * - name: max_repos
 *   param_type: integer
 *   required: false
 *   default: '40'
 *   description: 'Stop after this many repositories. The card says when the bound was reached, so a partial answer never reads like a complete one.'
 *   example: '40'
 * - name: departed_days
 *   param_type: integer
 *   required: false
 *   default: '365'
 *   description: 'An author with no commit anywhere in this many days is treated as gone, which is what turns a sole-authored file into an orphaned one.'
 *   example: '365'
 * - name: stale_days
 *   param_type: integer
 *   required: false
 *   default: '365'
 *   description: 'A sole-authored file untouched for this long is counted as stale: nobody has looked at it recently either.'
 *   example: '365'
 * - name: threshold
 *   param_type: string
 *   required: false
 *   default: '0.5'
 *   description: 'The share of a file''s surviving lines one author must hold before the file is called theirs. 0.5 means a simple majority.'
 *   example: '0.5'
 * steps:
 *   read_git:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'busfactor-read'
 *     - '--source'
 *     - 'git'
 *     - '--root'
 *     - '$root'
 *     - '--max-repos'
 *     - '$max_repos'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 180000
 *     depends_on:
 *     - read_git
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'busfactor-report'
 *     - '--departed-days'
 *     - '$departed_days'
 *     - '--stale-days'
 *     - '$stale_days'
 *     - '--threshold'
 *     - '$threshold'
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
    { label: "read_git", step: ctx.step(stepName("read_git")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.tracked_files ?? 0} tracked files across ${j.repos ?? 0} repositor(y/ies), ${j.sole_files ?? 0} of them with a single author, truck factor ${j.truck_factor ?? "?"}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
