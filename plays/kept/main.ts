#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: kept
 * description: 'Every other number a coding agent produces is about what it cost. This one is about what it was worth: of everything the agent wrote for you, how much of it is still in the file. Git already knows the answer and nobody asks it.
 *
 * It reads two things. The session transcripts your agents already keep — Claude Code, Codex and Pi — for the file-writing tool calls and the times they happened, and nothing else in them: no prompt, no reply, no model name, no content. Then, in the repositories under a root you choose, one fixed read-only `git` command line for the commits and the blame that say what became of those lines.
 *
 * The whole Play rests on one heuristic, and because the heuristic is arguable it is printed verbatim on the report rather than buried. Git records who *committed* a line, never who *typed* it, so a line is called the agent''s when the commit that introduced it has an author time inside a session window — from the first file-writing call in that session to the last, plus a grace period. That miscounts in both directions and the two errors do not cancel. What makes the answer honest anyway is the control group: the identical computation over the same files outside every window, which is you. A survival rate with nothing to compare it against is a dunk, not a measurement, so the card prints both or it prints neither.
 *
 * You get the lines ever written and the lines still alive for both, the gap between the two survival rates, where the rest went — reverted, deleted with the file, rewritten by a later edit, never committed at all — and a half-life curve with a denominator on every bucket. Everything expensive is bounded and every bound is reported, because a blame that was cut short gives a lower bound and a lower bound presented as a total is a lie.
 *
 * - Reads: the session transcript folders you name, for file-write records only, and git repositories under `root` through `git log`, `git blame` and their read-only siblings.
 * - Never reads: any credential, keychain, token or password file. This Play needs no account and has no login step. It does not read prompts, replies or any conversation content, and the git commands it will run are an allow-list containing nothing able to change a repository.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: an agent you do not use, a repository with no commits, a missing git and a shallow clone are each reported by name with the reason, and the run still completes. A shallow clone lowers the confidence rating on that repository''s answer rather than being quietly averaged in.
 * - Runs cold: set `demo=true` to run the whole Play against a bundled synthetic transcript set and two synthetic repositories with nothing configured, before you point it at your own.
 *
 * Requires python3 3.9 or newer, and `git` for a real run. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/kept
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
 *     - domain-software-engineering
 *     - job-agent-output-audit
 *     - job-code-survival
 *     - audience-engineering-teams
 *     - effect-read-only
 *     - tool-git
 *     - tool-claude-code
 * tags:
 * - domain-software-engineering
 * - job-agent-output-audit
 * - job-code-survival
 * - audience-engineering-teams
 * - effect-read-only
 * - tool-git
 * - tool-claude-code
 * discoverability:
 *   tags:
 *   - domain-software-engineering
 *   - job-agent-output-audit
 *   - job-code-survival
 *   - audience-engineering-teams
 *   - effect-read-only
 *   - tool-git
 *   - tool-claude-code
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       agent_ever:
 *         type: integer
 *       agent_alive:
 *         type: integer
 *       human_ever:
 *         type: integer
 *       human_alive:
 *         type: integer
 *       survival:
 *         type: integer
 *       sessions:
 *         type: integer
 *       repos:
 *         type: integer
 * presentation_fixtures:
 *   read_agent: resources/presentation-fixtures/read_agent/fixture.yaml
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
 *   description: 'true runs the whole Play against a bundled synthetic transcript set and two synthetic repositories, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: root
 *   param_type: string
 *   required: false
 *   default: '~'
 *   description: 'Every git repository under this folder is blamed for the lines the transcripts say an agent wrote. Nothing outside it is opened.'
 *   example: '~/Projects'
 * - name: claude_dir
 *   param_type: string
 *   required: false
 *   default: '~/.claude/projects'
 *   description: 'Where Claude Code keeps its session transcripts. Only the file-write records in them are read.'
 *   example: '~/.claude/projects'
 * - name: codex_dir
 *   param_type: string
 *   required: false
 *   default: '~/.codex/sessions'
 *   description: 'Where Codex keeps its session transcripts. Missing is an expected absence, not an error.'
 *   example: '~/.codex/sessions'
 * - name: pi_dir
 *   param_type: string
 *   required: false
 *   default: '~/.pi/sessions'
 *   description: 'Where Pi keeps its session transcripts. Missing is an expected absence, not an error.'
 *   example: '~/.pi/sessions'
 * - name: max_repos
 *   param_type: integer
 *   required: false
 *   default: '200'
 *   description: 'Stop after this many repositories. The card says when the bound was reached.'
 *   example: '200'
 * - name: grace_minutes
 *   param_type: integer
 *   required: false
 *   default: '30'
 *   description: 'How long after an agent wrote a file a commit may still be credited to that write. Beyond this the lines are treated as yours.'
 *   example: '30'
 * - name: min_lines
 *   param_type: integer
 *   required: false
 *   default: '20'
 *   description: 'Writes smaller than this are left out of the survival rate: a two-line edit tells you nothing and moves the percentage a lot.'
 *   example: '20'
 * - name: max_blame_files
 *   param_type: integer
 *   required: false
 *   default: '300'
 *   description: 'The most files to run blame over. Blame is the slow half of this Play, so this is the knob that decides how long it takes.'
 *   example: '300'
 * steps:
 *   read_agent:
 *     type: process.exec
 *     timeout_ms: 180000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'kept-read'
 *     - '--source'
 *     - 'agent'
 *     - '--claude-dir'
 *     - '$claude_dir'
 *     - '--codex-dir'
 *     - '$codex_dir'
 *     - '--pi-dir'
 *     - '$pi_dir'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_git:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'kept-read'
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
 *     timeout_ms: 300000
 *     depends_on:
 *     - read_agent
 *     - read_git
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'kept-report'
 *     - '--grace-minutes'
 *     - '$grace_minutes'
 *     - '--min-lines'
 *     - '$min_lines'
 *     - '--max-blame-files'
 *     - '$max_blame_files'
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
    { label: "read_agent", step: ctx.step(stepName("read_agent")) },
    { label: "read_git", step: ctx.step(stepName("read_git")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.agent_alive ?? 0} of ${j.agent_ever ?? 0} agent-written lines are still in the file${j.survival === null || j.survival === undefined ? "" : ` (${j.survival}% of them)`}, across ${j.sessions ?? 0} session(s)`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
