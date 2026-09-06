"""The only module in this package that may start a git process, and the rules it keeps.

Three of the Plays here answer questions only git can answer: who is the sole author of a file,
when a commit was really made, which lines an agent wrote that are still alive. None of those are
reasonably reimplementable against the object store in the standard library, so this module shells
out — and the whole cost of that decision is paid here, once, under four rules:

1. The binary is an absolute path from a fixed list. PATH is never searched, because a PATH search
   is the thing a shell injection looks like from the outside.
2. The subcommand must appear in ALLOWED, which contains only read-only subcommands. There is no
   escape hatch and no caller-supplied subcommand.
3. `shell` is never set, argv is always a list, and every element is a string this module built or
   a path the caller passed as a path.
4. A git that is missing, too old, or angry is a labelled unknown, never an exception. Callers get
   `Git.ok is False` and a reason they can print.

Author identity uses `%aN`/`%aE` rather than `%an`/`%ae` throughout: the capitalized forms are the
ones git resolves through `.mailmap`, so a repository that has already done the work of mapping
three addresses to one human gets that for free and never has it second-guessed here.
"""
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .common import Budget, expand

GIT_CANDIDATES = ("/usr/bin/git", "/usr/local/bin/git", "/opt/homebrew/bin/git")

# Read-only subcommands only. Nothing here can write an object, move a ref, or touch the index.
ALLOWED = frozenset(
    ("log", "blame", "rev-parse", "cat-file", "ls-files", "for-each-ref", "rev-list", "config"))

# `config` is the one subcommand with a writing form, so it is additionally pinned to --get.
CONFIG_READ_ONLY = ("--get", "--get-all", "--list")

_SHA = re.compile(r"^[0-9a-f]{7,40}$")


class GitUnavailable(Exception):
    """Raised inside this module only; every public entry point converts it to a labelled miss."""


@dataclass
class Git:
    """A bound git binary, or a labelled reason there isn't one."""
    binary: str = ""
    ok: bool = False
    note: str = ""

    @classmethod
    def find(cls) -> "Git":
        for candidate in GIT_CANDIDATES:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return cls(binary=candidate, ok=True)
        return cls(note="git was not found at any of {0}".format(", ".join(GIT_CANDIDATES)))

    def run(self, repo, argv, timeout: float = 20.0, max_bytes: int = 64 * 1024 * 1024) -> str:
        """Run one allowlisted read-only git subcommand in `repo`. Returns stdout, or "" on any failure.

        Never raises for a git-level problem: a broken repository, a missing object and a git that
        exits non-zero are all the same thing to a caller that wants an answer or a labelled gap.
        """
        if not self.ok:
            return ""
        if not argv or argv[0] not in ALLOWED:
            raise ValueError("subcommand {0!r} is not in the read-only allowlist".format(
                argv[0] if argv else None))
        if argv[0] == "config" and not any(a in CONFIG_READ_ONLY for a in argv[1:]):
            raise ValueError("config is permitted only in its reading form")
        command = [self.binary, "-C", str(repo), "--no-pager"] + [str(a) for a in argv]
        try:
            done = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError):
            return ""
        if done.returncode != 0:
            return ""
        return done.stdout[:max_bytes].decode("utf-8", "replace")


# ---------------------------------------------------------------- repositories

@dataclass
class Repo:
    """One git repository on disk, with the few facts every Play here needs about it."""
    path: Path
    name: str = ""
    head: str = ""
    shallow: bool = False
    bare: bool = False
    note: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.head)


def describe(git: Git, path) -> Repo:
    """Read the handful of facts that decide whether a repository can answer anything."""
    path = expand(path)
    repo = Repo(path=path, name=path.name)
    head = git.run(path, ["rev-parse", "HEAD"]).strip()
    if not _SHA.match(head or ""):
        repo.note = "no commits, or not a repository"
        return repo
    repo.head = head
    repo.shallow = git.run(path, ["rev-parse", "--is-shallow-repository"]).strip() == "true"
    repo.bare = git.run(path, ["rev-parse", "--is-bare-repository"]).strip() == "true"
    if repo.shallow:
        repo.note = "shallow clone: history is truncated, every count is a lower bound"
    return repo


def discover(root, budget: Budget, max_repos: int = 400) -> list:
    """Find every git repository under `root`, bounded, without descending into one that is found.

    A repository's own contents are never walked: the moment a `.git` is seen the subtree stops
    being interesting to this walk, which is what keeps a home directory full of node_modules from
    costing anything.
    """
    root = expand(root)
    found, skip = [], {"node_modules", ".venv", "venv", "Library", ".Trash", ".cache", "vendor",
                       "target", "build", "dist", "__pycache__", ".next", "DerivedData"}
    if not root.is_dir():
        return found
    stack = [(root, 0)]
    while stack and len(found) < max_repos:
        current, depth = stack.pop()
        if depth > budget.max_depth or budget.hit:
            continue
        try:
            entries = list(os.scandir(current))
        except (OSError, PermissionError):
            continue
        if any(e.name == ".git" for e in entries):
            found.append(Path(current))
            continue                                    # a repo is a leaf for this walk
        for entry in entries:
            if not budget.spend():
                break
            try:
                if entry.is_dir(follow_symlinks=False) and entry.name not in skip \
                        and not entry.name.startswith("."):
                    stack.append((Path(entry.path), depth + 1))
            except OSError:
                continue
    return sorted(found)


# ---------------------------------------------------------------- identity

_NOREPLY = re.compile(r"^(?:\d+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$", re.I)
_BOT = re.compile(r"\[bot\]|^(?:dependabot|renovate|github-actions|greenkeeper)\b", re.I)


@dataclass
class Identity:
    """One human, however many addresses they have committed under."""
    key: str
    names: set = field(default_factory=set)
    emails: set = field(default_factory=set)

    @property
    def display(self) -> str:
        return sorted(self.names)[0] if self.names else self.key

    @property
    def is_bot(self) -> bool:
        return bool(_BOT.search(self.display) or any(_BOT.search(e) for e in self.emails))


def identity_key(name: str, email: str) -> str:
    """The stable key two commits by the same human share.

    Order matters. A GitHub noreply address names the account outright and is the strongest signal
    available, so it wins. Otherwise the email is the identity, lowercased, with the plus-tag cut —
    `me+github@x.com` and `me@x.com` are one person. A commit with no email at all falls back to the
    name, which is weak but better than inventing a second human.
    """
    email = (email or "").strip().lower()
    match = _NOREPLY.match(email)
    if match:
        return "gh:" + match.group(1).lower()
    if email:
        local, _, domain = email.partition("@")
        local = local.split("+", 1)[0]
        return "{0}@{1}".format(local, domain) if domain else local
    return "name:" + (name or "").strip().lower()


def coalesce(pairs) -> dict:
    """Merge (name, email) pairs into identities, then merge identities that share a display name.

    The second pass is what catches the same person committing from a work laptop and a personal
    one under two unrelated addresses: git's own `.mailmap` handles it when a repository has one
    (which is why `%aN`/`%aE` are used everywhere), and this catches the common case where nobody
    has ever written a mailmap.
    """
    by_key = {}
    for name, email in pairs:
        key = identity_key(name, email)
        identity = by_key.setdefault(key, Identity(key=key))
        if name:
            identity.names.add(name.strip())
        if email:
            identity.emails.add(email.strip().lower())

    by_name, merged = {}, {}
    for key in sorted(by_key):
        identity = by_key[key]
        anchor = None
        for name in identity.names:
            anchor = by_name.get(name.strip().lower())
            if anchor:
                break
        if anchor is None:
            merged[key] = identity
            for name in identity.names:
                by_name[name.strip().lower()] = key
        else:
            merged[anchor].names |= identity.names
            merged[anchor].emails |= identity.emails
            for name in identity.names:
                by_name.setdefault(name.strip().lower(), anchor)
    return merged


def own_identities(git: Git, repos, configured=()) -> set:
    """The keys that mean "you": whatever `user.email` says, plus anything the caller passed."""
    keys = {identity_key("", e) for e in configured if e}
    for repo in repos:
        email = git.run(repo, ["config", "--get", "user.email"]).strip()
        name = git.run(repo, ["config", "--get", "user.name"]).strip()
        if email or name:
            keys.add(identity_key(name, email))
    return {k for k in keys if k and not k.startswith("name:")} or keys
