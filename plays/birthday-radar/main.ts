#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: birthday-radar
 * description: 'Your address book already knows every birthday in it. It mentions them on the morning of, which is the one moment the information is useless. This reads the book you already have and sorts it by how soon, so the next one is a number of days rather than a surprise.
 *
 * Three sources, any of which is enough. The macOS Contacts database is copied and reopened read-only, so the live database is never locked, journalled or upgraded by being looked at; when macOS refuses the read the Play says exactly that and names Full Disk Access as the fix rather than reporting an empty address book. Any folder of vCard files works, which is what every contacts app on every platform exports. So does a CSV export from Google Contacts or Outlook, with the columns matched by name.
 *
 * You get the next birthdays with the weekday and the age each person is turning, today''s if there are any, and then the part a contact list never tells you: how much of the book has no birthday at all, how many birthdays carry no year so no age can be shown, which names appear more than once, and which contacts have neither an email nor a phone number. A birthday on 29 February is placed on the 28th in a common year rather than skipped.
 *
 * Names are printed as initials unless you set redact=false, and no email address or phone number is ever written into the report, though both are read to find duplicates.
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
 * source_url: https://play.modiqo.ai/rajkaria/birthday-radar
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
 *     - job-birthday-reminder
 *     - job-contact-hygiene
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-contacts
 *     - tool-vcard
 * tags:
 * - domain-personal-computing
 * - job-birthday-reminder
 * - job-contact-hygiene
 * - audience-everyone
 * - effect-read-only
 * - tool-contacts
 * - tool-vcard
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-birthday-reminder
 *   - job-contact-hygiene
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-contacts
 *   - tool-vcard
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       contacts:
 *         type: integer
 *       with_birthday:
 *         type: integer
 *       upcoming:
 *         type: integer
 *       today:
 *         type: integer
 *       next_in_days:
 *         type: integer
 *       missing:
 *         type: integer
 *       duplicates:
 *         type: integer
 * presentation_fixtures:
 *   read_contacts: resources/presentation-fixtures/read_contacts/fixture.yaml
 *   read_csv: resources/presentation-fixtures/read_csv/fixture.yaml
 *   read_vcards: resources/presentation-fixtures/read_vcards/fixture.yaml
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
 *   description: 'true runs against a bundled synthetic address book, so a first run needs nothing exported.'
 *   example: 'false'
 * - name: horizon
 *   param_type: integer
 *   required: false
 *   default: '45'
 *   description: 'How far ahead to look for the next birthdays.'
 *   example: '45'
 * - name: vcard_dir
 *   param_type: string
 *   required: false
 *   default: '~/Documents'
 *   description: 'A folder of .vcf exports, or one .vcf file. Searched recursively.'
 *   example: '~/Documents'
 * - name: csv_path
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Optional path to a Google or Outlook contacts CSV. Columns are matched by name.'
 *   example: ''
 * - name: redact
 *   param_type: string
 *   required: false
 *   default: 'true'
 *   description: 'true prints A. L. instead of the full name. Set false for a private run on your own machine.'
 *   example: 'true'
 * steps:
 *   read_contacts:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'contacts-read'
 *     - '--source'
 *     - 'addressbook'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_vcards:
 *     type: process.exec
 *     timeout_ms: 60000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'contacts-read'
 *     - '--source'
 *     - 'vcard'
 *     - '--vcard-dir'
 *     - '$vcard_dir'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_csv:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'contacts-read'
 *     - '--source'
 *     - 'csv'
 *     - '--csv-path'
 *     - '$csv_path'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - read_contacts
 *     - read_vcards
 *     - read_csv
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'contacts-report'
 *     - '--horizon'
 *     - '$horizon'
 *     - '--redact'
 *     - '$redact'
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
    { label: "read_contacts", step: ctx.step(stepName("read_contacts")) },
    { label: "read_vcards", step: ctx.step(stepName("read_vcards")) },
    { label: "read_csv", step: ctx.step(stepName("read_csv")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.with_birthday ?? 0} of ${j.contacts ?? 0} contacts have a birthday${j.next_in_days === null || j.next_in_days === undefined ? "; none is coming up" : `; the next is in ${j.next_in_days} day(s)`}${j.missing ? `, ${j.missing} have none recorded` : ""}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
