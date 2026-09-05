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
        ("ledger-<harness>.jsonl", "One partial ledger per harness read: the reads run in parallel and each writes its own."),
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
        "record_id": "The dedup key. For Claude Code that is (message.id, requestId): the pair that collapses streaming duplicates.",
        "timestamp": "The record's own timestamp, in UTC. Windowing uses this, never the file's mtime.",
        "model": "As written by the harness, before alias resolution.",
        "input_tokens": "Uncached input tokens.",
        "cache_write_tokens": "Tokens written to the prompt cache, billed at a premium.",
        "cache_read_tokens": "Tokens served from cache, billed at a discount. Usually most of your traffic.",
        "output_tokens": "Generated tokens.",
        "reasoning_tokens": "Thinking tokens, reported separately and billed as output.",
        "project": "The working directory the session ran in.",
        "is_subagent": "True for subagent and sidechain traffic, which is easy to forget and expensive to ignore.",
        "turn_id": "The message that started this turn: how cost gets attributed to what you asked.",
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
        "tool_name": "Bash, Edit, exec_command, and so on: resolved from the call that named it.",
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
        price = "-" if p["monthly_usd"] is None else "${0}".format(p["monthly_usd"])
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
            esc(name), esc(" ".join(opts)) or "-"))
    out.append("</tbody></table>")
    return "\n".join(out)


def providers_table():
    """Generated from comped_core.detect, so the list on the page is the list in the code."""
    out = ["<table><thead><tr><th>Provider</th><th>What you call it</th><th>Model ids that name it</th>"
           "<th>Subscriptions priced</th></tr></thead><tbody>"]
    for key, label, talk, pattern, plans in PROVIDERS:
        ids = pattern.replace("^", "").replace("(", "").replace(")", "").replace("|", ", ")
        out.append("<tr><td>{0}</td><td>{1}</td><td><code>{2}…</code></td><td>{3}</td></tr>".format(
            esc(label), esc(talk), esc(ids), ", ".join("<code>{0}</code>".format(esc(p)) for p in plans) or "-"))
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


def params_table_for(slug, names):
    """A subset of a Play's parameters, for the user guide: the ones a person might actually change."""
    rows = json.loads((ROOT / "docs" / "plays" / slug / "PARAMETERS.json").read_text(encoding="utf-8"))
    out = ["<table><thead><tr><th>Option</th><th>Default</th><th>What it does</th></tr></thead><tbody>"]
    for p in rows:
        if p["name"] not in names:
            continue
        default = p["default"] if p["default"] != "" else "(empty)"
        out.append("<tr><td><code>{0}</code></td><td><code>{1}</code></td><td>{2}</td></tr>".format(
            esc(p["name"]), esc(default), esc(p["description"])))
    out.append("</tbody></table>")
    return "\n".join(out)


ONE_LINER = "curl -fsSL {0}/run.sh | sh".format(SITE_URL)
ASKING_LINER = 'curl -fsSL "https://play.modiqo.ai/install?play={0}/comped" | sh'.format(HANDLE)


def page(path, title, description, nav_active, toc, body):
    """One page in the site's shell: the shared head, nav and footer around a docs layout."""
    links = [("./", "Home", ""), ("leaderboard.html", "Leaderboard", ""), ("docs.html", "Docs", "docs"),
             ("developers.html", "Developers", "developers"),
             ("https://github.com/rajkaria/comped", "GitHub", "")]
    nav = "\n".join('      <a href="{0}"{2}>{1}</a>'.format(
        href, label, ' class="on"' if key and key == nav_active else "") for href, label, key in links)
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{site}/{path}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="comped">
<meta property="og:url" content="{site}/{path}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{site}/card-wide.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="675">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{site}/card-wide.png">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧾</text></svg>">
<link rel="stylesheet" href="style.css">
</head>
<body>

<nav>
  <div class="wrap">
    <a class="brand" href="./">comped<span>.</span></a>
    <div class="links">
{nav}
      <a class="cta" href="./#get">Get my comp score</a>
    </div>
  </div>
</nav>

<div class="wrap" style="padding-top:48px;padding-bottom:72px">
<div class="doc-layout">

<aside class="toc">
{toc}
</aside>

<main class="doc">
{body}
</main>
</div>
</div>

<footer>
  <div class="wrap row">
    <span>comped: built on <a href="https://www.modiqo.ai">Modiqo's rote</a>. Free, open, MIT licensed.</span>
    <span class="sp"><a href="./">Home</a> · <a href="leaderboard.html">Leaderboard</a> · <a href="docs.html">Docs</a> · <a href="developers.html">Developers</a> · <a href="https://github.com/rajkaria/comped">Source</a></span>
  </div>
</footer>

</body>
</html>
""".format(title=esc(title), description=esc(description), site=SITE_URL, path=path, nav=nav, toc=toc, body=body)


def docs_page():
    """The user guide: how to run it, how to read it, what to do when it looks wrong."""
    toc = """  <strong>Getting started</strong>
  <a href="#install">One line</a>
  <a href="#quickstart">Try it on sample data</a>
  <a href="#reading">Reading your card</a>
  <a href="#detection">What it works out</a>
  <a href="#leaderboard">The leaderboard</a>
  <strong>Going further</strong>
  <a href="#options">Options</a>
  <a href="#outputs">What it writes</a>
  <a href="#trouble">When it looks wrong</a>
  <a href="#privacy">Privacy</a>
  <strong>More</strong>
  <a href="developers.html">Developers →</a>"""
    body = """
<h2 id="install">One line</h2>
<p>You need a Mac or Linux machine, a terminal, and <strong>python3</strong> (3.9 or newer, which every Mac has). Copy this, paste it into Terminal, press Enter:</p>
<pre><code>{one}</code></pre>
<p>It fetches <strong>rote</strong>: the free runner from <a href="https://www.modiqo.ai">Modiqo</a> that comped is written for: only if you don't already have it, signs you in to the registry if you aren't, prints what the comped Play reads and writes, and runs it without stopping to ask. About a minute the first time; ten seconds after that. <a href="{site}/run.sh">The script</a> is fifty lines; read it first if you like. Anything after <code>sh -s --</code> goes to the Play: <code>… | sh -s -- plan=claude-pro-20</code>.</p>
<p>Prefer to be asked before anything runs? The registry's own installer does the same steps and waits for a <em>yes</em> at each:</p>
<pre><code>{asking}</code></pre>
<div class="callout"><p>Already have rote? Then it's just <code>rote play run https://play.modiqo.ai/{handle}/comped --yes</code>: drop <code>--yes</code> to see the Ready selector. Check you're on 0.78 or newer with <code>rote --version</code>.</p></div>

<h2 id="quickstart">Try it on sample data first</h2>
<p>If you'd rather see it work before pointing it at your own logs, the Play ships with sample logs: real in shape, made-up in content.</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/comped \\
  claude_dir=resources/fixtures/claude \\
  codex_dir=resources/fixtures/codex \\
  out_dir=comped-demo</code></pre>
<p>Eight steps, about two seconds, and a card with tiny numbers. Then the real thing:</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/comped</code></pre>
<p>Everything lands in <code>~/comped/</code>. Run it again tomorrow and the card grows a line telling you what moved.</p>

<h2 id="reading">Reading your card</h2>
<p>Top to bottom:</p>
<ul>
<li><strong>The big number.</strong> What the last 30 days would have cost at the provider's public API prices. <em>Not a bill</em>: you're on a subscription and you paid what you paid.</li>
<li><strong>Your comp score, and your tier.</strong> That number divided by what your plan costs for the same window. <strong>13×</strong> means your subscription paid for itself thirteen times over; the tier is the word for that.</li>
<li><strong>Which AI cost what,</strong> largest first, with a bar.</li>
<li><strong>Cache-read share.</strong> How much of what the AI read came from cache. High is normal and good.</li>
<li><strong>Active days and sessions,</strong> so a big number reads as either heavy use or a heavy week.</li>
<li><strong>Since last time,</strong> once there is a last time.</li>
<li><strong>Detected.</strong> Which AI you use and through which tools. None of it typed by you.</li>
<li><strong>If you're on…</strong> every plan your provider sells, scored at once, with the one it assumed marked. Find your row.</li>
<li><strong>Repeat offenders.</strong> Things you've asked your agent to do three or more times on different days, with what the repeats cost.</li>
</ul>

<h2 id="detection">What it works out for you</h2>
<p>You type nothing. Every request your AI tools log carries the name of the model that answered it, and that name says who made it. From that, comped knows whether you're on Claude, ChatGPT/Codex, Kimi, GLM, DeepSeek, Gemini, Grok, Qwen, MiniMax or Mistral, and which tools you read it through.</p>
<p>The one thing your logs don't record is which <em>tier</em> you pay for: a Pro session and a Max session look identical. So rather than ask, or peek at your account (it never will), the card prices every plan your provider sells and marks the most expensive one that fits as the safe assumption. Your real score is at least that. If you want the exact row on the headline, say so once:</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/comped plan=claude-pro-20</code></pre>
<p>Say it once: a typed plan is remembered in <code>~/comped/comped-plan.txt</code> and every later run uses it. Delete the file to go back to inferring. Paying for something the table doesn't list: a Kimi or GLM coding plan, a team seat? <code>plan=usd:29</code> prices it.</p>
<h3>Your tier</h3>
<p>The score lands you in one of seven tiers, printed on the card and in <code>comped-share.txt</code>: Paying customer (under 1×), Break-even (1–2×), Comped (2–5×), Properly comped (5–12×), All-you-can-eat (12–30×), Hostage situation (30–80×), Please stop (80× and up).</p>

<h2 id="leaderboard">The leaderboard</h2>
<p>The last step of a run posts your score to <a href="leaderboard.html">{site}/leaderboard.html</a> and prints your rank. The line in <code>comped-share.txt</code> is rewritten with it, so what you post already says where you stand.</p>
<table><thead><tr><th>Rule</th><th>What it means for you</th></tr></thead><tbody>
<tr><th>Ranked by comp score</th><td>Full price ÷ your plan. A $20 plan at 60× beats a $200 plan at 13×. Ties break on dollars, then active days.</td></tr>
<tr><th>Ranks from $20 and 3 days</th><td>Under $20 at full price, or fewer than three active days in the window, you're posted but not ranked; the run says so.</td></tr>
<tr><th>One row per handle</th><td>A re-run replaces your row. Two machines with the same handle: the latest run wins. Blank handles post as <code>anon-xxxx</code>, one per machine.</td></tr>
<tr><th>Your row is yours</th><td>A random id in <code>~/comped/comped-device.txt</code> keys it. Nothing anyone else posts can touch it; nothing you post can touch theirs. Keep the file if you want re-runs to replace rather than add.</td></tr>
<tr><th>Held for a look</th><td>Over 2,000× or $250,000 is stored but not shown until someone looks. The server also recomputes score = dollars ÷ plan and refuses a mismatch.</td></tr>
<tr><th>Off the board</th><td><code>leaderboard=false</code> posts nothing. To remove a row already there, <a href="https://github.com/rajkaria/comped/issues">open an issue</a> with the handle.</td></tr>
</tbody></table>

<h2 id="options">Options you might change</h2>
<p>Add any of these after the command as <code>name=value</code>. Everything has a sensible default.</p>
{options}
<p>The full parameter list, including where each tool's logs are read from, is on the <a href="developers.html#play-comped">developers page</a>.</p>

<h2 id="outputs">What it writes</h2>
<p>All of it under <code>~/comped/</code> (or the <code>out_dir</code> you chose), and nowhere else. The card lists every path it wrote.</p>
{outputs}

<h2 id="trouble">When it looks wrong</h2>
<h3>"no log directory found"</h3>
<p>Expected if you don't use that tool: it's skipped and the run continues. If you <em>do</em> use it, its logs live somewhere unusual; point the right option at them: <code>claude_dir</code>, <code>codex_dir</code>, <code>pi_dir</code>, <code>opencode_dir</code>.</p>
<h3>The number looks too low</h3>
<p>Check <code>days_back</code> (it's 30 by default), then the "unpriced" list at the bottom of the report. A model that isn't in the price list contributes nothing to the total, on purpose: a guessed price would make the number worse, not better.</p>
<h3>The score is lower than I expected</h3>
<p>The headline assumes the most expensive plan that fits. Look at the <em>If you're on…</em> rows for your actual tier, or pass <code>plan=</code>.</p>
<h3>No repeat offenders</h3>
<p>The bar is deliberately high: three asks, two sessions, two days. Try <code>repeat_threshold=2</code>.</p>
<h3>No PNG</h3>
<p>The SVG card is always written and uploads to LinkedIn as-is. For a PNG, install <code>rsvg-convert</code>, or use a Mac where it's built in.</p>
<h3>It asked me to sign in</h3>
<p>That's rote's registry, so the Play can be fetched and verified. comped itself never signs in to anything; the one thing it sends is your score to the leaderboard, and only if <code>leaderboard</code> is left at <code>true</code>.</p>
<h3>It says "not posted"</h3>
<p>The card is done; only the leaderboard post failed, usually because the machine is offline or the post timed out. Run again when you're online, or leave it. The exact reply is in <code>~/comped/comped-rank.json</code>.</p>
<h3>I'm on the board as anon-xxxx</h3>
<p>The run had no handle. <code>gotcomped.com/run.sh</code> fills in your rote handle; if you ran the Play some other way, pass <code>handle=yourname</code>. A re-run replaces your row, so the anonymous one goes away when a named one arrives from the same machine.</p>

<h2 id="privacy">Privacy</h2>
<ul>
<li><strong>Reads</strong> your AI tools' session logs. Nothing else.</li>
<li><strong>Never reads</strong> <code>~/.claude.json</code>, <code>~/.codex/auth.json</code> or any credential, keychain or token file. Which AI you use comes from the logs; your plan is never looked up.</li>
<li><strong>Sends one thing.</strong> After the card is written, your score goes to the leaderboard: handle, comp score, tier, full-price total, plan and its price, detected providers and tools, days, sessions, cache share, and a random id that keys your row. No paths, prompts, model names or hostnames. It's saved to <code>~/comped/comped-rank.json</code> before it goes. <code>leaderboard=false</code> makes the run entirely offline: no telemetry, no "anonymous usage", no version check, nothing.</li>
<li><strong>Writes</strong> only under the folder you choose, and tells you every path.</li>
<li><strong>Your messages</strong> are cut to 120 characters and hashed. Never the full text, never on a card.</li>
</ul>
<p>How to verify each of those rather than believe them is on the <a href="developers.html#privacy">developers page</a>.</p>
""".format(one=esc(ONE_LINER), asking=esc(ASKING_LINER), site=SITE_URL, handle=HANDLE,
           options=params_table_for("comped", ("days_back", "plan", "leaderboard", "handle", "repeat_threshold", "out_dir", "card_theme")),
           outputs=outputs_table("comped"))
    return page("docs.html", "comped: docs",
                "How to get your comp score in one line, how to read the card, what it works out for you, and what to do when a number looks wrong.",
                "docs", toc, body)


def developers_page():
    plans, plans_as_of = plans_table()
    model_links, model_count, price_meta = models_list()
    toc = """  <strong>The Plays</strong>
  <a href="#plays">Overview</a>
  <a href="#play-comped">comped</a>
  <a href="#play-session-ledger">session-ledger</a>
  <a href="#play-wrong-turns">wrong-turns</a>
  <strong>Under it</strong>
  <a href="#tracking">What it tracks</a>
  <a href="#math">The arithmetic</a>
  <a href="#detection">Detection</a>
  <a href="#prices">Prices and plans</a>
  <a href="#leaderboard">Leaderboard API</a>
  <a href="#privacy">Verifying privacy</a>
  <strong>Reference</strong>
  <a href="#cli">Without rote</a>
  <a href="#source">Source and spec</a>
  <a href="docs.html">← User docs</a>"""
    body = """
<h2 id="plays">Three Plays, one core</h2>
<p>comped is three <a href="https://www.modiqo.ai">rote</a> Plays on one dependency-free Python package, <code>comped_core</code>. The package is bundled byte-identical into each Play (a sync check in CI enforces it), so the three share every adapter, the ledger, the price table and the renderers. Every step is one <code>python3</code> invocation printing a JSON object as its last line; a missing log directory is a warning and exit 0, bad arguments exit 2, and nothing ever prints a traceback.</p>
{play_comped}
{play_ledger}
{play_wrong}

<h2 id="tracking">What it tracks, field by field</h2>
<p>Three record types come out of the logs. The tables are generated from the dataclasses that define them, so they cannot drift from the code.</p>
<h3>Usage records: one per API call</h3>
{usage_fields}
<h3>Human messages: one per message in the user role</h3>
<p>These exist to attribute cost to <em>what you asked</em>. Without them a month of agent work is an undifferentiated wall of API calls.</p>
{human_fields}
<h3>Tool events: one per tool call</h3>
{tool_fields}
<div class="callout"><p><strong>Never collected:</strong> file contents, tool outputs beyond a 300-character error snippet, prompt text beyond the 120-character truncation, and anything at all from a credential, keychain or token file. There is no identifier for you, no machine id and no run id that leaves your disk, because nothing leaves your disk.</p></div>

<h2 id="math">The arithmetic</h2>
<h3>Pricing</h3>
<p>Per record, in exact decimal arithmetic: never floating point, which is how cent-level errors get into totals:</p>
<pre><code>usd = uncached_input × in_rate
    + cache_write     × cache_write_rate
    + cache_read      × cache_read_rate
    + output          × out_rate</code></pre>
<p>Reasoning tokens are already counted inside output, because that is how they are billed. Rounding happens once, at display time.</p>
<h3>Deduplication</h3>
<p>Claude Code writes a line per content block, so the same API call appears several times with the same <code>message.id</code> and <code>requestId</code>. On real logs <strong>about four in ten usage lines are duplicates</strong>. They are collapsed on that pair, and the count of what was dropped appears in the source report. Codex has the opposite shape: cumulative counters, so each record is the difference from the previous snapshot, and a counter that goes backwards starts a new baseline rather than producing a negative. CI checks the per-model Claude Code totals against <a href="https://github.com/ryoppippi/ccusage">ccusage</a>, an independent parser.</p>
<h3>Windows and the multiplier</h3>
<p>A record is in the window if <em>its own timestamp</em> is, never the file's modification time. Plan cost is prorated by <code>days_back ÷ 30.4375</code>: the mean month: so a 14-day window is compared against 14 days of subscription, not a whole month of it.</p>
<h3>Repeat offenders</h3>
<p>Messages are normalised (lowercased, paths, URLs, numbers and hashes replaced by placeholders, stop-words dropped), turned into 2-word shingles, and clustered when their Jaccard similarity is <strong>0.5 or higher</strong>. A cluster qualifies when it has at least <code>repeat_threshold</code> asks across <strong>two or more sessions on two or more days</strong>. Its repeat cost is the cluster's total minus its cheapest single solve: what you paid to ask again. Harness-generated text: continuation preambles, injected reminders, observer prompts: stays in the ledger, because it costs real money, but is never counted as something you asked for.</p>
<h3>Wrong turns</h3>
<p>Three signals with honest confidence labels. <strong>Tool errors</strong> (high): the call returned an error; its first line, stripped of paths and numbers, is the signature. <strong>Corrections</strong> (medium): your next message matched a correction phrase: "no,", "revert", "that's not", "undo". <strong>Reverts</strong> (high): a destructive git command ran. A class is reported when it recurs at least <code>min_recurrence</code> times across two or more sessions. Recovery cost is the signalling turn plus the next one.</p>

<h2 id="detection">Detection</h2>
<p>Nothing on the machine records which subscription you pay for, and the one place it is written is a file this tool refuses to open. So <code>plan</code> defaults to <code>auto</code> and the run infers what it can:</p>
<ol class="steps">
<li><b>The harnesses.</b> {harnesses}. A directory that isn't there is a shrug, and the card names the ones it didn't find.</li>
<li><b>The provider.</b> Read off the model id after gateway and region prefixes are stripped: <code>us.anthropic.claude-opus-5</code>, <code>bedrock/anthropic.claude-sonnet-5</code> and <code>claude-opus-5</code> are one provider, not three. Claude Code pointed at Moonshot or Z.ai gives itself away the same way.</li>
<li><b>The tier: the one thing no log records.</b> A Pro session and a Max session are the same bytes. So every subscription the detected providers sell is priced against the window at once; the assumed row is deliberately the least flattering: the most expensive plan that fits, i.e. the smallest multiplier you could honestly claim: and the rest are one glance away.</li>
<li><b>Anything else.</b> A provider with no subscription in the table is named, its spend stays in the total, and the card says nothing in the plan cost covers it. <code>plan=usd:&lt;amount&gt;</code> prices one the table lacks; <code>plan=&lt;id&gt;</code> overrides the inference outright.</li>
</ol>
{providers}
<div class="callout"><p>Detection reads nothing new. It looks at records the ledger already parsed and at which of the four log directories existed. A model id nobody recognises is reported by name as unknown rather than assigned to a provider by guess. The table above is generated from <code>comped_core/detect.py</code>.</p></div>

<h2 id="prices">Prices and plans</h2>
<p>The price table is a snapshot, bundled with the Play, that carries its own provenance: the source URL, the upstream file's sha256, and the date it was taken. It is never fetched at runtime. Where several upstream keys map to one model: the vendor's own and a reseller's: the vendor's wins.</p>
<table><tbody>
<tr><th>Source</th><td><code>{price_source}</code></td></tr>
<tr><th>As of</th><td>{price_as_of}</td></tr>
<tr><th>Models</th><td>{model_count}</td></tr>
</tbody></table>
<p>{models}</p>
<p>A model not in this list is reported under "unpriced" with its token counts, and no dollar figure is invented for it.</p>
<h3>Plans</h3>
<p>Public list prices as of {plans_as_of}. <code>auto</code> is not a price: it means infer the provider and price every row it sells.</p>
{plans}
<div class="callout warn"><p>The tier is inferred from model ids in the logs, never from an account. The tool will not read <code>~/.claude.json</code> or <code>~/.codex/auth.json</code> to discover it, because a tool that reads your OAuth files to be convenient is a tool you should not run.</p></div>

<h2 id="leaderboard">Leaderboard API</h2>
<p>Two endpoints on this origin, both JSON, both stdlib Python on Vercel (<code>api/score.py</code>, <code>api/leaderboard.py</code>), both thin: each calls one Postgres function through PostgREST with a publishable key. The SQL functions are the trust boundary. The table is closed to the API role; every bound is enforced in SQL; the device id that keys a row is never returned by either call, so nothing you can read lets you write someone else's row.</p>
<h3>POST /api/score</h3>
<pre><code>{{"device": "&lt;uuid&gt;", "handle": "priya", "multiplier": 12.99, "comped_usd": 2560.98, "plan_usd": 197.13,
 "tier": "All-you-can-eat", "plan": "Claude Max 20x", "plan_id": "claude-max-200", "plan_source": "auto",
 "providers": ["anthropic"], "harnesses": ["claude-code"], "days_back": 30, "active_days": 22,
 "sessions": 99, "cache_share": 0.98, "client": "comped/0.1.4"}}</code></pre>
<p>Reply <code>200</code>: <code>{{"ok": true, "rank": 7, "of": 312, "percentile": 2.2, "eligible": true, "held": false, "reason": null, "handle": "priya", "url": "…/leaderboard.html#priya", "board": "…"}}</code>. <code>400</code> names the first bad field; <code>429</code> is the same device inside 15 seconds; <code>502</code> is storage. The server recomputes <code>multiplier = comped_usd / plan_usd</code> and refuses a mismatch above 2%. Handles are <code>[A-Za-z0-9][A-Za-z0-9_.-]{{0,31}}</code>. Over 2,000× or $250,000 is stored with <code>held: true</code> and not shown.</p>
<h3>GET /api/leaderboard?sort=multiplier|comped_usd&amp;limit=100</h3>
<p>One row per handle (the latest run) or per anonymous device, ranked; up to 500. Each row carries what the table above shows plus <code>plan_id</code>, <code>plan_source</code>, <code>runs</code>, <code>first_seen</code> and <code>updated_at</code>, and a <code>rules</code> object restates the thresholds. Cached for 30 seconds at the edge. CORS is open: embed it where you like.</p>
<h3>Posting without the Play</h3>
<p><code>python3 leaderboard/post_score.py --out-dir ~/comped --handle you</code> after a <code>card</code> run does exactly what the Play's last step does; <code>--url</code> points it elsewhere and <code>COMPED_LEADERBOARD_URL</code> does the same for the Play. A machine whose python cannot verify TLS certificates (a python.org build on a Mac that never ran <em>Install Certificates</em>) falls back to the system CA bundle, then to <code>curl</code> with a fixed argv.</p>

<h2 id="privacy">Verifying the privacy claims</h2>
<ul>
<li><strong>No network in the core.</strong> <code>python3 -m unittest tests.test_no_network</code> fails if <code>comped_core</code> imports <code>urllib</code>, <code>http</code>, <code>socket</code>, <code>requests</code> or <code>ssl</code>, if anything but the PNG renderer mentions <code>subprocess</code>, or if any source line references a credential path. A second test proves the only file in any Play package that can open a socket is <code>post_score.py</code>, the leaderboard poster, and that it is bundled into <code>comped</code> alone. The site is served with <code>connect-src 'self'</code>: the page can ask this origin for the board and nobody else for anything.</li>
<li><strong>What the poster sends</strong> is one JSON object, built in <a href="https://github.com/rajkaria/comped/blob/main/leaderboard/post_score.py">one function</a> from the priced summary, and written to <code>out_dir/comped-rank.json</code> before it goes. The test suite asserts the field list and that no path, model id or message text can be in it.</li>
<li><strong>No surprises in what it writes.</strong> Every run lists every path it wrote, in the report and in its JSON output.</li>
<li><strong>Determinism.</strong> Pin <code>--now</code> and two runs produce byte-identical output. The suite proves it with PATH emptied, which also proves the pipeline needs no external binary.</li>
<li><strong>Fixtures.</strong> The sample logs and the presentation fixtures captured from real runs are scanned for real paths, names and keys before every build.</li>
<li><strong>Read the code.</strong> A few thousand lines of standard-library Python, no dependencies: <a href="https://github.com/rajkaria/comped">github.com/rajkaria/comped</a>.</li>
</ul>

<h2 id="cli">Running it without rote</h2>
<p>The Plays are a thin wrapper around the package. Clone the repo and use the module directly:</p>
<pre><code>git clone https://github.com/rajkaria/comped &amp;&amp; cd comped
python3 -m comped_core ledger  --days-back 30 --out-dir ~/comped
python3 -m comped_core price   --out-dir ~/comped            # --plan auto by default
python3 -m comped_core repeats --out-dir ~/comped --repeat-threshold 3
python3 -m comped_core card    --out-dir ~/comped</code></pre>
<p>The full set, generated from the argument parser:</p>
{cli}
<p><code>verify</code> re-prices the ledger from scratch and confirms the total in your report still reproduces.</p>

<h2 id="source">Source and spec</h2>
<ul>
<li><a href="https://github.com/rajkaria/comped">Source</a>: MIT. CI runs the suite on Ubuntu and macOS across Python 3.9 and 3.12, checks the bundled copies of the core haven't drifted, and fails if these pages are stale.</li>
<li><a href="https://github.com/rajkaria/comped/blob/main/docs/SPEC.md">The spec</a>: the full derivation: record model, pricing, deduplication, windows, repeat clustering, wrong-turn signals, and the trust statements.</li>
<li>Play sources under <code>docs/plays/&lt;slug&gt;/</code>; the packages under <code>plays/</code> are generated from them by <code>tools/build_plays.py</code>.</li>
</ul>
""".format(play_comped=play_section("comped"), play_ledger=play_section("session-ledger"),
           play_wrong=play_section("wrong-turns"),
           usage_fields=fields_table(models.UsageRecord), human_fields=fields_table(models.HumanMessage),
           tool_fields=fields_table(models.ToolEvent),
           price_source=esc(price_meta.get("source_url", "")), price_as_of=esc(price_meta.get("as_of", "")),
           model_count=model_count, models=model_links, plans=plans, plans_as_of=esc(plans_as_of),
           cli=cli_reference(), providers=providers_table(), harnesses=harness_list())
    return page("developers.html", "comped: developers",
                "The three Plays, every parameter, the record fields, the arithmetic, how detection works, the price table, and how to verify the privacy claims.",
                "developers", toc, body)


def main():
    for name, html_text in (("docs.html", docs_page()), ("developers.html", developers_page())):
        out = ROOT / "site" / name
        out.write_text(html_text, encoding="utf-8")
        print("wrote {0} ({1} bytes)".format(out, len(html_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
