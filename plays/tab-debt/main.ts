#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: tab-debt
 * description: 'Your browser shows a tab strip. It never shows you a number, and it never shows you a date. Both are sitting in the session files the browser already writes, so this reads them and answers what the strip cannot: how many tabs are open across every browser on the machine, and how long since each one was actually looked at.
 *
 * Four formats, read directly and with no browser running. Chrome, Brave, Edge, Chromium, Vivaldi, Opera and Comet keep the live tab set as an SNSS command log, which is replayed here rather than scanned, because the last navigation recorded for a tab is the page it is showing and a tab closed later must not appear at all. Firefox, Zen and LibreWolf keep theirs as JSON inside an LZ4 container, decoded here by a decompressor written for the purpose. Safari and Arc keep property lists and a JSON sidebar store. Every profile is read separately, so a second Chrome profile is its own row.
 *
 * You get the count, the oldest tab with the date it was last used, an age histogram, the sites the tabs actually belong to, the pages open more than once and how many would close with nothing lost, and Safari''s reading list backlog with the date each item was saved. A tab whose browser recorded no last-used time is counted in the total and left out of every age figure, and the number of those is printed, because a cold-tab count quietly computed over half your tabs would be worse than one that admits what it could not judge.
 *
 * URLs are reduced to hostnames by default and query strings never appear anywhere, so the card is safe to show someone. Set keep_path=true to keep paths locally.
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
 * source_url: https://play.modiqo.ai/rajkaria/tab-debt
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
 *     - job-browser-tab-audit
 *     - job-attention-hygiene
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-chrome
 *     - tool-firefox
 *     - tool-safari
 * tags:
 * - domain-personal-computing
 * - job-browser-tab-audit
 * - job-attention-hygiene
 * - audience-everyone
 * - effect-read-only
 * - tool-chrome
 * - tool-firefox
 * - tool-safari
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-browser-tab-audit
 *   - job-attention-hygiene
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-chrome
 *   - tool-firefox
 *   - tool-safari
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       tabs:
 *         type: integer
 *       windows:
 *         type: integer
 *       cold:
 *         type: integer
 *       duplicates:
 *         type: integer
 *       oldest_days:
 *         type: integer
 *       browsers:
 *         type: integer
 *       verdict:
 *         type: string
 * presentation_fixtures:
 *   read_arc: resources/presentation-fixtures/read_arc/fixture.yaml
 *   read_chromium: resources/presentation-fixtures/read_chromium/fixture.yaml
 *   read_firefox: resources/presentation-fixtures/read_firefox/fixture.yaml
 *   read_safari: resources/presentation-fixtures/read_safari/fixture.yaml
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
 *   description: 'true runs the whole Play against bundled synthetic sessions, so a first run needs nothing installed.'
 *   example: 'false'
 * - name: keep_path
 *   param_type: string
 *   required: false
 *   default: 'false'
 *   description: 'false shows hostnames only. true keeps the path as well; query strings and fragments are dropped either way.'
 *   example: 'false'
 * steps:
 *   read_chromium:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'tabs-read'
 *     - '--source'
 *     - 'chromium'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_firefox:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'tabs-read'
 *     - '--source'
 *     - 'firefox'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_safari:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'tabs-read'
 *     - '--source'
 *     - 'safari'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_arc:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'tabs-read'
 *     - '--source'
 *     - 'arc'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - read_chromium
 *     - read_firefox
 *     - read_safari
 *     - read_arc
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'tabs-report'
 *     - '--keep-path'
 *     - '$keep_path'
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
    { label: "read_chromium", step: ctx.step(stepName("read_chromium")) },
    { label: "read_firefox", step: ctx.step(stepName("read_firefox")) },
    { label: "read_safari", step: ctx.step(stepName("read_safari")) },
    { label: "read_arc", step: ctx.step(stepName("read_arc")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.tabs ?? 0} open tabs across ${j.browsers ?? 0} browser(s), ${j.cold ?? 0} untouched for a week or more${j.oldest_days ? `, oldest last used ${j.oldest_days} days ago` : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
