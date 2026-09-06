#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: standing-cost
 * description: 'Nobody schedules a meeting by its price. A 30-minute standup with nine people is four and a half person-hours every time it fires, and over a year that is a number no calendar will ever show you. Every fact needed to compute it is already in the calendar — who was invited, who accepted, how long it ran, how often it was cancelled — so this does the arithmetic and prints the denominators.
 *
 * The Play is two programs on purpose, and the seam between them is a file. One step reads a window of your calendar and writes a normalised JSON file into `out_dir`; that step is the only part of this package that opens a connection, it is one short file you can read before you run it, and it calls `events.list` and nothing else. The second half — the arithmetic, the card and the report — is `daily_core`, which imports no networking module at all and only ever reads that file. If the file is not there, that is a labelled absence and the run still completes.
 *
 * What the arithmetic refuses to do is most of what makes it trustworthy. There is no default hourly rate: with `hourly_rate` unset the Play reports person-hours and says the rate is unset, and with it set every surface that prints money carries the word "assumed" next to the number. Declined and non-responding invitees are counted, reported, and left out of the headline, because billing someone for a meeting they said no to is how these numbers become fiction. Cancelled occurrences are credited, never billed. Google records invitations rather than attendance, so attendance is never claimed.
 *
 * You get the person-hours per series, the share of them that is recurring, the meetings where most of the room never speaks, how many focus blocks the week''s meetings cut in half, and the cancellation rate per series. Attendee names and addresses are reduced to initials unless you turn redaction off, and no address is printed in full on the card either way.
 *
 * - Reads: your calendar, over HTTPS, for the window you chose — and then only the file that step wrote into `out_dir`. Nothing else on your disk is opened.
 * - Never reads: any credential file, keychain or token file. The calendar step takes an OAuth access token from an environment variable you name and uses it for those requests only; it opens no keychain, stores no token, and prints none. With the variable unset the step says so and exits cleanly.
 * - Never sends: your files, your paths, your other calendars or anything about this machine. The one request made is a read of the calendar you named, to Google, with your own token. Nothing is written back to the calendar: no event is created, changed, accepted, declined or deleted, and there is no code path here that could. `daily_core`, which does all the arithmetic, imports no `urllib`, `http`, `socket` or `ssl` at all, and a test in the repository asserts that on every commit.
 * - Writes: only inside `out_dir`, which is created if missing — the normalised calendar file, the report, and a baseline so the next run can say what moved. Every written path is listed in the run output.
 * - Degrades, never fails: no token, an expired token, a refused request or a machine with no network each become a labelled absence with the reason, and the run still completes with nothing to price rather than with an invented number.
 * - Runs cold: set `demo=true` to run the whole Play against a bundled synthetic calendar of 439 events. In that mode the calendar step reads no environment variable and opens no connection at all, so a first run needs no account and no credential.
 *
 * Requires python3 3.9 or newer. No pip install, no node, no adapters.'
 * version: '0.1.0'
 * source_url: https://play.modiqo.ai/rajkaria/standing-cost
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
 *     - job-meeting-cost-review
 *     - job-calendar-audit
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-google-calendar
 * tags:
 * - domain-productivity
 * - job-meeting-cost-review
 * - job-calendar-audit
 * - audience-everyone
 * - effect-read-only
 * - tool-google-calendar
 * discoverability:
 *   tags:
 *   - domain-productivity
 *   - job-meeting-cost-review
 *   - job-calendar-audit
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-google-calendar
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       events_read:
 *         type: integer
 *       occurrences:
 *         type: integer
 *       cancelled:
 *         type: integer
 *       series:
 *         type: integer
 *       people:
 *         type: integer
 *       person_hours:
 *         type: number
 *       recurring_person_hours:
 *         type: number
 *       silent_person_hours:
 *         type: number
 *       rate_set:
 *         type: boolean
 * presentation_fixtures:
 *   fetch_calendar: resources/presentation-fixtures/fetch_calendar/fixture.yaml
 *   read_calendar: resources/presentation-fixtures/read_calendar/fixture.yaml
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
 *   description: 'true runs the whole Play against a bundled synthetic calendar of 439 events, so a first run needs nothing installed and no account.'
 *   example: 'false'
 * - name: partial
 *   param_type: string
 *   required: false
 *   default: '.standing-cost-calendar.json'
 *   description: 'Where the calendar step writes the normalised events and the report reads them. A relative name resolves inside out_dir.'
 *   example: '.standing-cost-calendar.json'
 * - name: calendar_id
 *   param_type: string
 *   required: false
 *   default: 'primary'
 *   description: 'Which calendar to read. primary is the account''s own. Only events.list is called; nothing is written back.'
 *   example: 'primary'
 * - name: days
 *   param_type: integer
 *   required: false
 *   default: '365'
 *   description: 'How many days back to fetch and price. A recurring meeting is worth judging over a year, not over a week.'
 *   example: '365'
 * - name: token_env
 *   param_type: string
 *   required: false
 *   default: 'GOOGLE_OAUTH_TOKEN'
 *   description: 'The environment variable holding a Google OAuth access token with the calendar.readonly scope. No file is read for it, and if the variable is unset the Play says so and still runs.'
 *   example: 'GOOGLE_OAUTH_TOKEN'
 * - name: focus_block_minutes
 *   param_type: integer
 *   required: false
 *   default: '90'
 *   description: 'How long an uninterrupted stretch has to be before it counts as one. It is what turns meeting times into the number of focus blocks they cut in half.'
 *   example: '90'
 * - name: currency
 *   param_type: string
 *   required: false
 *   default: '£'
 *   description: 'Printed in front of every money figure. It changes the symbol, never the arithmetic.'
 *   example: '£'
 * - name: hourly_rate
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Leave empty and the Play reports person-hours and claims no money at all. Set it and every money figure is labelled assumed, because it is.'
 *   example: '75'
 * - name: owner_address
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Your own address, for the case where the feed does not mark which attendee is you. Used to tell your time from everybody else''s; never printed in full.'
 *   example: 'you@example.com'
 * steps:
 *   fetch_calendar:
 *     type: process.exec
 *     timeout_ms: 180000
 *     argv:
 *     - 'python3'
 *     - '@resource{fetch/calendar_partial.py}'
 *     - '--partial'
 *     - '$partial'
 *     - '--calendar-id'
 *     - '$calendar_id'
 *     - '--days'
 *     - '$days'
 *     - '--token-env'
 *     - '$token_env'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_calendar:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - fetch_calendar
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'standingcost-read'
 *     - '--source'
 *     - 'calendar'
 *     - '--partial'
 *     - '$partial'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - read_calendar
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'standingcost-report'
 *     - '--source'
 *     - 'calendar'
 *     - '--partial'
 *     - '$partial'
 *     - '--days'
 *     - '$days'
 *     - '--focus-block-minutes'
 *     - '$focus_block_minutes'
 *     - '--currency'
 *     - '$currency'
 *     - '--hourly-rate'
 *     - '$hourly_rate'
 *     - '--self'
 *     - '$owner_address'
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
    { label: "fetch_calendar", step: ctx.step(stepName("fetch_calendar")) },
    { label: "read_calendar", step: ctx.step(stepName("read_calendar")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.occurrences ?? 0} occurrences of ${j.series ?? 0} recurring series cost ${j.recurring_person_hours ?? 0} person-hours${j.rate_set ? "" : "; no hourly rate is set, so no money is claimed"}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
