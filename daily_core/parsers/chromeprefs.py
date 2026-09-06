"""Chromium's `Preferences` and `Secure Preferences`, read for extension metadata only.

Every Chromium profile keeps one big JSON document of settings. The part this reader wants is
`extensions.settings`: one entry per installed extension holding the state the manifest cannot
know — whether it is enabled, when it was installed, where it came from, and which host
permissions the user actually granted as opposed to which ones the manifest asked for.

Two things make that document awkward to read from outside the browser, and both are handled here
rather than by the caller:

1. It is large. A profile that has been in use for years produces a file of several megabytes, of
   which the extension settings are a small fraction. The caller passes a bounded read, so the
   text this reader is handed is routinely a *prefix* of the document and will not parse as JSON.
2. It is written live. A read that lands during a flush sees a half-written tail.

So parsing degrades in three steps: the whole document, then a brace-matched slice of the settings
object alone, then entry by entry, keeping every extension whose own object closed cleanly. A
truncated file therefore yields the extensions it did contain plus an honest `partial` flag, never
an exception and never a silent zero.

Nothing here reads extension *storage*. The values returned are manifest fields the browser
copied into its own settings, plus timestamps and enum codes.
"""
import json
import re

# A Chromium extension id is thirty-two characters drawn from the first sixteen letters, which is
# what makes an entry-by-entry salvage possible: the keys are recognisable without a parser.
EXT_ID = re.compile(r'"([a-p]{32})"\s*:\s*\{')


class Unreadable(Exception):
    """Not a settings document, or nothing in it could be recovered."""


# Chromium's ManifestLocation enum, as written into the profile. The labels are what a person
# needs to know — "you installed this from the store" versus "something else put it here".
LOCATIONS = {
    0: "unknown",
    1: "installed from the web store",
    2: "sideloaded by another program (preference file)",
    3: "sideloaded by another program (registry)",
    4: "loaded unpacked by a developer",
    5: "shipped with the browser",
    6: "installed from outside the browser",
    7: "installed by policy",
    8: "loaded from the command line",
    9: "installed by policy",
    10: "shipped with the browser",
}
STORE = (1,)
UNPACKED = (4, 8)
COMPONENT = (5, 10)
POLICY = (7, 9)
SIDELOADED = (2, 3, 6)

# Chromium's Extension::State enum: 0 disabled, 1 enabled, 2 externally uninstalled/blacklisted.
STATE_ENABLED = 1


def read_settings(text: str) -> dict:
    """`{extension_id: raw entry}` from a settings document, however much of one arrived.

    Raises `Unreadable` only when not a single extension entry could be recovered, which is the
    one case where the caller genuinely learned nothing and must say so.
    """
    entries, partial = _whole(text)
    if entries is None:
        entries, partial = _settings_slice(text)
    if entries is None:
        entries, partial = _entry_by_entry(text)
    if entries is None:
        raise Unreadable("no extension settings could be recovered from the document")
    out = {}
    for key, value in entries.items():
        if isinstance(value, dict):
            out[key] = value
    if not out and not partial:
        return {}
    return out


def was_partial(text: str) -> bool:
    """True when the document did not parse whole, so the caller can label its counts a floor."""
    try:
        json.loads(text)
        return False
    except ValueError:
        return True


def _whole(text: str):
    try:
        doc = json.loads(text)
    except ValueError:
        return None, True
    if not isinstance(doc, dict):
        return None, True
    settings = ((doc.get("extensions") or {}) if isinstance(doc.get("extensions"), dict) else {}).get("settings")
    return (settings if isinstance(settings, dict) else {}), False


def _settings_slice(text: str):
    """The settings object on its own, brace-matched out of a document that would not parse."""
    for marker in ('"settings"', "'settings'"):
        at = text.find(marker)
        while at != -1:
            brace = text.find("{", at + len(marker))
            if brace != -1 and text[at + len(marker):brace].strip().startswith(":"):
                blob = _match_braces(text, brace)
                if blob:
                    try:
                        doc = json.loads(blob)
                    except ValueError:
                        doc = None
                    if isinstance(doc, dict) and any(EXT_ID.match('"{0}":{{'.format(k)) for k in doc):
                        return doc, True
            at = text.find(marker, at + 1)
    return None, True


def _entry_by_entry(text: str):
    """Last resort: every extension object that closed cleanly, and nothing that did not."""
    out = {}
    for m in EXT_ID.finditer(text):
        blob = _match_braces(text, m.end() - 1)
        if not blob:
            continue
        try:
            doc = json.loads(blob)
        except ValueError:
            continue
        if isinstance(doc, dict) and ("manifest" in doc or "state" in doc or "location" in doc):
            out[m.group(1)] = doc
    return (out, True) if out else (None, True)


def _match_braces(text: str, start: int) -> str:
    """The balanced `{...}` beginning at `start`, honouring string literals and escapes."""
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def merge(*documents) -> dict:
    """Later documents win. Chrome splits extension settings across two files and the signed one
    (`Secure Preferences`) is authoritative for anything that appears in both."""
    out = {}
    for doc in documents:
        for key, value in (doc or {}).items():
            if isinstance(value, dict):
                merged = dict(out.get(key) or {})
                merged.update(value)
                out[key] = merged
    return out


def normalise(ext_id: str, entry: dict) -> dict:
    """One settings entry as flat, typed fields, with everything absent reported as absent."""
    entry = entry if isinstance(entry, dict) else {}
    manifest = entry.get("manifest") if isinstance(entry.get("manifest"), dict) else {}
    active = entry.get("active_permissions") if isinstance(entry.get("active_permissions"), dict) else {}
    granted = entry.get("granted_permissions") if isinstance(entry.get("granted_permissions"), dict) else {}

    state = entry.get("state")
    state = state if isinstance(state, int) else None
    location = entry.get("location")
    location = location if isinstance(location, int) else None

    hosts = _strings(active.get("explicit_host")) + _strings(active.get("scriptable_host"))
    if not hosts:
        hosts = _strings(granted.get("explicit_host")) + _strings(granted.get("scriptable_host"))

    return {
        "id": ext_id,
        "state": state,
        "enabled": None if state is None else state == STATE_ENABLED,
        "location": location,
        "location_label": LOCATIONS.get(location, "unknown") if location is not None else "unknown",
        "install_source": _source_of(location),
        "from_store": None if location is None else location in STORE,
        "install_time": _stamp(entry, "install_time", "first_install_time"),
        "updated_time": _stamp(entry, "last_update_time"),
        "manifest_name": str(manifest.get("name") or ""),
        "manifest_version_string": str(manifest.get("version") or ""),
        "manifest_version": manifest.get("manifest_version")
        if isinstance(manifest.get("manifest_version"), int) else None,
        "manifest_permissions": _strings(manifest.get("permissions")),
        "manifest_host_permissions": _strings(manifest.get("host_permissions")),
        "active_api": sorted(set(_strings(active.get("api")) or _strings(granted.get("api")))),
        "active_hosts": sorted(set(hosts)),
        "hosts_withheld": bool(entry.get("withholding_permissions")),
        "disable_reasons": entry.get("disable_reasons")
        if isinstance(entry.get("disable_reasons"), int) else None,
        "acknowledged_external": bool(entry.get("ack_external")),
        "was_installed_by_default": bool(entry.get("was_installed_by_default")),
        "was_installed_by_oem": bool(entry.get("was_installed_by_oem")),
    }


def _source_of(location) -> str:
    if location is None:
        return "unknown"
    if location in UNPACKED:
        return "unpacked"
    if location in STORE:
        return "store"
    if location in COMPONENT:
        return "component"
    if location in POLICY:
        return "policy"
    if location in SIDELOADED:
        return "sideloaded"
    return "unknown"


def _stamp(entry: dict, *keys) -> str:
    """Chromium writes these as a decimal string of microseconds since 1601. Keep it as written."""
    for key in keys:
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return str(int(value))
        if isinstance(value, str) and value.strip().isdigit():
            return value.strip()
    return ""


def _strings(value) -> list:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str) and v]
