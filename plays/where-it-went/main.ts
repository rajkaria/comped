#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: where-it-went
 * description: 'A browser will show you the last nine things you opened. It will not tell you that one domain took a fifth of your quarter, that you opened the same question thirty-one times, or that your longest unbroken run at one site was four hours on a Tuesday afternoon. All of that is already sitting in a SQLite file on this machine, so this reads it and says so.
 *
 * Three families, three schemas, three different epochs, read independently and with no browser running. Chromium-family browsers, Firefox-family browsers and Safari each store visits their own way; each profile is read separately, so a second Chrome profile is its own row. The database is copied and opened read-only, so a browser that is running is not disturbed and nothing is ever written back to it.
 *
 * You get the visit count over the window, the domains that took the most of it, a category rollup from a lookup table that ships inside the package so you can read what it claims, sessions reconstructed from the gaps between visits, the longest single-domain run with the day it happened, and the hour-of-day and weekday shapes. Repeat visits to the same URL are counted separately, because opening one page thirty-one times is a different fact from opening thirty-one pages.
 *
 * What it reads is the history table and nothing else. The code names, once and in one place, the stores it deliberately never touches — form data, saved logins, autofill — and a test asserts those words appear nowhere else in the module: not as a table name, not as a path, not as a query. URLs are reduced to hostnames on the card and query strings never appear anywhere.
 *
 * - Reads: the visit history table of each browser profile listed above, through a read-only copy. Nothing else on your disk is opened.
 * - Never reads: saved passwords, autofill, form data, cookies, or any credential, keychain, token or password file. This Play needs no account and has no login step.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. No URL you visited is looked up anywhere; the categories come from a table bundled in the package.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: a browser this machine does not have, or one that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against bundled synthetic history databases with nothing configured, before you point it at your own machine.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/where-it-went
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
 *     - job-attention-audit
 *     - job-browsing-review
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-chrome
 *     - tool-firefox
 *     - tool-safari
 * tags:
 * - domain-personal-computing
 * - job-attention-audit
 * - job-browsing-review
 * - audience-everyone
 * - effect-read-only
 * - tool-chrome
 * - tool-firefox
 * - tool-safari
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-attention-audit
 *   - job-browsing-review
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-chrome
 *   - tool-firefox
 *   - tool-safari
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       visits:
 *         type: integer
 *       days:
 *         type: integer
 *       domains:
 *         type: integer
 *       unique_urls:
 *         type: integer
 *       categories:
 *         type: integer
 *       verdict:
 *         type: string
 * presentation_fixtures:
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
 *   description: 'true runs the whole Play against bundled synthetic history databases for three browsers, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: days
 *   param_type: integer
 *   required: false
 *   default: '90'
 *   description: 'How many days of history to read. The same value is passed to the read and the report, so the denominator on the card is the window you asked for.'
 *   example: '90'
 * - name: gap_minutes
 *   param_type: integer
 *   required: false
 *   default: '30'
 *   description: 'A gap this long between two visits starts a new session. It is what turns a list of visits into a run of time you can recognise.'
 *   example: '30'
 * - name: top
 *   param_type: integer
 *   required: false
 *   default: '10'
 *   description: 'How many domains and categories to name on the card. The totals are over everything, not just the rows shown.'
 *   example: '10'
 * - name: tz
 *   param_type: string
 *   required: false
 *   default: 'local'
 *   description: 'local reads this machine''s zone; utc reads everything in UTC. The hour-of-day histogram is the only thing that changes.'
 *   example: 'local'
 * steps:
 *   read_chromium:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'history-read'
 *     - '--source'
 *     - 'chromium'
 *     - '--days'
 *     - '$days'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_firefox:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'history-read'
 *     - '--source'
 *     - 'firefox'
 *     - '--days'
 *     - '$days'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_safari:
 *     type: process.exec
 *     timeout_ms: 90000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'history-read'
 *     - '--source'
 *     - 'safari'
 *     - '--days'
 *     - '$days'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - read_chromium
 *     - read_firefox
 *     - read_safari
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'history-report'
 *     - '--days'
 *     - '$days'
 *     - '--gap-minutes'
 *     - '$gap_minutes'
 *     - '--top'
 *     - '$top'
 *     - '--tz'
 *     - '$tz'
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
    { label: "read_safari", step: ctx.step(stepName("read_safari")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.visits ?? 0} page visits over ${j.days ?? 0} days across ${j.domains ?? 0} domains${j.categories ? `, sorted into ${j.categories} categories` : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
