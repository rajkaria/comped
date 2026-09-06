#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: extension-reach
 * description: 'An extension''s install page shows its permissions once, in a dialog nobody re-reads, and then never again. The browser keeps the answer on disk for ever. This reads it and answers the question the browser stops asking after install day: what can see your bank tab, and is anyone still shipping updates for it.
 *
 * Three families, read independently and with no browser running. Chromium-family browsers keep a manifest per extension and a settings entry per profile saying whether it is enabled, where it was installed from and which hosts you actually granted. Firefox-family browsers keep the same facts in their own store. Safari publishes rather less, and where it publishes nothing that is reported as nothing rather than filled in. Every profile is read separately, so a second Chrome profile is its own row.
 *
 * You get the count, the extensions that can read every page you open, the ones that pair blanket page access with a second power — reading what you type, rewriting requests, seeing every tab — the ones nobody has shipped a fix for in a year, and the ones you installed and stopped using, which are the cheapest permissions to take back. Every tier says what it is based on, and a permission the manifest does not declare is never inferred.
 *
 * This reads manifests and settings metadata only. It never opens extension storage: idle detection looks at the modification *time* of a state folder with `os.stat`, and the folder is never opened. Nothing under a local-storage, database or cookie path is opened by this Play, and a test in the repository asserts that those words appear nowhere in its code as a path, a table or a query.
 *
 * - Reads: the extension manifests and profile settings files listed above, plus the modification time of each extension''s state folder. Nothing else on your disk is opened.
 * - Never reads: extension storage, browsing data, cookies, or any credential, keychain, token or password file. This Play needs no account and has no login step.
 * - Never sends: `daily_core` imports no `urllib`, `http`, `socket` or `ssl`, which a test in the repository asserts on every commit. There is no network step, so there is nothing to opt out of. Nothing is looked up about an extension anywhere; every judgement comes from files already on this machine.
 * - Writes: only inside `out_dir`, which is created if missing. Every written path is listed in the run output.
 * - Degrades, never fails: a browser this machine does not have, or one that macOS will not let a terminal read, is reported by name with the reason and the run still completes. A scan that hits its own file or time bound says so and reports its counts as a lower bound.
 * - Runs cold: set `demo=true` to run the whole Play against bundled synthetic extension stores with nothing configured, before you point it at your own machine.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters, no credentials.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/extension-reach
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
 *     - job-browser-extension-audit
 *     - job-permission-review
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-chrome
 *     - tool-firefox
 *     - tool-safari
 * tags:
 * - domain-personal-computing
 * - job-browser-extension-audit
 * - job-permission-review
 * - audience-everyone
 * - effect-read-only
 * - tool-chrome
 * - tool-firefox
 * - tool-safari
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-browser-extension-audit
 *   - job-permission-review
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-chrome
 *   - tool-firefox
 *   - tool-safari
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       extensions:
 *         type: integer
 *       installs:
 *         type: integer
 *       browsers:
 *         type: integer
 *       all_urls:
 *         type: integer
 *       blanket:
 *         type: integer
 *       stale:
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
 *   description: 'true runs the whole Play against bundled synthetic extension stores for five browsers, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: roots
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Comma separated. Leave empty to use the standard locations for every Chromium-family and Firefox-family browser this machine has.'
 *   example: '~/Library/Application Support/Google/Chrome'
 * - name: safari_roots
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Comma separated path prefixes for Safari''s extension stores. Leave empty for the standard locations.'
 *   example: '~/Library/Containers'
 * - name: stale_days
 *   param_type: integer
 *   required: false
 *   default: '365'
 *   description: 'An extension whose files have not changed in this many days is reported as stale: nobody has shipped it a fix, and it can still read every page you open.'
 *   example: '365'
 * - name: idle_days
 *   param_type: integer
 *   required: false
 *   default: '90'
 *   description: 'An installed extension you have not used in this many days is reported as idle, which is the cheapest permission to take back.'
 *   example: '90'
 * steps:
 *   read_chromium:
 *     type: process.exec
 *     timeout_ms: 90000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'extensions-read'
 *     - '--source'
 *     - 'chromium'
 *     - '--roots'
 *     - '$roots'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_firefox:
 *     type: process.exec
 *     timeout_ms: 90000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'extensions-read'
 *     - '--source'
 *     - 'firefox'
 *     - '--roots'
 *     - '$roots'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_safari:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'extensions-read'
 *     - '--source'
 *     - 'safari'
 *     - '--safari-roots'
 *     - '$safari_roots'
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
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'extensions-report'
 *     - '--stale-days'
 *     - '$stale_days'
 *     - '--idle-days'
 *     - '$idle_days'
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
  out.summary(`${j.extensions ?? 0} extensions across ${j.browsers ?? 0} browser(s), ${j.all_urls ?? 0} able to read every page, ${j.stale ?? 0} not updated in a year`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
