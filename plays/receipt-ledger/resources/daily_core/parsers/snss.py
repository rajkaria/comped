"""Chrome-family session files (SNSS), read without Chrome.

Chromium writes the live tab set to `Sessions/Session_<ts>` as a command log, not a document:
a header, then a stream of small commands that each mutate one tab. Reconstructing the open tabs
means replaying the log, because the last navigation recorded for a tab is the page it is showing
and a tab closed later must not appear at all.

Layout, from chrome/browser/sessions/session_service_commands.cc and
components/sessions/core/command_storage_backend.cc:

    "SNSS" | int32 version | ( uint16 size | uint8 command_id | size-1 bytes payload )*

Payloads are either a packed C struct or a base::Pickle. A Pickle is a uint32 payload size
followed by fields, each padded to a four-byte boundary; strings are a length prefix and then
bytes (UTF-8) or UTF-16LE code units.

Version 2 is encrypted and is reported as such rather than guessed at.
"""
import struct

MAGIC = b"SNSS"
ENCRYPTED_VERSION = 2

CMD_SET_TAB_WINDOW = 0
CMD_TAB_INDEX_IN_WINDOW = 2
CMD_UPDATE_TAB_NAVIGATION = 6
CMD_SELECTED_NAVIGATION_INDEX = 7
CMD_SET_PINNED_STATE = 12
CMD_TAB_CLOSED = 16
CMD_WINDOW_CLOSED = 17
CMD_LAST_ACTIVE_TIME = 21
CMD_SET_TAB_GROUP = 25


class Unreadable(Exception):
    """The file is not an SNSS command log this reader can replay."""


class _Pickle:
    """A base::Pickle reader that refuses to read past its own declared payload."""

    __slots__ = ("buf", "pos", "end")

    def __init__(self, buf: bytes):
        if len(buf) < 4:
            raise Unreadable("pickle shorter than its header")
        declared = struct.unpack_from("<I", buf, 0)[0]
        self.buf = buf
        self.pos = 4
        # A declared size longer than the command is a version mismatch, not something to trust.
        self.end = min(len(buf), 4 + declared) if 0 < declared <= len(buf) - 4 else len(buf)

    def _take(self, n: int, align: bool = True) -> bytes:
        if n < 0 or self.pos + n > self.end:
            raise Unreadable("pickle field runs past the payload")
        b = self.buf[self.pos:self.pos + n]
        self.pos += n + ((-n) % 4 if align else 0)
        return b

    def int32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def uint32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def int64(self) -> int:
        return struct.unpack("<q", self._take(8))[0]

    def string(self, limit: int = 65536) -> str:
        n = self.int32()
        if n < 0 or n > limit:
            raise Unreadable("string length {0} is not plausible".format(n))
        return self._take(n).decode("utf-8", "replace")

    def string16(self, limit: int = 65536) -> str:
        n = self.int32()
        if n < 0 or n > limit:
            raise Unreadable("utf-16 string length {0} is not plausible".format(n))
        return self._take(n * 2).decode("utf-16-le", "replace")

    @property
    def left(self) -> int:
        return max(0, self.end - self.pos)


def commands(data: bytes):
    """Yield (command_id, payload) in file order. Stops at the first malformed record."""
    if not data.startswith(MAGIC):
        raise Unreadable("not an SNSS file")
    if len(data) < 8:
        raise Unreadable("SNSS header without a body")
    version = struct.unpack_from("<i", data, 4)[0]
    if version == ENCRYPTED_VERSION:
        raise Unreadable("session file is encrypted (version 2)")
    pos = 8
    n = len(data)
    while pos + 2 <= n:
        size = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        if size == 0 or pos + size > n:
            break        # a partial trailing write is normal: the browser is still running
        yield data[pos], data[pos + 1:pos + size]
        pos += size


def _struct_ids(payload: bytes):
    """Packed-struct payloads carry an int32 id first; alignment decides where the int64 sits."""
    if len(payload) < 4:
        return None, None
    first = struct.unpack_from("<i", payload, 0)[0]
    if len(payload) >= 16:
        return first, struct.unpack_from("<q", payload, 8)[0]
    if len(payload) >= 12:
        return first, struct.unpack_from("<q", payload, 4)[0]
    if len(payload) >= 8:
        return first, struct.unpack_from("<i", payload, 4)[0]
    return first, None


def read_session(data: bytes) -> dict:
    """Replay one session log into the tab set it describes.

    Returns {"tabs": [...], "windows": n, "closed": n, "commands": n}. A tab carries the URL and
    title of its selected navigation, its window, whether it is pinned, and the last time Chrome
    recorded it as active. Tabs closed by a later command are excluded, which is the whole reason
    the log has to be replayed rather than scanned for URLs.
    """
    navs = {}          # tab_id -> {index: (url, title, timestamp)}
    selected = {}      # tab_id -> selected navigation index
    windows = {}       # tab_id -> window_id
    order = {}         # tab_id -> index within its window
    pinned = set()
    grouped = {}
    active = {}
    closed = set()
    closed_windows = set()
    seen = 0

    for cid, payload in commands(data):
        seen += 1
        try:
            if cid == CMD_UPDATE_TAB_NAVIGATION:
                p = _Pickle(payload)
                tab_id = p.int32()
                index = p.int32()
                url = p.string()
                title = p.string16()
                navs.setdefault(tab_id, {})[index] = (url, title, _navigation_time(p))
            elif cid == CMD_SELECTED_NAVIGATION_INDEX:
                tab_id, index = _struct_ids(payload)
                if tab_id is not None and index is not None:
                    selected[tab_id] = index
            elif cid == CMD_SET_TAB_WINDOW:
                if len(payload) >= 8:
                    window_id, tab_id = struct.unpack_from("<ii", payload, 0)
                    windows[tab_id] = window_id
            elif cid == CMD_TAB_INDEX_IN_WINDOW:
                tab_id, index = _struct_ids(payload)
                if tab_id is not None and index is not None:
                    order[tab_id] = index
            elif cid == CMD_SET_PINNED_STATE:
                if len(payload) >= 5:
                    tab_id = struct.unpack_from("<i", payload, 0)[0]
                    (pinned.add if payload[4] else pinned.discard)(tab_id)
            elif cid == CMD_SET_TAB_GROUP:
                if len(payload) >= 4:
                    grouped[struct.unpack_from("<i", payload, 0)[0]] = payload[4:20].hex() or ""
            elif cid == CMD_LAST_ACTIVE_TIME:
                tab_id, when = _struct_ids(payload)
                if tab_id is not None and when:
                    active[tab_id] = when
            elif cid == CMD_TAB_CLOSED:
                tab_id, _ = _struct_ids(payload)
                if tab_id is not None:
                    closed.add(tab_id)
            elif cid == CMD_WINDOW_CLOSED:
                window_id, _ = _struct_ids(payload)
                if window_id is not None:
                    closed_windows.add(window_id)
        except (Unreadable, struct.error):
            continue      # one command this build writes differently is not a reason to lose the rest

    tabs = []
    for tab_id, entries in navs.items():
        if tab_id in closed or windows.get(tab_id) in closed_windows or not entries:
            continue
        index = selected.get(tab_id)
        if index not in entries:
            index = max(entries)
        url, title, stamp = entries[index]
        if not url or url.startswith(("chrome://newtab", "about:newtab")):
            continue
        tabs.append({"tab_id": tab_id, "window": windows.get(tab_id, 0), "index": order.get(tab_id, 0),
                     "url": url, "title": title, "pinned": tab_id in pinned,
                     "grouped": tab_id in grouped, "history_depth": len(entries),
                     "navigated_at": stamp, "active_at": active.get(tab_id)})
    tabs.sort(key=lambda t: (t["window"], t["index"], t["tab_id"]))
    return {"tabs": tabs, "windows": len({t["window"] for t in tabs}),
            "closed": len(closed), "commands": seen}


def _navigation_time(p: _Pickle):
    """The navigation timestamp, when this Chrome build wrote the fields that precede it.

    SerializedNavigationEntry appends fields over time and older files simply stop early. Reading
    the tail is therefore attempted and abandoned, never required: a tab with no timestamp is
    reported with none rather than with a plausible-looking wrong one.
    """
    try:
        p.string()      # encoded page state, empty in recent versions
        p.int32()       # transition type
        p.int32()       # type mask
        p.string()      # referrer url
        p.int32()       # referrer policy
        p.string()      # original request url
        p.int32()       # is_overriding_user_agent
        if p.left < 8:
            return None
        value = p.int64()
        return value if 0 < value < 20000000000000000 else None
    except (Unreadable, struct.error):
        return None
