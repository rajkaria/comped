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
from tools import build_dist                        # noqa: E402  (the one place the version lives)

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
        ("comped-report.md", "The whole run in Markdown: card, the line to post, a link that draws the card as a downloadable picture, per-model table, sources, repeats, dividend, delta, unpriced models, methodology, privacy, and every path written."),
        ("comped-card.svg", "The shareable card, 1200×675."),
        ("comped-card-square.svg", "The same card on a square canvas. PNG renderers fit thumbnails into a square box and would otherwise crop the wide one."),
        ("comped-card.png", "Rendered from the square SVG when this machine has rsvg-convert or macOS qlmanage. Absent, with a note pointing at the card page, when it doesn't: that page draws the same card in your browser and downloads it as a PNG."),
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
            # A switch has no value to show: "--json False" reads like a thing you would type.
            if a.default in (None, "") or a.nargs == 0:
                opts.append(flag)
            else:
                opts.append("{0} {1}".format(flag, a.default))
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


ONE_LINER = "curl -fsSL {0}/comped.sh | sh".format(SITE_URL)
PLAY_LINER = "curl -fsSL {0}/run.sh | sh".format(SITE_URL)
ASKING_LINER = 'curl -fsSL "https://play.modiqo.ai/install?play={0}/comped" | sh'.format(HANDLE)


def page(path, title, description, nav_active, toc, body, scripts=""):
    """One page in the site's shell: the shared head, nav and footer around a docs layout."""
    # (href, label, nav key, class that hides it on small screens)
    links = [("./", "Home", "", "hide-xs"), ("leaderboard.html", "Leaderboard", "", ""), ("docs.html", "Docs", "docs", ""),
             ("plays.html", "Plays", "plays", "hide-xs"),
             ("developers.html", "Developers", "developers", "hide-sm"),
             ("https://github.com/rajkaria/comped", "GitHub", "", "hide-sm")]
    nav = "\n".join('      <a href="{0}"{2}>{1}</a>'.format(
        href, label, ' class="{0}"'.format(" ".join(c for c in (("on" if key and key == nav_active else ""), hide) if c))
        if (key == nav_active and key) or hide else "") for href, label, key, hide in links)
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
      <a class="cta" href="./#get">Get my <span class="hide-xs">comp </span>score</a>
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
    <span class="sp"><a href="./">Home</a> · <a href="leaderboard.html">Leaderboard</a> · <a href="docs.html">Docs</a> · <a href="plays.html">Plays</a> · <a href="developers.html">Developers</a> · <a href="https://github.com/rajkaria/comped">Source</a></span>
  </div>
</footer>
{scripts}
</body>
</html>
""".format(title=esc(title), description=esc(description), site=SITE_URL, path=path, nav=nav, toc=toc, body=body, scripts=scripts)


def docs_page():
    """The user guide: how to run it, how to read it, what to do when it looks wrong."""
    toc = """  <strong>Getting started</strong>
  <a href="#install">One line</a>
  <a href="#agent">Or ask your agent</a>
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
<p>You need a terminal and <strong>python3</strong> (3.9 or newer, which every Mac has). Copy this, paste it into Terminal, press Enter:</p>
<pre><code>{one}</code></pre>
<p>No account, no package manager, nothing installed. It downloads about 150 KB of standard-library Python into a temporary directory, runs it, and deletes the directory on the way out. Ten seconds, and the only thing left on your machine is <code>~/comped/</code>. <a href="{site}/comped.sh">The script</a> is sixty lines; read it before you paste it. Anything after <code>sh -s --</code> goes to the run: <code>… | sh -s -- plan=claude-pro-20</code>.</p>
<p>It checks the download against <a href="{site}/comped.tar.gz.sha256">its published checksum</a> before running anything. That proves the download arrived whole, not that this site is honest; for that, read <a href="https://github.com/{gh}">the source</a>.</p>

<h3>With node: npx</h3>
<p>If you already have node, there is nothing to download by hand and no shell to worry about, which also makes this the one to try on Windows:</p>
<pre><code>npx comped</code></pre>
<p>The package is the same standard-library Python in an npm wrapper: <strong>no node dependencies</strong>, no install script, and <code>bin/comped.js</code> does nothing but find an interpreter and hand it the payload. You still need Python 3.9 or newer on your PATH. Arguments work the same: <code>npx comped plan=claude-pro-20</code>.</p>

<h3>The other way in: as a rote Play</h3>
<p>comped is also published as a Play on Modiqo's registry, and that is the careful way in: <strong>rote</strong> prints every parameter and every path the Play will touch and waits for your yes, and the whole package sits in public where you can read it before you run it. The trade is a free Modiqo account, because rote will not run anything until you are signed in.</p>
<pre><code>{play_one}</code></pre>
<p>That line installs rote if you don't have it, signs you in, and runs the Play. About a minute the first time. To be asked at every step instead, use the registry's own installer:</p>
<pre><code>{asking}</code></pre>
<div class="callout"><p>Already have rote? Then it's just <code>rote play run https://play.modiqo.ai/{handle}/comped --yes</code>: drop <code>--yes</code> to see the Ready selector. Check you're on 0.78 or newer with <code>rote --version</code>. Want to read the whole thing before you run it? <code>rote play inspect {handle}/comped</code> prints the manifest, and that much needs no account.</p></div>
<p>Same code every way. The Play, the download and the npm package carry a byte-identical copy of the core, and CI fails if they ever drift apart. Same parameters, same card, same row on the board.</p>

<h2 id="agent">Or ask the agent you already have</h2>
<p>If you spend your day in Claude Code, Codex, Cursor or anything else with a shell, you don't need the terminal line at all. Paste this at your agent:</p>
<pre><code>Run comped on this machine: fetch {site}/llms.txt and follow it.</code></pre>
<p>It reads <a href="{site}/llms.txt">llms.txt</a>, a briefing written for agents rather than people, and takes it from there: it asks you first whether to put your score on the leaderboard, runs comped without needing an account, and reads the card back to you. That file also tells it what it must not do, including summarising your logs by eye and copying anything out of <code>~/comped</code> into a message or a commit. It is short. Read it before you paste the line.</p>

<h2 id="quickstart">Try it on sample data first</h2>
<p>If you'd rather see it work before pointing it at your own logs, sample logs travel with it: real in shape, made-up in content. This works through every door.</p>
<pre><code>{one} -s -- \\
  claude_dir=resources/fixtures/claude \\
  codex_dir=resources/fixtures/codex \\
  out_dir=comped-demo leaderboard=false</code></pre>
<p>Or with node:</p>
<pre><code>npx comped \\
  claude_dir=resources/fixtures/claude \\
  codex_dir=resources/fixtures/codex \\
  out_dir=comped-demo leaderboard=false</code></pre>
<p>Or, as a Play:</p>
<pre><code>rote play run https://play.modiqo.ai/{handle}/comped \\
  claude_dir=resources/fixtures/claude \\
  codex_dir=resources/fixtures/codex \\
  out_dir=comped-demo</code></pre>
<p>About two seconds, and a card with tiny numbers. Then the real thing:</p>
<pre><code>{one}</code></pre>
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
<p>The run had no handle, which is what happens by default: nothing about you is assumed. Pass <code>handle=yourname</code> to claim a name. The rote path fills in your rote handle automatically. A re-run replaces your row, so the anonymous one goes away when a named one arrives from the same machine.</p>

<h2 id="privacy">Privacy</h2>
<ul>
<li><strong>Reads</strong> your AI tools' session logs. Nothing else.</li>
<li><strong>Never reads</strong> <code>~/.claude.json</code>, <code>~/.codex/auth.json</code> or any credential, keychain or token file. Which AI you use comes from the logs; your plan is never looked up.</li>
<li><strong>Sends one thing.</strong> After the card is written, your score goes to the leaderboard: handle, comp score, tier, full-price total, plan and its price, detected providers and tools, days, sessions, cache share, and a random id that keys your row. No paths, prompts, model names or hostnames. It's saved to <code>~/comped/comped-rank.json</code> before it goes. <code>leaderboard=false</code> makes the run entirely offline: no telemetry, no "anonymous usage", no version check, nothing.</li>
<li><strong>Writes</strong> only under the folder you choose, and tells you every path.</li>
<li><strong>Your messages</strong> are cut to 120 characters and hashed. Never the full text, never on a card.</li>
</ul>
<p>How to verify each of those rather than believe them is on the <a href="developers.html#privacy">developers page</a>.</p>
""".format(one=esc(ONE_LINER), play_one=esc(PLAY_LINER), asking=esc(ASKING_LINER), site=SITE_URL, handle=HANDLE,
           gh="rajkaria/comped",
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
  <a href="#agents">From an agent</a>
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
 "sessions": 99, "cache_share": 0.98, "client": "comped/0.1.5"}}</code></pre>
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
<p>Three ways, no account for any of them. The quickest is the published npm package, which is this same standard-library Python with a launcher in front of it: no node dependencies, no install script, nothing compiled.</p>
<pre><code>npx comped                                                # or npx comped@{version} to pin it</code></pre>
<p>The one-line download, <code>curl -fsSL https://gotcomped.com/comped.sh | sh</code>, needs no node either and checks itself against <a href="https://gotcomped.com/comped.tar.gz.sha256">its published checksum</a>. Or clone the repo and use the module directly. One command does the whole card:</p>
<pre><code>git clone https://github.com/rajkaria/comped &amp;&amp; cd comped
python3 -m comped_core run --out-dir ~/comped              # read, price, cluster, render</code></pre>
<p><code>run</code> is the four steps the Play runs, in one process, calling the same functions in the same order: the numbers are identical. It stays offline, so posting your score to the leaderboard is still a separate script you run yourself:</p>
<pre><code>python3 leaderboard/post_score.py --out-dir ~/comped --handle you</code></pre>
<p>The steps on their own, when you want to look at one of them:</p>
<pre><code>python3 -m comped_core ledger  --days-back 30 --out-dir ~/comped
python3 -m comped_core price   --out-dir ~/comped            # --plan auto by default
python3 -m comped_core repeats --out-dir ~/comped --repeat-threshold 3
python3 -m comped_core card    --out-dir ~/comped</code></pre>
<p>The full set, generated from the argument parser:</p>
{cli}
<p><code>verify</code> re-prices the ledger from scratch and confirms the total in your report still reproduces. Every command prints one JSON object as its last stdout line; <code>ok: false</code> exits 1.</p>

<h2 id="agents">Running it from your coding agent</h2>
<p>You already have an agent with a shell. Paste this at it and it will do the rest:</p>
<pre><code>Run comped on this machine: fetch https://gotcomped.com/llms.txt and follow it.</code></pre>
<p><a href="https://gotcomped.com/llms.txt">llms.txt</a> is the briefing written for the agent rather than for you: what comped reads and refuses to read, the three ways to run it in the order to try them, the rule that it must ask you before posting your score anywhere, the output contract, and how to read the report back to you. It tells the agent not to summarise your logs by eye and not to paste anything out of <code>~/comped</code> into a message or a commit.</p>
<p>It tries the doors in order and stops at the first that opens: the published Play if rote is already signed in, then the account-free <code>comped.sh</code> download, then <code>npx comped</code> where there is node but no Unix shell, and a <code>git clone --depth 1</code> last. Same code every way. Read the file before you paste the line; it is {llms_lines} lines and it is the whole of what your agent is being told.</p>

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
           cli=cli_reference(), providers=providers_table(), harnesses=harness_list(),
           llms_lines=len((ROOT / "site" / "llms.txt").read_text().splitlines()),
           version=build_dist.version())
    return page("developers.html", "comped: developers",
                "The three Plays, every parameter, the record fields, the arithmetic, how detection works, the price table, and how to verify the privacy claims.",
                "developers", toc, body)


PLAYS_INDEX = [
    ("agents", "What your agents cost", "comped_core",
     "Three Plays that read the transcripts your coding agents already write. Nothing is sent, "
     "nothing is guessed, and every number has a line showing the arithmetic behind it.",
     [
      ("comped",
       "What would this month have cost at list price, and how far ahead of your plan are you?",
       "The card. List-price total for the window, the multiplier against the plan you actually pay "
       "for, your cache share, the delta since last time, the asks you keep repeating, and your rank "
       "on the board. It works out which AI you run from the model ids in the logs, so you type nothing.",
       "", "handle=yourname"),
      ("session-ledger",
       "One ledger, four harnesses, no double counting.",
       "The primitive the other two are built on. Claude Code writes one line per content block, so "
       "roughly four in ten usage lines are streaming duplicates of the same API call. Codex writes "
       "cumulative counters. This collapses both into one deduplicated ledger, subagents included, "
       "and judges nothing.",
       "", ""),
      ("wrong-turns",
       "What does your agent keep getting wrong, and what did recovering cost?",
       "Tool calls that errored, the messages where you corrected it, and reverts. Grouped into "
       "recurring classes, counted across sessions and days, priced in tokens, one redacted line of "
       "evidence each, and a drafted CLAUDE.md rule for every class that recurred three times. It "
       "never edits your rules file.",
       "", ""),
     ]),
    ("machine", "What your machine has been hoarding", "daily_core",
     "Six read-only scans of files your machine already keeps. No network, no credentials, and every "
     "one runs cold on bundled fixtures first so you can watch it work before you point it at anything "
     "of yours.",
     [
      ("tab-debt",
       "How many tabs are open, and how long since the oldest one was looked at?",
       "The tab strip shows neither a number nor a date, but the session files your browser writes "
       "hold both. Chrome and its family, Firefox, Safari and Arc, read directly: Chrome session files "
       "are a binary command log and Firefox stores its session in a compressed container, so both "
       "readers were written from the format up.",
       "demo=true", ""),
      ("birthday-radar",
       "Whose birthday is next, and how much of your address book has no date at all?",
       "Your address book mentions a birthday on the morning of, which is the one moment the "
       "information is useless. This sorts by how soon, so the next one is a number of days. Contacts "
       "database, vCard exports and CSV, any one of which is enough.",
       "demo=true", "vcard_dir=~/Documents"),
      ("app-graveyard",
       "Which applications did you stop opening, and which are still Intel only?",
       "macOS records the last time you opened every application and never shows you the list. This "
       "asks Spotlight, measures each bundle, and reads sixteen bytes into every executable to say "
       "which ones your Apple silicon Mac is still emulating.",
       "demo=true", "unused_days=180"),
      ("vault-pulse",
       "Which notes are load-bearing, which were written once, and is the daily habit alive?",
       "A notes folder only grows, and nothing in the editor says which notes matter. The links give "
       "the graph and the timestamps give the habit. Orphans, broken links, and the daily-note streak. "
       "Obsidian is found automatically; any markdown folder works.",
       "demo=true", "vault=~/Notes"),
      ("desktop-clutter",
       "What is actually on the Desktop and in Downloads, by age and by size?",
       "Both folders are append-only in practice, and the Finder sorts by name so the oldest file is "
       "invisible. Counted, aged, sized, duplicates found by hash, and graded A to F. On the machine "
       "this was built on it came back F with 164 duplicate groups.",
       "demo=true", ""),
      ("receipt-ledger",
       "What do the receipt files you already have add up to?",
       "PDF invoices, saved confirmation pages, exported messages and plain text, four formats in one "
       "folder that nobody opens one at a time. The PDF reader decodes ToUnicode maps and rebuilds "
       "lines from the text matrix. Currencies are totalled separately and never summed across each "
       "other, and a document has to prove it is a receipt before it counts.",
       "demo=true", "receipts_dir=~/Downloads"),
     ]),
    ("micro", "Ten seconds, many times a day", "micro_core",
     "Twelve Plays small enough to run on reflex. Five of them remember what you told them in one "
     "append-only file under your home directory. None of them touch the network, and none of them "
     "take an out_dir, because these print.",
     [
      ("whatis",
       "What is that opaque string?",
       "Paste it and it peels it. A base64 blob holding gzip holding JSON holding a JWT is one input "
       "and four layers, and you get all four. JWTs, base64, gzip, epochs, UUIDs, IPs, cron "
       "expressions and magic bytes.",
       "text=aHR0cHM6Ly9nb3Rjb21wZWQuY29t", ""),
      ("fits",
       "Will this fit the window, and what will it cost?",
       "Point it at text or a file. Bytes, lines and words are facts and it states them. The token "
       "figure is an estimate, so it prints a range and the method that produced it rather than "
       "asserting a number the stdlib cannot know.",
       "path=README.md", ""),
      ("is-it-secret",
       "What should you redact before pasting that?",
       "Run it on anything about to leave your machine. It knows the literal shapes: AWS key ids, "
       "GitHub tokens including fine-grained ones, private key headers, connection strings. It hands "
       "back the same text with those parts replaced, and it never prints what it found.",
       "path=README.md", ""),
      ("cron-when",
       "When does that cron expression actually fire?",
       "The English, the next five fires in your zone and in UTC side by side, and the daylight saving "
       "trap. When both day fields are restricted, cron takes the union rather than the intersection, "
       "which is the thing most readers get wrong.",
       "expr='0 3 * * 1' tz=Europe/London", ""),
      ("punch",
       "How many times was the day broken, and what was the longest block you got?",
       "One line saying what you are doing, which takes two seconds. Do it a few times a day and it "
       "answers what a calendar cannot: not where the time went, but how often it was cut.",
       "note='writing the launch post'", ""),
      ("spent",
       "What went out today, and where does the month land?",
       "One line in, a spend log that owes nothing to a bank, an app or an export. Amount, label, "
       "optional tag. Decimal arithmetic end to end, never a float.",
       "entry='320 lunch #food'", ""),
      ("jot",
       "The thought, into the vault, in two seconds.",
       "A thought arrives while you are doing something else. One line and it is appended to a "
       "markdown file in your vault, timestamped, and you are back to what you were doing. No app to "
       "open, no place to decide on.",
       "note='ring the dentist'", "vault_dir=~/Notes"),
      ("streak",
       "How long is the run, and which weekday do you keep dropping?",
       "One word, and it keeps the only part of habit tracking that changes behaviour: the current "
       "run, the record, a grid of the last twenty-one days, and the day of the week you keep losing.",
       "did=water", ""),
      ("last-turn",
       "What did the turn that just finished cost?",
       "Not this month and not this project. That one turn, ninety seconds ago. Model, tokens in and "
       "out, cache share, dollars, and today's running total. It reads a 256 KB tail rather than your "
       "history, which is why it can run twenty times a day.",
       "", ""),
      ("budget-left",
       "How much of today's budget is gone, and how fast is it going?",
       "You set a number you are willing to spend on agents today. This says how much is left, the "
       "burn rate, and whether you hit the cap before the day ends.",
       "daily_budget=10", ""),
      ("since-last",
       "What did the agent actually touch?",
       "Not what it said it did. What moved on disk since you last asked. Created, changed, deleted, "
       "and whether anything outside the repository moved. It watches the mtimes of the sensitive "
       "directories and can tell you something under one of them changed. It never opens them.",
       "root=.", ""),
      ("safe-to-commit",
       "What is staged that should not enter history?",
       "The last thing between a live credential and permanent git history is you, at the moment you "
       "type commit. It parses .git/index directly, with no subprocess: credentials, a tracked .env, "
       "leftover debugging, and files large enough to regret for the life of the repository.",
       "repo=.", ""),
     ]),
    ("repos", "What your git history knows", "daily_core",
     "Four Plays over the repositories already on this machine. Git records more than anyone reads "
     "back: who wrote each surviving line, the committer's own UTC offset, and whether the code an "
     "agent wrote is still there.",
     [
      ("bus-factor",
       "Which files have exactly one author left, and has that person gone?",
       "Every team knows some of its code has one author and nobody knows which files. Blame gives "
       "the surviving lines, the log gives the last time each author committed anything, and the "
       "join is the answer. Sole ownership is only a risk when the owner has stopped showing up, so "
       "the two facts are reported together rather than collapsed into one score.",
       "demo=true", "root=~/Projects"),
      ("night-shift",
       "When were you actually working, in your own zone rather than this laptop's?",
       "Every editor shows commit times in whatever zone the machine is set to today, which quietly "
       "rewrites your history each time you travel. Git stores the committer's own UTC offset "
       "inside the timestamp, so a commit made at 04:12 in Tokyo stays a 04:12 commit. This reads "
       "that offset instead of the local clock.",
       "demo=true", "root=~/Projects days=90"),
      ("kept",
       "Of everything the agent wrote for you, how much is still in the file?",
       "Every other number about a coding agent is what it cost. This one is what it was worth. It "
       "joins the session transcripts your agents already keep against git blame to ask how much "
       "agent-written code survived. Git knows the answer and nobody asks it.",
       "demo=true", "root=~/Projects"),
      ("upstream-pulse",
       "Which of your dependencies has nobody left maintaining it?",
       "A vulnerability scanner tells you about the bugs somebody already found and wrote down. "
       "This tells you about the packages where nobody is looking any more: last release years ago, "
       "exactly one human who can publish, repository archived. It reads the lockfiles you have.",
       "demo=true", "root=~/Projects"),
     ]),
    ("world", "What your browser, disk and calendar hold", "daily_core",
     "Six more read-only scans. Three of them, reply-debt, standing-cost and upstream-pulse, have a "
     "network half, and it lives in a separate fetch script outside the core for the same reason the "
     "leaderboard poster does: the core stays verifiably offline, and everything that opens a "
     "connection sits in one short file you can read.",
     [
      ("extension-reach",
       "What can your browser extensions see, and is anyone still shipping updates?",
       "An extension shows its permissions once, in a dialog nobody re-reads, and then never again. "
       "The browser keeps the answer on disk for ever. This reads it and answers what the browser "
       "stops asking after install day: what can see your bank tab, and which of them was last "
       "updated years ago.",
       "demo=true", ""),
      ("where-it-went",
       "Where did the quarter actually go?",
       "A browser shows the last nine things you opened. It will not tell you that one domain took "
       "a fifth of your quarter, that you opened the same question thirty-one times, or that your "
       "longest unbroken run at one site was four hours on a Tuesday afternoon.",
       "demo=true", "days=90"),
      ("photo-debt",
       "What is your photo library actually made of?",
       "A photo library only grows. The shutter fires ten times to get one usable frame, every "
       "screenshot lands next to the family album, and the same image arrives again from a message, "
       "an AirDrop and a download. The Photos app is organised by date and by face, so none of that "
       "is visible in it.",
       "demo=true", ""),
      ("what-grew",
       "Something ate 40 GB. What moved?",
       "Every disk tool answers the wrong question: they show what is big, and what is big is mostly "
       "what was always big. The useful question is what changed, and nothing can answer that "
       "without having looked before. So the first run writes a baseline and says so, rather than "
       "reporting your whole home directory as new.",
       "demo=true", "root=~"),
      ("reply-debt",
       "Who asked you something and is still waiting?",
       "An unread badge counts messages. It does not know the difference between a newsletter and "
       "somebody who asked you a direct question eleven days ago. That difference is what this "
       "counts: threads where the last word is not yours, somebody asked for something, and nothing "
       "went back.",
       "demo=true", ""),
      ("standing-cost",
       "What does that recurring meeting cost, per year?",
       "Nobody schedules a meeting by its price. A 30-minute standup with nine people is four and a "
       "half person-hours every time it fires, and over a year that is a number no calendar will "
       "ever show you. Every fact needed to compute it is already in the calendar.",
       "demo=true", ""),
     ]),
]

PLAY_URI = "https://play.modiqo.ai/" + HANDLE + "/{0}"


def cmd_block(cid, text, label):
    # The button lives outside the scrolling span. Inside it, a long command scrolls the Copy
    # button off the right edge, which is the one control the block exists for.
    return ('<div class="cmd pinned" data-label="{2}">\n'
            '  <span class="cmd-scroll"><span class="dollar">$</span>'
            '<code id="{0}">{1}</code></span>\n'
            '  <button class="copy" data-copy="#{0}">Copy</button>\n'
            '</div>').format(cid, esc(text), esc(label))


def plays_page():
    """One page for all thirty-one published Plays, with a paste-ready line under each.

    The registry lists them one at a time behind a search box. A person who liked one of these has
    no way to find the other thirty, and a link to thirty-one registry pages is not a link.
    This is.
    """
    toc = ['  <strong>Thirty-one Plays</strong>', '  <a href="#run">How to run one</a>']
    body = ['<h1>Every Play</h1>',
            '<p class="lede">Thirty-one published rote Plays on three stdlib-only Python cores. '
            'No pip install, no node, no keys, and no network in any core. Each one is a public '
            'archive you can read before you run it.</p>',
            '<h2 id="run">How to run one</h2>',
            '<p>Every line on this page is complete. Paste it, and rote fetches the published '
            'archive, shows you a consent screen listing every file the Play touches, and runs it. '
            'It needs rote, the free runner from <a href="https://www.modiqo.ai">Modiqo</a>, and a '
            'free account. If you have neither, the registry installs both and the Play in one go. '
            'Swap the name at the end for any Play on this page:</p>',
            cmd_block("cmd-install",
                      'curl -fsSL "https://play.modiqo.ai/install?play=rajkaria/comped" | sh',
                      "no rote yet"),
            '<p><b>No account, no install, nothing kept.</b> <code>comped</code> also has a door that '
            'needs neither. It downloads about 40 KB of stdlib Python to a temporary directory, runs '
            'it, and deletes itself:</p>',
            cmd_block("cmd-noaccount", "curl -fsSL https://gotcomped.com/comped.sh | sh", "no account"),
            '<p>Prefer node? <code>npx comped</code> runs the same code. The full walkthrough is in '
            '<a href="docs.html">the docs</a>.</p>']
    for anchor, heading, core, intro, plays in PLAYS_INDEX:
        toc.append('  <strong>{0}</strong>'.format(esc(heading)))
        body.append('<h2 id="{0}">{1}</h2>'.format(anchor, esc(heading)))
        body.append('<p>{0} Built on <code>{1}</code>.</p>'.format(esc(intro), core))
        for slug, question, blurb, try_args, real_args in plays:
            toc.append('  <a href="#{0}">{0}</a>'.format(slug))
            body.append('<h3 id="{0}">{0}</h3>'.format(slug))
            body.append('<p><strong>{0}</strong></p>'.format(esc(question)))
            body.append('<p>{0}</p>'.format(esc(blurb)))
            uri = PLAY_URI.format(slug)
            first = "rote play run {0}{1}".format(uri, (" " + try_args) if try_args else "")
            label = "try it cold" if try_args.startswith("demo=") else "run it"
            body.append(cmd_block("cmd-{0}".format(slug), first, label))
            if real_args:
                body.append(cmd_block("cmd-{0}-real".format(slug),
                                      "rote play run {0} {1}".format(uri, real_args), "on your own"))
            body.append('<p class="src"><a href="{0}">Read the archive</a> before you run it, or '
                        '<a href="https://github.com/rajkaria/comped/blob/main/docs/plays/{1}/DESCRIPTION.md">'
                        'the full description</a>.</p>'.format(uri, slug))
    return page("plays.html", "Every Play: thirty-one rote Plays that read what your machine already wrote",
                "Thirty-one published rote Plays on three stdlib-only Python cores. What your agents "
                "cost, what your machine and your git history have been hoarding, and twelve you "
                "run many times a day. Paste-ready run line under each.",
                "plays", "\n".join(toc), "\n".join(body),
                scripts='<script src="app.js" defer></script>')


def main():
    for name, html_text in (("docs.html", docs_page()), ("developers.html", developers_page()),
                            ("plays.html", plays_page())):
        out = ROOT / "site" / name
        out.write_text(html_text, encoding="utf-8")
        print("wrote {0} ({1} bytes)".format(out, len(html_text)))
    sm = ROOT / "site" / "sitemap.xml"
    pages = ["", "docs.html", "plays.html", "developers.html", "leaderboard.html", "card.html"]
    sm.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join("  <url><loc>{0}/{1}</loc></url>\n".format(SITE_URL, page) for page in pages)
        + "</urlset>\n", encoding="utf-8")
    print("wrote {0}".format(sm))
    # The no-account download is part of the site, so it is built with the site. Deploying a page
    # that offers comped.tar.gz without building comped.tar.gz would be a 404 on the front door.
    from tools import build_dist, build_npm
    build_dist.main()
    build_npm.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
