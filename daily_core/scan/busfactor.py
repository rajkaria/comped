"""bus-factor: if one person left tomorrow, which code would nobody left behind understand?

Every team knows the answer is "some of it" and nobody knows which. The facts that settle it are
already in the repository — who wrote which line, when they last touched it, and whether anybody
else has ever been in the file — so this reads them and does the arithmetic nobody does by hand.

Four decisions shape everything below, and each one is printed on the card rather than hidden:

1. A file's authors come from its whole history, not from `blame` on the current text. A person who
   wrote a file and was then edited over still knows it; blame would have already forgotten them.
2. Ownership is measured in lines added, because that is the only size git gives without opening a
   working-tree file. Churn inflates it, so every line count here is "lines written", never "lines".
3. The truck factor is computed greedily, largest owner first. Greedy is an upper bound on the true
   minimum, so the number reported is honest about which direction it can be wrong in.
4. Bots, vendored trees, generated code and lock files are excluded by name, and both counts are
   reported, because an exclusion you cannot see is an exclusion you cannot check.

Nothing here starts a process: `gitread` owns the one git call in this package and every fact used
below arrives through it. A missing git, a missing directory and a repository with no commits are
all labelled misses, never exceptions, and a shallow clone is reported as a lower bound because
that is exactly what a truncated history gives you.
"""
import hashlib
import json
import re
from collections import Counter

from .. import gitread
from ..card import Card, legend, tier_bar
from ..common import (Budget, Source, age_days, ago, baseline_read, baseline_write, day, delta,
                      expand, from_unix, iso, pct, redact_name, since_note)

NAME = "bus-factor"
FIXTURE = "repos.json"

# Paths whose sole authorship says nothing about anybody's knowledge: code that was vendored in,
# code that was generated, and files a tool rewrites wholesale. Excluded by default; the count of
# what they removed is carried in the view so the exclusion can be argued with.
EXCLUDED_PATTERNS = (
    r"(^|/)vendor(ed)?/",
    r"(^|/)third[_-]?party/",
    r"(^|/)node_modules/",
    r"(^|/)bower_components/",
    r"(^|/)site-packages/",
    r"(^|/)\.venv/",
    r"(^|/)Pods/",
    r"(^|/)Carthage/",
    r"(^|/)dist/",
    r"(^|/)build/",
    r"(^|/)target/",
    r"(^|/)__pycache__/",
    r"(^|/)generated/",
    r"(^|/)__generated__/",
    r"\.min\.(js|css)$",
    r"\.map$",
    r"_pb2(_grpc)?\.pyi?$",
    r"\.pb\.(go|cc|h|ts|js)$",
    r"\.generated\.[A-Za-z0-9]+$",
    r"(^|/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock)$",
    r"(^|/)(Pipfile\.lock|Cargo\.lock|composer\.lock|Gemfile\.lock|go\.sum|flake\.lock|uv\.lock)$",
    r"(^|/)(mix\.lock|Podfile\.lock|packages\.lock\.json|gradle\.lockfile)$",
)
_EXCLUDED = re.compile("|".join(EXCLUDED_PATTERNS))

# Stems too generic for "another file names this one" to mean anything. `index.ts` appears in every
# directory in the tree; counting that as a reference would make every index file critical.
GENERIC_STEMS = frozenset((
    "index", "main", "init", "__init__", "test", "tests", "spec", "app", "mod", "lib", "core",
    "util", "utils", "types", "type", "const", "consts", "config", "conf", "setup", "readme",
    "helper", "helpers", "common", "base", "data", "model", "models", "view", "views", "api",
))

# The two rules a reader has to know before any number below means anything, printed on the card.
RULES = (
    "lines = lines added over the file's history (git numstat), not lines on disk today",
    "referenced ≈ other tracked files whose path carries this file's name as a token; "
    "stems under 4 characters and generic names (index, main, utils, …) never count",
)

MAX_REPOS = 40
LOG_FORMAT = "--format=%H|%aN|%aE|%at"          # capitalised, so git applies the repo's own mailmap


# ---------------------------------------------------------------- reading

def read_source(source, budget: Budget, cfg: dict) -> tuple:
    """Every tracked file under `cfg["root"]`, with the whole authorship history of each.

    `source` selects the slice: "git" (the default) walks `cfg["root"]` for repositories, and any
    other value is taken to be the path of one repository, so a Play can fan its reads out per
    repository and pay for a repository that will not answer only once.
    """
    if cfg.get("demo_root"):
        return _demo(source, cfg)

    git = gitread.Git.find()
    if not git.ok:
        return [Source(name="git").miss(git.note)], []

    label = str(source or "git").strip()
    if label in ("", "git", "repos", "all"):
        root = expand(cfg.get("root") or "~")
        if not root.is_dir():
            return [Source(name="git", path=str(root)).miss("no folder at {0}".format(root))], []
        repos = gitread.discover(root, budget, max_repos=int(cfg.get("max_repos", MAX_REPOS)))
        if not repos:
            return [Source(name="git", path=str(root)).miss(
                "no git repository under {0}".format(root))], []
    else:
        repos = [expand(label)]

    sources, records = [], []
    for path in repos:
        src, rows = _read_repo(git, path, budget, cfg)
        sources.append(src)
        records += rows
        if budget.exhausted:
            break
    return sources, records


def _read_repo(git, path, budget: Budget, cfg: dict) -> tuple:
    repo = gitread.describe(git, path)
    src = Source(name=repo.name or str(path), path=str(path))
    if not repo.usable:
        return src.miss(repo.note or "not a readable repository"), []

    timeout = float(cfg.get("timeout", 30.0))
    tracked = sorted({p for p in git.run(path, ["ls-files", "-z"], timeout=timeout).split("\0") if p})
    if not tracked:
        return src.miss("no tracked files at HEAD"), []

    text = git.run(path, ["log", "--numstat", LOG_FORMAT, "--no-renames"], timeout=timeout)
    if not text:
        return src.miss("git log answered nothing (empty, unreadable or slower than {0:.0f}s)".format(
            timeout)), []

    history = _parse_log(text, set(tracked))
    records = []
    for rel in tracked:
        if not budget.spend():
            break
        authors, commits, last = _fold(history.get(rel, {}))
        records.append({"repo": repo.name, "repo_path": str(path), "shallow": repo.shallow,
                        "path": rel, "authors": authors, "commits": commits, "last": last})

    note = "{0}, {1}".format(_many(len(records), "tracked file"),
                             _many(len({(a["name"], a["email"]) for r in records for a in r["authors"]}),
                                   "author"))
    if repo.shallow:
        note += "; " + (repo.note or "shallow clone: every count is a lower bound")
    if budget.exhausted:
        note += "; stopped at the {0} bound".format(budget.hit)
    return src.hit(len(records), note), records


def _fold(per_author: dict) -> tuple:
    """One path's raw (name, email) tallies, sorted into the record shape the view is built from."""
    authors, commits, last = [], 0, 0
    for (name, email) in sorted(per_author):
        row = per_author[(name, email)]
        commits += row["commits"]
        last = max(last, row["last"])
        authors.append({"name": name, "email": email, "lines": row["lines"],
                        "deleted": row["deleted"], "commits": row["commits"],
                        "first": row["first"], "last": row["last"]})
    authors.sort(key=lambda a: (-a["lines"], -a["commits"], a["name"], a["email"]))
    return authors, commits, last


def _parse_log(text: str, tracked: set) -> dict:
    """Fold one `git log --numstat` stream into {path: {(name, email): tallies}}.

    Two line shapes and nothing else: a numstat row always contains tabs, a commit header never
    does. Anything that is neither (blank separators, a stray line from a strange format) is
    skipped rather than guessed at.
    """
    out, name, email, when = {}, "", "", 0
    for line in text.splitlines():
        if not line:
            continue
        if "\t" in line:
            added, _, rest = line.partition("\t")
            deleted, _, raw = rest.partition("\t")
            path = _unquote(raw.strip())
            if path not in tracked:
                continue
            slot = out.setdefault(path, {}).setdefault(
                (name, email), {"lines": 0, "deleted": 0, "commits": 0, "first": when, "last": when})
            slot["lines"] += _count(added)
            slot["deleted"] += _count(deleted)
            slot["commits"] += 1
            slot["first"] = min(slot["first"] or when, when) if when else slot["first"]
            slot["last"] = max(slot["last"], when)
        elif "|" in line:
            head, _, stamp = line.rpartition("|")
            head, _, email = head.rpartition("|")
            _, _, name = head.partition("|")
            name, email = name.strip(), email.strip()
            when = _count(stamp)
    return out


def _count(text: str) -> int:
    """A numstat cell. `-` means binary, which is a real commit against a file of no known size."""
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return 0


_OCTAL = re.compile(r"\\[0-7]{3}")
_ESCAPES = {"n": b"\n", "t": b"\t", "r": b"\r", "\\": b"\\", '"': b'"', "a": b"\a", "b": b"\b",
            "f": b"\f", "v": b"\v"}


def _unquote(path: str) -> str:
    """Undo git's C-style quoting of a path with a non-ASCII or awkward byte in it.

    `core.quotepath` cannot be turned off here — the git runner takes a subcommand, not options
    before one — so a path like "src/caf\\303\\251.py" is decoded rather than mis-counted as a
    second, differently-spelled file.
    """
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    body, out, i = path[1:-1], bytearray(), 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            if _OCTAL.match(body, i):
                out.append(int(body[i + 1:i + 4], 8))
                i += 4
                continue
            out += _ESCAPES.get(body[i + 1], body[i + 1].encode("utf-8"))
            i += 2
            continue
        out += ch.encode("utf-8")
        i += 1
    return out.decode("utf-8", "replace")


def _demo(source, cfg: dict) -> tuple:
    """The bundled fixture: a captured record list, so a cold first run has something to show.

    Real repositories cannot be shipped — a git checkout inside a git checkout is not a thing a
    package should carry — so the demo replays the parsed records rather than re-running git.
    """
    path = expand(cfg["demo_root"]) / FIXTURE
    src = Source(name="{0} (demo)".format(source or "git"), path=str(path))
    if not path.is_file():
        return [src.miss("fixture missing at {0}".format(path))], []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [src.miss("fixture is not readable JSON")], []
    records = doc.get("records") if isinstance(doc, dict) else doc
    if not isinstance(records, list):
        return [src.miss("fixture has no record list")], []
    records = [r for r in records if isinstance(r, dict) and r.get("path")]
    repos = sorted({str(r.get("repo", "")) for r in records})
    return [src.hit(len(records), "bundled fixture: {0}".format(
        _many(len(repos), "repository", "repositories")))], records


# ---------------------------------------------------------------- identity

def _identities(records: list) -> tuple:
    """Every (name, email) that appears, merged into humans, plus the lookups to resolve back."""
    pairs = sorted({(str(a.get("name", "")), str(a.get("email", "")))
                    for r in records for a in (r.get("authors") or [])})
    merged = gitread.coalesce(pairs)
    by_email, by_name = {}, {}
    for anchor in sorted(merged):
        ident = merged[anchor]
        for e in sorted(ident.emails):
            by_email.setdefault(e, anchor)
        for n in sorted(ident.names):
            by_name.setdefault(n.strip().lower(), anchor)
    return merged, by_email, by_name


def _resolve(name: str, email: str, merged: dict, by_email: dict, by_name: dict) -> str:
    key = gitread.identity_key(name, email)
    if key in merged:
        return key
    lowered = (email or "").strip().lower()
    if lowered in by_email:
        return by_email[lowered]
    plain = (name or "").strip().lower()
    if plain in by_name:
        return by_name[plain]
    return key


def _hash6(key: str) -> str:
    return hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:6]


def _display(merged: dict, key: str) -> str:
    """A name to print. An address is cut at the @ whether or not redaction is on: a report that
    leaves the machine must never carry a working email address out with it."""
    ident = merged.get(key)
    text = ident.display if ident else str(key)
    return text.split("@", 1)[0] if "@" in text else text


def _label(merged: dict, key: str, redact: bool) -> str:
    """Initials plus a short stable hash when redacting, so two rows about one person still join."""
    text = _display(merged, key)
    if not redact:
        return text
    return "{0}·{1}".format(redact_name(text, True) or "(name)", _hash6(key))


# ---------------------------------------------------------------- analysis

def analyse(records: list, now, cfg: dict) -> dict:
    cfg = cfg or {}
    redact = bool(cfg.get("redact", True))
    departed_days = int(cfg.get("departed_days", 365))
    stale_days = int(cfg.get("stale_days", 365))
    threshold = float(cfg.get("threshold", 0.5))

    rows = [r for r in (records or []) if isinstance(r, dict) and r.get("path")]
    rows.sort(key=lambda r: (str(r.get("repo", "")), str(r.get("path", ""))))
    kept, excluded = [], []
    for r in rows:
        (excluded if _EXCLUDED.search(str(r["path"])) else kept).append(r)

    merged, by_email, by_name = _identities(kept)
    bots = sorted(k for k in merged if merged[k].is_bot)
    bot_set = set(bots)

    files, bot_rows, unattributed = [], 0, 0
    for r in kept:
        owners = {}
        for a in (r.get("authors") or []):
            key = _resolve(str(a.get("name", "")), str(a.get("email", "")), merged, by_email, by_name)
            if key in bot_set:
                bot_rows += 1
                continue
            slot = owners.setdefault(key, {"lines": 0, "deleted": 0, "commits": 0, "last": 0, "first": 0})
            slot["lines"] += int(a.get("lines", 0) or 0)
            slot["deleted"] += int(a.get("deleted", 0) or 0)
            slot["commits"] += int(a.get("commits", 0) or 0)
            slot["last"] = max(slot["last"], int(a.get("last", 0) or 0))
            first = int(a.get("first", 0) or 0)
            slot["first"] = min(slot["first"] or first, first) if first else slot["first"]
        if not owners:
            unattributed += 1
        path = str(r["path"])
        files.append({"repo": str(r.get("repo", "")), "path": path, "dir": _dirname(path),
                      "owners": owners, "lines": sum(o["lines"] for o in owners.values()),
                      "commits": int(r.get("commits", 0) or 0),
                      "last": max([o["last"] for o in owners.values()] + [int(r.get("last", 0) or 0)]),
                      "shallow": bool(r.get("shallow"))})

    refs = _reference_index(files)
    for f in files:
        f["refs"] = refs.get((f["repo"], f["path"]), 0)
        f["age_days"] = age_days(from_unix(f["last"]), now) if f["last"] else None
        f["stale"] = bool(f["age_days"] is not None and f["age_days"] >= stale_days)

    attributed = [f for f in files if f["owners"]]
    sole = [f for f in attributed if len(f["owners"]) == 1]
    tracked_lines = sum(f["lines"] for f in attributed)
    tiers = [("one author", sum(1 for f in attributed if len(f["owners"]) == 1)),
             ("two", sum(1 for f in attributed if len(f["owners"]) == 2)),
             ("three or more", sum(1 for f in attributed if len(f["owners"]) >= 3))]

    authors = _authors(files, sole, merged, redact, now, departed_days, tracked_lines)
    risk = [a for a in authors if a["sole_files"]]
    risk.sort(key=lambda a: (-a["risk"], -a["sole_lines"], a["name"]))
    clusters = _clusters(sole, merged, redact, now)
    repos = _per_repo(files, sole, merged, redact, threshold, now, departed_days)
    shallow_repos = sorted({f["repo"] for f in files if f["shallow"]})

    truck = _truck(attributed, authors, lambda f: f["lines"], threshold, "lines")
    truck_files = _truck(attributed, authors, lambda f: 1, threshold, "files")

    view = {
        "repos": repos, "repo_count": len(repos),
        "tracked_files": len(files), "tracked_lines": tracked_lines,
        "attributed_files": len(attributed), "unattributed_files": unattributed,
        "excluded_paths": len(excluded), "excluded_patterns": list(EXCLUDED_PATTERNS),
        "excluded_examples": [e["path"] for e in excluded[:6]],
        "bots_excluded": len(bots), "bot_rows": bot_rows,
        "bot_names": [_label(merged, k, redact) for k in bots],
        "authors": authors, "author_count": len(authors),
        "tiers": [list(t) for t in tiers],
        "sole_files": len(sole), "sole_share": pct(len(sole), len(attributed)),
        "sole_lines": sum(f["lines"] for f in sole),
        "sole_lines_share": pct(sum(f["lines"] for f in sole), tracked_lines),
        "stale_days": stale_days,
        "stale_files": sum(1 for f in files if f["stale"]),
        "stale_sole_files": sum(1 for f in sole if f["stale"]),
        "clusters": clusters[:12], "cluster_count": len(clusters),
        "largest_cluster": clusters[0] if clusters else None,
        "directories": _directories(files, sole)[:12],
        "risk": risk[:12], "risk_total": sum(a["risk"] for a in risk),
        "departed_days": departed_days,
        "departed": [a for a in risk if a["departed"]],
        "truck_factor": truck, "truck_factor_files": truck_files,
        "threshold": threshold,
        "cross_repo": _cross_repo(sole, merged, redact),
        "shallow": bool(shallow_repos), "shallow_repos": shallow_repos,
        "redacted": redact, "rules": list(RULES),
        "worst_files": _worst_files(sole, merged, redact, now)[:8],
    }
    view["headline"] = _headline(view)
    view["cluster_line"] = _cluster_line(view)
    view["verdict"] = _verdict(view)
    view["baseline"] = _payload(view)
    previous = baseline_read(cfg["out_dir"], NAME) if cfg.get("out_dir") else {}
    view["delta"] = delta(view["baseline"], previous.get("payload", {}))
    view["since"] = since_note(previous, now)
    return view


def save_baseline(view: dict, cfg: dict, now) -> str:
    """Record this run so tomorrow's can say what moved. Kept out of `analyse` on purpose: a
    function that both reads and writes the baseline would report a different delta the second
    time it was called with the same input, and every number here has to survive being re-run."""
    return baseline_write(cfg["out_dir"], NAME, view["baseline"], now)


def _payload(view: dict) -> dict:
    payload = {"tracked_files": view["tracked_files"], "tracked_lines": view["tracked_lines"],
               "sole_files": view["sole_files"], "sole_lines": view["sole_lines"],
               "stale_sole_files": view["stale_sole_files"], "authors": view["author_count"],
               "truck_factor": view["truck_factor"]["n"]}
    for repo in view["repos"]:
        payload["sole:{0}".format(repo["repo"])] = repo["sole_files"]
    return payload


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] + "/" if "/" in path else "./"


def _where(repo: str, folder: str) -> str:
    """`repo/billing/` for a directory, `repo/` for the top level: never `repo/./`."""
    if not repo:
        return folder
    return repo + "/" if folder == "./" else "{0}/{1}".format(repo, folder)


def _many(n: int, one: str, many: str = "") -> str:
    """`plural`, with the thousands separator a five-figure count needs."""
    return "{0:,} {1}".format(n, one if n == 1 else (many or one + "s"))


_TOKENS = re.compile(r"[^A-Za-z0-9]+")


def _reference_index(files: list) -> dict:
    """How many other tracked files carry this file's name as a path token, per repository.

    A real "who imports this" needs every file's contents; this needs one pass over the path list
    and gets the same shape of answer for the cost of nothing. It is an approximation and the card
    says so — a helper that half the tree names in its own path is load-bearing whether or not the
    naming is an import statement.
    """
    per_repo = {}
    for f in files:
        counts = per_repo.setdefault(f["repo"], Counter())
        for token in set(t.lower() for t in _TOKENS.split(f["path"]) if t):
            counts[token] += 1
    out = {}
    for f in files:
        stem = _stem(f["path"])
        if len(stem) < 4 or stem in GENERIC_STEMS:
            out[(f["repo"], f["path"])] = 0
            continue
        out[(f["repo"], f["path"])] = max(0, per_repo[f["repo"]].get(stem, 0) - 1)
    return out


def _stem(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    return (base.split(".", 1)[0] if "." in base else base).lower()


def _authors(files: list, sole: list, merged: dict, redact: bool, now, departed_days: int,
             tracked_lines: int) -> list:
    """Every non-bot human, line-weighted and file-weighted, with their knowledge-at-risk score.

    risk = Σ over the files only they have ever touched of
           lines × age weight (1.0 fresh, rising to 2.0 at two years) × (1 + files that name it)

    The age weight rises rather than falls because the risk is forgetting, not absence: code one
    person wrote last week is still in their head, and code one person wrote three years ago is
    already gone from it.
    """
    stats = {}
    for f in files:
        for key, owned in sorted(f["owners"].items()):
            slot = stats.setdefault(key, {"files": 0, "lines": 0, "commits": 0, "last": 0,
                                          "first": 0, "sole_files": 0, "sole_lines": 0,
                                          "majority": 0, "risk": 0.0, "repos": set(),
                                          "sole_repos": set(), "refs": 0})
            slot["files"] += 1
            slot["lines"] += owned["lines"]
            slot["commits"] += owned["commits"]
            slot["last"] = max(slot["last"], owned["last"])
            slot["first"] = min(slot["first"] or owned["first"], owned["first"]) if owned["first"] \
                else slot["first"]
            slot["repos"].add(f["repo"])
            top = sorted(f["owners"].items(), key=lambda kv: (-kv[1]["lines"], kv[0]))[0][0]
            if top == key:
                slot["majority"] += 1
    for f in sole:
        key = sorted(f["owners"])[0]
        slot = stats[key]
        slot["sole_files"] += 1
        slot["sole_lines"] += f["lines"]
        slot["sole_repos"].add(f["repo"])
        slot["refs"] += f["refs"]
        slot["risk"] += f["lines"] * _age_weight(f["age_days"]) * (1 + f["refs"])

    out = []
    for key in sorted(stats):
        s = stats[key]
        last = from_unix(s["last"])
        gap = age_days(last, now)
        out.append({
            "id": _hash6(key), "name": _label(merged, key, redact),
            "files": s["files"], "lines": s["lines"], "commits": s["commits"],
            "majority_files": s["majority"], "sole_files": s["sole_files"],
            "sole_lines": s["sole_lines"], "referenced_by": s["refs"],
            "line_share": pct(s["lines"], tracked_lines),
            "risk": int(round(s["risk"])),
            "last": iso(last), "last_day": day(last), "last_ago": ago(last, now),
            "idle_days": gap, "departed": bool(gap is not None and gap >= departed_days),
            "repos": sorted(s["repos"]), "sole_repos": sorted(s["sole_repos"]),
        })
    out.sort(key=lambda a: (-a["lines"], -a["files"], a["name"]))
    return out


def _age_weight(age: "int") -> float:
    if age is None:
        return 1.0
    return 1.0 + min(1.0, float(age) / 730.0)


def _clusters(sole: list, merged: dict, redact: bool, now) -> list:
    """Sole-author files grouped by directory and owner: the unit a handover actually happens in.

    One orphaned file is a bad afternoon. Thirty-one of them in one directory under one name is the
    thing worth putting on a card, so the headline is a cluster and never an individual file.
    """
    groups = {}
    for f in sole:
        key = sorted(f["owners"])[0]
        slot = groups.setdefault((f["repo"], f["dir"], key),
                                 {"files": 0, "lines": 0, "last": 0, "refs": 0, "paths": []})
        slot["files"] += 1
        slot["lines"] += f["lines"]
        slot["refs"] += f["refs"]
        slot["last"] = max(slot["last"], f["last"])
        slot["paths"].append(f["path"])
    out = []
    for (repo, folder, key) in sorted(groups):
        slot = groups[(repo, folder, key)]
        last = from_unix(slot["last"])
        out.append({"repo": repo, "dir": folder, "owner": _label(merged, key, redact),
                    "owner_id": _hash6(key), "files": slot["files"], "lines": slot["lines"],
                    "referenced_by": slot["refs"], "last_ago": ago(last, now), "last_day": day(last),
                    "where": _where(repo, folder), "paths": sorted(slot["paths"])[:6]})
    out.sort(key=lambda c: (-c["files"], -c["lines"], c["repo"], c["dir"]))
    return out


def _directories(files: list, sole: list) -> list:
    """The same rollup without the owner, so a directory's share has its own denominator."""
    total, one = Counter(), Counter()
    for f in files:
        total[(f["repo"], f["dir"])] += 1
    for f in sole:
        one[(f["repo"], f["dir"])] += 1
    out = [{"repo": repo, "dir": folder, "files": total[(repo, folder)],
            "sole_files": one[(repo, folder)], "share": pct(one[(repo, folder)], total[(repo, folder)]),
            "where": "{0}/{1}".format(repo, folder) if repo else folder}
           for (repo, folder) in sorted(one)]
    out.sort(key=lambda d: (-d["sole_files"], -d["share"], d["repo"], d["dir"]))
    return out


def _worst_files(sole: list, merged: dict, redact: bool, now) -> list:
    ranked = sorted(sole, key=lambda f: (-(f["lines"] * (1 + f["refs"])), f["repo"], f["path"]))
    return [{"repo": f["repo"], "path": f["path"], "lines": f["lines"], "referenced_by": f["refs"],
             "owner": _label(merged, sorted(f["owners"])[0], redact),
             "last_ago": ago(from_unix(f["last"]), now)} for f in ranked]


def _truck(attributed: list, authors: list, weight, threshold: float, unit: str) -> dict:
    """The smallest set of departures that orphans more than `threshold` of the code.

    Greedy, largest owner first, which is an upper bound on the true minimum: the exact answer is
    a set-cover problem and a card is not the place to spend that. A file is orphaned when every
    one of its authors has gone, which is the only definition that survives being argued with.
    """
    total = sum(weight(f) for f in attributed)
    order = [a for a in authors if a["lines"] or a["files"]]
    removed, who, orphaned = set(), [], 0
    if total:
        for a in order:
            removed.add(a["id"])
            who.append(a)
            orphaned = sum(weight(f) for f in attributed
                           if set(_ids(f)) <= removed)
            if orphaned > threshold * total:
                break
    return {"n": len(who), "of": len(order), "unit": unit, "total": total,
            "orphaned": orphaned, "orphaned_share": pct(orphaned, total),
            "threshold": threshold, "threshold_pct": int(round(threshold * 100)),
            "who": [a["name"] for a in who],
            "method": "greedy, largest owner first: an upper bound on the true minimum"}


def _ids(f: dict) -> list:
    return [_hash6(k) for k in sorted(f["owners"])]


def _cross_repo(sole: list, merged: dict, redact: bool) -> list:
    """One person who is the only author of code in five repositories is one risk, not five."""
    spread = {}
    for f in sole:
        key = sorted(f["owners"])[0]
        slot = spread.setdefault(key, {"repos": set(), "files": 0, "lines": 0})
        slot["repos"].add(f["repo"])
        slot["files"] += 1
        slot["lines"] += f["lines"]
    out = [{"name": _label(merged, k, redact), "id": _hash6(k), "repos": sorted(spread[k]["repos"]),
            "repo_count": len(spread[k]["repos"]), "files": spread[k]["files"],
            "lines": spread[k]["lines"]}
           for k in sorted(spread) if len(spread[k]["repos"]) > 1]
    out.sort(key=lambda a: (-a["repo_count"], -a["files"], a["name"]))
    return out


def _per_repo(files: list, sole: list, merged: dict, redact: bool, threshold: float, now,
              departed_days: int) -> list:
    out = []
    for repo in sorted({f["repo"] for f in files}):
        mine = [f for f in files if f["repo"] == repo]
        attributed = [f for f in mine if f["owners"]]
        mine_sole = [f for f in sole if f["repo"] == repo]
        authors = _authors(mine, mine_sole, merged, redact, now, departed_days,
                           sum(f["lines"] for f in attributed))
        truck = _truck(attributed, authors, lambda f: f["lines"], threshold, "lines")
        out.append({"repo": repo, "files": len(mine), "attributed": len(attributed),
                    "lines": sum(f["lines"] for f in attributed), "authors": len(authors),
                    "sole_files": len(mine_sole), "sole_lines": sum(f["lines"] for f in mine_sole),
                    "sole_share": pct(len(mine_sole), len(attributed)),
                    "truck_factor": truck["n"], "shallow": any(f["shallow"] for f in mine),
                    "top": authors[0]["name"] if authors else ""})
    out.sort(key=lambda r: (-r["sole_files"], r["repo"]))
    return out


def _span(days: int) -> str:
    if days >= 365:
        years = days // 365
        return "a year" if years == 1 and days < 400 else "{0} years".format(years)
    if days >= 60:
        return "{0} months".format(days // 30)
    return "{0} days".format(days)


def _headline(view: dict) -> str:
    return "{0} {1}".format(_headline_files(view), _headline_stale(view))


def _headline_files(view: dict) -> str:
    return "{0}. {1} exactly one author, ever.".format(
        _many(view["tracked_files"], "file"),
        _many(view["sole_files"], "has", "have"))


def _headline_stale(view: dict) -> str:
    return "{0:,} untouched in {1}.".format(view["stale_files"], _span(view["stale_days"]))


def _cluster_line(view: dict) -> str:
    c = view["largest_cluster"]
    if not c:
        return "No directory has a sole-author cluster in it."
    return "Largest cluster: {0} — {1}, {2}, one name.".format(
        c["where"], _many(c["files"], "file"), _many(c["lines"], "line"))


def _verdict(view: dict) -> str:
    n = view["truck_factor"]["n"]
    if not view["attributed_files"]:
        return "nothing to weigh: no tracked file has an attributable author"
    if n <= 1:
        return "one departure orphans most of this code"
    if n == 2:
        return "two departures orphan most of this code"
    return "{0} departures orphan most of this code".format(n)


# ---------------------------------------------------------------- presentation

def render(view: dict, cfg: dict) -> str:
    cfg = cfg or {}
    c = Card("BUS FACTOR", "truck factor {0}".format(view["truck_factor"]["n"]), cfg.get("color"))
    c.blank()
    if not view["tracked_files"]:
        c.headline("No tracked file could be read.", "1;33")
        c.wrap("Nothing was written to any repository, and nothing was sent anywhere.")
        return c.close()

    c.headline(_headline_files(view), "1;36")
    c.wrap(_headline_stale(view))
    c.wrap(view["cluster_line"])
    c.blank()

    c.rule("AUTHORS PER FILE")
    tiers = [(name, count) for name, count in view["tiers"]]
    bar = tier_bar(tiers, width=44)
    if bar:
        c.row(bar)
        c.row(legend(tiers))
    c.row("{0:,} of {1:,} files ({2}%) carry one name, {3:,} lines ({4}%)".format(
        view["sole_files"], view["attributed_files"], view["sole_share"],
        view["sole_lines"], view["sole_lines_share"]))
    if view["stale_sole_files"]:
        c.row("{0:,} of those have not been touched in {1}".format(
            view["stale_sole_files"], _span(view["stale_days"])))

    if view["risk"]:
        c.rule("KNOWLEDGE AT RISK")
        c.table([("who", "files", "lines", "risk")], [24, -7, -10, -11])
        for a in view["risk"][:5]:
            c.table([(a["name"], "{0:,}".format(a["sole_files"]), "{0:,}".format(a["sole_lines"]),
                      "{0:,}".format(a["risk"]))], [24, -7, -10, -11])

    c.rule("IF THEY LEFT TOMORROW")
    t = view["truck_factor"]
    c.wrap("{0} of {1} would orphan {2}% of {3} — more than the {4}% this asks for.".format(
        _many(t["n"], "departure"), _many(t["of"], "author"), t["orphaned_share"],
        _many(t["total"], "line"), t["threshold_pct"]))
    if t["who"]:
        c.wrap("In order: {0}.".format(", ".join(t["who"])))
    c.row("file-weighted, the same test gives {0}".format(view["truck_factor_files"]["n"]))
    c.row("greedy, so this is an upper bound on the true minimum")

    if view["departed"]:
        c.rule("ALREADY GONE")
        for a in view["departed"][:4]:
            c.cols("{0} — sole author of {1}".format(a["name"], _many(a["sole_files"], "file")),
                   "last seen {0}".format(a["last_ago"]), 18)

    if view["clusters"]:
        c.rule("CLUSTERS")
        # With one repository the prefix is the same on every row and only costs the reader
        # the directory it was there to disambiguate.
        widths, one_repo = [24, 15, -7, -11], view["repo_count"] == 1
        c.table([("where", "who", "files", "lines")], widths)
        for cluster in view["clusters"][:4]:
            c.table([(cluster["dir"] if one_repo else cluster["where"], cluster["owner"],
                      "{0:,}".format(cluster["files"]), "{0:,}".format(cluster["lines"]))], widths)

    if view["cross_repo"]:
        c.rule("ACROSS REPOSITORIES")
        for a in view["cross_repo"][:3]:
            c.cols("{0} is sole author in {1}".format(
                a["name"], _many(a["repo_count"], "repository", "repositories")),
                _many(a["files"], "file"), 12)

    c.blank()
    c.headline(view["verdict"], "1;33" if view["truck_factor"]["n"] <= 2 else "1;32")
    c.wrap(_footnote(view))
    c.note(view["since"])
    return c.close()


def _footnote(view: dict) -> str:
    bits = ["{0} scanned".format(_many(view["repo_count"], "repository", "repositories"))]
    if view["excluded_paths"]:
        bits.append("{0} vendored or generated excluded".format(view["excluded_paths"]))
    if view["bots_excluded"]:
        bits.append("{0} excluded".format(_many(view["bots_excluded"], "bot")))
    if view["unattributed_files"]:
        bits.append("{0} with no readable history".format(view["unattributed_files"]))
    if view["shallow"]:
        bits.append("shallow history, so every count is a lower bound")
    bits.append("git log was read; nothing was written to any repository")
    return ". ".join(b[0].upper() + b[1:] for b in bits) + "."


def report_markdown(view: dict, cfg: dict, sources: list) -> str:
    cfg = cfg or {}
    t, tf = view["truck_factor"], view["truck_factor_files"]
    L = ["# Bus factor", "", view["headline"], "", view["cluster_line"], "",
         "| measure | value | of |", "|---|---|---|",
         "| tracked files | {0:,} | {1:,} scanned, {2:,} excluded |".format(
             view["tracked_files"], view["tracked_files"] + view["excluded_paths"],
             view["excluded_paths"]),
         "| files with an attributable author | {0:,} | {1:,} tracked |".format(
             view["attributed_files"], view["tracked_files"]),
         "| lines written | {0:,} | across {1:,} files |".format(
             view["tracked_lines"], view["attributed_files"]),
         "| files with exactly one author | {0:,} ({1}%) | {2:,} attributed |".format(
             view["sole_files"], view["sole_share"], view["attributed_files"]),
         "| lines in those files | {0:,} ({1}%) | {2:,} lines |".format(
             view["sole_lines"], view["sole_lines_share"], view["tracked_lines"]),
         "| untouched in {0} | {1:,} | {2:,} tracked |".format(
             _span(view["stale_days"]), view["stale_files"], view["tracked_files"]),
         "| sole-author files nobody has touched in {0} | {1:,} | {2:,} sole-author |".format(
             _span(view["stale_days"]), view["stale_sole_files"], view["sole_files"]),
         "| authors | {0:,} | {1:,} bot identities excluded |".format(
             view["author_count"], view["bots_excluded"]),
         "| truck factor (lines) | {0} | of {1} authors, at the {2}% line |".format(
             t["n"], t["of"], t["threshold_pct"]),
         "| truck factor (files) | {0} | of {1} authors, at the {2}% line |".format(
             tf["n"], tf["of"], tf["threshold_pct"]),
         "| repositories | {0} | {1} shallow |".format(
             view["repo_count"], len(view["shallow_repos"])), "",
         "## Authors per file", "", "| authors on the file | files | share |", "|---|---|---|"]
    L += ["| {0} | {1:,} | {2}% |".format(name, count, pct(count, view["attributed_files"]))
          for name, count in view["tiers"]]
    if view["unattributed_files"]:
        L += ["| no readable history | {0:,} | {1}% |".format(
            view["unattributed_files"], pct(view["unattributed_files"], view["tracked_files"]))]

    L += ["", "## Knowledge at risk", "",
          "Risk is the sum, over the files only that person has ever touched, of "
          "`lines × age weight × (1 + files that name it)`. The age weight runs from 1.0 for code "
          "touched today to 2.0 for code untouched for two years, because the risk being measured "
          "is forgetting rather than absence.", "",
          "| who | sole files | sole lines | referenced by | last commit | risk |",
          "|---|---|---|---|---|---|"]
    L += ["| {0} | {1:,} of {2:,} | {3:,} of {4:,} | {5:,} | {6} | {7:,} |".format(
        a["name"], a["sole_files"], view["sole_files"], a["sole_lines"], view["sole_lines"],
        a["referenced_by"], a["last_day"] or "unknown", a["risk"]) for a in view["risk"]]
    if not view["risk"]:
        L += ["| — | 0 of 0 | 0 of 0 | 0 | — | 0 |"]

    L += ["", "## Every author, line-weighted and file-weighted", "",
          "| who | lines | share | files touched | files they lead | last commit |",
          "|---|---|---|---|---|---|"]
    L += ["| {0} | {1:,} | {2}% | {3:,} of {4:,} | {5:,} | {6} |".format(
        a["name"], a["lines"], a["line_share"], a["files"], view["attributed_files"],
        a["majority_files"], a["last_day"] or "unknown") for a in view["authors"][:20]]

    L += ["", "## If they left tomorrow", "",
          "{0} of {1} authors, removed largest-owner-first, orphans {2:,} of {3:,} lines "
          "({4}%, past the {5}% line). {6}.".format(
              t["n"], t["of"], t["orphaned"], t["total"], t["orphaned_share"], t["threshold_pct"],
              t["method"]), "",
          "Counted by files rather than lines the answer is {0} of {1}, orphaning {2:,} of {3:,} "
          "files ({4}%).".format(tf["n"], tf["of"], tf["orphaned"], tf["total"],
                                 tf["orphaned_share"]), ""]
    if t["who"]:
        L += ["In order: {0}.".format(", ".join(t["who"])), ""]

    if view["departed"]:
        L += ["## Already gone", "",
              "Sole authors whose most recent commit anywhere is more than {0} days old.".format(
                  view["departed_days"]), "",
              "| who | sole files | sole lines | last commit | idle days |", "|---|---|---|---|---|"]
        L += ["| {0} | {1:,} of {2:,} | {3:,} | {4} | {5} |".format(
            a["name"], a["sole_files"], view["sole_files"], a["sole_lines"],
            a["last_day"] or "unknown", a["idle_days"]) for a in view["departed"]]
        L += [""]

    L += ["## Clusters", "",
          "A cluster is one directory's sole-author files under one name — the unit a handover "
          "actually happens in.", "",
          "| where | who | files | lines | referenced by | last touched |",
          "|---|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2:,} | {3:,} | {4:,} | {5} |".format(
        c["where"], c["owner"], c["files"], c["lines"], c["referenced_by"], c["last_day"] or "unknown")
        for c in view["clusters"]] or ["| — | — | 0 | 0 | 0 | — |"]

    L += ["", "## Directories", "", "| where | sole-author files | files | share |", "|---|---|---|---|"]
    L += ["| {0} | {1:,} | {2:,} | {3}% |".format(d["where"], d["sole_files"], d["files"], d["share"])
          for d in view["directories"]] or ["| — | 0 | 0 | 0% |"]

    L += ["", "## Per repository", "",
          "| repository | files | lines | authors | sole-author files | truck factor | shallow |",
          "|---|---|---|---|---|---|---|"]
    L += ["| {0} | {1:,} | {2:,} | {3} | {4:,} ({5}%) | {6} | {7} |".format(
        r["repo"], r["files"], r["lines"], r["authors"], r["sole_files"], r["sole_share"],
        r["truck_factor"], "yes" if r["shallow"] else "no") for r in view["repos"]]

    if view["cross_repo"]:
        L += ["", "## Across repositories", "",
              "One person who is the only author of code in several repositories is one risk, "
              "not several.", "",
              "| who | repositories | files | lines |", "|---|---|---|---|"]
        L += ["| {0} | {1} ({2}) | {3:,} | {4:,} |".format(
            a["name"], a["repo_count"], ", ".join(a["repos"]), a["files"], a["lines"])
            for a in view["cross_repo"]]

    L += ["", "## Single files worth reading with somebody", "",
          "| repository | file | who | lines | referenced by | last touched |",
          "|---|---|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3:,} | {4:,} | {5} |".format(
        f["repo"], f["path"], f["owner"], f["lines"], f["referenced_by"], f["last_ago"])
        for f in view["worst_files"]] or ["| — | — | — | 0 | 0 | — |"]

    moved = view["delta"]
    L += ["", "## Since the last run", "", view["since"], ""]
    if not moved.get("first_run"):
        L += ["| measure | change |", "|---|---|"]
        for key in sorted(set(list(moved["grew"]) + list(moved["shrank"]))):
            change = moved["grew"].get(key, moved["shrank"].get(key, 0))
            L += ["| {0} | {1:+,} |".format(key, int(change))]
        for key in sorted(moved["added"]):
            L += ["| {0} | new ({1}) |".format(key, moved["added"][key])]
        for key in sorted(moved["removed"]):
            L += ["| {0} | gone (was {1}) |".format(key, moved["removed"][key])]
        L += [""]

    L += ["## What was excluded", "",
          "| kind | count | why |", "|---|---|---|",
          "| vendored, generated and lock files | {0:,} | matched one of the {1} patterns in "
          "`EXCLUDED_PATTERNS` |".format(view["excluded_paths"], len(view["excluded_patterns"])),
          "| bot identities | {0} | {1} |".format(
              view["bots_excluded"], ", ".join(view["bot_names"]) or "none"),
          "| authorship rows from bots | {0:,} | dropped before any count |".format(view["bot_rows"]),
          "| files with no readable history | {0:,} | of {1:,} tracked |".format(
              view["unattributed_files"], view["tracked_files"]), ""]

    L += ["## How to read these numbers", ""] + ["- {0}".format(r) for r in view["rules"]]
    L += ["- names are {0}".format(
        "initials plus a short stable hash, so two rows about one person still join"
        if view["redacted"] else "shown as git recorded them, with any address cut at the @")]
    if view["shallow"]:
        L += ["- {0} of the repositories read are shallow clones, so every count here is a lower "
              "bound: {1}".format(len(view["shallow_repos"]), ", ".join(view["shallow_repos"]))]

    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s.get("name", ""), "yes" if s.get("found") else "no",
                                       s.get("note", "") or "") for s in (sources or [])]
    L += ["", "Read-only. `git log` and `git ls-files` were read through the package's one git "
          "runner; no repository was written to, no file's contents were opened, and nothing left "
          "this machine.", ""]
    return "\n".join(L)
