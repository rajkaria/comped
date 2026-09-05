#!/usr/bin/env python3
"""Run the site locally with the leaderboard API attached, the way Vercel serves it.

Serves site/ statically and routes /api/score and /api/leaderboard to the handler classes in
api/, so the board on the home page and leaderboard.html render against real storage.

    printf 'SUPABASE_URL=https://<ref>.supabase.co\nSUPABASE_KEY=sb_publishable_...\n' > .env.local
    python3 tools/devserver.py 8123

(.env.local is gitignored. `vercel env pull` writes "[SENSITIVE]" for these two, so write them by
hand; the key is the publishable one, which the SQL functions treat as anonymous anyway.)

Without the two variables the pages still serve; the API answers 502 and the board shows its
empty state, which is also worth seeing.
"""
import os
import pathlib
import ssl
import sys
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))


def load_env(path: pathlib.Path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env(ROOT / ".env.local")

# A python.org build on a Mac that never ran "Install Certificates" has no CA bundle; use the system one.
_real_urlopen = urllib.request.urlopen
_ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem") if os.path.exists("/etc/ssl/cert.pem") else None
urllib.request.urlopen = lambda req, timeout=None, **k: _real_urlopen(req, timeout=timeout, context=k.get("context", _ctx))

import leaderboard  # noqa: E402
import score  # noqa: E402

ROUTES = {"/api/score": score.handler, "/api/leaderboard": leaderboard.handler}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT / "site"), **k)

    def _api(self):
        return ROUTES.get(self.path.split("?", 1)[0])

    def do_GET(self):
        h = self._api()
        return h.do_GET(self) if h else super().do_GET()

    def do_POST(self):
        h = self._api()
        return h.do_POST(self) if h else self.send_error(404)

    def do_OPTIONS(self):
        h = self._api()
        return h.do_OPTIONS(self) if h else self.send_error(404)

    def log_message(self, fmt, *args):
        pass


def main(argv):
    port = int(argv[1]) if len(argv) > 1 else 8123
    print("comped site + API on http://127.0.0.1:{0}  (storage {1})".format(
        port, "configured" if os.environ.get("SUPABASE_URL") else "NOT configured: API answers 502"), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(sys.argv)
