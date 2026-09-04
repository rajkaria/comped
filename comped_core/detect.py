"""Work out which AI you are running, from the logs themselves.

Nothing on this machine writes down which subscription you pay for -- not the session logs, not
the harness config -- and the one place it is written is a file this tool refuses to open. So it
is inferred instead of asked for: the model ids the harnesses already recorded name the providers
behind them, and every subscription those providers sell is priced at once, so you read your own
row off a ladder instead of typing an answer the tool could have worked out.

Detection reads nothing new. It looks at records the ledger already parsed and at which of the
configured log directories existed. A model nobody recognises is reported by name as unknown,
never assigned to a provider by guess.
"""
import re
from typing import Dict, List, Optional

# (key, label, what to call the thing you talk to, model-id pattern, plan ids in plans.json).
# Ordered: the first pattern that matches wins, so put the specific ones first.
PROVIDERS = [
    ("anthropic", "Anthropic", "Claude", r"^(claude|anthropic)", ["claude-pro-20", "claude-max-100", "claude-max-200"]),
    ("openai", "OpenAI", "GPT / Codex", r"^(gpt|o1|o3|o4|o5|codex|chatgpt|davinci)", ["chatgpt-plus-20", "chatgpt-pro-200"]),
    ("moonshot", "Moonshot", "Kimi", r"^(kimi|moonshot)", []),
    ("zai", "Z.ai", "GLM", r"^(glm|zai|zhipu|chatglm)", []),
    ("deepseek", "DeepSeek", "DeepSeek", r"^deepseek", []),
    ("google", "Google", "Gemini", r"^(gemini|gemma|palm|bison)", []),
    ("xai", "xAI", "Grok", r"^grok", []),
    ("alibaba", "Alibaba", "Qwen", r"^(qwen|qwq)", []),
    ("minimax", "MiniMax", "MiniMax", r"^minimax", []),
    ("mistral", "Mistral", "Mistral", r"^(mistral|codestral|devstral|magistral|ministral|pixtral)", []),
    ("meta", "Meta", "Llama", r"^(llama|meta-llama)", []),
    ("amazon", "Amazon", "Nova", r"^(nova-|titan)", []),
    ("cohere", "Cohere", "Command", r"^command", []),
]
UNKNOWN = ("unknown", "Unknown", "an unrecognised model", [])

# What the harness is called in prose, and which provider it talks to unless a model id says
# otherwise. The default is only a fallback for a window with no usage records in it at all.
HARNESSES = {
    "claude-code": ("Claude Code", "anthropic"),
    "codex": ("Codex CLI", "openai"),
    "pi": ("Pi", "anthropic"),
    "opencode": ("OpenCode", ""),
}

_RE = [(key, label, talk, re.compile(pat, re.I), plans) for key, label, talk, pat, plans in PROVIDERS]
# Gateway and region prefixes are routing, not identity: bedrock/, us.anthropic., openrouter/z-ai/
# all describe where the call went, not who made the model. Strip them before asking.
_SLASH = re.compile(r"^(?:[a-z0-9_.-]+/)+", re.I)
_DOTTED = re.compile(r"^(?:[a-z]{2,6}\.)?(?:anthropic|moonshotai|moonshot|zai|zhipu|deepseek|minimax|qwen|xai|mistral|meta|cohere)\.", re.I)


def provider_of(model: str) -> tuple:
    """(key, label, what you call it, plan ids) for a model id as the harness wrote it."""
    raw = (model or "").strip()
    stripped = _DOTTED.sub("", _SLASH.sub("", raw))
    for cand in (stripped, raw):
        if not cand:
            continue
        for key, label, talk, rx, plans in _RE:
            if rx.search(cand):
                return key, label, talk, list(plans)
    return UNKNOWN[0], UNKNOWN[1], UNKNOWN[2], []


def _blank(model: str) -> str:
    return model or "(blank)"


def detect_stack(records, sources, table=None) -> dict:
    """Name the harnesses, providers and models behind a window of usage records.

    `table` is the price table, used only to mark a model priced or unpriced -- detection never
    needs a rate, and a model with no rate is still a detected model.
    """
    from .prices import resolve_model

    models: Dict[str, dict] = {}
    provs: Dict[str, dict] = {}
    per_harness: Dict[str, dict] = {}
    for r in records:
        name = _blank(r.model)
        key, label, talk, plans = provider_of(name)
        toks = r.input_tokens + r.cache_write_tokens + r.cache_read_tokens + r.output_tokens
        m = models.setdefault(name, {"model": name, "provider": key, "provider_label": label,
                                     "records": 0, "tokens": 0, "harnesses": [],
                                     "priced": bool(table) and resolve_model(name, table) is not None})
        m["records"] += 1
        m["tokens"] += toks
        if r.harness not in m["harnesses"]:
            m["harnesses"].append(r.harness)
        p = provs.setdefault(key, {"key": key, "label": label, "talk_to": talk, "plans": plans,
                                   "records": 0, "tokens": 0, "models": [], "harnesses": []})
        p["records"] += 1
        p["tokens"] += toks
        if name not in p["models"]:
            p["models"].append(name)
        if r.harness not in p["harnesses"]:
            p["harnesses"].append(r.harness)
        h = per_harness.setdefault(r.harness, {"records": 0, "sessions": set(), "models": []})
        h["records"] += 1
        h["sessions"].add(r.session_id)
        if name not in h["models"]:
            h["models"].append(name)

    harnesses = []
    for s in sources:
        label, default_vendor = HARNESSES.get(s.harness, (s.harness, ""))
        h = per_harness.get(s.harness, {"records": 0, "sessions": set(), "models": []})
        harnesses.append({"harness": s.harness, "label": label, "found": bool(s.found), "files": s.files,
                          "records": h["records"], "sessions": len(h["sessions"]), "models": sorted(h["models"]),
                          "default_provider": default_vendor, "note": s.note})

    # A harness whose directory exists but whose window is empty still says something about the
    # stack, so it seeds its default provider -- with no records behind it, and marked as such.
    if not provs:
        for h in harnesses:
            key = h["default_provider"]
            if h["found"] and key:
                _, label, talk, plans = _lookup(key)
                provs.setdefault(key, {"key": key, "label": label, "talk_to": talk, "plans": list(plans),
                                       "records": 0, "tokens": 0, "models": [], "harnesses": [h["harness"]]})

    basis = "models" if any(p["records"] for p in provs.values()) else ("harnesses" if provs else "nothing")
    return {"harnesses": harnesses,
            "providers": sorted(provs.values(), key=lambda p: (-p["records"], -p["tokens"], p["key"])),
            "models": sorted(models.values(), key=lambda m: (-m["tokens"], m["model"])),
            "basis": basis}


def _lookup(key: str) -> tuple:
    for k, label, talk, _pat, plans in PROVIDERS:
        if k == key:
            return k, label, talk, plans
    return UNKNOWN


def infer_plans(detected: dict, plans: dict) -> tuple:
    """(assumed plan ids, every candidate id, notes).

    The tier is the one thing the logs cannot tell you: a Pro session and a Max session are the
    same bytes. So the assumption is deliberately the least flattering one -- the most expensive
    plan the detected provider sells, which is the smallest multiplier you could honestly claim --
    and every other tier is priced beside it so a cheaper plan is one glance away, not a re-run.
    """
    known = plans.get("plans", {})

    def price(pid):
        e = known.get(pid) or {}
        return float(e["monthly_usd"]) if e.get("monthly_usd") is not None else -1.0

    assumed: List[str] = []
    candidates: List[str] = []
    notes: List[str] = []
    for p in detected["providers"]:
        usable = [pid for pid in p["plans"] if pid in known and known[pid].get("monthly_usd") is not None]
        if not usable:
            if p["key"] != UNKNOWN[0]:
                notes.append("{0} ({1}) has no subscription in the plan table: its spend is in the total, "
                             "and nothing in the plan cost covers it".format(p["label"], p["talk_to"]))
            continue
        for pid in sorted(usable, key=price):
            if pid not in candidates:
                candidates.append(pid)
        assumed.append(max(usable, key=price))
    if not assumed:
        notes.append("no subscription could be inferred; the card shows the list-price total only "
                     "(pass plan=<id> or plan=usd:<amount> for a multiplier)")
    return assumed, candidates, notes


def summary_line(detected: dict) -> str:
    """One line for the card: what it found, in the order it found it."""
    provs = [p for p in detected["providers"] if p["records"]] or detected["providers"]
    who = " · ".join("{0} {1}".format(p["talk_to"], _pct(p, detected)) for p in provs[:3]) or "nothing"
    where = ", ".join(h["label"] for h in detected["harnesses"] if h["found"]) or "no log directory"
    return "{0} via {1}".format(who, where)


def _pct(p: dict, detected: dict) -> str:
    total = sum(x["records"] for x in detected["providers"]) or 0
    return "{0}%".format(int(round(100.0 * p["records"] / total))) if total else ""


def attach_costs(detected: dict, per_model_usd: Dict[str, object], zero) -> dict:
    """Fold priced totals back in, so providers can be ranked by money rather than record count."""
    for m in detected["models"]:
        m["usd"] = per_model_usd.get(m["model"], zero)
    by_model = {m["model"]: m for m in detected["models"]}
    for p in detected["providers"]:
        p["usd"] = sum((by_model[n]["usd"] for n in p["models"] if n in by_model), zero)
    detected["providers"].sort(key=lambda p: (-float(p["usd"]), -p["records"], p["key"]))
    detected["models"].sort(key=lambda m: (-float(m["usd"]), -m["tokens"], m["model"]))
    return detected
