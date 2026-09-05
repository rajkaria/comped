#!/bin/sh
# comped -- your comp score in one paste. No account, no runner, nothing installed.
#                                                        https://gotcomped.com
# What this does, in order:
#   1. Checks for python3 (3.9+). comped is standard-library Python; nothing is pip-installed.
#   2. Downloads https://gotcomped.com/comped.tar.gz, about 150 KB, into a temporary directory,
#      and checks it against the published sha256 if this machine has a checksum tool.
#   3. Runs it. It reads your agent logs, writes ~/comped, and posts just your score to the
#      gotcomped.com leaderboard. That is the only network call it makes, the exact payload is
#      saved to ~/comped/comped-rank.json, and leaderboard=false turns it off.
#   4. Deletes the temporary directory. Nothing is left on your machine but ~/comped.
#
# Want to watch it work on invented logs before pointing it at your own? The sample ones travel
# in the download:
#   curl -fsSL https://gotcomped.com/comped.sh | sh -s -- \
#     claude_dir=resources/fixtures/claude codex_dir=resources/fixtures/codex leaderboard=false
#
# Read it before you run it; it is short. Anything after sh -s -- is passed straight through:
#   curl -fsSL https://gotcomped.com/comped.sh | sh -s -- plan=claude-pro-20
#   curl -fsSL https://gotcomped.com/comped.sh | sh -s -- handle=yourname
#   curl -fsSL https://gotcomped.com/comped.sh | sh -s -- leaderboard=false
#
# Prefer to run it as an inspectable rote Play instead, with a consent screen and a public
# archive you can read first? That is https://gotcomped.com/run.sh -- it needs a free account.
set -e

BASE="${COMPED_BASE_URL:-https://gotcomped.com}"
say() { printf '%s\n' "$*" >&2; }
die() { say "$*"; exit 1; }

# python3 first; some minimal images ship only `python`, which may still be a modern 3.
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || die "comped needs python3 (3.9 or newer). Install it, then paste the line again.
  macOS:  it is already there; try opening a new Terminal window.
  Ubuntu: sudo apt install python3
  Fedora: sudo dnf install python3"

command -v curl >/dev/null 2>&1 || die "comped needs curl to download itself."

TMP=$(mktemp -d "${TMPDIR:-/tmp}/comped.XXXXXX") || die "could not make a temporary directory."
# Leave nothing behind, however this exits.
trap 'rm -rf "$TMP"' EXIT INT TERM

# The published origin is https and stays https through any redirect. Only a COMPED_BASE_URL the
# caller set themselves, for local development, is allowed to be anything else.
case "$BASE" in
  https://*) PROTO="--proto =https --proto-redir =https" ;;
  *)         PROTO="" ;;
esac

say "→ Fetching comped (about 150 KB)…"
# shellcheck disable=SC2086
curl -fsSL $PROTO "$BASE/comped.tar.gz" -o "$TMP/comped.tar.gz" \
  || die "could not download $BASE/comped.tar.gz. Are you online?"

# The checksum is served from the same origin, so it proves the download arrived whole, not that
# the origin is honest. For that, read the source: https://github.com/rajkaria/comped
SUM=""
if command -v shasum >/dev/null 2>&1; then SUM="shasum -a 256"
elif command -v sha256sum >/dev/null 2>&1; then SUM="sha256sum"
fi
# shellcheck disable=SC2086
if [ -n "$SUM" ] && curl -fsSL $PROTO "$BASE/comped.tar.gz.sha256" -o "$TMP/sum" 2>/dev/null; then
  WANT=$(cut -d' ' -f1 <"$TMP/sum")
  GOT=$($SUM "$TMP/comped.tar.gz" | cut -d' ' -f1)
  [ "$WANT" = "$GOT" ] || die "the download did not match its published checksum; nothing was run.
  expected $WANT
  got      $GOT"
fi

tar -xzf "$TMP/comped.tar.gz" -C "$TMP" || die "could not unpack the download."
[ -f "$TMP/comped/comped.py" ] || die "the download is missing comped.py; nothing was run."

# Not exec: exec replaces this shell and the EXIT trap never runs, which would leave the
# temporary directory behind. Run it, keep its exit code, let the trap clean up.
set +e
"$PY" "$TMP/comped/comped.py" "$@"
RC=$?
set -e
exit "$RC"
