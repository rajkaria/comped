"""Lockfile readers: who you depend on, which of them you asked for, which are only for tests.

Nothing here touches a network and nothing here knows what a registry is. This module answers the
half of `upstream-pulse` that is already sitting on the disk: the complete dependency inventory,
which packages are DIRECT (you named them) and which are transitive (somebody else named them),
and which of them are reachable from the production path rather than only from dev or test.

That split is the whole reason the module exists. "This package has not shipped in three years" is
a fact about the world; "and it is in the code path that answers requests" is a fact about *your*
repository, it costs nothing to establish, and it is the difference between a finding and noise.

Everything is derived, never guessed. A file that does not carry the information says so: each
parse result names its `direct_basis`, and a package whose direct-ness could not be established
gets `direct: None` rather than a cheerful `True` that would inflate the headline count.

## Formats, and the exact subset of each that is read

| file | read |
|---|---|
| `package-lock.json` | v1 (`dependencies` tree, `dev` flags, `requires` edges), v2 and v3 (`packages` map keyed by install path, the `""` root entry for direct names, `dev`/`devOptional` flags, per-entry `dependencies` for edges). Workspace and link entries are recorded as local, never looked up. |
| `pnpm-lock.yaml` | v5 (top-level `dependencies`/`devDependencies`, `packages` keyed `/name/version`), v6 (`/name@version`), v9 (`importers`, `packages` keyed `name@version`, `snapshots` for edges). Peer-suffixed keys `name@1.0.0(peer@2.0.0)` are reduced to `name@1.0.0`. |
| `yarn.lock` | classic (descriptor headers, `version "x"`, nested `dependencies:` blocks) and berry v2+ (YAML, `__metadata`, `resolution:`, the `@workspace:` entry as the root). |
| `requirements.txt` | one requirement per line, `\\` continuations, `#` comments, extras `pkg[a,b]`, environment markers after `;`, `--hash=` fragments, `-e`/`--editable`, direct URLs and `name @ url`. `-r other.txt` is recorded as an include, not followed. |
| `poetry.lock` | `[[package]]` blocks (`name`, `version`, `category`, `groups`, `optional`) and `[package.dependencies]` for edges. |
| `Pipfile.lock` | `default` and `develop` maps, `version` pinned as `==x.y.z`. |
| `go.mod` / `go.sum` | `require` lines and `require (...)` blocks, `// indirect` markers, `replace`/`exclude`/`retract` blocks skipped; `go.sum` module lines with the `/go.mod` suffix folded away. |
| `Cargo.lock` | `[[package]]` blocks (`name`, `version`, `source`, `dependencies`), with a sourceless package treated as your own crate and therefore as the graph root. |

## The two hand-written format readers

The standard library has no YAML and no TOML reader, and this package may not add a dependency, so
`mini_yaml` and `mini_toml` below are written from scratch. Both are deliberately narrow and both
document their own subset in their docstrings. Neither is a general parser and neither pretends to
be: anything outside the subset is returned as opaque text rather than silently mis-read.
"""
import json
import re

# ---------------------------------------------------------------- what counts as a lockfile

EXACT = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "pnpm-lock.yaml": "npm",
    "yarn.lock": "npm",
    "poetry.lock": "pypi",
    "Pipfile.lock": "pypi",
    "go.sum": "go",
    "go.mod": "go",
    "Cargo.lock": "crates",
}

# requirements.txt, requirements-dev.txt, requirements/base.txt … all read the same way.
REQUIREMENTS = re.compile(r"^requirements[a-z0-9._-]*\.txt$", re.I)

# The manifest that sits next to a lockfile and names what you actually asked for.
MANIFEST = {
    "package-lock.json": ("package.json",),
    "npm-shrinkwrap.json": ("package.json",),
    "pnpm-lock.yaml": ("package.json",),
    "yarn.lock": ("package.json",),
    "poetry.lock": ("pyproject.toml",),
    "Pipfile.lock": ("Pipfile",),
    "Cargo.lock": ("Cargo.toml",),
    "go.sum": ("go.mod",),
}

DEV_GROUPS = ("dev", "devel", "develop", "development", "test", "tests", "testing", "lint",
              "linting", "style", "docs", "doc", "typing", "types", "ci", "check", "checks")

MAX_PACKAGES = 20000        # a lockfile larger than this is reported as truncated, not read whole


def is_lockfile(name: str) -> bool:
    return name in EXACT or bool(REQUIREMENTS.match(name or ""))


def ecosystem_of(name: str) -> str:
    return EXACT.get(name, "pypi" if REQUIREMENTS.match(name or "") else "unknown")


def manifests_for(name: str) -> tuple:
    return MANIFEST.get(name, ())


def normalise(ecosystem: str, name: str) -> str:
    """The name two files must agree on before they can be talked about as one package.

    PyPI is the only ecosystem here with a normalisation rule of its own (PEP 503: case-folded,
    every run of `-`, `_` or `.` collapsed to a single `-`), and without it `Flask` in a
    requirements file and `flask` in a lock file are two packages that are obviously one.
    """
    n = str(name or "").strip()
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", n).lower()
    return n


def is_dev_group(group: str) -> bool:
    return str(group or "").strip().lower() in DEV_GROUPS


# ---------------------------------------------------------------- minimal YAML

def mini_yaml(text: str):
    """Indentation-based YAML, restricted to the shapes lockfiles actually use.

    Handled: block mappings, block sequences, nesting by indentation, `#` comments on their own
    line or after an unquoted value, single- and double-quoted keys and scalars, and the plain
    scalars `true`, `false`, `null` and `~`.

    Not handled, on purpose: anchors and aliases, tags, multi-line scalars (`|`, `>`), multiple
    documents, and merge keys. Flow collections (`{a: b}`, `[1, 2]`) are kept as the raw text
    between their brackets rather than parsed, because the only fields lockfiles put in flow style
    are integrity hashes this module never reads. Anything unhandled degrades to a string; nothing
    raises.
    """
    lines = _yaml_lines(text)
    if not lines:
        return {}
    value, _ = _yaml_block(lines, 0, lines[0][0])
    return value


def _yaml_lines(text: str) -> list:
    out = []
    for raw in str(text or "").splitlines():
        stripped = raw.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(stripped)
        if "\t" in raw[:indent]:
            continue                                    # a tab is never valid YAML indentation
        out.append((indent, stripped.rstrip()))
    return out


def _yaml_block(lines: list, i: int, indent: int):
    if i < len(lines) and (lines[i][1] == "-" or lines[i][1].startswith("- ")):
        return _yaml_seq(lines, i, indent)
    return _yaml_map(lines, i, indent)


def _yaml_map(lines: list, i: int, indent: int):
    node = {}
    while i < len(lines):
        ind, content = lines[i]
        if ind < indent:
            break
        if ind > indent:                                # stray deeper line with no parent key
            i += 1
            continue
        key, rest, ok = _yaml_split(content)
        i += 1
        if not ok:
            continue
        if rest:
            node[key] = _yaml_scalar(rest)
        elif i < len(lines) and lines[i][0] > ind:
            child, i = _yaml_block(lines, i, lines[i][0])
            node[key] = child
        else:
            node[key] = ""
    return node, i


def _yaml_seq(lines: list, i: int, indent: int):
    items = []
    while i < len(lines):
        ind, content = lines[i]
        if ind < indent or not (content == "-" or content.startswith("- ")):
            break
        rest = content[1:].strip()
        i += 1
        if rest:
            key, value, ok = _yaml_split(rest)
            if ok and i < len(lines) and lines[i][0] > ind:
                child, i = _yaml_map(lines, i, lines[i][0])
                child[key] = _yaml_scalar(value) if value else child.get(key, "")
                items.append(child)
            elif ok and value:
                items.append({key: _yaml_scalar(value)})
            else:
                items.append(_yaml_scalar(rest))
        elif i < len(lines) and lines[i][0] > ind:
            child, i = _yaml_block(lines, i, lines[i][0])
            items.append(child)
    return items, i


def _yaml_split(content: str) -> tuple:
    """(key, rest, is_a_mapping_line). Quoted keys are honoured, which berry's yarn.lock needs."""
    s = content
    if s[:1] in ('"', "'"):
        quote = s[0]
        j = 1
        while j < len(s):
            if s[j] == "\\" and quote == '"':
                j += 2
                continue
            if s[j] == quote:
                break
            j += 1
        key = s[1:j]
        rest = s[j + 1:].lstrip()
        if not rest.startswith(":"):
            return "", "", False
        return key, rest[1:].strip(), True
    for j, ch in enumerate(s):
        if ch == ":" and (j + 1 == len(s) or s[j + 1] == " "):
            return s[:j].strip(), s[j + 1:].strip(), True
    return "", "", False


def _yaml_scalar(s: str):
    s = s.strip()
    if not s:
        return ""
    if s[0] in ('"', "'"):
        quote = s[0]
        j = 1
        out = []
        while j < len(s):
            if s[j] == "\\" and quote == '"' and j + 1 < len(s):
                out.append({"n": "\n", "t": "\t"}.get(s[j + 1], s[j + 1]))
                j += 2
                continue
            if s[j] == quote:
                break
            out.append(s[j])
            j += 1
        return "".join(out)
    if s[0] in "{[":
        return s                                        # flow collection, kept as opaque text
    s = s.split(" #")[0].rstrip()
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    return s


# ---------------------------------------------------------------- minimal TOML

def mini_toml(text: str) -> dict:
    """TOML restricted to what `poetry.lock`, `Cargo.lock`, `Cargo.toml`, `Pipfile` and
    `pyproject.toml` put in front of a reader.

    Handled: `[table]` and `[[array of tables]]` headers including dotted and quoted names,
    `key = value` pairs, basic and literal strings, integers, floats, booleans, arrays (including
    arrays written across several lines), inline tables, and `#` comments outside strings.

    Not handled: multi-line basic and literal strings (`\"\"\"`, `'''`), dotted keys on the
    left-hand side of an assignment, and date-times, which are returned as plain strings. Nothing
    here raises: an unreadable line is skipped and the rest of the document is still returned.
    """
    doc = {}
    current = doc
    for line in _toml_logical_lines(text):
        if line.startswith("[[") and line.endswith("]]"):
            current = _toml_descend(doc, _toml_key_parts(line[2:-2]), True)
        elif line.startswith("[") and line.endswith("]"):
            current = _toml_descend(doc, _toml_key_parts(line[1:-1]), False)
        elif "=" in line:
            key, _, raw = line.partition("=")
            name = _toml_key_parts(key.strip())
            if name:
                current[name[-1]] = _toml_value(raw.strip())
    return doc


def _toml_logical_lines(text: str) -> list:
    lines = str(text or "").splitlines()
    out, i = [], 0
    while i < len(lines):
        line = _toml_strip_comment(lines[i])
        i += 1
        if not line.strip():
            continue
        depth = _toml_balance(line)
        while depth > 0 and i < len(lines):
            nxt = _toml_strip_comment(lines[i])
            i += 1
            line = line + " " + nxt.strip()
            depth += _toml_balance(nxt)
        out.append(line.strip())
    return out


def _toml_strip_comment(line: str) -> str:
    out, mode, i = [], "", 0
    while i < len(line):
        ch = line[i]
        if mode == '"':
            if ch == "\\" and i + 1 < len(line):
                out.append(ch)
                out.append(line[i + 1])
                i += 2
                continue
            if ch == '"':
                mode = ""
        elif mode == "'":
            if ch == "'":
                mode = ""
        else:
            if ch == "#":
                break
            if ch in ('"', "'"):
                mode = ch
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _toml_balance(line: str) -> int:
    depth, mode, i = 0, "", 0
    while i < len(line):
        ch = line[i]
        if mode:
            if ch == "\\" and mode == '"' and i + 1 < len(line):
                i += 2
                continue
            if ch == mode:
                mode = ""
        elif ch in ('"', "'"):
            mode = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        i += 1
    # A table header is balanced by construction; only an unterminated collection matters.
    return depth


def _toml_key_parts(s: str) -> list:
    parts, buf, mode = [], [], ""
    for ch in str(s or "").strip():
        if mode:
            if ch == mode:
                mode = ""
            else:
                buf.append(ch)
            continue
        if ch in ('"', "'"):
            mode = ch
        elif ch == ".":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _toml_descend(doc: dict, parts: list, array: bool) -> dict:
    if not parts:
        return doc
    node = doc
    for part in parts[:-1]:
        nxt = node.get(part)
        if isinstance(nxt, list) and nxt and isinstance(nxt[-1], dict):
            nxt = nxt[-1]
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    last = parts[-1]
    if array:
        existing = node.get(last)
        if not isinstance(existing, list):
            existing = []
            node[last] = existing
        fresh = {}
        existing.append(fresh)
        return fresh
    existing = node.get(last)
    if isinstance(existing, dict):
        return existing
    fresh = {}
    node[last] = fresh
    return fresh


def _toml_value(s: str):
    value, _ = _toml_read(str(s or "").strip(), 0)
    return value


def _toml_read(s: str, i: int):
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    ch = s[i]
    if ch == '"':
        out, i = [], i + 1
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(s[i + 1], s[i + 1]))
                i += 2
                continue
            if s[i] == '"':
                i += 1
                break
            out.append(s[i])
            i += 1
        return "".join(out), i
    if ch == "'":
        end = s.find("'", i + 1)
        if end < 0:
            return s[i + 1:], len(s)
        return s[i + 1:end], end + 1
    if ch == "[":
        items, i = [], i + 1
        while i < len(s):
            while i < len(s) and s[i] in " ,":
                i += 1
            if i < len(s) and s[i] == "]":
                return items, i + 1
            if i >= len(s):
                break
            item, i = _toml_read(s, i)
            items.append(item)
        return items, i
    if ch == "{":
        table, i = {}, i + 1
        while i < len(s):
            while i < len(s) and s[i] in " ,":
                i += 1
            if i < len(s) and s[i] == "}":
                return table, i + 1
            j = s.find("=", i)
            if j < 0:
                break
            key = _toml_key_parts(s[i:j])
            value, i = _toml_read(s, j + 1)
            if key:
                table[key[-1]] = value
        return table, i
    j = i
    while j < len(s) and s[j] not in ",]}":
        j += 1
    raw = s[i:j].strip()
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true", j
    if re.match(r"^[+-]?\d[\d_]*$", raw):
        return int(raw.replace("_", "")), j
    if re.match(r"^[+-]?\d[\d_]*\.\d+$", raw):
        return float(raw.replace("_", "")), j
    return raw, j


# ---------------------------------------------------------------- the dispatcher

def parse(name: str, text: str, manifest_text: str = "", manifest_name: str = "",
          extra_text: str = "") -> dict:
    """Read one lockfile. Never raises: an unreadable file comes back with `ok` False and a note.

    The result is the raw shape — packages, edges and roots — and `resolve()` turns it into the
    flat inventory. They are separate so the graph walk is written once rather than eight times.
    """
    base = {"lockfile": name, "ecosystem": ecosystem_of(name), "format": name, "ok": True,
            "direct_basis": "", "note": "", "roots": {"production": [], "development": []},
            "packages": [], "edges": {}, "includes": []}
    try:
        if name in ("package-lock.json", "npm-shrinkwrap.json"):
            return _npm_lock(base, text, manifest_text)
        if name == "pnpm-lock.yaml":
            return _pnpm_lock(base, text, manifest_text)
        if name == "yarn.lock":
            return _yarn_lock(base, text, manifest_text)
        if name == "poetry.lock":
            return _poetry_lock(base, text, manifest_text)
        if name == "Pipfile.lock":
            return _pipfile_lock(base, text, manifest_text)
        if name == "Cargo.lock":
            return _cargo_lock(base, text, manifest_text)
        if name in ("go.sum", "go.mod"):
            return _go(base, text if name == "go.sum" else "",
                       manifest_text if name == "go.sum" else text)
        if REQUIREMENTS.match(name or ""):
            return _requirements(base, text)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        base["ok"] = False
        base["note"] = "could not be read ({0})".format(type(exc).__name__)
        return base
    base["ok"] = False
    base["note"] = "not a format this Play reads"
    return base


def read(name: str, text: str, manifest_text: str = "", manifest_name: str = "") -> tuple:
    """`parse` then `resolve`: (result, packages). The one call a scanner needs."""
    result = parse(name, text, manifest_text, manifest_name)
    return result, resolve(result)


# ---------------------------------------------------------------- graph resolution

def resolve(result: dict) -> list:
    """Turn one parse result into the flat inventory, with direct-ness and scope settled.

    Scope is answered by reachability, not by a label: a package is in the production path when a
    walk from the production roots reaches it, and the shortest such walk is kept so the report can
    print *why* rather than assert it. A package no walk reaches falls back to whatever hint the
    file itself carried, and to `"unknown"` when it carried none — which the card prints as its own
    tier, because "we could not tell" and "only used in tests" are very different answers.
    """
    edges = result.get("edges") or {}
    roots = result.get("roots") or {}
    prod_roots = sorted(set(roots.get("production") or ()))
    dev_roots = sorted(set(roots.get("development") or ()))
    prod = _reach(prod_roots, edges)
    dev = _reach([r for r in dev_roots if r not in prod], edges)
    have_roots = bool(prod_roots or dev_roots)
    root_names = set(prod_roots) | set(dev_roots)

    out = []
    for p in result.get("packages") or ():
        name = p.get("name") or ""
        if name in prod:
            scope, depth, path = "production", prod[name][0], prod[name][1]
        elif name in dev:
            scope, depth, path = "development", dev[name][0], dev[name][1]
        else:
            scope, depth, path = p.get("scope_hint") or "unknown", None, []
        direct = p.get("direct_hint")
        if name in root_names:
            direct = True
        elif direct is None and have_roots:
            direct = False
        out.append({
            "name": name,
            "display": p.get("display") or name,
            "ecosystem": result.get("ecosystem") or "unknown",
            "version": p.get("version") or "",
            "direct": direct,
            "scope": scope,
            "depth": depth,
            "path": list(path),
            "local": bool(p.get("local")),
            "lockfile": result.get("lockfile") or "",
            "format": result.get("format") or "",
            "direct_basis": result.get("direct_basis") or "",
        })
    return sorted(out, key=lambda q: (q["ecosystem"], q["name"], q["version"]))


def _reach(roots, edges: dict) -> dict:
    """Breadth-first from the roots. {name: (depth, path)} with the shortest path kept."""
    seen, queue = {}, []
    for r in sorted(set(roots)):
        if r not in seen:
            seen[r] = (0, [r])
            queue.append(r)
    head = 0
    while head < len(queue):
        node = queue[head]
        head += 1
        depth, path = seen[node]
        if depth > 24:                                  # a cycle-proof ceiling, never reached in practice
            continue
        for child in sorted(set(edges.get(node) or ())):
            if child in seen:
                continue
            seen[child] = (depth + 1, path + [child])
            queue.append(child)
    return seen


def _graph_roots(names, edges: dict) -> list:
    """Everything nobody depends on. The honest fallback when no manifest is next to the lock."""
    children = set()
    for parent in edges:
        for child in edges[parent] or ():
            children.add(child)
    return sorted(n for n in set(names) if n not in children)


# ---------------------------------------------------------------- npm: package-lock.json

def _npm_name(key: str) -> str:
    """`node_modules/a/node_modules/@scope/b` is package `@scope/b`."""
    return str(key or "").split("node_modules/")[-1]


def _npm_manifest_roots(manifest_text: str) -> tuple:
    doc = _json_or_empty(manifest_text)
    prod = sorted(set(doc.get("dependencies") or {}) | set(doc.get("optionalDependencies") or {}))
    dev = sorted(set(doc.get("devDependencies") or {}))
    return prod, dev


def _npm_lock(base: dict, text: str, manifest_text: str) -> dict:
    doc = _json_or_empty(text)
    version = doc.get("lockfileVersion")
    try:
        version = int(version)
    except (TypeError, ValueError):
        version = 1
    base["format"] = "{0} (lockfileVersion {1})".format(base["lockfile"], version)
    packages, edges = [], {}
    prod, dev = _npm_manifest_roots(manifest_text)
    basis = "the package.json next to it" if (prod or dev) else ""

    entries = doc.get("packages")
    if isinstance(entries, dict) and entries:
        root = entries.get("") if isinstance(entries.get(""), dict) else {}
        if not basis and root:
            prod = sorted(set(root.get("dependencies") or {}) |
                          set(root.get("optionalDependencies") or {}))
            dev = sorted(set(root.get("devDependencies") or {}))
            basis = "the lockfile's own root entry"
        for key in sorted(entries):
            if key == "" or len(packages) >= MAX_PACKAGES:
                continue
            meta = entries[key] if isinstance(entries[key], dict) else {}
            if "node_modules/" not in key:
                packages.append({"name": key, "display": key, "version": meta.get("version") or "",
                                 "local": True, "scope_hint": "production", "direct_hint": False})
                continue
            name = _npm_name(key)
            hint = "development" if (meta.get("dev") or meta.get("devOptional")) else "production"
            packages.append({"name": name, "display": name, "version": meta.get("version") or "",
                             "scope_hint": hint, "local": bool(meta.get("link"))})
            kids = sorted(set(meta.get("dependencies") or {}) | set(meta.get("optionalDependencies") or {}))
            if kids:
                edges.setdefault(name, [])
                edges[name] = sorted(set(edges[name]) | set(kids))
    else:
        tree = doc.get("dependencies")
        if isinstance(tree, dict):
            _npm_v1_walk(tree, packages, edges)
            if not basis:
                prod = sorted(set(tree))
                dev = []
                basis = "the lockfile's hoisted top level (approximate: npm v1 does not record " \
                        "which of them you asked for)"
        else:
            base["ok"] = False
            base["note"] = "no dependencies recorded"

    base["packages"] = _dedupe(packages)
    base["edges"] = edges
    base["roots"] = {"production": prod, "development": dev}
    base["direct_basis"] = basis or "not recorded by this file"
    return base


def _npm_v1_walk(tree: dict, packages: list, edges: dict):
    for name in sorted(tree):
        meta = tree[name] if isinstance(tree[name], dict) else {}
        if len(packages) >= MAX_PACKAGES:
            return
        packages.append({"name": name, "display": name, "version": meta.get("version") or "",
                         "scope_hint": "development" if meta.get("dev") else "production"})
        kids = sorted(set(meta.get("requires") or {}))
        if kids:
            edges[name] = sorted(set(edges.get(name) or []) | set(kids))
        nested = meta.get("dependencies")
        if isinstance(nested, dict):
            _npm_v1_walk(nested, packages, edges)


# ---------------------------------------------------------------- npm: pnpm-lock.yaml

def _pnpm_key(key: str) -> tuple:
    k = str(key or "").strip().strip("'\"")
    k = k.split("(")[0]                                 # peer suffix: name@1.0.0(peer@2.0.0)
    if k.startswith("/"):
        k = k[1:]
    if "@" in k[1:]:
        name, _, ver = k.rpartition("@")
        if name and "/" not in ver:
            return name, ver
    parts = k.rsplit("/", 1)                            # v5 form: @scope/name/1.0.0
    if len(parts) == 2 and parts[1][:1].isdigit():
        return parts[0], parts[1]
    return k, ""


def _pnpm_versions(block) -> list:
    """`{name: "1.0.0"}` in v5, `{name: {specifier, version}}` in v6 and v9. Both are just names."""
    return sorted(block) if isinstance(block, dict) else []


def _pnpm_lock(base: dict, text: str, manifest_text: str) -> dict:
    doc = mini_yaml(text)
    doc = doc if isinstance(doc, dict) else {}
    base["format"] = "pnpm-lock.yaml (lockfileVersion {0})".format(doc.get("lockfileVersion") or "?")
    prod, dev, basis = [], [], ""

    importers = doc.get("importers")
    if isinstance(importers, dict) and importers:
        for key in sorted(importers):
            block = importers[key] if isinstance(importers[key], dict) else {}
            prod += _pnpm_versions(block.get("dependencies"))
            prod += _pnpm_versions(block.get("optionalDependencies"))
            dev += _pnpm_versions(block.get("devDependencies"))
        basis = "the lockfile's own importers section"
    elif isinstance(doc.get("dependencies"), dict) or isinstance(doc.get("devDependencies"), dict):
        prod = _pnpm_versions(doc.get("dependencies")) + _pnpm_versions(doc.get("optionalDependencies"))
        dev = _pnpm_versions(doc.get("devDependencies"))
        basis = "the lockfile's own top-level dependency blocks"
    if not basis:
        prod, dev = _npm_manifest_roots(manifest_text)
        basis = "the package.json next to it" if (prod or dev) else "not recorded by this file"

    packages, edges = [], {}
    for section in ("packages", "snapshots"):
        block = doc.get(section)
        if not isinstance(block, dict):
            continue
        for key in sorted(block):
            name, ver = _pnpm_key(key)
            if not name:
                continue
            meta = block[key] if isinstance(block[key], dict) else {}
            if section == "packages" and len(packages) < MAX_PACKAGES:
                packages.append({"name": name, "display": name, "version": ver,
                                 "scope_hint": "unknown"})
            kids = []
            for kind in ("dependencies", "optionalDependencies"):
                kids += _pnpm_versions(meta.get(kind))
            if kids:
                edges[name] = sorted(set(edges.get(name) or []) | set(kids))
    base["packages"] = _dedupe(packages)
    base["edges"] = edges
    base["roots"] = {"production": sorted(set(prod)), "development": sorted(set(dev))}
    base["direct_basis"] = basis
    return base


# ---------------------------------------------------------------- npm: yarn.lock

def _descriptor_name(descriptor: str) -> str:
    """`@scope/name@npm:^1.0.0` and `name@^1.0.0` both name a package; the range is not part of it."""
    d = str(descriptor or "").strip().strip('"').strip("'")
    if d.startswith("@"):
        head, _, _rest = d[1:].partition("@")
        return "@" + head
    return d.partition("@")[0] or d


def _yarn_lock(base: dict, text: str, manifest_text: str) -> dict:
    berry = bool(re.search(r"^__metadata:", str(text or ""), re.M)) or \
        bool(re.search(r"^\s+resolution: ", str(text or ""), re.M))
    return _yarn_berry(base, text, manifest_text) if berry else _yarn_classic(base, text, manifest_text)


def _yarn_berry(base: dict, text: str, manifest_text: str) -> dict:
    base["format"] = "yarn.lock (berry)"
    doc = mini_yaml(text)
    doc = doc if isinstance(doc, dict) else {}
    packages, edges, prod, dev, basis = [], {}, [], [], ""
    for header in sorted(doc):
        if header == "__metadata":
            continue
        meta = doc[header] if isinstance(doc[header], dict) else {}
        descriptors = [d.strip() for d in str(header).split(",") if d.strip()]
        name = _descriptor_name(descriptors[0]) if descriptors else ""
        if not name:
            continue
        if any("@workspace:" in d for d in descriptors):
            prod += sorted(meta.get("dependencies") or {})
            dev += sorted(meta.get("devDependencies") or {})
            basis = "the workspace entry inside the lockfile"
            continue
        if len(packages) < MAX_PACKAGES:
            packages.append({"name": name, "display": name,
                             "version": str(meta.get("version") or ""), "scope_hint": "unknown"})
        kids = sorted(meta.get("dependencies") or {})
        if kids:
            edges[name] = sorted(set(edges.get(name) or []) | set(kids))
    return _yarn_finish(base, packages, edges, prod, dev, basis, manifest_text)


def _yarn_classic(base: dict, text: str, manifest_text: str) -> dict:
    base["format"] = "yarn.lock (classic)"
    packages, edges = [], {}
    header, version, kids, in_deps = "", "", [], False
    for raw in str(text or "").splitlines() + [""]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            if header and len(packages) < MAX_PACKAGES:
                name = _descriptor_name(header.split(",")[0])
                packages.append({"name": name, "display": name, "version": version,
                                 "scope_hint": "unknown"})
                if kids:
                    edges[name] = sorted(set(edges.get(name) or []) | set(kids))
            header, version, kids, in_deps = line.rstrip(":"), "", [], False
            continue
        if indent == 2:
            in_deps = line.rstrip(":") in ("dependencies", "optionalDependencies")
            m = re.match(r'^version\s+"?([^"\s]+)"?$', line)
            if m:
                version = m.group(1)
            continue
        if in_deps and indent >= 4:
            kids.append(line.split()[0].strip('"'))
    if header and len(packages) < MAX_PACKAGES:
        name = _descriptor_name(header.split(",")[0])
        packages.append({"name": name, "display": name, "version": version, "scope_hint": "unknown"})
        if kids:
            edges[name] = sorted(set(edges.get(name) or []) | set(kids))
    return _yarn_finish(base, packages, edges, [], [], "", manifest_text)


def _yarn_finish(base: dict, packages: list, edges: dict, prod: list, dev: list, basis: str,
                 manifest_text: str) -> dict:
    if not basis:
        prod, dev = _npm_manifest_roots(manifest_text)
        basis = "the package.json next to it" if (prod or dev) else ""
    packages = _dedupe(packages)
    if not basis:
        prod = _graph_roots([p["name"] for p in packages], edges)
        basis = "packages nothing else depends on (approximate: yarn.lock records no manifest " \
                "and none was found next to it)"
    base["packages"] = packages
    base["edges"] = edges
    base["roots"] = {"production": sorted(set(prod)), "development": sorted(set(dev))}
    base["direct_basis"] = basis
    return base


# ---------------------------------------------------------------- pypi: requirements.txt

REQ_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
REQ_PIN = re.compile(r"==\s*([A-Za-z0-9][A-Za-z0-9._+!-]*)")


def _requirements(base: dict, text: str) -> dict:
    """Every line of a requirements file is something a person typed, so every line is direct.

    That is not always literally true — `pip freeze` writes transitive packages too — so the basis
    says exactly what was assumed rather than letting the number stand unqualified.
    """
    name = base["lockfile"]
    dev = any(tag in name.lower() for tag in ("dev", "test", "lint", "doc", "typing", "ci"))
    base["format"] = "{0} ({1})".format(name, "dev/test requirements" if dev else "requirements")
    packages, includes = [], []
    for line in _logical_requirement_lines(text):
        if line.startswith(("-r", "--requirement")):
            includes.append(line.split(None, 1)[-1].strip())
            continue
        if line.startswith("-") and not line.startswith(("-e", "--editable")):
            continue
        body = line
        for prefix in ("-e ", "--editable "):
            if body.startswith(prefix):
                body = body[len(prefix):].strip()
        body = body.split(";")[0].strip()                # environment markers
        body = re.sub(r"--hash=\S+", "", body).strip()
        if " @ " in body:
            body = body.split(" @ ")[0].strip()
        if "://" in body and not REQ_NAME.match(body):
            frag = re.search(r"#egg=([A-Za-z0-9][A-Za-z0-9._-]*)", body)
            if not frag:
                continue
            body = frag.group(1)
        body = body.split("[")[0].strip() + ("" if "[" not in body else body.split("]", 1)[-1])
        m = REQ_NAME.match(body)
        if not m or len(packages) >= MAX_PACKAGES:
            continue
        pin = REQ_PIN.search(line)
        packages.append({"name": normalise("pypi", m.group(1)), "display": m.group(1),
                         "version": pin.group(1) if pin else "",
                         "scope_hint": "development" if dev else "production", "direct_hint": True})
    base["packages"] = _dedupe(packages)
    base["includes"] = sorted(set(includes))
    names = [p["name"] for p in base["packages"]]
    key = "development" if dev else "production"
    base["roots"] = {"production": [] if dev else names, "development": names if dev else []}
    base["direct_basis"] = "every line of a requirements file is a requirement someone wrote " \
                           "(counted as {0} because of the file name)".format(key)
    return base


def _logical_requirement_lines(text: str) -> list:
    out, buf = [], ""
    for raw in str(text or "").splitlines():
        line = raw.split(" #")[0].rstrip() if " #" in raw else raw.rstrip()
        if line.lstrip().startswith("#"):
            continue
        if not line.strip():
            continue
        if line.endswith("\\"):
            buf += line[:-1].strip() + " "
            continue
        out.append((buf + line.strip()).strip())
        buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


# ---------------------------------------------------------------- pypi: poetry.lock

def _python_manifest_roots(text: str) -> tuple:
    doc = mini_toml(text)
    prod, dev = set(), set()
    project = doc.get("project") if isinstance(doc.get("project"), dict) else {}
    for spec in project.get("dependencies") or ():
        got = REQ_NAME.match(str(spec).strip())
        if got:
            prod.add(normalise("pypi", got.group(1)))
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group in sorted(optional):
            target = dev if is_dev_group(group) else prod
            for spec in optional[group] or ():
                got = REQ_NAME.match(str(spec).strip())
                if got:
                    target.add(normalise("pypi", got.group(1)))
    poetry = ((doc.get("tool") or {}).get("poetry") or {}) if isinstance(doc.get("tool"), dict) else {}
    for name in (poetry.get("dependencies") or {}):
        if normalise("pypi", name) != "python":
            prod.add(normalise("pypi", name))
    for name in (poetry.get("dev-dependencies") or {}):
        dev.add(normalise("pypi", name))
    groups = poetry.get("group") if isinstance(poetry.get("group"), dict) else {}
    for group in sorted(groups):
        block = groups[group] if isinstance(groups[group], dict) else {}
        target = dev if is_dev_group(group) else prod
        for name in (block.get("dependencies") or {}):
            target.add(normalise("pypi", name))
    # Pipfile uses the same reader: [packages] and [dev-packages].
    for name in (doc.get("packages") or {}) if isinstance(doc.get("packages"), dict) else {}:
        prod.add(normalise("pypi", name))
    for name in (doc.get("dev-packages") or {}) if isinstance(doc.get("dev-packages"), dict) else {}:
        dev.add(normalise("pypi", name))
    return sorted(prod), sorted(dev - prod)


def _poetry_lock(base: dict, text: str, manifest_text: str) -> dict:
    doc = mini_toml(text)
    base["format"] = "poetry.lock (lock-version {0})".format(
        ((doc.get("metadata") or {}).get("lock-version") or "?") if isinstance(doc.get("metadata"), dict) else "?")
    packages, edges = [], {}
    for entry in doc.get("package") or ():
        if not isinstance(entry, dict) or len(packages) >= MAX_PACKAGES:
            continue
        raw = str(entry.get("name") or "")
        if not raw:
            continue
        name = normalise("pypi", raw)
        groups = entry.get("groups") if isinstance(entry.get("groups"), list) else []
        category = str(entry.get("category") or "")
        if groups:
            hint = "production" if any(not is_dev_group(g) for g in groups) else "development"
        elif category:
            hint = "development" if is_dev_group(category) else "production"
        else:
            hint = "unknown"
        packages.append({"name": name, "display": raw, "version": str(entry.get("version") or ""),
                         "scope_hint": hint})
        kids = entry.get("dependencies")
        if isinstance(kids, dict) and kids:
            edges[name] = sorted(normalise("pypi", k) for k in kids)
    prod, dev = _python_manifest_roots(manifest_text)
    basis = "the pyproject.toml next to it" if (prod or dev) else ""
    packages = _dedupe(packages)
    if not basis:
        prod = _graph_roots([p["name"] for p in packages], edges)
        basis = "packages nothing else in the lock depends on (approximate: no pyproject.toml " \
                "was found next to it)"
    base["packages"] = packages
    base["edges"] = edges
    base["roots"] = {"production": prod, "development": dev}
    base["direct_basis"] = basis
    return base


# ---------------------------------------------------------------- pypi: Pipfile.lock

def _pipfile_lock(base: dict, text: str, manifest_text: str) -> dict:
    doc = _json_or_empty(text)
    meta = doc.get("_meta") if isinstance(doc.get("_meta"), dict) else {}
    base["format"] = "Pipfile.lock (pipfile-spec {0})".format(meta.get("pipfile-spec") or "?")
    packages = []
    for section, hint in (("default", "production"), ("develop", "development")):
        block = doc.get(section)
        if not isinstance(block, dict):
            continue
        for raw in sorted(block):
            if len(packages) >= MAX_PACKAGES:
                break
            entry = block[raw] if isinstance(block[raw], dict) else {}
            version = str(entry.get("version") or "").lstrip("=")
            packages.append({"name": normalise("pypi", raw), "display": raw, "version": version,
                             "scope_hint": hint})
    prod, dev = _python_manifest_roots(manifest_text)
    basis = "the Pipfile next to it" if (prod or dev) else ""
    packages = _dedupe(packages)
    if not basis:
        # Pipfile.lock is a flat resolved set with no graph in it at all, so direct-ness is not
        # merely approximate here, it is absent. Saying `None` is the only honest answer.
        for p in packages:
            p["direct_hint"] = None
        basis = "not recorded: Pipfile.lock is a flat resolved set and no Pipfile was found " \
                "next to it, so direct and transitive cannot be told apart"
    base["packages"] = packages
    base["edges"] = {}
    base["roots"] = {"production": prod, "development": dev}
    base["direct_basis"] = basis
    return base


# ---------------------------------------------------------------- go

def _go(base: dict, sum_text: str, mod_text: str) -> dict:
    base["ecosystem"] = "go"
    direct, indirect, versions = [], [], {}
    block = ""
    for raw in str(mod_text or "").splitlines():
        body, _, comment = raw.partition("//")
        body = body.strip()
        if not body:
            continue
        if body.endswith("(") and body.split()[0] in ("require", "replace", "exclude", "retract"):
            block = body.split()[0]
            continue
        if body == ")":
            block = ""
            continue
        if body.startswith("require "):
            entry, where = body[len("require "):].strip(), "require"
        elif block:
            entry, where = body, block
        else:
            continue
        if where != "require":
            continue
        parts = entry.split()
        if len(parts) < 2 or not parts[1].startswith("v"):
            continue
        versions[parts[0]] = parts[1]
        (indirect if "indirect" in comment else direct).append(parts[0])

    for raw in str(sum_text or "").splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        name, version = parts[0], parts[1]
        if version.endswith("/go.mod"):
            version = version[:-len("/go.mod")]
        versions.setdefault(name, version)

    known = sorted(versions)
    packages = [{"name": n, "display": n, "version": versions[n], "scope_hint": "production",
                 "direct_hint": (True if n in direct else (False if (direct or indirect) else None))}
                for n in known[:MAX_PACKAGES]]
    base["format"] = "go.sum + go.mod" if sum_text and mod_text else ("go.sum" if sum_text else "go.mod")
    base["packages"] = packages
    base["edges"] = {}
    base["roots"] = {"production": sorted(set(direct)), "development": []}
    base["direct_basis"] = ("go.mod's require block, where a transitive module carries an "
                            "`// indirect` marker") if (direct or indirect) else \
        "not recorded: go.sum lists every module in the graph and no go.mod was found next to it"
    return base


# ---------------------------------------------------------------- crates: Cargo.lock

def _cargo_lock(base: dict, text: str, manifest_text: str) -> dict:
    doc = mini_toml(text)
    base["format"] = "Cargo.lock (version {0})".format(doc.get("version") or "?")
    packages, edges, local = [], {}, []
    for entry in doc.get("package") or ():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if not name:
            continue
        kids = [str(d).split()[0] for d in (entry.get("dependencies") or ()) if str(d).strip()]
        if kids:
            edges[name] = sorted(set(edges.get(name) or []) | set(kids))
        if not entry.get("source"):
            local.append(name)                          # your own crate: the root, not a dependency
            continue
        if len(packages) < MAX_PACKAGES:
            packages.append({"name": name, "display": name,
                             "version": str(entry.get("version") or ""), "scope_hint": "unknown"})

    manifest = mini_toml(manifest_text)
    prod = sorted(set(manifest.get("dependencies") or {}) | set(manifest.get("build-dependencies") or {})) \
        if isinstance(manifest.get("dependencies"), dict) or isinstance(manifest.get("build-dependencies"), dict) else []
    dev = sorted(manifest.get("dev-dependencies") or {}) \
        if isinstance(manifest.get("dev-dependencies"), dict) else []
    basis = "the Cargo.toml next to it" if (prod or dev) else ""
    if not basis and local:
        prod = sorted(set(c for crate in local for c in (edges.get(crate) or ())))
        basis = "the dependencies of your own crate, which Cargo.lock records without a source"
    packages = _dedupe(packages)
    if not basis:
        prod = _graph_roots([p["name"] for p in packages], edges)
        basis = "packages nothing else depends on (approximate: no Cargo.toml was found next to it)"
    base["packages"] = packages
    base["edges"] = edges
    base["roots"] = {"production": prod, "development": sorted(set(dev) - set(prod))}
    base["direct_basis"] = basis
    return base


# ---------------------------------------------------------------- shared

def _json_or_empty(text: str) -> dict:
    try:
        doc = json.loads(text or "{}")
    except (ValueError, TypeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _dedupe(packages: list) -> list:
    """One row per name and version. A lockfile can pin two versions of one package; both stay."""
    seen = {}
    for p in packages:
        key = (p.get("name") or "", p.get("version") or "")
        if key not in seen:
            seen[key] = p
        elif p.get("scope_hint") == "production":
            seen[key] = p
    return [seen[k] for k in sorted(seen)]
