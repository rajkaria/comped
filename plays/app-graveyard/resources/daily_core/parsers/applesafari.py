"""Safari's session and reading list, both of which are property lists the standard library reads.

Safari keeps `LastSession.plist` and `Bookmarks.plist` inside a container macOS protects: without
Full Disk Access for the running terminal, opening either raises PermissionError. That is a real
answer and the scanners report it as one, with the remedy, rather than reporting zero tabs.
"""
import plistlib


class Unreadable(Exception):
    pass


def _load(data: bytes):
    try:
        return plistlib.loads(data)
    except Exception as exc:                       # plistlib raises several unrelated types
        raise Unreadable("not a readable property list: {0}".format(exc))


def read_session(data: bytes) -> dict:
    """LastSession.plist -> the same tab shape the Chrome and Firefox readers return."""
    doc = _load(data)
    if not isinstance(doc, dict):
        raise Unreadable("session plist is not a dictionary")
    tabs, windows = [], 0
    for w_index, window in enumerate(doc.get("SessionWindows") or []):
        if not isinstance(window, dict):
            continue
        windows += 1
        for t_index, tab in enumerate(window.get("TabStates") or []):
            if not isinstance(tab, dict):
                continue
            url = str(tab.get("TabURL") or tab.get("URL") or "")
            if not url or url in ("about:blank", "favorites://"):
                continue
            tabs.append({"tab_id": "{0}:{1}".format(w_index, t_index), "window": w_index, "index": t_index,
                         "url": url, "title": str(tab.get("TabTitle") or tab.get("TitleWithSuffix") or ""),
                         "pinned": bool(tab.get("IsPinned") or window.get("IsPinnedTab")),
                         "grouped": bool(window.get("TabGroupUUID") or window.get("TabGroupTitle")),
                         # Safari keeps the back-stack in an opaque blob: depth is unknown, not zero.
                         "history_depth": None,
                         "navigated_at": tab.get("LastVisitTime"), "active_at": tab.get("LastVisitTime")})
    return {"tabs": tabs, "windows": windows, "closed": 0, "commands": len(tabs)}


def read_reading_list(data: bytes) -> list:
    """Bookmarks.plist -> the reading list, which is the backlog nobody remembers subscribing to."""
    doc = _load(data)
    out = []

    def walk(node, in_list: bool):
        if isinstance(node, list):
            for child in node:
                walk(child, in_list)
            return
        if not isinstance(node, dict):
            return
        title = str(node.get("Title") or "")
        here = in_list or title == "com.apple.ReadingList"
        entry = node.get("ReadingList")
        if here and isinstance(entry, dict) and node.get("URLString"):
            names = node.get("URIDictionary") or {}
            out.append({"url": str(node.get("URLString")),
                        "title": str(names.get("title") or "") if isinstance(names, dict) else "",
                        "added": entry.get("DateAdded"), "viewed": entry.get("DateLastViewed"),
                        "unread": entry.get("DateLastViewed") is None})
        for child in node.get("Children") or []:
            walk(child, here)

    walk(doc, False)
    return out
