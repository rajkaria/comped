"""What is this string, and what is inside it.

Two rules keep the answers honest. The detectors run most-constrained first, so a forty-character
git object id is a hash before it is ever offered to the base64 reader. And a guess is labelled a
guess: a ten-digit integer is a plausible epoch AND a plausible number, and the output says which
reading was taken and why rather than quietly picking one.
"""
import base64
import binascii
import gzip
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

# urllib.parse would do the percent-decoding and the URL split, and it cannot open a socket. It is
# still not imported: "micro_core imports no urllib, http, socket or subprocess" is a claim anyone
# can check with grep in one second, and a claim that needs an exception is worth less than the
# forty lines below.
URL = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<netloc>[^/?#]*)"
                 r"(?P<path>[^?#]*)(?:\?(?P<query>[^#]*))?(?:#(?P<fragment>.*))?$")
PCT = re.compile(r"%([0-9A-Fa-f]{2})")


def unquote(s, plus=False):
    """Percent-decoding, UTF-8, byte-wise so a multi-byte sequence survives."""
    text = str(s).replace("+", " ") if plus else str(s)
    out, i = bytearray(), 0
    while i < len(text):
        m = PCT.match(text, i)
        if m:
            out.append(int(m.group(1), 16))
            i = m.end()
        else:
            out.extend(text[i].encode("utf-8"))
            i += 1
    return out.decode("utf-8", "replace")


class _Split(object):
    """The five pieces of a URL, named as urlsplit names them, and nothing else."""

    def __init__(self, m):
        self.scheme = (m.group("scheme") or "").lower() if m else ""
        netloc = m.group("netloc") if m else ""
        self.path = (m.group("path") or "") if m else ""
        self.query = (m.group("query") or "") if m else ""
        self.fragment = (m.group("fragment") or "") if m else ""
        self.netloc = netloc or ""
        creds, _, host = netloc.rpartition("@") if netloc else ("", "", "")
        self.username, _, self.password = creds.partition(":") if creds else ("", "", "")
        if host.startswith("["):                      # an IPv6 literal keeps its brackets
            hostname, _, rest = host[1:].partition("]")
            port = rest.lstrip(":")
        else:
            hostname, _, port = host.partition(":")
        self.hostname = hostname.lower() or None
        self.port = int(port) if port.isdigit() else None


def urlsplit(s):
    return _Split(URL.match(str(s)))


def parse_qsl(query):
    out = []
    for pair in str(query or "").split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        out.append((unquote(key, plus=True), unquote(value, plus=True)))
    return out

MAGIC = ((b"\x1f\x8b", "gzip"), (b"%PDF", "PDF"), (b"\x89PNG", "PNG"), (b"PK\x03\x04", "ZIP"),
         (b"\xff\xd8\xff", "JPEG"), (b"GIF8", "GIF"), (b"BZh", "bzip2"), (b"\xfd7zXZ", "xz"),
         (b"OggS", "Ogg"), (b"\x00\x00\x00\x1cftyp", "MP4"), (b"SQLite format 3", "SQLite"))
HASHES = {32: ["md5"], 40: ["sha1"], 56: ["sha224"], 64: ["sha256"], 96: ["sha384"], 128: ["sha512"]}
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RE = {
    "uuid": re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
    "ulid": re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$"),
    "mac": re.compile(r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$"),
    "semver": re.compile(r"^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"),
    "color": re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"),
    "hex": re.compile(r"^(?:0x)?[0-9a-fA-F]+$"),
    "digits": re.compile(r"^-?\d+$"),
    "b64": re.compile(r"^[A-Za-z0-9+/]+={0,2}$"),
    "b64url": re.compile(r"^[A-Za-z0-9_-]+={0,2}$"),
    "jwt": re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)?$"),
    "cron": re.compile(r"^(?:@(?:yearly|annually|monthly|weekly|daily|midnight|hourly)|"
                       r"[\d*/,\-A-Za-z]+(?:\s+[\d*/,\-A-Za-z]+){4})$"),
    "iso": re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"),
}


@dataclass(frozen=True)
class Layer:
    kind: str
    label: str
    detail: dict = field(default_factory=dict)
    text: object = None          # the payload to look inside next, or None at a leaf


# ---------------------------------------------------------------- helpers

def _printable(b):
    try:
        s = b.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return None
    if not s:
        return None
    printable = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    return s if printable >= 0.9 * len(s) else None


def _magic(b):
    for sig, name in MAGIC:
        if b.startswith(sig):
            return name
    return None


def _when(seconds):
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _relative(ts, now=None):
    now = now or datetime.now(timezone.utc)
    delta = int((datetime.fromtimestamp(ts, timezone.utc) - now).total_seconds())
    word, n = ("expires in", delta) if delta >= 0 else ("expired", -delta)
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if n >= size:
            return "{0} {1}{2}{3}".format(word, n // size, unit, "" if delta >= 0 else " ago")
    return "{0} {1}s{2}".format(word, n, "" if delta >= 0 else " ago")


def _b64_decode(s, urlsafe):
    pad = "=" * (-len(s) % 4)
    try:
        return (base64.urlsafe_b64decode if urlsafe else base64.b64decode)(s + pad)
    except (binascii.Error, ValueError):
        return None


def _shape(value, depth=0):
    """A JSON document described by its shape, so a big payload is legible without being printed."""
    if isinstance(value, dict):
        if depth >= 2:
            return "{...}"
        return "{" + ", ".join("{0}: {1}".format(k, _shape(v, depth + 1)) for k, v in list(value.items())[:8]) + "}"
    if isinstance(value, list):
        return "[{0} × {1}]".format(len(value), _shape(value[0], depth + 1) if value else "empty")
    return type(value).__name__ if not isinstance(value, str) else "str"


# ---------------------------------------------------------------- detectors

def _try_data_uri(s):
    if not s.lower().startswith("data:"):
        return None
    head, _, payload = s[5:].partition(",")
    mime = head.split(";")[0] or "text/plain"
    is_b64 = head.lower().endswith(";base64")
    body = _b64_decode(payload, False) if is_b64 else unquote(payload).encode("utf-8")
    if body is None:
        return None
    return Layer("data-uri", "data URI, {0}, {1} bytes".format(mime, len(body)),
                 {"mime": mime, "base64": is_b64, "bytes": len(body)}, body)


def _try_jwt(s):
    parts = s.split(".")
    if len(parts) not in (2, 3) or not RE["jwt"].match(s):
        return None
    head = _b64_decode(parts[0], True)
    if head is None:
        return None
    try:
        header = json.loads(head.decode("utf-8"))
        claims = json.loads(_b64_decode(parts[1], True).decode("utf-8"))
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None
    if not isinstance(header, dict) or "alg" not in header or not isinstance(claims, dict):
        return None
    detail = {"alg": header.get("alg"), "typ": header.get("typ"), "claims": claims,
              "claim_names": sorted(claims)}
    for name in ("iat", "nbf", "exp"):
        if isinstance(claims.get(name), (int, float)):
            detail[name] = _when(claims[name])
            if name == "exp":
                detail["expiry"] = _relative(claims[name])
    if len(parts) == 3 and parts[2]:
        # The signature is the one part that is a secret in shape: never print it whole.
        detail["signature"] = "{0}… ({1} chars)".format(parts[2][:8], len(parts[2]))
    else:
        detail["signature"] = "none (unsigned)"
    return Layer("jwt", "JWT, {0}{1}".format(header.get("alg"),
                                             ", " + detail["expiry"] if "expiry" in detail else ""), detail)


def _try_uuid(s):
    if not RE["uuid"].match(s):
        return None
    hexed = s.replace("-", "")
    version = int(hexed[12], 16)
    detail = {"version": version, "variant": "RFC 4122" if hexed[16].lower() in "89ab" else "other"}
    if version == 1:
        ticks = int(hexed[13:16] + hexed[8:12] + hexed[0:8], 16)
        detail["time"] = _when(ticks / 1e7 - 12219292800)
    elif version == 7:
        detail["time"] = _when(int(hexed[:12], 16) / 1000.0)
    return Layer("uuid", "UUID v{0}{1}".format(version, ", " + detail["time"] if "time" in detail else ""), detail)


def _try_ulid(s):
    if not RE["ulid"].match(s):
        return None
    ms = 0
    for ch in s[:10]:
        ms = ms * 32 + CROCKFORD.index(ch)
    return Layer("ulid", "ULID, {0}".format(_when(ms / 1000.0)), {"time": _when(ms / 1000.0)})


def _try_net(s):
    import ipaddress
    try:
        net = ipaddress.ip_network(s, strict=False)
        if "/" in s:
            return Layer("cidr", "{0} network, {1} addresses".format(net.version and "IPv{0}".format(net.version),
                                                                     net.num_addresses),
                         {"version": net.version, "addresses": net.num_addresses,
                          "first": str(net[0]), "last": str(net[-1])})
    except ValueError:
        pass
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return None
    scope = "public"
    if ip.is_loopback:
        scope = "loopback"
    elif ip.is_private:
        scope = "private"
    elif ip.is_link_local:
        scope = "link-local"
    elif ip.version == 4 and ipaddress.ip_address("100.64.0.0") <= ip <= ipaddress.ip_address("100.127.255.255"):
        scope = "carrier-grade NAT"
    return Layer("ipv{0}".format(ip.version), "IPv{0} address, {1}".format(ip.version, scope),
                 {"scope": scope, "version": ip.version})


def _try_color(s):
    if not RE["color"].match(s):
        return None
    body = s[1:]
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    r, g, b = (int(body[i:i + 2], 16) for i in (0, 2, 4))
    mx, mn = max(r, g, b) / 255.0, min(r, g, b) / 255.0
    light = (mx + mn) / 2
    return Layer("color", "colour #{0}, rgb({1}, {2}, {3})".format(body[:6], r, g, b),
                 {"rgb": [r, g, b], "hex": "#" + body[:6],
                  "lightness": int(light * 100), "alpha": int(body[6:8], 16) if len(body) == 8 else None})


def _try_epoch(s):
    if not RE["digits"].match(s):
        return None
    n = int(s)
    for unit, divisor in (("s", 1), ("ms", 1000), ("µs", 1000000), ("ns", 1000000000)):
        seconds = n / float(divisor)
        if 978307200 <= seconds <= 2145916800:          # 2001-01-01 … 2038-01-01: a date a person meant
            return Layer("epoch", "unix time in {0}, {1}".format(unit, _when(seconds)),
                         {"unit": unit, "utc": _when(seconds), "seconds": seconds,
                          "note": "also a plain integer; read as a time because it lands between 2001 and 2038"})
    return Layer("number", "an integer, {0} digits".format(len(s.lstrip("-"))),
                 {"value": n, "note": "no plausible date reading between 2001 and 2038"})


def _try_hash(s):
    if not RE["hex"].match(s) or len(s) not in HASHES:
        return None
    detail = {"candidates": HASHES[len(s)], "bits": len(s) * 4}
    if len(s) == 40:
        detail["git"] = True
        detail["note"] = "40 hex characters: a sha1, and the shape of a git object id"
    return Layer("hash", "{0} hex characters — {1}".format(len(s), "/".join(HASHES[len(s)])), detail)


def _try_url(s):
    parts = urlsplit(s)
    if parts.scheme not in ("http", "https", "ftp", "ws", "wss", "postgres", "postgresql", "mysql", "redis"):
        return None
    if not parts.netloc:
        return None
    return Layer("url", "{0} URL, host {1}".format(parts.scheme, parts.hostname),
                 {"scheme": parts.scheme, "host": parts.hostname, "port": parts.port,
                  "path": parts.path, "query": dict(parse_qsl(parts.query)),
                  "has_credentials": bool(parts.username or parts.password)})


def _try_json(s):
    t = s.strip()
    if not t or t[0] not in "{[":
        return None
    try:
        doc = json.loads(t)
    except ValueError:
        return None
    return Layer("json", "JSON {0}".format(_shape(doc)),
                 {"shape": _shape(doc), "keys": sorted(doc)[:20] if isinstance(doc, dict) else None,
                  "length": len(doc), "value": doc})


def _try_urlencoded(s):
    if "%" not in s:
        return None
    out = unquote(s)
    if out == s:
        return None
    return Layer("urlencoded", "percent-encoded, {0} bytes decoded".format(len(out)), {}, out)


def _try_base64(s):
    body = s.strip()
    if len(body) < 8 or " " in body:
        return None
    urlsafe = bool(RE["b64url"].match(body)) and not RE["b64"].match(body)
    if not (RE["b64"].match(body) or RE["b64url"].match(body)):
        return None
    raw = _b64_decode(body, urlsafe)
    if raw is None or not raw:
        return None
    # Base64 of nothing recognisable is how everything becomes "base64" — demand a real payload.
    if _magic(raw) is None and _printable(raw) is None:
        return None
    kind = "base64url" if urlsafe else "base64"
    return Layer(kind, "{0}, {1} bytes decoded".format(kind, len(raw)), {"bytes": len(raw)}, raw)


def _try_hex_blob(s):
    body = s[2:] if s.lower().startswith("0x") else s
    if len(body) < 16 or len(body) % 2 or not RE["hex"].match(body):
        return None
    try:
        raw = binascii.unhexlify(body)
    except (binascii.Error, ValueError):
        return None
    if _magic(raw) is None and _printable(raw) is None:
        return None
    return Layer("hex", "hex, {0} bytes decoded".format(len(raw)), {"bytes": len(raw)}, raw)


def _try_simple(s):
    if RE["mac"].match(s):
        return Layer("mac", "MAC address", {"oui": s[:8].lower()})
    if RE["semver"].match(s):
        return Layer("semver", "semantic version", {"version": s.lstrip("v")})
    if RE["email"].match(s):
        return Layer("email", "e-mail address", {"domain": s.split("@")[-1]})
    if RE["iso"].match(s):
        return Layer("iso8601", "ISO-8601 timestamp", {"value": s})
    if RE["cron"].match(s) and (s.startswith("@") or len(s.split()) == 5):
        return Layer("cron", "cron expression", {"expr": s,
                                                 "note": "run cron-when for the next fires and the DST warning"})
    return None


STRING_DETECTORS = (_try_data_uri, _try_jwt, _try_uuid, _try_ulid, _try_simple, _try_net, _try_color,
                    _try_url, _try_json, _try_hash, _try_epoch, _try_urlencoded, _try_base64, _try_hex_blob)


# ---------------------------------------------------------------- the peeler

def _identify_bytes(raw):
    name = _magic(raw)
    if name == "gzip":
        try:
            return Layer("gzip", "gzip, {0} bytes compressed".format(len(raw)),
                         {"compressed": len(raw)}, gzip.decompress(raw))
        except (OSError, EOFError, zlib.error):
            pass
    if name and name != "gzip":
        return Layer("binary", "{0} file, {1} bytes".format(name, len(raw)),
                     {"format": name, "bytes": len(raw)})
    text = _printable(raw)
    if text is not None:
        return identify(text)
    return Layer("binary", "{0} bytes, no recognised format".format(len(raw)),
                 {"format": None, "bytes": len(raw)})


def identify(text):
    """One layer. The order of the detectors is the design: most constrained shape wins."""
    s = str(text).strip()
    if not s:
        return Layer("empty", "nothing to read")
    for detector in STRING_DETECTORS:
        found = detector(s)
        if found is not None:
            return found
    return Layer("text", "plain text, {0} characters, {1} words".format(len(s), len(s.split())),
                 {"chars": len(s), "words": len(s.split()), "lines": s.count("\n") + 1})


def peel(text, depth=4, reveal=False):
    """Outermost layer first. Stops at depth, at a leaf, or when a decode changed nothing."""
    layers, value, seen = [], text, set()
    for _ in range(max(1, int(depth))):
        layer = identify(value) if isinstance(value, str) else _identify_bytes(value)
        layers.append(layer)
        if layer.text is None:
            break
        key = layer.text if isinstance(layer.text, bytes) else str(layer.text).encode("utf-8", "replace")
        if key in seen:
            break
        seen.add(key)
        value = layer.text
    return layers


# ---------------------------------------------------------------- rendering

def _value(v, reveal):
    text = v if isinstance(v, str) else json.dumps(v, default=str, sort_keys=True)
    return text if reveal or len(text) <= 80 else text[:79] + "…"


def render(layers, reveal=False):
    lines = []
    for i, layer in enumerate(layers):
        lines.append("{0}{1} {2}".format("  " * i, "└─" if i else "•", layer.label))
        pad = "  " * i + "   "
        if layer.kind == "jwt":
            for name in ("typ", "iat", "nbf", "exp", "signature"):
                if layer.detail.get(name):
                    lines.append("{0}{1}: {2}".format(pad, name, layer.detail[name]))
            for k, v in list(layer.detail.get("claims", {}).items())[:12]:
                lines.append("{0}claim {1}: {2}".format(pad, k, _value(v, reveal)))
        elif layer.kind == "json" and layer.detail.get("keys"):
            lines.append("{0}keys: {1}".format(pad, ", ".join(layer.detail["keys"])))
            for k, v in list((layer.detail.get("value") or {}).items())[:8]:
                lines.append("{0}{1}: {2}".format(pad, k, _value(v, reveal)))
        else:
            for k, v in layer.detail.items():
                if k in ("value", "claims", "keys", "claim_names") or v in (None, "", [], {}):
                    continue
                lines.append("{0}{1}: {2}".format(pad, k, _value(v, reveal)))
    return "\n".join(lines)
