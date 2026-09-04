import json, re
from decimal import Decimal
from pathlib import Path
from typing import Optional


def _bundled(name: str) -> Path:
    """Repo layout: comped_core/../resources/<name>. Play layout: resources/comped_core/../<name>. First existing wins."""
    here = Path(__file__).resolve().parent.parent
    for cand in (here / "resources" / name, here / name):
        if cand.exists():
            return cand
    return here / "resources" / name


BUNDLED = _bundled("prices.json")
PREFIXES = sorted(["global.anthropic.", "us.anthropic.", "eu.anthropic.", "au.anthropic.", "jp.anthropic.", "apac.anthropic.",
                   "anthropic.", "openrouter/openai/", "openrouter/anthropic/", "azure_ai/", "azure/us/", "azure/eu/", "azure/",
                   "openai/", "anthropic/", "bedrock/", "vertex_ai/", "gemini/", "deepseek/", "moonshot/", "xai/", "mistral/"],
                  key=len, reverse=True)
_DATE = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8})$")
_VER = re.compile(r"-v\d+:\d+$")


def load_table(path: Optional[Path] = None) -> dict:
    p = Path(path) if path else BUNDLED
    doc = json.loads(p.read_text(encoding="utf-8"))
    models = {}
    for k, v in doc.get("models", {}).items():
        models[k] = {f: Decimal(str(v.get(f, "0") or "0")) for f in ("in", "out", "cache_write", "cache_read")}
    return {"meta": doc.get("meta", {}), "models": models, "path": str(p)}


def _candidates(model: str):
    yield model
    m = model
    for p in PREFIXES:
        if m.startswith(p):
            m = m[len(p):]
            yield m
            break
    m2 = _VER.sub("", m)
    if m2 != m:
        yield m2
    m3 = _DATE.sub("", m2)
    if m3 != m2:
        yield m3


def resolve_model(model: str, table: dict) -> Optional[str]:
    if not model or not isinstance(model, str):
        return None
    for c in _candidates(model.strip()):
        if c in table["models"]:
            return c
    return None


def rate_for(model: str, table: dict) -> Optional[dict]:
    k = resolve_model(model, table)
    return table["models"][k] if k else None
