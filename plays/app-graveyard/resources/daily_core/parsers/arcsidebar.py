"""Arc's sidebar store, which is JSON rather than a Chromium session log.

Arc keeps its spaces, folders and tabs in `StorableSidebar.json` as containers of heterogeneous
items: a flat list that alternates identifier strings with the objects they point at. A tab is
any object carrying `data.tab.savedURL`, so the reader walks for that shape rather than assuming
a nesting depth Arc is free to change between releases.
"""
import json


class Unreadable(Exception):
    pass


def read_session(data: bytes) -> dict:
    try:
        doc = json.loads(data.decode("utf-8", "replace"))
    except ValueError as exc:
        raise Unreadable("sidebar store is not JSON: {0}".format(exc))
    if not isinstance(doc, dict) or "sidebar" not in doc:
        raise Unreadable("no sidebar in the store")

    tabs, spaces, seen = [], set(), set()

    def visit(node, depth=0):
        if depth > 8:
            return
        if isinstance(node, list):
            for child in node:
                visit(child, depth + 1)
            return
        if not isinstance(node, dict):
            return
        tab = (node.get("data") or {}).get("tab") if isinstance(node.get("data"), dict) else None
        if isinstance(tab, dict) and tab.get("savedURL"):
            key = str(node.get("id") or len(tabs))
            if key not in seen:
                seen.add(key)
                space = str(node.get("parentID") or "")
                spaces.add(space)
                tabs.append({"tab_id": key, "window": 0, "index": len(tabs),
                             "url": str(tab.get("savedURL")), "title": str(tab.get("savedTitle") or ""),
                             "pinned": bool(node.get("childrenIds")), "grouped": bool(space),
                             "history_depth": None,
                             "navigated_at": tab.get("timeLastActiveAt"),
                             "active_at": tab.get("timeLastActiveAt")})
        for value in node.values():
            visit(value, depth + 1)

    visit(doc.get("sidebar"))
    return {"tabs": tabs, "windows": max(1, len(spaces)) if tabs else 0, "closed": 0, "commands": len(tabs)}
