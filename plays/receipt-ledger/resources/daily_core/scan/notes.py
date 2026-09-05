"""vault-pulse: whether a notes folder is a library or a landfill.

A vault grows monotonically and nothing in the editor ever says which notes are load-bearing and
which were written once and never opened again. Both facts are in the files: links give the graph,
timestamps give the habit. This reads the markdown, builds the link graph, and reports the notes
nothing points at, the links that point at nothing, and whether the daily-note streak is alive.
"""
import re
from collections import Counter

from ..common import (Budget, Source, ago, expand, from_unix, human_bytes, iso, parse_date, pct,
                      read_text, shorten_path, walk)

KINDS = ("vault",)
SKIP = (".obsidian", ".git", ".trash", "node_modules", ".DS_Store", ".smart-env", ".makemd")
NOTE_EXT = (".md", ".markdown", ".mdx", ".txt")

WIKILINK = re.compile(r"\[\[([^\]\|#^]+)")
MDLINK = re.compile(r"\[[^\]]*\]\(<?([^)>\s#]+)")
TAG = re.compile(r"(?:^|\s)#([A-Za-z][\w/\-]{1,40})")
TODO = re.compile(r"^\s*[-*]\s+\[ \]\s+\S", re.M)
DONE = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+\S", re.M)
DAILY = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def find_vault(hint: str = "") -> tuple:
    """The folder to read. An explicit hint wins; otherwise look for an Obsidian vault, then Notes."""
    if hint:
        p = expand(hint)
        return (p, "given") if p.is_dir() else (p, "missing")
    home = expand("~")
    for depth1 in ("", "Documents", "Library/Mobile Documents/iCloud~md~obsidian/Documents", "Notes", "Desktop"):
        base = home / depth1 if depth1 else home
        if not base.is_dir():
            continue
        try:
            for child in sorted(base.iterdir()):
                if child.is_dir() and (child / ".obsidian").is_dir():
                    return child, "found an Obsidian vault"
        except (OSError, PermissionError):
            continue
    for guess in ("~/Documents/Notes", "~/Notes", "~/Documents"):
        p = expand(guess)
        if p.is_dir():
            return p, "no Obsidian vault found; read {0}".format(guess)
    return home, "no notes folder found"


def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    root, how = (expand(cfg["demo_root"]) / "vault", "bundled fixture") if cfg.get("demo_root") \
        else find_vault(cfg.get("vault", ""))
    src = Source(name="notes", path=str(root))
    if not root.is_dir():
        return [src.miss("no folder at {0}".format(root))], []
    notes, attachments = [], []
    for path, st, _ in walk(root, budget, skip_names=SKIP):
        rel = str(path.relative_to(root))
        if path.suffix.lower() not in NOTE_EXT:
            attachments.append({"path": rel, "bytes": st.st_size, "ext": path.suffix.lower()})
            continue
        text = read_text(path, 2 * 1024 * 1024)
        budget.spend(len(text))
        notes.append(_note(rel, path, st, text))
    if not notes:
        return [src.miss("no markdown files under {0}".format(root))], []
    doc = {"root": str(root), "how": how, "notes": notes, "attachments": attachments}
    return [src.hit(len(notes), "{0}; {1} attachment(s)".format(how, len(attachments)))], [doc]


def _note(rel: str, path, st, text: str) -> dict:
    body = FRONTMATTER.sub("", text)
    words = len(body.split())
    created = getattr(st, "st_birthtime", st.st_ctime)
    fm = FRONTMATTER.search(text)
    fm_tags = re.findall(r"[-\s]([A-Za-z][\w/\-]{1,40})", fm.group(1).split("tags:", 1)[1].split("\n\n")[0]) \
        if fm and "tags:" in fm.group(1) else []
    return {
        "path": rel, "stem": path.stem, "bytes": st.st_size, "words": words,
        "created": iso(from_unix(created)), "modified": iso(from_unix(st.st_mtime)),
        "revised": abs(st.st_mtime - created) > 120,
        "wikilinks": sorted({m.strip() for m in WIKILINK.findall(body)}),
        "mdlinks": sorted({m for m in MDLINK.findall(body) if not m.startswith(("http://", "https://", "mailto:"))}),
        "external": len([m for m in MDLINK.findall(body) if m.startswith(("http://", "https://"))]),
        "tags": sorted({t for t in TAG.findall(body)} | set(fm_tags)),
        "todo": len(TODO.findall(body)), "done": len(DONE.findall(body)),
        "daily": bool(DAILY.fullmatch(path.stem)),
    }


# ---------------------------------------------------------------- analysis

def analyse(doc: dict, now, stale_days: int) -> dict:
    notes = doc["notes"]
    by_stem, by_path = {}, {}
    for n in notes:
        by_stem.setdefault(n["stem"].lower(), []).append(n)
        by_path[n["path"].lower()] = n
        by_path[n["path"].lower().rsplit(".", 1)[0]] = n

    inbound = Counter()
    broken = []
    for n in notes:
        for target in n["wikilinks"] + n["mdlinks"]:
            key = target.lower().lstrip("./")
            hit = by_stem.get(key.rsplit("/", 1)[-1].rsplit(".", 1)[0]) or (
                [by_path[key]] if key in by_path else None) or (
                [by_path[key.rsplit(".", 1)[0]]] if key.rsplit(".", 1)[0] in by_path else None)
            if hit:
                inbound[hit[0]["path"]] += 1
            elif not target.startswith("#"):
                broken.append({"from": n["path"], "to": target})

    orphans = [n for n in notes if not inbound[n["path"]] and not n["wikilinks"] and not n["mdlinks"]]
    unlinked = [n for n in notes if not inbound[n["path"]] and (n["wikilinks"] or n["mdlinks"])]
    stubs = [n for n in notes if n["words"] < 30]
    write_only = [n for n in notes if not n["revised"]]
    stale = [n for n in notes if n["modified"] and (now - parse_date(n["modified"])).days >= stale_days]
    dailies = sorted(n["stem"] for n in notes if n["daily"])
    tags = Counter(t for n in notes for t in n["tags"])

    weeks = Counter()
    for n in notes:
        when = parse_date(n["created"]) if n["created"] else None
        if when:
            weeks[when.strftime("%G-W%V")] += 1
    recent_weeks = [weeks.get(k, 0) for k in _last_weeks(now, 16)]

    created = sorted(parse_date(n["created"]) for n in notes if n["created"])
    clone_like = bool(created) and len(created) > 3 and (created[-1] - created[0]).total_seconds() < 300

    return {
        "root": doc["root"], "how": doc["how"], "clone_like": clone_like,
        "notes": len(notes), "words": sum(n["words"] for n in notes),
        "bytes": sum(n["bytes"] for n in notes),
        "attachments": len(doc["attachments"]),
        "attachment_bytes": sum(a["bytes"] for a in doc["attachments"]),
        "links": sum(len(n["wikilinks"]) + len(n["mdlinks"]) for n in notes),
        "external_links": sum(n["external"] for n in notes),
        "orphans": len(orphans), "orphan_share": pct(len(orphans), len(notes)),
        "orphan_list": [{"path": n["path"], "words": n["words"], "age": ago(parse_date(n["modified"]), now)}
                        for n in sorted(orphans, key=lambda n: -n["words"])[:6]],
        "unlinked": len(unlinked),
        "broken": len(broken), "broken_list": broken[:6],
        "stubs": len(stubs), "stub_share": pct(len(stubs), len(notes)),
        "write_only": len(write_only), "write_only_share": pct(len(write_only), len(notes)),
        "stale": len(stale), "stale_days": stale_days,
        "hubs": [{"path": p, "inbound": c} for p, c in inbound.most_common(5)],
        "tags": [{"tag": t, "notes": c} for t, c in tags.most_common(6)], "tag_total": len(tags),
        "todo": sum(n["todo"] for n in notes), "done": sum(n["done"] for n in notes),
        "todo_notes": len([n for n in notes if n["todo"]]),
        "daily": _streak(dailies, now),
        "weeks": recent_weeks,
        "newest": max((n["created"] for n in notes if n["created"]), default="")[:10],
        "oldest": min((n["created"] for n in notes if n["created"]), default="")[:10],
        "biggest": [{"path": n["path"], "words": n["words"]}
                    for n in sorted(notes, key=lambda n: -n["words"])[:5]],
    }


def _last_weeks(now, count: int) -> list:
    from datetime import timedelta
    return [(now - timedelta(days=7 * i)).strftime("%G-W%V") for i in range(count - 1, -1, -1)]


def _streak(stems: list, now) -> dict:
    """Consecutive daily notes ending today or yesterday, plus the longest run ever recorded."""
    from datetime import date, timedelta
    days = sorted({date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                   for m in (DAILY.fullmatch(s) for s in stems) if m})
    if not days:
        return {"notes": 0, "current": 0, "longest": 0, "last": "", "alive": False}
    longest = run = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    today = now.date()
    current, cursor = 0, days[-1]
    if (today - cursor).days <= 1:
        index = len(days) - 1
        current = 1
        while index > 0 and (days[index] - days[index - 1]).days == 1:
            current += 1
            index -= 1
    return {"notes": len(days), "current": current, "longest": longest,
            "last": days[-1].isoformat(), "alive": (today - days[-1]).days <= 1}


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card, sparkline

    c = Card("VAULT PULSE", "{0} notes".format(v["notes"]), cfg.get("color"))
    c.blank()
    c.headline("{0:,} words across {1} notes".format(v["words"], v["notes"]), "1;36")
    c.cols(shorten_path(v["root"], 36), v["how"], 22)
    spark = sparkline(v["weeks"])
    if spark:
        c.row("new notes, last 16 weeks  {0}".format(spark))
    c.blank()

    c.rule("THE GRAPH")
    c.cols("links between notes", "{0} ({1} external)".format(v["links"], v["external_links"]), 20)
    c.cols("orphans, no link either way", "{0}  ({1}%)".format(v["orphans"], v["orphan_share"]), 14)
    c.cols("nothing links to them", str(v["unlinked"]), 8)
    c.cols("links pointing at nothing", str(v["broken"]), 8)
    for h in v["hubs"][:3]:
        c.cols("  most linked: {0}".format(shorten_path(h["path"], 34)), "{0} in".format(h["inbound"]), 8)

    c.rule("WRITTEN ONCE")
    c.cols("never edited after creation", "{0}  ({1}%)".format(v["write_only"], v["write_only_share"]), 14)
    c.cols("under 30 words", "{0}  ({1}%)".format(v["stubs"], v["stub_share"]), 14)
    c.cols("untouched {0}+ days".format(v["stale_days"]), str(v["stale"]), 8)
    if v["clone_like"]:
        c.wrap("Every note carries the same creation time, which is what a fresh clone or a "
               "restored backup looks like. Treat the never-edited count as unmeasured here.")
    for o in v["orphan_list"][:3]:
        c.cols("  {0}".format(shorten_path(o["path"], 32)), "{0}w · {1}".format(o["words"], o["age"]), 16)

    d = v["daily"]
    c.rule("HABIT")
    if d["notes"]:
        c.cols("daily notes", "{0}, last on {1}".format(d["notes"], d["last"]), 24)
        c.cols("streak", "{0} day{1} {2} · longest {3}".format(
            d["current"], "" if d["current"] == 1 else "s", "and alive" if d["alive"] else "(broken)",
            d["longest"]), 34)
    else:
        c.row("no notes are named as a date, so there is no streak to measure")
    if v["todo"]:
        c.cols("open checkboxes", "{0} across {1} notes, {2} done".format(
            v["todo"], v["todo_notes"], v["done"]), 30)
    if v["tag_total"]:
        c.cols("tags", "{0} distinct · {1}".format(
            v["tag_total"], ", ".join("#{0}".format(t["tag"]) for t in v["tags"][:3])), 36)
    if v["attachments"]:
        c.cols("attachments", "{0} files, {1}".format(v["attachments"], human_bytes(v["attachment_bytes"])), 22)

    c.blank()
    c.wrap("Read-only: every note was opened for reading and nothing was written into the vault. "
           "The report lands in your output folder instead.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    d = v["daily"]
    L = ["# Vault pulse", "", "`{0}` — {1}".format(v["root"], v["how"]), "",
         "| measure | value |", "|---|---|",
         "| notes | {0} |".format(v["notes"]),
         "| words | {0:,} |".format(v["words"]),
         "| links between notes | {0} |".format(v["links"]),
         "| orphans | {0} ({1}%) |".format(v["orphans"], v["orphan_share"]),
         "| links pointing at nothing | {0} |".format(v["broken"]),
         "| never edited after creation | {0} ({1}%){2} |".format(
             v["write_only"], v["write_only_share"],
             " — unmeasurable: every note shares one creation time" if v["clone_like"] else ""),
         "| under 30 words | {0} |".format(v["stubs"]),
         "| untouched {0}+ days | {1} |".format(v["stale_days"], v["stale"]),
         "| open checkboxes | {0} |".format(v["todo"]),
         "| daily-note streak | {0} (longest {1}) |".format(d["current"], d["longest"]),
         "| attachments | {0} ({1}) |".format(v["attachments"], human_bytes(v["attachment_bytes"])), ""]
    if v["orphan_list"]:
        L += ["## Orphans", "", "| note | words | last touched |", "|---|---|---|"]
        L += ["| {0} | {1} | {2} |".format(o["path"], o["words"], o["age"]) for o in v["orphan_list"]]
        L.append("")
    if v["broken_list"]:
        L += ["## Links pointing at nothing", "", "| in note | target |", "|---|---|"]
        L += ["| {0} | {1} |".format(b["from"], b["to"]) for b in v["broken_list"]]
        L.append("")
    if v["hubs"]:
        L += ["## Most linked-to", "", "| note | inbound links |", "|---|---|"]
        L += ["| {0} | {1} |".format(h["path"], h["inbound"]) for h in v["hubs"]]
        L.append("")
    L += ["## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "") for s in sources]
    L += ["", "Read-only. No note was modified and nothing was written inside the vault.", ""]
    return "\n".join(L)
