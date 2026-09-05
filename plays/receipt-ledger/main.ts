#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: receipt-ledger
 * description: 'Every purchase leaves a file somewhere. A PDF invoice, a saved confirmation page, an exported message. None of them are ever added up, because they are four formats sitting in one folder and opening them one at a time is nobody''s evening.
 *
 * This reads all four. Email files are parsed with their headers, so the sender and the date are the real ones and not the file''s. Saved pages are stripped to text. PDFs are decompressed and, where the fonts use their own encoding, decoded through the document''s own ToUnicode table, then laid back out into lines from the coordinates each glyph was placed at, because a PDF has no concept of a line and reading one without reconstructing it gives you a column of single letters. A scanned receipt has no text at all and is reported as unreadable rather than guessed at.
 *
 * A document only counts as a receipt if it says it is one. An amount sitting on a line that says total, amount due or you paid is enough on its own; otherwise the document needs at least two of invoice number, order number, subtotal, a tax line, a payment method, a transaction reference or a billing period, and a phrase introduced by a negation does not count. A pitch deck full of dollar figures is not a receipt and is excluded by name in the source note.
 *
 * Totals are per currency and are never added across currencies. You get the spend by vendor and by month, the vendors that appear in three or more months, the same charge appearing in two files, and a confidence block saying how many amounts came from a total line rather than from being the largest figure on the page, and how many dates came from the file rather than the document.
 *
 * Nothing logs in to anything. There is no bank, no email account and no API. It reads files you already have.
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
 * source_url: https://play.modiqo.ai/rajkaria/receipt-ledger
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
 *     - job-spend-review
 *     - job-receipt-reconciliation
 *     - audience-everyone
 *     - effect-read-only
 *     - tool-pdf
 *     - tool-email
 * tags:
 * - domain-personal-computing
 * - job-spend-review
 * - job-receipt-reconciliation
 * - audience-everyone
 * - effect-read-only
 * - tool-pdf
 * - tool-email
 * discoverability:
 *   tags:
 *   - domain-personal-computing
 *   - job-spend-review
 *   - job-receipt-reconciliation
 *   - audience-everyone
 *   - effect-read-only
 *   - tool-pdf
 *   - tool-email
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       documents:
 *         type: integer
 *       priced:
 *         type: integer
 *       in_window:
 *         type: integer
 *       currencies:
 *         type: object
 *       vendors:
 *         type: integer
 *       recurring:
 *         type: integer
 *       duplicates:
 *         type: integer
 * presentation_fixtures:
 *   read_files: resources/presentation-fixtures/read_files/fixture.yaml
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
 *   description: 'true runs against bundled synthetic receipts in four formats, including one that must not count.'
 *   example: 'false'
 * - name: months_back
 *   param_type: integer
 *   required: false
 *   default: '12'
 *   description: 'How far back to total. Receipts older than this are read and reported as outside the window.'
 *   example: '12'
 * - name: receipts_dir
 *   param_type: string
 *   required: false
 *   default: '~/Downloads'
 *   description: 'A folder of PDFs, .eml exports and saved pages. Searched recursively.'
 *   example: '~/Downloads'
 * - name: mail_dir
 *   param_type: string
 *   required: false
 *   default: '~/Library/Mail'
 *   description: 'Optional second folder. macOS protects this one; without Full Disk Access it is skipped by name.'
 *   example: '~/Library/Mail'
 * steps:
 *   read_files:
 *     type: process.exec
 *     timeout_ms: 180000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'receipts-read'
 *     - '--source'
 *     - 'files'
 *     - '--receipts-dir'
 *     - '$receipts_dir'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   read_mail:
 *     type: process.exec
 *     timeout_ms: 180000
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'receipts-read'
 *     - '--source'
 *     - 'mail'
 *     - '--mail-dir'
 *     - '$mail_dir'
 *     - '--out-dir'
 *     - '$out_dir'
 *     - '--demo'
 *     - '$demo'
 *   report:
 *     type: process.exec
 *     timeout_ms: 60000
 *     depends_on:
 *     - read_files
 *     - read_mail
 *     argv:
 *     - 'python3'
 *     - '@resource{daily_core/cli.py}'
 *     - 'receipts-report'
 *     - '--months-back'
 *     - '$months_back'
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
    { label: "read_files", step: ctx.step(stepName("read_files")) },
    { label: "read_mail", step: ctx.step(stepName("read_mail")) }
  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.in_window ?? 0} receipts totalled from ${j.documents ?? 0} documents: ${(j.currencies ?? []).map((c: any) => `${c.total} ${c.currency}`).join(" · ") || "nothing inside the window"}`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
