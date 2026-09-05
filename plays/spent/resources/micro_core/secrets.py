"""Read it before the agent does.

Precision is the whole product. A scanner that flags `API_KEY=your-key-here` gets turned off within
a day, and then it is not protecting anything — so every rule here is a literal shape with its own
test, the entropy rule carries a floor AND a placeholder list, and a documented example key
(AWS's own AKIAIOSFODNN7EXAMPLE, Stripe's sk_test_) is deliberately not a finding.
"""
import math
import re
from dataclasses import dataclass

PLACEHOLDERS = ("changeme", "change_me", "your-key-here", "your_key_here", "yourkey", "example",
                "xxxxx", "placeholder", "redacted", "dummy", "test", "sample", "todo", "none",
                "secret", "password", "hunter2", "abc123", "foobar", "notreal", "fake")
EXAMPLES = ("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
KEYNAME = re.compile(r"(?i)\b([\w.\-]*(?:secret|token|passwd|password|api[_-]?key|access[_-]?key|"
                     r"private[_-]?key|client[_-]?secret|auth)[\w.\-]*)\s*[:=]\s*[\"']?([^\s\"',;]{8,})")

# Each rule is a literal shape, named, with the severity it earns. No catch-all regex lives here.
RULES = (
    ("aws-access-key", "blocker", re.compile(r"\b((?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA)[0-9A-Z]{16})\b"),
     "an AWS access key id"),
    ("github-token", "blocker", re.compile(r"\b((?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
     "a GitHub token"),
    ("slack-token", "blocker", re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"), "a Slack token"),
    ("stripe-key", "blocker", re.compile(r"\b((?:sk|rk)_live_[A-Za-z0-9]{16,})\b"), "a live Stripe key"),
    ("google-api-key", "blocker", re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b"), "a Google API key"),
    ("anthropic-key", "blocker", re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{20,})\b"), "an Anthropic API key"),
    ("openai-key", "blocker", re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9]{32,})\b"), "an OpenAI API key"),
    ("twilio-key", "blocker", re.compile(r"\b(SK[0-9a-f]{32})\b"), "a Twilio key"),
    ("sendgrid-key", "blocker", re.compile(r"\b(SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,})\b"),
     "a SendGrid key"),
    ("npm-token", "blocker", re.compile(r"\b(npm_[A-Za-z0-9]{36})\b"), "an npm token"),
    ("pypi-token", "blocker", re.compile(r"\b(pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{16,})\b"), "a PyPI token"),
    ("private-key", "blocker",
     re.compile(r"(-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)"), "a private key block"),
    ("ssh-public-key", "medium", re.compile(r"\b(ssh-(?:rsa|ed25519|dss) [A-Za-z0-9+/]{40,}={0,2})"),
     "an SSH public key — harmless alone, but it names a machine"),
    ("jwt", "high", re.compile(r"\b(eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})\b"),
     "a JWT, which may still be valid"),
    ("connection-string", "blocker",
     re.compile(r"\b((?:postgres|postgresql|mysql|mongodb|redis|amqp|https?)://[^\s:@/]+:[^\s:@/]+@[^\s]+)"),
     "a connection string carrying a password"),
)


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str
    line: int
    col: int
    masked: str
    why: str
    start: int = 0
    end: int = 0


def entropy(s):
    """Shannon entropy in bits per character. Repetition scores near zero; randomness near 5."""
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = float(len(s))
    return -sum((c / n) * math.log(c / n, 2) for c in counts.values())


def _placeholder(value):
    low = value.strip().strip("\"'").lower()
    if not low or low in ("null", "none", "true", "false"):
        return True
    if low.startswith("${") or low.startswith("$") or low.startswith("<") or low.startswith("{{"):
        return True
    if len(set(low)) <= 2:
        return True
    return any(word in low for word in PLACEHOLDERS)


def _mask(value):
    """Enough to recognise it in your own file, never enough to use."""
    v = str(value)
    if len(v) <= 8:
        return v[:2] + "…"
    return "{0}…{1} ({2} chars)".format(v[:4], v[-2:], len(v))


def _at(text, index):
    before = text[:index]
    line = before.count("\n") + 1
    return line, index - (before.rfind("\n") + 1)


def scan(text, strict=True):
    """Every finding, sorted by position. Overlapping matches keep the more severe one."""
    body = str(text or "")
    found = []
    for kind, severity, pattern, why in RULES:
        for m in pattern.finditer(body):
            value = m.group(1)
            if any(ex in value for ex in EXAMPLES) or value.startswith("sk_test_"):
                continue
            if kind not in ("private-key", "connection-string") and _placeholder(value):
                continue
            line, col = _at(body, m.start(1))
            found.append(Finding(kind, severity, line, col, _mask(value), why, m.start(1), m.end(1)))
    if strict:
        for m in KEYNAME.finditer(body):
            name, value = m.group(1), m.group(2)
            if _placeholder(value) or len(value) < 12 or entropy(value) < 3.5:
                continue
            start = m.start(2)
            if any(f.start <= start < f.end for f in found):
                continue
            line, col = _at(body, start)
            found.append(Finding("high-entropy-value", "medium", line, col, _mask(value),
                                 "{0} holds {1:.1f} bits per character of randomness — that is a key, "
                                 "not a setting".format(name, entropy(value)), start, m.end(2)))
    ranked = {"blocker": 0, "high": 1, "medium": 2}
    found.sort(key=lambda f: (f.start, ranked.get(f.severity, 9)))
    kept = []
    for f in found:
        if kept and f.start < kept[-1].end:
            continue                       # an inner match of an outer one: report it once
        kept.append(f)
    return kept


def redact(text, findings):
    """Right to left, so an earlier span's offsets stay true after a later one is replaced."""
    body = str(text or "")
    for f in sorted(findings, key=lambda f: f.start, reverse=True):
        body = body[:f.start] + "<REDACTED:{0}>".format(f.kind) + body[f.end:]
    return body


def verdict(findings):
    if any(f.severity == "blocker" for f in findings):
        return "do-not-paste"
    return "redact" if findings else "safe"


def counts(findings):
    out = {}
    for f in findings:
        out[f.kind] = out.get(f.kind, 0) + 1
    return out
