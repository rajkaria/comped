#!/bin/sh
# comped -- your comp score in one paste.            https://gotcomped.com
#
# What this does, in order:
#   1. Checks for python3 (3.9+). comped is standard-library Python; nothing is pip-installed.
#   2. Installs rote, the free runner from Modiqo (https://rote.dev), only if it is missing.
#      That is the same installer as https://getrote.dev/install, run non-interactively.
#   3. Signs you in to the rote registry if you are not already (that is rote's login,
#      on your terminal; comped itself never signs in to anything).
#   4. Runs the comped Play from the registry with --yes, so the "Ready?" selector is skipped.
#      rote still prints the Play's parameters and access before it runs. The Play reads your
#      agent logs, writes ~/comped, and then posts just your score to the gotcomped.com
#      leaderboard under your rote handle (the one network call it makes; the payload is saved
#      to ~/comped/comped-rank.json so you can read it).
#
# Read it before you run it; it is short. Anything after the URL is passed to the Play, e.g.
#   curl -fsSL https://gotcomped.com/run.sh | sh -s -- plan=claude-pro-20
#   ... | sh -s -- leaderboard=false        the card only; then the run makes no network call at all
#
set -e

PLAY="https://play.modiqo.ai/rajkaria/comped"
say() { printf '%s\n' "$*" >&2; }

command -v python3 >/dev/null 2>&1 || {
  say "comped needs python3 (3.9 or newer). Install it, then paste the line again."; exit 1; }

# rote goes to ~/.local/bin; a fresh install is not on PATH until the next shell opens.
PATH="$HOME/.local/bin:$PATH"
if ! command -v rote >/dev/null 2>&1; then
  say "→ rote is not installed. Installing it (about a minute)…"
  curl -fsSL --proto '=https' --proto-redir '=https' https://getrote.dev/install | ROTE_YES=1 bash
  PATH="$HOME/.local/bin:$PATH"
fi
command -v rote >/dev/null 2>&1 || {
  say "rote did not land on PATH. Open a new terminal window and paste the line again."; exit 1; }

# Prompts read from the terminal even though this script arrived through a pipe.
if [ -c /dev/tty ] && ( : <>/dev/tty ) 2>/dev/null; then
  TTY=/dev/tty
else
  TTY=""
fi

if ! rote whoami --check >/dev/null 2>&1; then
  if [ -n "$TTY" ]; then
    say "→ rote needs you signed in to fetch the Play. Opening sign-in…"
    rote login <"$TTY"
  else
    say "Not signed in and no terminal to sign in on. Run: rote login"; exit 1
  fi
fi

# Your rote handle is your name on the leaderboard. Passed only if you did not set handle= yourself.
HANDLE_ARG=""
case " $* " in
  *" handle="*) ;;
  *) H=$(rote whoami 2>/dev/null | sed -n 's/^handle: *//p' | head -n 1)
     [ -n "$H" ] && HANDLE_ARG="handle=$H" ;;
esac

say "→ reading your agent logs on this machine. The logs stay here; only your score is posted."
if [ -n "$TTY" ]; then
  rote play run "$PLAY" --yes $HANDLE_ARG "$@" <"$TTY"
else
  rote play run "$PLAY" --yes $HANDLE_ARG "$@"
fi

say ""
say "Your card: ~/comped/comped-card.png   Your post: ~/comped/comped-share.txt"
say "Your rank: https://gotcomped.com/leaderboard.html${H:+#$H}"
say "Post it. Everyone thinks theirs is the bad one."
