#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: reply-debt
 * description: 'An unread badge counts messages. It does not know the difference between a newsletter and somebody who asked you a direct question eleven days ago and is still waiting. That difference is what this counts: threads where the last word is not yours, somebody asked for something, and nothing went back.
 *
 * The Play is two programs on purpose, and the seam between them is a file. One step reads a window of your mailbox and writes a normalised JSON file into `out_dir`; that step is the only part of this package that opens a connection, it is one short file you can read before you run it, and it asks for message *headers* — from, to, cc, date, subject, list headers — plus the mailbox''s own one-line snippet. It does not ask for message bodies or attachments. The second half — the ageing, the card and the report — is `daily_core`, which imports no networking module at all and only ever reads that file. If the file is not there, that is a labelled absence and the run still completes.
 *
 * Debt is graded rather than counted. A direct ask — a question addressed to you by name — is separated from an implied one, and both from a thread where you were only copied in. Automated mail, mailing lists and calendar invitations are excluded and the number excluded is printed, because an exclusion you cannot see is an exclusion you cannot check. Threads waiting longer than the cold threshold are reported as cold on the honest grounds that the useful reply there is usually to say so.
 *
 * You get the debt count with its grades, the oldest threads with who is waiting and for how long, the share of your inbox that is really a mailing list, and the people you most often leave waiting. Names and addresses are reduced to initials unless you turn redaction off.
 *
 * - Reads: your mailbox, over HTTPS, for the window you chose — headers and snippets only — and then only the file that step wrote into `out_dir`. Nothing else on your disk is opened.
 * - Never reads: message bodies or attachments, and no credential file, keychain or token file. The mail step takes an OAuth access token from an environment variable you name and uses it for those requests only; it opens no keychain, stores no token, and prints none. With the variable unset the step says so and exits cleanly.
 * - Never sends: any mail. This Play composes nothing, saves no draft, marks nothing as read, and moves nothing. The mail step calls three read methods and no others, and there is no code path in it that writes to a mailbox. Nothing about your machine, your files or your paths is transmitted either. `daily_core`, which does all the analysis, imports no `urllib`, `http`, `socket` or `ssl` at all, and a test in the repository asserts that on every commit.
 * - Writes: only inside `out_dir`, which is created if missing — the normalised mail file, the report, and a baseline so the next run can say what moved. Every written path is listed in the run output.
 * - Degrades, never fails: no token, an expired token, a refused request or a machine with no network each become a labelled absence with the reason, and the run still completes with no threads to age rather than with an invented number.
 * - Runs cold: set `demo=true` to run the whole Play against a bundled synthetic mailbox of 52 threads. In that mode the mail step reads no environment variable and opens no connection at all, so a first run needs no account and no credential.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/reply-debt
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
 *     - domain-productivity
 *     - job-inbox-triage
 *     - job-followup-review
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-gmail
 * tags:
 * - domain-productivity
 * - job-inbox-triage
 * - job-followup-review
 * - audience-everyone
 * - effect-read-only
 * - tool-gmail
 * discoverability:
 *   tags:
 *   - domain-productivity
 *   - job-inbox-triage
 *   - job-followup-review
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-gmail
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       threads_seen:
 *         type: integer
 *       considered:
 *         type: integer
 *       debt:
 *         type: integer
 *       direct:
 *         type: integer
 *       implied:
 *         type: integer
 *       fyi:
 *         type: integer
 *       cold:
 *         type: integer
 *       excluded:
 *         type: integer
 * presentation_fixtures:
 *   fetch_mail: resources/presentation-fixtures/fetch_mail/fixture.yaml
 *   read_mail: resources/presentation-fixtures/read_mail/fixture.yaml
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
 *   description: 'true runs the whole Play against a bundled synthetic mailbox of 52 threads, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: days
 *   param_type: integer
 *   required: false
 *   default: '120'
 *   description: 'How many days of threads to fetch. A thread older than this is not read at all.'
 *   example: '120'
 * - name: max_threads
 *   param_type: integer
 *   required: false
 *   default: '400'
 *   description: 'The most threads to read. The card says when the bound was reached, so a partial answer never reads like a complete one.'
 *   example: '400'
 * - name: query
 *   param_type: string
 *   required: false
 *   default: '-in:chats'
 *   description: 'Added to the mailbox search alongside the window. The default leaves chat messages out.'
 *   example: '-in:chats'
 * - name: token_env
 *   param_type: string
 *   required: false
 *   default: 'GMAIL_OAUTH_TOKEN'
 *   description: 'The environment variable holding a Gmail OAuth access token with the gmail.metadata scope. No file is read for it, and if the variable is unset the Play says so and still runs.'
 *   example: 'GMAIL_OAUTH_TOKEN'
 * - name: min_age_days
 *   param_type: integer
 *   required: false
 *   default: '3'
 *   description: 'A thread younger than this is not debt yet. Three days is the difference between a backlog and an inbox.'
 *   example: '3'
 * - name: cold_days
 *   param_type: integer
 *   required: false
 *   default: '30'
 *   description: 'A thread waiting longer than this is reported as cold, because the honest answer there is usually to say so rather than to reply.'
 *   example: '30'
 * - name: me
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Comma separated. The mailbox already names one; add the others so a message you sent from a second address is not read as somebody writing to you.'
 *   example: 'you@example.com,you@work.example'
 * steps:
 *   fetch_mail:
 *     type: process.exec
 *     timeout_ms: 300000
 *     argv:
 *     - 'python3'
 *     - '@resource{fetch/mail_partial.py}'
 *     - '--partial'
 *     - '$out_dir/.reply-debt-mail.json'
 *     - '--days'
 *     - '$days'
 *     - '--max-threads'
 *     - '$max_threads'
 *     - '--query=$query'
 *     - '--token-env'
 *     - '$token_env'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_mail:
 *     type: process.exec
 *     timeout_ms: 90000
 *     depends_on:
 *     - fetch_mail
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'replydebt-read'
 *     - '--source'
 *     - 'mail'
 *     - '--partial'
 *     - '$out_dir/.reply-debt-mail.json'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 90000
 *     depends_on:
 *     - read_mail
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'replydebt-report'
 *     - '--min-age-days'
 *     - '$min_age_days'
 *     - '--cold-days'
 *     - '$cold_days'
 *     - '--me'
 *     - '$me'
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
    { label: "fetch_mail", step: ctx.step(stepName("fetch_mail")) },
    { label: "read_mail", step: ctx.step(stepName("read_mail")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.debt ?? 0} of ${j.considered ?? 0} threads are waiting on you, ${j.direct ?? 0} of them asked you directly, ${j.cold ?? 0} have gone cold`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
