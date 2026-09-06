"""extension-reach: which browser extensions can read every page you visit, and who still maintains them.

An extension's install page shows its permissions once, in a dialog nobody re-reads, and then never
again. The browser keeps the answer on disk for ever: a manifest per extension, and a settings
entry per profile saying whether it is on, where it came from and which hosts you actually granted.
This reads both and answers the question the browser stops asking after install day — what can see
your bank tab, and is anyone still shipping updates for it.

Three families, read independently, so a browser this machine does not have, a profile macOS will
not open, or a Safari that simply does not publish this information costs that browser and never
the run.

**Never reads extension storage.** Manifests and settings metadata only. Idle detection looks at
the modification *time* of a state folder, with `os.stat`; the folder is never opened and its
contents are never read. Nothing under a `Local Storage`, `IndexedDB`, `Local Extension Settings`
or `Cookies` path is ever opened by this module.
"""
import json
import os
import plistlib

from ..common import (Budget, Source, age_days, ago, baseline_read, day, delta, expand, from_chrome,
                      from_unix, iso, pct, plural, read_text, since_note)
from ..parsers import chromeprefs, mozlz4
from .tabs import CHROMIUM, FIREFOX, support_dirs

FAMILIES = ("chromium", "firefox", "safari")

# Arc is Chromium underneath but keeps its profiles one level deeper, so it is not in tab-debt's
# table (which looks for a Sessions folder directly under the vendor root). The vendor list itself
# stays imported rather than copied: one table, one place to add the next browser.
EXTRA_CHROMIUM = [("Arc", "Arc/User Data", "arc")]
VENDORS = list(CHROMIUM) + EXTRA_CHROMIUM

# Where a Chromium profile records that an extension did something locally. These are looked at
# with os.stat for a modification time and are never opened. Naming them here is what lets the
# test suite assert that no read in this module ever touches one.
STATE_DIRS = ("Local Extension Settings", "Sync Extension Settings", "Managed Extension Settings")
NEVER_OPENED = ("Local Storage", "IndexedDB", "Local Extension Settings", "Cookies")

MANIFEST = "manifest.json"
SKIP_DIRS = ("_metadata", "Temp")
DEMO_FILE = "installs.json"

PREFS_LIMIT = 24 * 1024 * 1024          # a long-lived profile's settings document is megabytes
MANIFEST_LIMIT = 2 * 1024 * 1024

# ---------------------------------------------------------------- reach

TIERS = ("all_urls", "broad_wildcard", "specific_hosts", "active_tab_only", "none")
TIER_RANK = {"all_urls": 5, "broad_wildcard": 4, "specific_hosts": 3, "active_tab_only": 2, "none": 1,
             "unknown": 0}
TIER_LABEL = {
    "all_urls": "every page you visit",
    "broad_wildcard": "a wildcard slice of the web",
    "specific_hosts": "named sites only",
    "active_tab_only": "only the tab you click on",
    "none": "no page access",
    "unknown": "not published by this browser",
}
EVERYTHING = ("<all_urls>", "<all-urls>", "*://*/*", "*://*", "https://*/*", "http://*/*")

# Wildcarding a whole suffix is not the same as wildcarding one company's subdomains, and the two
# should not sit in the same tier. This is the small table needed to tell them apart; it is not a
# public suffix list and does not pretend to be one.
BROAD_SUFFIXES = {
    "com", "net", "org", "io", "co", "dev", "app", "xyz", "info", "biz", "me", "tv", "ai",
    "uk", "co.uk", "org.uk", "de", "fr", "nl", "se", "es", "it", "pl", "ru", "jp", "cn", "in",
    "co.in", "br", "com.br", "au", "com.au", "ca", "us", "eu", "ch", "no", "dk", "fi", "cz",
}

# Blanket host access plus one of these is a different animal from blanket host access alone, and
# each one is named with what it actually lets the extension do.
DANGEROUS = (
    ("cookies", "read the cookies that keep you signed in, on every site"),
    ("webRequest", "watch every network request the browser makes"),
    ("webRequestBlocking", "block or rewrite requests before they are sent"),
    ("declarativeNetRequest", "block or rewrite requests by standing rule"),
    ("debugger", "attach the developer debugger to any page"),
    ("nativeMessaging", "talk to a program installed outside the browser"),
    ("downloads", "start downloads and read what you have downloaded"),
    ("history", "read your whole browsing history, not just this session"),
    ("clipboardRead", "read whatever you last copied"),
    ("management", "enable, disable or remove your other extensions"),
    ("proxy", "route your traffic through a proxy of its choosing"),
    ("scripting", "inject its own code into pages"),
)
DANGEROUS_ORDER = [name for name, _ in DANGEROUS]
DANGEROUS_REASON = dict(DANGEROUS)

STALE_DAYS = 365
IDLE_DAYS = 90


# ---------------------------------------------------------------- reading

def read_source(family: str, budget: Budget, cfg=None) -> tuple:
    """Read one browser family. Returns (sources, records). Never raises for a browser it cannot read."""
    cfg = cfg or {}
    if cfg.get("demo_root"):
        return _read_demo(family, cfg)
    if family == "chromium":
        return _read_chromium(budget, cfg)
    if family == "firefox":
        return _read_firefox(budget, cfg)
    if family == "safari":
        return _read_safari(budget, cfg)
    return [Source(name=family).miss("unknown browser family")], []


def _read_demo(family: str, cfg) -> tuple:
    """The bundled fixture: a captured install list, so a cold first run has something to show.

    A tree of real profiles cannot be shipped. Every `updated` and `state_touched` this module
    produces is a filesystem timestamp, so a checked-in folder would carry the date of the clone
    and every extension in the demo would read as installed this morning -- which is exactly the
    half of the card that matters.
    """
    path = expand(cfg["demo_root"]) / DEMO_FILE
    src = Source(name="{0} (demo)".format(family), path=str(path))
    if not path.is_file():
        return [src.miss("fixture missing at {0}".format(path))], []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [src.miss("fixture is not readable JSON")], []
    rows = doc.get("installs") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        return [src.miss("fixture has no install list")], []
    records = [r for r in rows
               if isinstance(r, dict) and r.get("id") and r.get("family") == family]
    if not records:
        return [src.miss("fixture holds no {0} extension".format(family))], []
    return [src.hit(len(records), "bundled fixture")], records


def _bases(cfg) -> list:
    """The directories a browser might keep a profile in. Overridable so a test owns its own tree."""
    roots = cfg.get("roots")
    if roots:
        return [expand(r) for r in roots]
    return support_dirs()


def _vendor_root(base, mac: str, linux: str):
    return base / mac if base.name == "Application Support" else base / linux


def _note_for(exc, path=None) -> str:
    """Absent and forbidden look alike from one failed open; the parent directory tells them apart."""
    if isinstance(exc, PermissionError):
        return "macOS blocked the read; grant Full Disk Access to your terminal"
    if isinstance(exc, FileNotFoundError):
        parent = os.path.dirname(str(path)) if path else ""
        if parent and os.path.isdir(parent) and not os.access(parent, os.R_OK):
            return "macOS blocked the read; grant Full Disk Access to your terminal"
        return "not installed here"
    return str(exc)[:120]


def _profiles_chromium(cfg):
    """Every profile of every Chromium-family browser that has an Extensions folder."""
    for label, mac, linux in VENDORS:
        for base in _bases(cfg):
            root = _vendor_root(base, mac, linux)
            if not root.is_dir():
                continue
            try:
                children = sorted(p for p in root.iterdir() if p.is_dir())
            except OSError:
                children = []
            for profile in children:
                if (profile / "Extensions").is_dir():
                    yield label, profile
            break


def _read_chromium(budget: Budget, cfg) -> tuple:
    sources, records = [], []
    for label, profile in _profiles_chromium(cfg):
        name = label if profile.name in ("Default", "default") else "{0} ({1})".format(label, profile.name)
        ext_dir = profile / "Extensions"
        src = Source(name=name, path=str(ext_dir))
        settings, prefs_note = _read_prefs(profile, budget)
        try:
            found = _read_manifests(ext_dir, settings, name, profile, budget, cfg)
        except OSError as exc:
            sources.append(src.miss(_note_for(exc, ext_dir)))
            continue
        if not found:
            sources.append(src.miss("no readable extension folder in this profile"))
            continue
        records += found
        sources.append(src.hit(len(found), prefs_note))
    if not sources:
        sources.append(Source(name="chromium").miss("no Chromium-family profile found on this machine"))
    return sources, records


def _read_prefs(profile, budget: Budget) -> tuple:
    """Enabled state, install time and install source. Both files, the signed one winning."""
    docs, notes, seen = [], [], False
    for filename in ("Preferences", "Secure Preferences"):
        path = profile / filename
        if not path.is_file():
            continue
        seen = True
        text = read_text(path, PREFS_LIMIT)
        if not text:
            notes.append("{0} unreadable".format(filename))
            continue
        budget.spend(len(text))
        try:
            docs.append(chromeprefs.read_settings(text))
        except chromeprefs.Unreadable:
            notes.append("{0} held no readable extension settings".format(filename))
            continue
        if chromeprefs.was_partial(text):
            notes.append("{0} read partially".format(filename))
    if not seen:
        return {}, "no settings file; enabled state and install source unknown"
    merged = chromeprefs.merge(*docs)
    if not merged:
        return {}, "; ".join(notes) or "settings file held no extension entries"
    detail = "{0} from settings".format(plural(len(merged), "entry", "entries"))
    return merged, "; ".join([detail] + notes)


def _read_manifests(ext_dir, settings: dict, browser: str, profile, budget: Budget, cfg) -> list:
    out = []
    for ext_id in sorted(p.name for p in ext_dir.iterdir() if p.is_dir()):
        if ext_id in SKIP_DIRS or ext_id.startswith("."):
            continue
        version_dir = _newest_version(ext_dir / ext_id)
        meta = chromeprefs.normalise(ext_id, settings.get(ext_id) or {})
        if version_dir is None:
            if not settings.get(ext_id):
                continue
            out.append(_record_from_meta(ext_id, meta, browser, profile))
            continue
        manifest = _load_manifest(version_dir, budget)
        out.append(_record_chromium(ext_id, manifest, meta, version_dir, browser, profile))
    return out


def _newest_version(folder):
    """Several versions can sit side by side; the one the browser runs is the newest it kept."""
    try:
        versions = [p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return None
    if not versions:
        return None
    return max(versions, key=lambda p: (_version_key(p.name), _mtime(p), p.name))


def _version_key(name: str) -> tuple:
    parts = name.split("_")[0].split(".")
    key = []
    for part in parts[:4]:
        key.append(int(part) if part.isdigit() else 0)
    while len(key) < 4:
        key.append(0)
    return tuple(key)


def _mtime(path) -> float:
    try:
        return os.stat(str(path)).st_mtime
    except OSError:
        return 0.0


def _load_manifest(version_dir, budget: Budget) -> dict:
    text = read_text(version_dir / MANIFEST, MANIFEST_LIMIT)
    if not text:
        return {}
    budget.spend(len(text))
    try:
        doc = json.loads(text)
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def _localised(version_dir, raw: str, default_locale: str) -> str:
    """`__MSG_appName__` is a lookup into the extension's own bundled strings, not a name."""
    token = str(raw or "")
    if not (token.startswith("__MSG_") and token.endswith("__")):
        return token
    key = token[6:-2]
    for locale in [l for l in (default_locale, "en", "en_US", "en_GB") if l]:
        text = read_text(version_dir / "_locales" / locale / "messages.json", 1024 * 1024)
        if not text:
            continue
        try:
            doc = json.loads(text)
        except ValueError:
            continue
        entry = doc.get(key) if isinstance(doc, dict) else None
        if isinstance(entry, dict) and entry.get("message"):
            return str(entry["message"])
    return ""


def _record_chromium(ext_id, manifest, meta, version_dir, browser, profile) -> dict:
    name = _localised(version_dir, manifest.get("name"), str(manifest.get("default_locale") or ""))
    name = name or meta["manifest_name"] or ext_id
    matches = []
    for script in manifest.get("content_scripts") or []:
        if isinstance(script, dict):
            matches += [m for m in (script.get("matches") or []) if isinstance(m, str)]
    permissions = _texts(manifest.get("permissions")) or meta["manifest_permissions"]
    hosts = _texts(manifest.get("host_permissions")) or meta["manifest_host_permissions"]
    granted = meta["active_hosts"]
    record = {
        "id": ext_id,
        "family": "chromium",
        "browser": browser,
        "profile": profile.name,
        "name": name,
        "version": str(manifest.get("version") or meta["manifest_version_string"] or ""),
        "manifest_version": manifest.get("manifest_version")
        if isinstance(manifest.get("manifest_version"), int) else meta["manifest_version"],
        "permissions": sorted(set(permissions + meta["active_api"])),
        "host_permissions": sorted(set(hosts)),
        "optional_host_permissions": sorted(set(
            _texts(manifest.get("optional_host_permissions")) + _texts(manifest.get("optional_permissions")))),
        "content_matches": sorted(set(matches)),
        "granted_hosts": sorted(set(granted)),
        "hosts_withheld": meta["hosts_withheld"],
        "enabled": meta["enabled"],
        "install_source": meta["install_source"],
        "location_label": meta["location_label"],
        "installed": iso(from_chrome(meta["install_time"])) if meta["install_time"] else "",
        "updated": iso(from_unix(_mtime(version_dir))),
        "updated_is_proxy": True,
        "state_touched": iso(from_unix(_state_mtime(profile, ext_id, version_dir))),
        "settings_seen": bool(meta["state"] is not None or meta["location"] is not None),
    }
    return record


def _record_from_meta(ext_id, meta, browser, profile) -> dict:
    """An extension the settings know about whose folder is gone or unreadable: still a row."""
    return {
        "id": ext_id, "family": "chromium", "browser": browser, "profile": profile.name,
        "name": meta["manifest_name"] or ext_id, "version": meta["manifest_version_string"],
        "manifest_version": meta["manifest_version"],
        "permissions": sorted(set(meta["manifest_permissions"] + meta["active_api"])),
        "host_permissions": sorted(set(meta["manifest_host_permissions"] + meta["active_hosts"])),
        "optional_host_permissions": [], "content_matches": [],
        "granted_hosts": meta["active_hosts"], "hosts_withheld": meta["hosts_withheld"],
        "enabled": meta["enabled"], "install_source": meta["install_source"],
        "location_label": meta["location_label"],
        "installed": iso(from_chrome(meta["install_time"])) if meta["install_time"] else "",
        "updated": "", "updated_is_proxy": True, "state_touched": "", "settings_seen": True,
    }


def _state_mtime(profile, ext_id: str, version_dir=None) -> float:
    """When this extension last changed anything locally.

    The folder's timestamp is the whole answer, so the folder is stat'ed and never opened: this
    module reads no extension storage, and an idle count is not worth breaking that for.
    """
    best = 0.0
    for state in STATE_DIRS:
        best = max(best, _mtime(profile / state / ext_id))
    if best:
        return best
    return _mtime(version_dir) if version_dir is not None else 0.0


def _texts(value) -> list:
    if not isinstance(value, list):
        return []
    return sorted({v for v in value if isinstance(v, str) and v})


# ---------------------------------------------------------------- firefox

def _read_firefox(budget: Budget, cfg) -> tuple:
    sources, records = [], []
    for label, mac, linux in FIREFOX:
        for base in _bases(cfg):
            root = _vendor_root(base, mac, linux)
            if not root.is_dir():
                continue
            try:
                profiles = sorted(p for p in root.iterdir() if p.is_dir())
            except OSError:
                profiles = []
            for profile in profiles:
                inventory = profile / "extensions.json"
                if not inventory.is_file():
                    continue
                name = "{0} ({1})".format(label, profile.name.split(".")[-1][:18])
                src = Source(name=name, path=str(inventory))
                text = read_text(inventory, PREFS_LIMIT)
                if not text:
                    sources.append(src.miss(_note_for(FileNotFoundError(), inventory)))
                    continue
                budget.spend(len(text))
                try:
                    doc = json.loads(text)
                except ValueError as exc:
                    sources.append(src.miss("extension inventory is not JSON: {0}".format(str(exc)[:60])))
                    continue
                startup, startup_note = _firefox_startup(profile, budget)
                found = [_record_firefox(a, startup, name, profile)
                         for a in (doc.get("addons") or []) if isinstance(a, dict)]
                found = [r for r in found if r is not None]
                records += found
                sources.append(src.hit(len(found), startup_note))
            break
    if not sources:
        sources.append(Source(name="firefox").miss("no Firefox-family profile found on this machine"))
    return sources, records


def _firefox_startup(profile, budget: Budget) -> tuple:
    """`addonStartup.json.lz4` carries the real last-modified time, which beats a folder mtime."""
    path = profile / "addonStartup.json.lz4"
    if not path.is_file():
        return {}, "no startup cache; last-update times come from the inventory"
    try:
        with open(path, "rb") as fh:
            raw = fh.read(16 * 1024 * 1024)
        doc = mozlz4.read_json(raw)
    except (mozlz4.Unreadable, OSError, ValueError):
        return {}, "startup cache unreadable; last-update times come from the inventory"
    budget.spend(len(raw))
    out = {}
    for scope in doc.values() if isinstance(doc, dict) else []:
        addons = scope.get("addons") if isinstance(scope, dict) else None
        for key, value in (addons or {}).items():
            if isinstance(value, dict):
                out[key] = value
    return out, "startup cache read for {0}".format(plural(len(out), "add-on"))


def _record_firefox(addon: dict, startup: dict, browser: str, profile) -> dict:
    kind = str(addon.get("type") or "extension")
    if kind not in ("extension", "webextension"):
        return None                                  # a theme or a dictionary reads no pages
    ext_id = str(addon.get("id") or "")
    if not ext_id:
        return None
    locale = addon.get("defaultLocale") if isinstance(addon.get("defaultLocale"), dict) else {}
    label = str(locale.get("name") or "") or str(addon.get("name") or "") or ext_id
    user = addon.get("userPermissions") if isinstance(addon.get("userPermissions"), dict) else {}
    optional = addon.get("optionalPermissions") if isinstance(addon.get("optionalPermissions"), dict) else {}
    boot = startup.get(ext_id) if isinstance(startup.get(ext_id), dict) else {}

    location = str(addon.get("location") or "")
    source = ("unpacked" if location == "app-temporary" else
              "component" if location.startswith("app-") and location != "app-profile" else
              "store" if str(addon.get("sourceURI") or "").find("addons.mozilla.org") != -1 else
              "sideloaded" if location in ("winreg-app-global", "winreg-app-user", "app-global") else
              "unknown")
    if source == "unknown" and isinstance(addon.get("signedState"), int):
        source = "store" if addon["signedState"] >= 2 else "sideloaded"

    modified = boot.get("lastModifiedTime")
    updated = from_unix(_ms(modified)) or from_unix(_ms(addon.get("updateDate")))
    return {
        "id": ext_id,
        "family": "firefox",
        "browser": browser,
        "profile": profile.name,
        "name": label,
        "version": str(addon.get("version") or ""),
        "manifest_version": addon.get("manifestVersion")
        if isinstance(addon.get("manifestVersion"), int) else None,
        "permissions": _texts(user.get("permissions")),
        "host_permissions": _texts(user.get("origins")),
        "optional_host_permissions": _texts(optional.get("origins")) + _texts(optional.get("permissions")),
        "content_matches": [],
        "granted_hosts": _texts(user.get("origins")),
        "hosts_withheld": False,
        "enabled": bool(addon.get("active")) if addon.get("active") is not None else
        (not addon.get("userDisabled") if addon.get("userDisabled") is not None else None),
        "install_source": source,
        "location_label": location or "unknown",
        "installed": iso(from_unix(_ms(addon.get("installDate")))),
        "updated": iso(updated),
        "updated_is_proxy": False,
        "state_touched": iso(updated),
        "settings_seen": True,
    }


def _ms(value):
    """Firefox records milliseconds since the Unix epoch; the shared helpers expect seconds."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v / 1000.0 if v > 1e11 else v


# ---------------------------------------------------------------- safari

# Safari keeps extension state inside its container and publishes no per-extension host
# permissions anywhere a reader outside the browser can see. Reporting zero would be a lie, so the
# Play enumerates what is legible and labels the rest a partial.
SAFARI_STORES = (
    "~/Library/Containers/com.apple.Safari/Data/Library/Safari/AppExtensions/Extensions.plist",
    "~/Library/Safari/AppExtensions/Extensions.plist",
)
SAFARI_WEB_EXTENSIONS = "~/Library/Containers/com.apple.Safari/Data/Library/Safari/WebExtensions"


def _read_safari(budget: Budget, cfg) -> tuple:
    roots = cfg.get("safari_roots") or [""]
    sources, records = [], []
    for prefix in roots:
        for candidate in SAFARI_STORES:
            path = (expand(prefix) / candidate.replace("~/", "")) if prefix else expand(candidate)
            if not path.is_file():
                continue
            src = Source(name="Safari extensions", path=str(path))
            try:
                with open(path, "rb") as fh:
                    doc = plistlib.loads(fh.read(8 * 1024 * 1024)) or {}
                budget.spend(1)
            except (OSError, ValueError, plistlib.InvalidFileException) as exc:
                sources.append(src.miss(_note_for(exc, path)))
                continue
            found = _safari_records(doc)
            records += found
            sources.append(src.hit(len(found),
                                   "names and enabled state only; Safari publishes no host "
                                   "permissions here, so reach is reported as not published"))
        listing = (expand(prefix) / SAFARI_WEB_EXTENSIONS.replace("~/", "")) if prefix \
            else expand(SAFARI_WEB_EXTENSIONS)
        if listing.is_dir():
            try:
                names = sorted(p.name for p in listing.iterdir() if not p.name.startswith("."))
            except OSError as exc:
                sources.append(Source(name="Safari web extensions", path=str(listing))
                               .miss(_note_for(exc, listing)))
                names = []
            if names:
                sources.append(Source(name="Safari web extensions", path=str(listing))
                               .hit(len(names), "folder names only; no manifest is readable here"))
    if not sources:
        sources.append(Source(name="Safari", path=str(expand(SAFARI_STORES[0]))).miss(
            "Safari keeps extension state inside its container and publishes no host permissions "
            "to a reader outside the browser; this is unknown, not zero"))
    return sources, records


def _safari_records(doc: dict) -> list:
    out = []
    entries = doc.get("Installed Extensions") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        entries = [{"WebExtensionBundleIdentifier": k, "Enabled": v} for k, v in sorted(doc.items())] \
            if isinstance(doc, dict) and all(isinstance(v, bool) for v in doc.values()) and doc else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ext_id = str(entry.get("WebExtensionBundleIdentifier") or entry.get("Bundle Identifier")
                     or entry.get("Archive File Name") or "")
        if not ext_id:
            continue
        out.append({
            "id": ext_id, "family": "safari", "browser": "Safari", "profile": "Default",
            "name": str(entry.get("Extension Name") or entry.get("WebExtensionDisplayName") or ext_id),
            "version": str(entry.get("Version") or ""), "manifest_version": None,
            "permissions": [], "host_permissions": [], "optional_host_permissions": [],
            "content_matches": [], "granted_hosts": [], "hosts_withheld": False,
            "enabled": bool(entry.get("Enabled")) if entry.get("Enabled") is not None else None,
            "install_source": "unknown", "location_label": "Safari container",
            "installed": "", "updated": "", "updated_is_proxy": True, "state_touched": "",
            "settings_seen": False, "reach_published": False,
        })
    return sorted(out, key=lambda r: (r["name"].lower(), r["id"]))


# ---------------------------------------------------------------- reach classification

def pattern_scope(pattern: str) -> str:
    """One match pattern's reach: 'all', 'http_all', 'https_all', 'wild', 'specific' or ''."""
    p = str(pattern or "").strip()
    if not p:
        return ""
    if p in ("<all_urls>", "<all-urls>", "*://*/*", "*://*"):
        return "all"
    if p == "https://*/*":
        return "https_all"
    if p == "http://*/*":
        return "http_all"
    if "://" not in p:
        return ""
    scheme, rest = p.split("://", 1)
    host = rest.split("/", 1)[0].lower()
    if scheme in ("file", "*") and host in ("", "*"):
        return "wild"
    if host == "*":
        return "wild"
    if host.startswith("*."):
        suffix = host[2:]
        return "wild" if (suffix in BROAD_SUFFIXES or "." not in suffix) else "specific"
    return "specific" if host else ""


def reach_of(patterns, permissions) -> str:
    """The tier a set of granted patterns lands in, worst case wins."""
    scopes = set()
    hosts = []
    for p in patterns:
        scope = pattern_scope(p)
        if scope:
            scopes.add(scope)
        if scope == "specific":
            hosts.append(p)
    if "all" in scopes:
        return "all_urls"
    if "https_all" in scopes and "http_all" in scopes:
        return "all_urls"
    if scopes & {"wild", "https_all", "http_all"}:
        return "broad_wildcard"
    if "specific" in scopes:
        return "specific_hosts"
    if "activeTab" in set(permissions or ()):
        return "active_tab_only"
    return "none"


def granted_patterns(record: dict) -> list:
    """Every pattern that already grants page access, from wherever this browser recorded it.

    Manifest V2 puts host patterns in `permissions` alongside API names, so those are separated
    here rather than being silently dropped or silently counted as APIs.
    """
    out = list(record.get("host_permissions") or [])
    out += list(record.get("content_matches") or [])
    out += list(record.get("granted_hosts") or [])
    out += [p for p in (record.get("permissions") or []) if pattern_scope(p)]
    return sorted(set(out))


def api_permissions(record: dict) -> list:
    return sorted({p for p in (record.get("permissions") or []) if not pattern_scope(p)})


def _host_names(patterns) -> list:
    """`https://mail.example.com/*` is a match pattern; `mail.example.com` is what a person reads."""
    out = []
    for p in patterns:
        host = str(p).split("://", 1)[-1].split("/", 1)[0].lstrip("*.")
        if host and host not in out:
            out.append(host)
    return out


def plain_english(reach: str, hosts, risky, mv2: bool) -> str:
    """The sentence a person can act on, with no jargon and no security-industry adjectives."""
    if reach == "all_urls":
        base = "can read and change everything you do on every site, including your bank"
    elif reach == "broad_wildcard":
        base = "can read and change pages across a wildcard slice of the web"
    elif reach == "specific_hosts":
        shown = ", ".join(_host_names(hosts)[:3])
        base = "can read and change pages on {0}{1}".format(
            shown or "the sites it names", " and more" if len(hosts) > 3 else "")
    elif reach == "active_tab_only":
        base = "can only touch the tab you are on, and only when you click it"
    elif reach == "none":
        base = "asks for no access to your pages at all"
    else:
        base = "does not publish what it can reach, so this is unknown rather than none"
    if risky:
        base += "; it can also " + DANGEROUS_REASON.get(risky[0], risky[0])
    if mv2:
        base += "; built on the extension platform Chrome no longer supports"
    return base


# ---------------------------------------------------------------- analysis

def analyse(records: list, now, cfg=None) -> dict:
    """Roll installs up into extensions, tier them by reach, and say what is unmaintained.

    The same extension in three browsers is one row with three badges. Reach, staleness and risk
    are merged worst-case across those installs, because the answer to "what can read my bank tab"
    does not improve when one of the three copies is a bit tamer.
    """
    cfg = cfg or {}
    stale_days = int(cfg.get("stale_days") or STALE_DAYS)
    idle_days = int(cfg.get("idle_days") or IDLE_DAYS)

    rows = {}
    per_browser = {}
    for record in sorted(records, key=lambda r: (r.get("browser", ""), r.get("profile", ""), r.get("id", ""))):
        per_browser[record.get("browser", "?")] = per_browser.get(record.get("browser", "?"), 0) + 1
        _fold(rows, record, now, stale_days, idle_days)

    ordered = sorted(rows.values(), key=lambda r: (-TIER_RANK.get(r["reach"], 0), -len(r["risky"]),
                                                   r["name"].lower(), r["id"]))
    for row in ordered:
        row["plain"] = plain_english(row["reach"], row["hosts"], row["risky"], row["mv2"])

    known = [r for r in ordered if r["reach_known"]]
    counts = {}
    for tier in TIERS:
        counts[tier] = sum(1 for r in known if r["reach"] == tier)
    total = len(ordered)
    blanket = counts["all_urls"] + counts["broad_wildcard"]

    combos = []
    for name in DANGEROUS_ORDER:
        hit = sorted((r["name"] for r in ordered if name in r["risky"]), key=lambda s: s.lower())
        if hit:
            combos.append({"permission": name, "reason": DANGEROUS_REASON[name],
                           "extensions": hit, "count": len(hit)})
    combo_rows = sorted({r["name"] for r in ordered if r["risky"]}, key=lambda s: s.lower())

    stale = [r for r in ordered if r["stale"]]
    idle = [r for r in ordered if r["idle"]]
    idle_reading = [r for r in idle if r["reach"] in ("all_urls", "broad_wildcard")]
    mv2 = [r for r in ordered if r["mv2"]]
    sideloaded = [r for r in ordered if r["install_source"] == "sideloaded"]
    policy = [r for r in ordered if r["install_source"] == "policy"]
    unpacked = [r for r in ordered if r["install_source"] == "unpacked"]

    buckets, labels = [0, 0, 0, 0, 0], ["this month", "3 months", "this year", "1-2 years", "older"]
    undated = 0
    for r in ordered:
        d = r["updated_days"]
        if d is None:
            undated += 1
            continue
        buckets[0 if d < 30 else 1 if d < 90 else 2 if d < 365 else 3 if d < 730 else 4] += 1

    current = dict((r["id"], TIER_RANK.get(r["reach"], 0)) for r in ordered)
    baseline = baseline_read(cfg.get("out_dir") or ".", "extension-reach")
    moved = delta(current, (baseline.get("payload") or {}).get("reach") or {})

    view = {
        "extensions": total,
        "installs": len(records),
        "browsers": [{"name": k, "installs": v} for k, v in sorted(per_browser.items(),
                                                                   key=lambda kv: (-kv[1], kv[0]))],
        "enabled": sum(1 for r in ordered if r["enabled"] is True),
        "disabled": sum(1 for r in ordered if r["enabled"] is False),
        "state_unknown": sum(1 for r in ordered if r["enabled"] is None),
        "reach": [{"tier": t, "label": TIER_LABEL[t], "extensions": counts[t],
                   "share": (counts[t] / len(known)) if known else 0.0} for t in TIERS],
        "reach_known": len(known),
        "reach_unknown": total - len(known),
        "reach_unknown_names": sorted((r["name"] for r in ordered if not r["reach_known"]),
                                      key=lambda s: s.lower()),
        "all_urls": counts["all_urls"],
        "blanket": blanket,
        "blanket_share": pct(blanket, len(known)),
        "combinations": combos,
        "combination_extensions": len(combo_rows),
        "combination_names": combo_rows,
        "stale": {"days": stale_days, "count": len(stale), "share": pct(len(stale), total),
                  "names": [r["name"] for r in stale][:12], "undated": undated,
                  "buckets": [{"label": l, "extensions": c} for l, c in zip(labels, buckets)],
                  "proxy": True,
                  "proxy_note": "last update is a proxy: the modification time of the extension's "
                                "version folder, which is when the browser last wrote that "
                                "version to disk, not a date the author published"},
        "idle": {"days": idle_days, "count": len(idle), "still_reading": len(idle_reading),
                 "names": [r["name"] for r in idle_reading][:12],
                 "note": "idle means no local extension state folder has changed in {0} days; the "
                         "folder's timestamp was read, never its contents".format(idle_days)},
        "mv2": {"count": len(mv2), "names": [r["name"] for r in mv2][:12]},
        "sideloaded": {"count": len(sideloaded), "names": [r["name"] for r in sideloaded][:12]},
        "policy": {"count": len(policy), "names": [r["name"] for r in policy][:12]},
        "unpacked": {"count": len(unpacked), "names": [r["name"] for r in unpacked][:12],
                     "note": "loaded unpacked by a developer: usually yours, usually fine"},
        "withheld": sum(1 for r in ordered if r["hosts_withheld"]),
        "cross_browser": sorted(({"name": r["name"], "id": r["id"], "browsers": r["browsers"]}
                                 for r in ordered if len(r["browsers"]) > 1),
                                key=lambda d: (-len(d["browsers"]), d["name"].lower())),
        "rows": ordered,
        "worst": ordered[:6],
        "delta": moved,
        "since": since_note(baseline, now),
        "never_read": "Manifests and settings metadata only. This Play never opens extension "
                      "storage: nothing under a Local Storage, IndexedDB, Local Extension "
                      "Settings or Cookies path is read, and idle detection uses a folder's "
                      "modification time rather than anything inside it.",
    }
    view["headline"] = _headline(view)
    view["verdict"] = _verdict(view)
    return view


def _fold(rows: dict, record: dict, now, stale_days: int, idle_days: int) -> None:
    """Merge one install into its extension row, worst case winning on every axis."""
    key = record.get("id") or record.get("name") or "?"
    patterns = granted_patterns(record)
    apis = api_permissions(record)
    published = record.get("reach_published", True)
    reach = reach_of(patterns, apis) if published else "unknown"
    hosts = sorted({p for p in patterns if pattern_scope(p) == "specific"})
    risky = [name for name in DANGEROUS_ORDER
             if name in apis and reach in ("all_urls", "broad_wildcard")]
    mv2 = record.get("manifest_version") == 2
    updated = _days(record.get("updated"), now)
    touched = _days(record.get("state_touched"), now)
    badge = record.get("browser", "?")

    row = rows.get(key)
    if row is None:
        row = {
            "id": key, "name": record.get("name") or key, "reach": reach,
            "reach_known": published, "reach_label": TIER_LABEL.get(reach, TIER_LABEL["unknown"]),
            "hosts": hosts, "host_count": len(hosts), "risky": risky,
            "permissions": apis, "optional_reach": reach_of(record.get("optional_host_permissions") or [], []),
            "browsers": [badge], "profiles": [record.get("profile", "")], "installs": 1,
            "enabled": record.get("enabled"), "enabled_in": 1 if record.get("enabled") else 0,
            "mv2": mv2, "manifest_version": record.get("manifest_version"),
            "version": record.get("version", ""),
            "install_source": record.get("install_source", "unknown"),
            "location_label": record.get("location_label", "unknown"),
            "installed": day_or_blank(record.get("installed")),
            "updated": day_or_blank(record.get("updated")),
            "updated_days": updated, "updated_is_proxy": bool(record.get("updated_is_proxy")),
            "updated_ago": _ago(record.get("updated"), now),
            "idle_days": touched, "hosts_withheld": bool(record.get("hosts_withheld")),
            "families": [record.get("family", "")],
        }
        rows[key] = row
    else:
        if TIER_RANK.get(reach, 0) > TIER_RANK.get(row["reach"], 0):
            row["reach"], row["reach_label"] = reach, TIER_LABEL.get(reach, TIER_LABEL["unknown"])
        row["reach_known"] = row["reach_known"] or published
        row["hosts"] = sorted(set(row["hosts"]) | set(hosts))
        row["host_count"] = len(row["hosts"])
        row["permissions"] = sorted(set(row["permissions"]) | set(apis))
        row["risky"] = [n for n in DANGEROUS_ORDER if n in set(row["risky"]) | set(risky)]
        row["mv2"] = row["mv2"] or mv2
        row["installs"] += 1
        row["enabled_in"] += 1 if record.get("enabled") else 0
        if record.get("enabled") is True:
            row["enabled"] = True
        if badge not in row["browsers"]:
            row["browsers"] = sorted(row["browsers"] + [badge])
        if record.get("profile") not in row["profiles"]:
            row["profiles"] = sorted(row["profiles"] + [record.get("profile", "")])
        if record.get("family") not in row["families"]:
            row["families"] = sorted(row["families"] + [record.get("family", "")])
        if updated is not None and (row["updated_days"] is None or updated < row["updated_days"]):
            row["updated_days"] = updated
            row["updated"] = day_or_blank(record.get("updated"))
            row["updated_ago"] = _ago(record.get("updated"), now)
            row["updated_is_proxy"] = bool(record.get("updated_is_proxy"))
        if touched is not None and (row["idle_days"] is None or touched < row["idle_days"]):
            row["idle_days"] = touched
        if row["install_source"] in ("unknown", "store") and \
                record.get("install_source") not in ("unknown", "store"):
            row["install_source"] = record.get("install_source", "unknown")
            row["location_label"] = record.get("location_label", "unknown")
        row["hosts_withheld"] = row["hosts_withheld"] or bool(record.get("hosts_withheld"))

    row["badges"] = " ".join("[{0}]".format(b) for b in row["browsers"])
    row["stale"] = row["updated_days"] is not None and row["updated_days"] >= stale_days
    row["idle"] = row["idle_days"] is not None and row["idle_days"] >= idle_days
    row["risk_reasons"] = [{"permission": n, "reason": DANGEROUS_REASON[n]} for n in row["risky"]]


def day_or_blank(stamp) -> str:
    from ..common import parse_date
    parsed = parse_date(stamp) if stamp else None
    return day(parsed) if parsed else ""


def _days(stamp, now):
    from ..common import parse_date
    parsed = parse_date(stamp) if stamp else None
    return age_days(parsed, now) if parsed else None


def _ago(stamp, now) -> str:
    from ..common import parse_date
    parsed = parse_date(stamp) if stamp else None
    return ago(parsed, now) if parsed else "unknown"


def _headline(v: dict) -> str:
    parts = ["{0}.".format(plural(v["extensions"], "extension"))]
    if v["all_urls"]:
        parts.append("{0} read every page including your bank.".format(v["all_urls"]))
    elif v["blanket"]:
        parts.append("{0} read a wildcard slice of the web.".format(v["blanket"]))
    if v["stale"]["count"]:
        window = "a year" if v["stale"]["days"] == 365 else "{0} days".format(v["stale"]["days"])
        parts.append("{0} not updated in {1}.".format(v["stale"]["count"], window))
    if v["idle"]["still_reading"]:
        parts.append("{0} unused for {1} days and still reading.".format(
            v["idle"]["still_reading"], v["idle"]["days"]))
    if len(parts) == 1:
        parts.append("None of them holds blanket access to your pages.")
    return " ".join(parts)


def _verdict(v: dict) -> str:
    if not v["extensions"]:
        return "no extensions found in any readable profile"
    if v["combination_extensions"]:
        return "{0} of {1} extensions pair blanket page access with a second power".format(
            v["combination_extensions"], v["extensions"])
    if v["blanket"]:
        return "{0} of {1} extensions can read every page, none with a second power".format(
            v["blanket"], v["extensions"])
    return "no extension holds blanket access to your pages"


def write_baseline(out_dir, view: dict, now) -> str:
    """Record this run's reach map so tomorrow's run can say what changed."""
    from ..common import baseline_write
    payload = {"reach": dict((r["id"], TIER_RANK.get(r["reach"], 0)) for r in view["rows"]),
               "names": dict((r["id"], r["name"]) for r in view["rows"])}
    return baseline_write(out_dir, "extension-reach", payload, now)


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg=None) -> str:
    from ..card import Card, legend, tier_bar

    cfg = cfg or {}
    c = Card("EXTENSION REACH", "{0} across {1}".format(
        plural(v["extensions"], "extension"), plural(len(v["browsers"]), "browser")), cfg.get("color"))
    c.blank()
    c.wrap(v["headline"])
    c.blank()

    tiers = [(TIER_LABEL[t["tier"]], t["extensions"]) for t in v["reach"]]
    c.rule("WHAT THEY CAN REACH")
    bar = tier_bar(tiers, 40)
    if bar:
        c.row(bar)
        c.wrap(legend(tiers))
    for tier in v["reach"]:
        if tier["extensions"]:
            c.bar(tier["label"], str(tier["extensions"]), tier["share"], label_w=26)
    if v["reach_unknown"]:
        c.wrap("{0} more could not be tiered: {1}. Unknown, not zero.".format(
            v["reach_unknown"], ", ".join(v["reach_unknown_names"][:3])))

    if v["combinations"]:
        c.rule("BLANKET ACCESS PLUS SOMETHING ELSE")
        for combo in v["combinations"][:5]:
            c.cols("{0}: {1}".format(combo["permission"], combo["reason"]), str(combo["count"]), 4)
        c.row("{0} of {1} extensions are in at least one of those classes".format(
            v["combination_extensions"], v["extensions"]))

    c.rule("STILL MAINTAINED?")
    stale, idle = v["stale"], v["idle"]
    c.row("{0} of {1} not updated in {2}+ days ({3}%)".format(
        stale["count"], v["extensions"], stale["days"], stale["share"]))
    if stale["undated"]:
        c.row("{0} carried no date at all and are left out of that share".format(stale["undated"]))
    c.row("{0} idle {1}+ days, {2} of those still holding blanket access".format(
        idle["count"], idle["days"], idle["still_reading"]))
    if v["mv2"]["count"]:
        c.row("{0} on Manifest V2, which Chrome no longer supports".format(v["mv2"]["count"]))
    flags = []
    if v["sideloaded"]["count"]:
        flags.append("{0} sideloaded".format(v["sideloaded"]["count"]))
    if v["policy"]["count"]:
        flags.append("{0} installed by policy".format(v["policy"]["count"]))
    if v["unpacked"]["count"]:
        flags.append("{0} unpacked (yours)".format(v["unpacked"]["count"]))
    if flags:
        c.row(" · ".join(flags))

    if v["worst"]:
        c.rule("WORST FIRST")
        for row in v["worst"][:5]:
            c.cols(row["name"], row["badges"], 22)
            c.wrap(row["plain"], "  ")

    if v["cross_browser"]:
        c.rule("SAME EXTENSION, MORE THAN ONE BROWSER")
        for item in v["cross_browser"][:4]:
            c.cols(item["name"], " ".join(item["browsers"]), 26)

    c.blank()
    c.row(v["since"] if v["delta"]["first_run"] else "{0}: {1} added, {2} removed, {3} gained reach".format(
        v["since"], len(v["delta"]["added"]), len(v["delta"]["removed"]), len(v["delta"]["grew"])))
    c.wrap("Read from the manifests and settings your browsers already wrote. No extension "
           "storage was opened.")
    return c.close()


def report_markdown(v: dict, cfg=None, sources=None) -> str:
    cfg, sources = cfg or {}, sources or []
    stale, idle = v["stale"], v["idle"]
    L = ["# Extension reach", "", v["headline"], "", v["verdict"] + ".", "",
         "| measure | value |", "|---|---|",
         "| extensions (unique ids) | {0} |".format(v["extensions"]),
         "| installs (id × browser × profile) | {0} |".format(v["installs"]),
         "| enabled / disabled / state unknown | {0} / {1} / {2} of {3} |".format(
             v["enabled"], v["disabled"], v["state_unknown"], v["extensions"]),
         "| can read every page | {0} of {1} |".format(v["all_urls"], v["extensions"]),
         "| blanket access (every page or wildcard) | {0} of {1} tiered ({2}%) |".format(
             v["blanket"], v["reach_known"], v["blanket_share"]),
         "| blanket access plus a second power | {0} of {1} |".format(
             v["combination_extensions"], v["extensions"]),
         "| not updated in {0}+ days | {1} of {2} ({3}%) |".format(
             stale["days"], stale["count"], v["extensions"], stale["share"]),
         "| no last-update date at all | {0} of {1} |".format(stale["undated"], v["extensions"]),
         "| idle {0}+ days | {1} of {2} |".format(idle["days"], idle["count"], v["extensions"]),
         "| idle and still holding blanket access | {0} of {1} |".format(
             idle["still_reading"], v["extensions"]),
         "| Manifest V2 | {0} of {1} |".format(v["mv2"]["count"], v["extensions"]),
         "| sideloaded | {0} of {1} |".format(v["sideloaded"]["count"], v["extensions"]),
         "| installed by policy | {0} of {1} |".format(v["policy"]["count"], v["extensions"]),
         "| unpacked (developer) | {0} of {1} |".format(v["unpacked"]["count"], v["extensions"]),
         "| host access withheld by you | {0} of {1} |".format(v["withheld"], v["extensions"]),
         "| reach not published by the browser | {0} of {1} |".format(
             v["reach_unknown"], v["extensions"]),
         "", "## Reach", "",
         "Sorted by reach, worst first. Shares are of the {0} extension(s) whose reach this "
         "machine could establish, not of all {1}.".format(v["reach_known"], v["extensions"]), "",
         "| tier | what it means | extensions | share of {0} |".format(v["reach_known"]), "|---|---|---|---|"]
    L += ["| {0} | {1} | {2} | {3}% |".format(t["tier"], t["label"], t["extensions"],
                                              pct(t["extensions"], v["reach_known"])) for t in v["reach"]]
    if v["reach_unknown"]:
        L += ["", "{0} extension(s) publish no reach information to a reader outside the browser: "
              "{1}. That is unknown, not zero.".format(
                  v["reach_unknown"], ", ".join(v["reach_unknown_names"]))]

    L += ["", "## Blanket access plus something else", ""]
    if v["combinations"]:
        L += ["Each row is its own class, named by what the second power actually does. An "
              "extension appears in every class it belongs to.", "",
              "| second power | what it lets the extension do | extensions | of {0} |".format(v["extensions"]),
              "|---|---|---|---|"]
        L += ["| {0} | {1} | {2} | {3} |".format(c["permission"], c["reason"],
                                                 ", ".join(c["extensions"]), c["count"])
              for c in v["combinations"]]
    else:
        L += ["None. No extension pairs blanket page access with a second power."]

    L += ["", "## Every extension", "",
          "| extension | reach | what that means | browsers | last update (proxy) | flags |",
          "|---|---|---|---|---|---|"]
    for row in v["rows"]:
        flags = []
        if row["mv2"]:
            flags.append("MV2")
        if row["stale"]:
            flags.append("stale")
        if row["idle"]:
            flags.append("idle")
        if row["install_source"] not in ("store", "unknown"):
            flags.append(row["install_source"])
        if row["enabled"] is False:
            flags.append("disabled")
        if row["hosts_withheld"]:
            flags.append("access withheld")
        L.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            row["name"], row["reach"], row["plain"], " ".join(row["browsers"]),
            "{0} ({1})".format(row["updated"] or "unknown", row["updated_ago"]),
            ", ".join(flags) or "—"))

    L += ["", "## Maintenance", "",
          stale["proxy_note"] + ".", "",
          "| last written | extensions | of {0} |".format(v["extensions"]), "|---|---|---|"]
    L += ["| {0} | {1} | {2}% |".format(b["label"], b["extensions"], pct(b["extensions"], v["extensions"]))
          for b in stale["buckets"]]
    L += ["| no date at all | {0} | {1}% |".format(stale["undated"], pct(stale["undated"], v["extensions"]))]
    L += ["", idle["note"] + "."]

    if v["cross_browser"]:
        L += ["", "## The same extension in more than one browser", "",
              "Counted once each, not once per browser.", "",
              "| extension | browsers |", "|---|---|"]
        L += ["| {0} | {1} |".format(x["name"], ", ".join(x["browsers"])) for x in v["cross_browser"]]

    d = v["delta"]
    L += ["", "## Since the last run", ""]
    if d["first_run"]:
        L += ["First run: nothing to compare against yet."]
    else:
        L += ["{0} ({1} added, {2} removed, {3} gained reach, {4} gave reach up).".format(
            v["since"], len(d["added"]), len(d["removed"]), len(d["grew"]), len(d["shrank"]))]

    L += ["", "## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"] if isinstance(s, dict) else s.name,
                                       "yes" if (s["found"] if isinstance(s, dict) else s.found) else "no",
                                       (s["note"] if isinstance(s, dict) else s.note) or "")
          for s in sources]
    L += ["", v["never_read"], ""]
    return "\n".join(L)
