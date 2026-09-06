#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: night-shift
 * description: 'Every editor and every dashboard shows commit times in whatever zone this machine is set to today, which quietly rewrites your history every time you travel or change laptops. Git records the committer''s own UTC offset inside the timestamp, so a commit made at 04:12 in Tokyo is a 04:12 commit for ever. This reads that offset intact and answers, from the record rather than from memory, how much of your work lands after midnight.
 *
 * Every git repository under a root you choose, read through one fixed, read-only `git` command line. Every hour, weekday and calendar date on the card is the wall clock the committer''s own offset encodes, never this machine''s idea of local time. Commits are matched to you by the addresses git already knows, plus any others you name.
 *
 * The distributions are the easy half. The half worth having is the correlation: for late commits against the rest, how often a commit was later reverted, how often a fix-up followed it within the hour, and how long its subject line was — three recorded facts, each printed with its denominator beside it, which is the only reason they belong on a card at all. You also get the weekend count, the longest unbroken run of days, and the stretches that were rebased, reported rather than straightened out.
 *
 * Two things this deliberately does not do. It does not interpret: these are counts of commits, they are not a measure of health, sleep, wellbeing or output quality, and nothing here offers advice. And it does not guess at a time zone: when more than one UTC offset appears in the window the card says so, because a fortnight abroad and a changed routine look identical in an hour histogram and only one of them is about your schedule.
 *
 * - Reads: git repositories under `root`, through `git log` and its read-only siblings. No working-tree file is opened and nothing outside `root` is looked at.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. The git commands it will run are an allow-list that contains nothing able to change a repository — no commit, no checkout, no fetch, no clean.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: a repository with no commits, a missing git, a directory that cannot be read, and a shallow clone are each reported by name with the reason, and the run still completes. A scan that hits its own repository or time bound says so and reports its counts as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against a bundled synthetic commit history with nothing configured, before you point it at your own.
 *
 * Requires python3 3.9 or newer, and `git` for a real run. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/night-shift
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
 *     - job-work-pattern-review
 *     - job-burnout-check
 *     - audience-engineering-teams
 *     - effect-read-only
 *     - tool-git
 * tags:
 * - domain-software-engineering
 * - job-work-pattern-review
 * - job-burnout-check
 * - audience-engineering-teams
 * - effect-read-only
 * - tool-git
 * discoverability:
 *   tags:
 *   - domain-software-engineering
 *   - job-work-pattern-review
 *   - job-burnout-check
 *   - audience-engineering-teams
 *   - effect-read-only
 *   - tool-git
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       commits:
 *         type: integer
 *       days:
 *         type: integer
 *       late:
 *         type: integer
 *       weekend:
 *         type: integer
 *       longest_streak:
 *         type: integer
 *       repos:
 *         type: integer
 * presentation_fixtures:
 *   read_commits: resources/presentation-fixtures/read_commits/fixture.yaml
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
 *   description: 'true runs the whole Play against a bundled synthetic commit history, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '~'
 *   description: 'Every git repository under this folder has its commit log read. Nothing outside it is opened.'
 *   example: '~/Projects'
 * - name: days
 *   param_type: integer
 *   required: false
 *   default: '90'
 *   description: 'How many days back to read. The same value is passed to the read and the report, so the denominator on the card is the window you asked for.'
 *   example: '90'
 * - name: emails
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Comma separated. Commits are matched to you by the addresses git already knows; add any others here so a second identity is not counted as somebody else.'
 *   example: 'you@work.example,you@home.example'
 * - name: late_hour
 *   param_type: integer
 *   required: false
 *   default: '23'
 *   description: 'Local hour after which a commit counts as late. 23 means from 11pm.'
 *   example: '23'
 * - name: dawn_hour
 *   param_type: integer
 *   required: false
 *   default: '5'
 *   description: 'Local hour the late window closes. 5 means the window runs 11pm to 5am.'
 *   example: '5'
 * - name: fixup_minutes
 *   param_type: integer
 *   required: false
 *   default: '60'
 *   description: 'A commit that amends or fixes another within this many minutes is counted as a fixup, which is how the card compares late work with the rest.'
 *   example: '60'
 * steps:
 *   read_commits:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'nightshift-read'
 *     - '--source'
 *     - 'commits'
 *     - '--root'
 *     - '$root'
 *     - '--days'
 *     - '$days'
 *     - '--emails'
 *     - '$emails'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - read_commits
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'nightshift-report'
 *     - '--days'
 *     - '$days'
 *     - '--late-hour'
 *     - '$late_hour'
 *     - '--dawn-hour'
 *     - '$dawn_hour'
 *     - '--fixup-minutes'
 *     - '$fixup_minutes'
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
    { label: "read_commits", step: ctx.step(stepName("read_commits")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.commits ?? 0} commits over ${j.days ?? 0} days, ${j.late ?? 0} of them late and ${j.weekend ?? 0} at the weekend, longest run of days ${j.longest_streak ?? 0}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
