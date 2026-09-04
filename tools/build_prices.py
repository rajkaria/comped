#!/usr/bin/env python3
"""Build resources/prices.json from the LiteLLM price table. Run by a human, never by a Play."""
import json, sys, hashlib, datetime, ssl, urllib.request, pathlib, re

SRC = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
# Fallback CA bundles for interpreters installed without root certificates (common on macOS).
CA_FALLBACKS = ["/etc/ssl/cert.pem", "/usr/local/etc/openssl@3/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem"]
# Normalised ids we always keep, even if unseen in fixtures. An id absent upstream (e.g. gpt-5.5-codex,
# gemini-3-*, kimi-k2, qwen3-coder, which upstream only ships as previews or provider-prefixed keys)
# simply does not appear in the snapshot: unpriced models are reported, never estimated.
ALLOW = [
    "claude-fable-5-1", "claude-fable-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5",
    "claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-6", "claude-opus-4-5", "claude-opus-4-1", "claude-sonnet-4-5",
    "gpt-5.6", "gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.2", "gpt-5.2-pro",
    "gpt-5.1", "gpt-5.5-codex", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.1-codex", "gpt-5.1-codex-max", "gpt-5.1-codex-mini",
    "gpt-5-codex", "codex-mini-latest", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o3", "o4-mini",
    "gemini-3-pro", "gemini-3-flash", "gemini-2.5-pro", "gemini-2.5-flash",
    "deepseek-chat", "deepseek-reasoner", "kimi-k2", "grok-4", "mistral-large-latest", "qwen3-coder",
]
PREFIXES = ["global.anthropic.", "us.anthropic.", "eu.anthropic.", "au.anthropic.", "jp.anthropic.", "apac.anthropic.",
            "anthropic.", "openrouter/openai/", "openrouter/anthropic/", "azure_ai/", "azure/us/", "azure/eu/", "azure/",
            "openai/", "anthropic/", "bedrock/", "vertex_ai/", "gemini/", "deepseek/", "moonshot/", "xai/", "mistral/"]
DATE = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")


def normalise(k):
    for p in sorted(PREFIXES, key=len, reverse=True):
        if k.startswith(p):
            k = k[len(p):]
            break
    k = re.sub(r"-v\d+:\d+$", "", k)
    return DATE.sub("", k)


def fetch(url):
    """Download the upstream table, falling back to a system CA bundle if the default store is empty."""
    try:
        return urllib.request.urlopen(url, timeout=60).read()
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e.reason):
            raise
    for ca in CA_FALLBACKS:
        if pathlib.Path(ca).exists():
            ctx = ssl.create_default_context(cafile=ca)
            return urllib.request.urlopen(url, timeout=60, context=ctx).read()
    raise SystemExit("no usable CA bundle; install certificates or pass one via SSL_CERT_FILE")


def main(out="resources/prices.json"):
    raw = fetch(SRC)
    sha = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    models = {}
    for key, e in data.items():
        if not isinstance(e, dict) or "input_cost_per_token" not in e:
            continue
        n = normalise(key)
        if n not in ALLOW:
            continue
        rec = {"in": repr(e.get("input_cost_per_token") or 0), "out": repr(e.get("output_cost_per_token") or 0),
               "cache_write": repr(e.get("cache_creation_input_token_cost") or 0),
               "cache_read": repr(e.get("cache_read_input_token_cost") or 0), "from_key": key}
        # prefer the unprefixed key when several map to the same normalised id
        if n not in models or key == n or ("/" not in key and "." not in key.split("-")[0]):
            models[n] = rec
    doc = {"meta": {"source_url": SRC, "upstream_sha": sha, "as_of": datetime.date.today().isoformat(),
                    "generated_by": "tools/build_prices.py", "unit": "USD per token",
                    "note": "List prices. Not a bill. Unknown models are never estimated."},
           "models": dict(sorted(models.items()))}
    pathlib.Path(out).write_text(json.dumps(doc, indent=1) + "\n")
    print("wrote {0}: {1} models, sha {2}".format(out, len(models), sha[:12]))


if __name__ == "__main__":
    main(*sys.argv[1:])
