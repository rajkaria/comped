#!/usr/bin/env -S rote play run
/**
 * @rote-frontmatter
 * ---
 * name: whatis
 * description: 'Something opaque is on your clipboard and you need to know what it is before you can do anything with it. Paste it here. This identifies it and then peels it: a base64 blob holding gzip holding JSON holding a JWT is one input and four layers, and you get all four.
 *
 * It reads JWTs (algorithm, every claim, and whether the thing expired four hours ago or expires in ninety days), base64 and base64url, hex, percent-encoding, gzip, JSON described by its shape rather than dumped at you, unix time in seconds, milliseconds, microseconds or nanoseconds, UUIDs v1 through v7 with the timestamp that is buried inside a v1 and a v7, ULIDs, IPv4 and IPv6 with the scope spelled out (private, loopback, link-local, carrier-grade NAT), CIDR ranges with their size, MAC addresses, semantic versions, cron expressions, hex colours, data URIs, e-mail addresses, URLs with the query string broken into pairs, hashes named by length, and the magic bytes of a PDF, PNG, ZIP or SQLite file sitting behind a base64 wrapper.
 *
 * The order the detectors run in is the design. A forty-character git object id is reported as a sha1, not offered to the base64 reader, because the more constrained shape always wins. And where two readings are genuinely possible the output says so rather than picking quietly: a ten-digit integer is read as a time only when it lands between 2001 and 2038, and the note explaining that choice is printed next to the answer.
 *
 * - Reads: the text you pass in, and nothing else. There is no file access, no clipboard access, and no directory to configure.
 * - Never reads: any credential, keychain or token file. This Play needs no account and has no login step.
 * - Never sends: `micro_core` imports no `urllib`, `http`, `socket` or `subprocess`, which a test in the repository asserts on every commit. It does not even use `urllib.parse`; the percent-decoder is forty lines in the package, so the offline claim needs no exception.
 * - Writes nothing. No state, no cache, no output file.
 * - A JWT signature is never printed. You get its first eight characters and its length, which is enough to recognise it in your own file and not enough to use.
 * - Runs cold: set `demo=true` to peel a bundled synthetic token with nothing configured.
 *
 * See also: `is-it-secret`, which reads the same kind of paste and tells you what to redact, and `fits`, which tells you how big it is and what it costs to send. Requires python3 3.9 or newer. No pip install, no node, no network, no credentials.'
 * version: '0.1.1'
 * source_url: https://play.modiqo.ai/rajkaria/whatis
 * metadata:
 *   version: '0.1.1'
 *   rote_version: '0.80.0'
 *   status: released
 *   kind: atomic
 *   flow_type: sequential
 *   execution_model: steps_with_presentation
 *   requires_endpoints: []
 *   requires_sessions: false
 *   license: MIT
 *   discoverability:
 *     tags:
 *     - domain-developer-tooling
 *     - job-string-decoding
 *     - job-token-inspection
 *     - audience-developers
 *     - effect-read-only
 *     - tool-jwt
 *     - tool-base64
 * tags:
 * - domain-developer-tooling
 * - job-string-decoding
 * - job-token-inspection
 * - audience-developers
 * - effect-read-only
 * - tool-jwt
 * - tool-base64
 * discoverability:
 *   tags:
 *   - domain-developer-tooling
 *   - job-string-decoding
 *   - job-token-inspection
 *   - audience-developers
 *   - effect-read-only
 *   - tool-jwt
 *   - tool-base64
 * output:
 *   schema:
 *     type: object
 *     properties:
 *       kind:
 *         type: string
 *       chain:
 *         type: string
 *       layers:
 *         type: object
 *       depth_reached:
 *         type: integer
 *       chars:
 *         type: integer
 * presentation_fixtures:
 *   report: resources/presentation-fixtures/report/fixture.yaml
 * parameters:
 * - name: text
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'The opaque thing you are holding. Paste it whole; whatever it turns out to be, it is read on this machine and printed back to you.'
 *   example: 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig'
 * - name: depth
 *   param_type: integer
 *   required: false
 *   default: '4'
 *   description: 'A base64 blob holding gzip holding JSON is three layers. This is where the peeling stops.'
 *   example: '4'
 * - name: reveal
 *   param_type: string
 *   required: false
 *   default: 'false'
 *   description: 'false truncates every decoded value at 80 characters. true prints them in full. A JWT signature is never printed either way.'
 *   example: 'false'
 * - name: demo
 *   param_type: string
 *   required: false
 *   default: 'false'
 *   description: 'true runs the whole Play against bundled synthetic input, so a first run needs nothing configured and touches nothing of yours.'
 *   example: 'false'
 * - name: now
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: 'Empty reads the real clock. An ISO-8601 instant makes the run reproducible, which is how the tests and the demo produce the same bytes on every machine.'
 *   example: '2026-09-05T14:22:03Z'
 * steps:
 *   report:
 *     type: process.exec
 *     timeout_ms: 30000
 *     argv:
 *     - 'python3'
 *     - '@resource{micro_core/cli.py}'
 *     - 'whatis'
 *     - 'report'
 *     - '--text'
 *     - '$text'
 *     - '--depth'
 *     - '$depth'
 *     - '--reveal'
 *     - '$reveal'
 *     - '--now'
 *     - '$now'
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

  ]);
  out.human([final.human, notes.length ? `Could not read: ${notes.join("; ")}` : ""].filter(Boolean).join("\n"));
  out.summary(`${j.chain ?? "nothing"} — ${j.depth_reached ?? 0} layer(s) deep`);
  out.result({ run_id: ctx.run.run_id, ...j, absences: notes });
}
