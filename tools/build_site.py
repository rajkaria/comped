#!/usr/bin/env python3
"""Generate site/docs.html from the repo's single sources.

Parameter tables come from docs/plays/<slug>/PARAMETERS.json, the record fields from the
dataclasses themselves, the model list and plan table from the bundled resources, and the CLI
reference from argparse. Documentation that is generated from the thing it documents cannot drift
away from it, and this page makes several load-bearing promises about what the tool reads.
"""
import dataclasses, html, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from comped_core import models                      # noqa: E402
from comped_core.detect import PROVIDERS, HARNESSES  # noqa: E402
from comped_core.cli import build_parser            # noqa: E402

SLUGS = ("comped", "session-ledger", "wrong-turns")
HANDLE = "rajkaria"
# The canonical origin. site/CNAME points GitHub Pages here; the canonical link and the
# og:url below must agree with it or the two hostnames compete for the same page.
SITE_URL = "https://gotcomped.com"

PLAY_BLURB = {
    "comped": "The card: what your window cost at list price, the multiplier against your plan, and the asks you keep repeating.",
    "session-ledger": "The deduplicated ledger everything else is built on. Nothing priced, nothing judged.",
    "wrong-turns": "Recurring mistakes, what recovering from them cost, and a drafted rule for each.",
}

PLAY_STEPS = {
    "comped": "read_claude, read_codex, read_pi, read_opencode (in parallel) → merge_ledger → price_ledger → find_repeats → render_card",
    "session-ledger": "read_claude, read_codex, read_pi, read_opencode (in parallel) → merge_ledger → summarize",
    "wrong-turns": "read_claude, read_codex (in parallel) → merge_ledger → classify_turns → draft_rules",
}

PLAY_OUTPUTS = {
    "comped": [
        ("comped-report.md", "The whole run in Markdown: card, per-model table, sources, repeats, dividend, delta, unpriced models, methodology, privacy, and every path written."),
        ("comped-card.svg", "The shareable card, 1200×675."),
        ("comped-card-square.svg", "The same card on a square canvas. PNG renderers fit thumbnails into a square box and would otherwise crop the wide one."),
        ("comped-card.png", "Rendered from the square SVG when this machine has rsvg-convert or macOS qlmanage. Absent, with a note, when it doesn't."),
        ("comped-explain.txt", "One line per model showing tokens × rate = dollars, plus the plan arithmetic and one line per source."),
        ("comped-share.txt", "A post you can paste, with the numbers already in it."),
        ("comped-baseline.json", "Totals and repeat labels from this run, so the next one can show you the delta."),
        ("ledger.jsonl", "The full ledger. Same file session-ledger produces."),
        ("ledger-summary.json", "Counts per source, including what could not be read and why."),
    ],
    "session-ledger": [
        ("ledger-<harness>.jsonl", "One partial ledger per harness read — the reads run in parallel and each writes its own."),
        ("ledger.jsonl", "The merged, deduplicated, turn-attributed ledger."),
        ("ledger-summary.json", "Record, message and tool counts, sessions, subagent records, and a per-source report."),
    ],
    "wrong-turns": [
        ("wrong-turns-report.md", "A table of recurring mistake classes: kind, confidence, tool, signature, count, sessions, recovery cost, evidence."),
        ("wrong-turns-rules.md", "The drafted rules, one block per class, ready to paste into CLAUDE.md or AGENTS.md. Nothing is applied for you."),
        ("ledger.jsonl", "The ledger it classified."),
    ],
}

FIELD_NOTES = {
    "UsageRecord": {
        "harness": "Which tool wrote the line: claude-code, codex, pi, opencode.",
        "session_id": "The harness's own session identifier.",
        "record_id": "The dedup key. For Claude Code that is (message.id, requestId) — the pair that collapses streaming duplicates.",
        "timestamp": "The record's own timestamp, in UTC. Windowing uses this, never the file's mtime.",
        "model": "As written by the harness, before alias resolution.",
        "input_tokens": "Uncached input tokens.",
        "cache_write_tokens": "Tokens written to the prompt cache, billed at a premium.",
        "cache_read_tokens": "Tokens served from cache, billed at a discount. Usually most of your traffic.",
        "output_tokens": "Generated tokens.",
        "reasoning_tokens": "Thinking tokens, reported separately and billed as output.",
        "project": "The working directory the session ran in.",
        "is_subagent": "True for subagent and sidechain traffic, which is easy to forget and expensive to ignore.",
        "turn_id": "The message that started this turn — how cost gets attributed to what you asked.",
    },
    "HumanMessage": {
        "harness": "Which tool the message came from.",
        "session_id": "The session it belongs to.",
        "message_id": "Stable id, used as the turn id.",
        "timestamp": "UTC.",
        "text": "Truncated to 120 characters by default. Set redact=false and full text stays local.",
        "text_sha256": "Hash of the normalised text, so identical asks can be matched without keeping them.",
        "project": "Working directory.",
        "origin": "human, unknown or automated. Harness-generated messages arrive in the user role and are labelled, not counted as yours.",
    },
    "ToolEvent": {
        "harness": "Which tool.",
        "session_id": "Session.",
        "event_id": "Stable id.",
        "timestamp": "UTC.",
        "tool_name": "Bash, Edit, exec_command, and so on — resolved from the call that named it.",
        "input_summary": "One short line: the command, path or query. Never the full input.",
        "is_error": "Whether the call came back as an error.",
        "error_text": "Up to 300 characters of the error, for errors only.",
        "turn_id": "The turn this happened in.",
    },
}

CSS_ORDER = ("comped", "session-ledger", "wrong-turns")


def esc(s):
    return html.escape(str(s), quote=False)


def params_table(slug):
    rows = json.loads((ROOT / "docs" / "plays" / slug / "PARAMETERS.json").read_text(encoding="utf-8"))
    out = ["<table><thead><tr><th>Parameter</th><th>Type</th><th>Default</th><th>What it does</th></tr></thead><tbody>"]
    for p in rows:
        default = p["default"] if p["default"] != "" else "(empty)"
        out.append("<tr><td><code>{0}</code></td><td>{1}</td><td><code>{2}</code></td><td>{3}</td></tr>".format(
            esc(p["name"]), esc(p["type"]), esc(default), esc(p["description"])))
    out.append("</tbody></table>")
    return "\n".join(out)


def outputs_table(slug):
    out = ["<table><thead><tr><th>File</th><th>What's in it</th></tr></thead><tbody>"]
    for name, what in PLAY_OUTPUTS[slug]:
        out.append("<tr><td><code>{0}</code></td><td>{1}</td></tr>".format(esc(name), esc(what)))
    out.append("</tbody></table>")
    return "\n".join(out)


def fields_table(cls):
    notes = FIELD_NOTES[cls.__name__]
    out = ["<table><thead><tr><th>Field</th><th>Meaning</th></tr></thead><tbody>"]
    for f in dataclasses.fields(cls):
        out.append("<tr><td><code>{0}</code></td><td>{1}</td></tr>".format(esc(f.name), esc(notes.get(f.name, ""))))
    out.append("</tbody></table>")
    return "\n".join(out)


def plans_table():
    doc = json.loads((ROOT / "resources" / "plans.json").read_text(encoding="utf-8"))
    out = ["<table><thead><tr><th>Plan id</th><th>Label</th><th>Monthly</th></tr></thead><tbody>"]
    for pid, p in doc["plans"].items():
        price = "—" if p["monthly_usd"] is None else "${0}".format(p["monthly_usd"])
        out.append("<tr><td><code>{0}</code></td><td>{1}</td><td>{2}</td></tr>".format(esc(pid), esc(p["label"]), esc(price)))
    out.append("</tbody></table>")
    return "\n".join(out), doc["meta"]["as_of"]


def models_list():
    doc = json.loads((ROOT / "resources" / "prices.json").read_text(encoding="utf-8"))
    names = sorted(doc["models"])
    return ", ".join("<code>{0}</code>".format(esc(n)) for n in names), len(names), doc["meta"]


def cli_reference():
    parser = build_parser()
    sub = parser._subparsers._group_actions[0]
    out = ["<table><thead><tr><th>Subcommand</th><th>Options</th></tr></thead><tbody>"]
    for name, p in sub.choices.items():
        opts = []
        for a in p._actions:
            if not a.option_strings:
                continue
            flag = a.option_strings[-1]
            if flag == "--help":
                continue
            opts.append(flag if a.default in (None, "") else "{0} {1}".format(flag, a.default))
        out.append("<tr><td><code>{0}</code></td><td><code>{1}</code></td></tr>".format(
            esc(name), esc(" ".join(opts)) or "—"))
    out.append("</tbody></table>")
    return "\n".join(out)


def providers_table():
    """Generated from comped_core.detect, so the list on the page is the list in the code."""
    out = ["<table><thead><tr><th>Provider</th><th>What you call it</th><th>Model ids that name it</th>"
           "<th>Subscriptions priced</th></tr></thead><tbody>"]
    for key, label, talk, pattern, plans in PROVIDERS:
        ids = pattern.replace("^", "").replace("(", "").replace(")", "").replace("|", ", ")
        out.append("<tr><td>{0}</td><td>{1}</td><td><code>{2}…</code></td><td>{3}</td></tr>".format(
            esc(label), esc(talk), esc(ids), ", ".join("<code>{0}</code>".format(esc(p)) for p in plans) or "—"))
    out.append("</tbody></table>")
    return "\n".join(out)


def harness_list():
    return ", ".join("<strong>{0}</strong>".format(esc(label)) for label, _ in HARNESSES.values())


def play_section(slug):
    return """
<h3 id="play-{slug}">{slug}</h3>
<p>{blurb}</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/{slug}</code></pre>
<p><strong>Steps.</strong> {steps}</p>
<p><strong>Parameters.</strong> Every one has a default, so the bare command above works. Pass them as <code>name=value</code> after the URI.</p>
{params}
<p><strong>What it writes,</strong> all of it under <code>out_dir</code> and nowhere else:</p>
{outputs}
""".format(slug=slug, blurb=esc(PLAY_BLURB[slug]), handle=HANDLE, steps=esc(PLAY_STEPS[slug]),
           params=params_table(slug), outputs=outputs_table(slug))


def main():
    plans, plans_as_of = plans_table()
    model_links, model_count, price_meta = models_list()
    body = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>comped — docs</title>
<meta name="description" content="How to run the comped Plays, every parameter, exactly what they read from your logs, and the arithmetic behind every number on the card.">
<link rel="canonical" href="{site}/docs.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="comped">
<meta property="og:url" content="{site}/docs.html">
<meta property="og:title" content="comped — docs">
<meta property="og:description" content="How to run the comped Plays, every parameter, exactly what they read from your logs, and the arithmetic behind every number on the card.">
<meta property="og:image" content="{site}/card-wide.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="675">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="comped — docs">
<meta name="twitter:description" content="How to run the comped Plays, every parameter, exactly what they read from your logs, and the arithmetic behind every number on the card.">
<meta name="twitter:image" content="{site}/card-wide.png">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧾</text></svg>">
<link rel="stylesheet" href="style.css">
</head>
<body>

<nav>
  <div class="wrap">
    <a class="brand" href="./">comped<span>.</span></a>
    <div class="links">
      <a href="./">Home</a>
      <a href="#install">Install</a>
      <a href="#plays" class="hide-sm">Plays</a>
      <a href="#tracking" class="hide-sm">What it tracks</a>
      <a href="https://github.com/rajkaria/comped">GitHub</a>
    </div>
  </div>
</nav>

<div class="wrap" style="padding-top:48px;padding-bottom:72px">
<div class="doc-layout">

<aside class="toc">
  <strong>Getting started</strong>
  <a href="#install">Install</a>
  <a href="#quickstart">Quick start</a>
  <a href="#reading">Reading the card</a>
  <a href="#detection">What you're running</a>
  <strong>The Plays</strong>
  <a href="#play-comped">comped</a>
  <a href="#play-session-ledger">session-ledger</a>
  <a href="#play-wrong-turns">wrong-turns</a>
  <strong>Under it</strong>
  <a href="#tracking">What it tracks</a>
  <a href="#math">The arithmetic</a>
  <a href="#prices">Prices and plans</a>
  <a href="#privacy">Privacy</a>
  <strong>Reference</strong>
  <a href="#cli">Without rote</a>
  <a href="#trouble">Troubleshooting</a>
</aside>

<main class="doc">

<h2 id="install">Install</h2>
<p>You need two things: <strong>rote</strong>, and a <strong>python3</strong> of at least 3.9. Nothing else — no pip install, no node, no lockfile.</p>
<pre><code>curl -fsSL https://getrote.dev/install | sh</code></pre>
<p>Then sign in when it asks. That's it; the Plays pull themselves on first run.</p>
<div class="callout"><p>Already have rote? Check you're on 0.78 or newer with <code>rote --version</code>. The Plays declare their tool requirements in <code>deps.toml</code>, and <code>rote play inspect &lt;uri&gt;</code> will tell you before you run anything whether this machine satisfies them.</p></div>

<h2 id="quickstart">Quick start</h2>
<p>Run it against the synthetic logs bundled inside the Play first. They are real logs in structure and completely fabricated in content, so you can watch the whole thing work without pointing it at anything of yours:</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/comped \\
  claude_dir=resources/fixtures/claude \\
  codex_dir=resources/fixtures/codex \\
  out_dir=comped-demo</code></pre>
<p>Eight steps, about two seconds, and a card. Then the real thing:</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/comped</code></pre>
<p>Ten seconds or so on a month of heavy use. Everything lands in <code>~/comped/</code>. Run it again tomorrow and the card grows a line telling you what moved.</p>

<h2 id="reading">Reading the card</h2>
<p>Top to bottom, the card says:</p>
<ul>
<li><strong>The total.</strong> What the window's tokens would have cost at API list prices. Not a bill — you're on a subscription and you paid what you paid.</li>
<li><strong>The multiplier.</strong> That total divided by your plan, prorated across the window by days ÷ 30.4375. You do not type the plan: see <a href="#detection">what you're running</a>.</li>
<li><strong>Spend per model,</strong> largest first, with a bar. If one model is quietly eating your month, this is where you see it.</li>
<li><strong>Cache-read share.</strong> The fraction of your input tokens served from cache. High is good and normal — most agent traffic is re-reading the same context. A number near zero means something at the front of your prompt keeps changing and the whole prefix is being re-billed.</li>
<li><strong>Active days and sessions,</strong> so a big total can be read as either heavy use or a heavy week.</li>
<li><strong>The delta,</strong> once there's a previous run to compare against.</li>
<li><strong>Repeat offenders.</strong> Jobs you've asked for repeatedly, with what the repeats cost, and the command to turn the top one into a Play so you stop paying for it.</li>
<li><strong>The Rote dividend.</strong> What those repeats would have cost as a Play instead, at Modiqo's stated 98% reduction and at a more conservative 80%.</li>
<li><strong>Detected.</strong> Which providers your window actually used — Claude, GPT/Codex, Kimi, GLM and the rest — with their share and the harnesses they came through. None of it typed.</li>
<li><strong>If you're on…</strong> every subscription those providers sell, priced against this window at once, with the assumed row marked. Your tier is the one thing your logs do not record, so the card shows all of them rather than asking.</li>
</ul>

<h2 id="detection">What you're running, worked out for you</h2>
<p>Asking you which AI you use makes no sense: your logs already say. Every usage record carries the model id the harness sent, and that id names the provider behind it. So <code>plan</code> defaults to <code>auto</code> and the run works the rest out itself.</p>
<ol class="steps">
<li><b>The harnesses.</b> {harnesses}. A directory that isn't there is a shrug, and the card names the ones it didn't find so you know what wasn't counted.</li>
<li><b>The provider.</b> Read off the model id, after gateway and region prefixes are stripped — <code>us.anthropic.claude-opus-5</code>, <code>bedrock/anthropic.claude-sonnet-5</code> and <code>claude-opus-5</code> are one provider, not three. Point Claude Code at Moonshot or Z.ai and the ids give that away too, which is the whole point.</li>
<li><b>The tier — the one thing no log records.</b> A Pro session and a Max session are the same bytes. So instead of asking, every subscription the detected providers sell is priced against your window at once and you read your own row. The one the card assumes is deliberately the least flattering: the most expensive plan that fits, which is the smallest multiplier you could honestly claim.</li>
<li><b>Anything else.</b> A provider with no subscription in the table (Kimi, GLM, DeepSeek and friends) is named, its spend stays in the total, and the card says plainly that nothing in the plan cost covers it. If you pay for one, <code>plan=usd:29</code> prices it without the table having to know.</li>
</ol>
<p>Overriding is still one word — <code>plan=claude-pro-20</code>, or several separated by commas — and it wins over the inference.</p>
{providers}
<div class="callout"><p>Detection reads nothing new. It looks at records the ledger already parsed, and at which of the four log directories existed. A model id nobody recognises is reported by name as unknown rather than assigned to a provider by guess.</p></div>

<h2 id="plays">The three Plays</h2>
{play_comped}
{play_ledger}
{play_wrong}

<h2 id="tracking">What it tracks, field by field</h2>
<p>Three record types come out of your logs. This is all of them — the table below is generated from the code that defines them, so it cannot drift.</p>

<h3>Usage records — one per API call</h3>
{usage_fields}

<h3>Human messages — one per message in the user role</h3>
<p>These exist for one reason: to attribute cost to <em>what you asked</em>. Without them a month of agent work is an undifferentiated wall of API calls.</p>
{human_fields}

<h3>Tool events — one per tool call</h3>
{tool_fields}

<div class="callout"><p><strong>What is never collected:</strong> file contents, tool outputs beyond a 300-character error snippet, prompt text beyond the 120-character truncation, and anything at all from a credential, keychain or token file. There is no identifier for you, no machine id and no run id that leaves your disk, because nothing leaves your disk.</p></div>

<h2 id="math">The arithmetic</h2>

<h3>Pricing</h3>
<p>Per record, in exact decimal arithmetic — never floating point, which is how cent-level errors get into totals:</p>
<pre><code>usd = uncached_input × in_rate
    + cache_write     × cache_write_rate
    + cache_read      × cache_read_rate
    + output          × out_rate</code></pre>
<p>Reasoning tokens are already counted inside output, because that is how they are billed. Rounding happens once, at display time.</p>

<h3>Deduplication</h3>
<p>Claude Code writes a line per content block, so the same API call appears several times with the same <code>message.id</code> and <code>requestId</code>. On real logs <strong>about four in ten usage lines are duplicates</strong>. They are collapsed on that pair, and the count of what was dropped appears in the source report. Codex has the opposite shape: its counters are cumulative totals, so each record is the difference from the previous snapshot, and a counter that goes backwards starts a new baseline rather than producing a negative.</p>

<h3>Windows and the multiplier</h3>
<p>A record is in the window if <em>its own timestamp</em> is, never the file's modification time. Plan cost is prorated by <code>days_back ÷ 30.4375</code> — the mean month — so a 14-day window is compared against 14 days of subscription, not a whole month of it.</p>

<h3>Repeat offenders</h3>
<p>Messages are normalised (lowercased, paths, URLs, numbers and hashes replaced by placeholders, stop-words dropped), turned into 2-word shingles, and clustered when their Jaccard similarity is <strong>0.5 or higher</strong>. A cluster qualifies when it has at least <code>repeat_threshold</code> asks across <strong>two or more sessions on two or more days</strong> — one frustrated afternoon of retries is not a repeated job. Its repeat cost is the cluster's total minus its cheapest single solve: what you paid to ask again.</p>
<p>Harness-generated text is kept out: session-continuation preambles, injected reminders, observer prompts and anything in the automated origin class. They stay in the ledger, because they cost real money, but they are not things you asked for.</p>

<h3>Wrong turns</h3>
<p>Three signals, with honest confidence labels. <strong>Tool errors</strong> (high confidence): the call returned an error, and the error's first line is stripped of paths and numbers to make a signature that clusters across sessions. <strong>Corrections</strong> (medium): your next message matched a correction phrase — "no,", "revert", "that's not", "undo". <strong>Reverts</strong> (high): a destructive git command ran. A class is reported when it recurs at least <code>min_recurrence</code> times across two or more sessions. Recovery cost is the signalling turn plus the next one — what it took to get back on track.</p>

<h2 id="prices">Prices and plans</h2>
<p>The price table is a snapshot, bundled with the Play, that carries its own provenance: the source URL, the upstream file's sha256, and the date it was taken. It is never fetched at runtime.</p>
<table><tbody>
<tr><th>Source</th><td><code>{price_source}</code></td></tr>
<tr><th>As of</th><td>{price_as_of}</td></tr>
<tr><th>Models</th><td>{model_count}</td></tr>
</tbody></table>
<p>{models}</p>
<p>A model that is not in this list is reported under "unpriced" with its token counts, and no dollar figure is invented for it.</p>
<h3>Plans</h3>
<p>Public list prices as of {plans_as_of}. You normally pass none of these: <code>plan=auto</code> prices every row a detected provider sells and marks the one it assumed. Pass one id, or several separated by commas, to override — or <code>usd:&lt;amount&gt;</code> for a subscription this table does not carry.</p>
{plans}
<div class="callout warn"><p>Your tier is inferred from the model ids in your own logs, never from your account. The tool will not read <code>~/.claude.json</code> or <code>~/.codex/auth.json</code> to discover it, because a tool that reads your OAuth files to be convenient is a tool you should not run.</p></div>

<h2 id="privacy">Privacy, and how to check it</h2>
<p>The claims are on the <a href="./#privacy">front page</a>. Here is how you verify them rather than believing them:</p>
<ul>
<li><strong>No network.</strong> <code>python3 -m unittest tests.test_no_network</code> fails if the core imports <code>urllib</code>, <code>http</code>, <code>socket</code>, <code>requests</code> or <code>ssl</code>, if anything but the PNG renderer mentions <code>subprocess</code>, or if any source line references a credential path.</li>
<li><strong>No surprises in what it writes.</strong> Every run lists every path it wrote, in the report and in its JSON output.</li>
<li><strong>Determinism.</strong> Pin <code>--now</code> and two runs produce byte-identical output. The suite proves it with the PATH emptied, which also proves the pipeline needs no external binary.</li>
<li><strong>Read the code.</strong> It is a few thousand lines of standard-library Python with no dependencies. <a href="https://github.com/rajkaria/comped">github.com/rajkaria/comped</a>.</li>
</ul>

<h2 id="cli">Running it without rote</h2>
<p>The Plays are a thin wrapper around a Python package with no dependencies. If you would rather run it directly, clone the repo and use the module. Every subcommand prints one JSON object as its last line; a missing log directory is a warning and exit 0, bad arguments exit 2, and nothing ever prints a traceback.</p>
<pre><code>git clone https://github.com/rajkaria/comped &amp;&amp; cd comped
python3 -m comped_core ledger  --days-back 30 --out-dir ~/comped
python3 -m comped_core price   --out-dir ~/comped            # --plan auto by default
python3 -m comped_core repeats --out-dir ~/comped --repeat-threshold 3
python3 -m comped_core card    --out-dir ~/comped</code></pre>
<p>The full set:</p>
{cli}
<p><code>verify</code> is worth knowing about: it re-prices the ledger from scratch and confirms the total in your report still reproduces.</p>

<h2 id="trouble">Troubleshooting</h2>
<h3>"no log directory found"</h3>
<p>Expected, not an error, if you don't use that harness — the step exits 0 with a warning and the run continues. If you <em>do</em> use it and it's missing, point the parameter at the right path: <code>claude_dir</code>, <code>codex_dir</code>, <code>pi_dir</code>, <code>opencode_dir</code>.</p>
<h3>The total looks too low</h3>
<p>Check <code>days_back</code> — it defaults to 30 — and check the unpriced list at the bottom of the report. A model missing from the price table contributes tokens but no dollars, on purpose.</p>
<h3>No repeat offenders</h3>
<p>The bar is deliberately high: three asks, two sessions, two days. Try <code>repeat_threshold=2</code>. If you work on one thing at a time in long sessions, you may genuinely not repeat yourself across days.</p>
<h3>No PNG</h3>
<p>Install <code>rsvg-convert</code>, or use macOS where <code>qlmanage</code> is built in. The SVG is always written, and it uploads to LinkedIn as-is.</p>
<h3>The numbers moved and I didn't change anything</h3>
<p>You ran it on a different day: the window slid. Pin it with <code>--now</code> on the CLI if you need two runs to be comparable.</p>

</main>
</div>
</div>

<footer>
  <div class="wrap row">
    <span>comped — built on <a href="https://www.modiqo.ai">Modiqo's rote</a>. MIT licensed.</span>
    <span class="sp"><a href="./">Home</a> · <a href="https://github.com/rajkaria/comped">Source</a> · <a href="https://github.com/rajkaria/comped/blob/main/docs/SPEC.md">Methodology</a></span>
  </div>
</footer>

</body>
</html>
""".format(handle=HANDLE,
           site=SITE_URL,
           play_comped=play_section("comped"),
           play_ledger=play_section("session-ledger"),
           play_wrong=play_section("wrong-turns"),
           usage_fields=fields_table(models.UsageRecord),
           human_fields=fields_table(models.HumanMessage),
           tool_fields=fields_table(models.ToolEvent),
           price_source=esc(price_meta.get("source_url", "")),
           price_as_of=esc(price_meta.get("as_of", "")),
           model_count=model_count,
           models=model_links,
           plans=plans,
           plans_as_of=esc(plans_as_of),
           cli=cli_reference(),
           providers=providers_table(),
           harnesses=harness_list())
    out = ROOT / "site" / "docs.html"
    out.write_text(body, encoding="utf-8")
    print("wrote {0} ({1} bytes)".format(out, len(body)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
