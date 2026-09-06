"""The macOS Photos asset table, read through whatever columns this particular macOS happens to have.

Photos.sqlite is a Core Data store, and Core Data renames its columns whenever the managed object
model changes. The same logical field is `ZDATECREATED` on one release, `Z54_DATECREATED` on the
next, `ZDATECREATED1` after a migration, and simply absent on a third. A hard-coded SELECT is
therefore a bug with a release date on it: it works until the user upgrades, and then it raises
`no such column` and the Play dies on the one machine it was written for.

So nothing here names a column it has not first seen. `bind` asks the database what it actually has
(`PRAGMA table_info`) and attaches each logical field to the first physical column that can
plausibly be it, comparing exact names first and then names normalised for the two decorations Core
Data adds — a `Z<entity>_` prefix and a migration suffix. Every logical field that finds no column
is returned in `missing`, the caller reports that one fact as unknown, and the scan continues. A
schema this module has never seen produces a partial answer with a note; it never produces an
exception, and it never produces a confident wrong number.

Nothing in this file writes to the library. The only removal it performs is of the temporary copy
that `common.open_sqlite_readonly` made of the database, which is the whole reason the live library
is never opened, locked or migrated by being looked at.
"""
import re
import shutil

from ..common import from_apple, iso

TABLE = "ZASSET"

# Each logical field, and the physical columns that have carried it. Order is preference order:
# the first candidate that exists wins, so a schema carrying both an old and a new spelling binds
# to the one this module understands best rather than to whichever came first in the table.
FIELDS = (
    ("pk", ("Z_PK",)),
    ("uuid", ("ZUUID",)),
    ("captured", ("ZDATECREATED", "ZCREATIONDATE", "ZCAPTUREDATE")),
    ("added", ("ZADDEDDATE", "ZDATEADDED", "ZIMPORTDATE")),
    ("viewed", ("ZLASTVIEWEDDATE", "ZLASTVIEWEDTIMESTAMP", "ZLASTVIEWEDATDATE")),
    ("width", ("ZWIDTH", "ZPIXELWIDTH")),
    ("height", ("ZHEIGHT", "ZPIXELHEIGHT")),
    ("filename", ("ZFILENAME", "ZORIGINALFILENAME")),
    ("directory", ("ZDIRECTORY",)),
    ("favourite", ("ZFAVORITE", "ZISFAVORITE", "ZFAVOURITE")),
    ("edited", ("ZHASADJUSTMENTS", "ZHASADJUSTMENT", "ZADJUSTMENTTIMESTAMP")),
    ("trashed", ("ZTRASHEDSTATE", "ZTRASHED", "ZTRASHEDDATE")),
    ("kind", ("ZKIND", "ZMEDIATYPE", "ZASSETTYPE")),
    ("subtype", ("ZKINDSUBTYPE", "ZSUBTYPE")),
    ("saved_type", ("ZSAVEDASSETTYPE",)),
    ("uti", ("ZUNIFORMTYPEIDENTIFIER", "ZUTI", "ZCONTENTTYPE")),
    ("bytes", ("ZORIGINALFILESIZE", "ZFILESIZE", "ZDATALENGTH")),
    ("local", ("ZLOCALLYAVAILABLE", "ZLOCALAVAILABILITY", "ZCLOUDLOCALSTATE")),
    ("burst_id", ("ZAVALANCHEUUID", "ZBURSTIDENTIFIER")),
)

LOGICAL = tuple(name for name, _ in FIELDS)

# What the library calls a screenshot. Two different columns have carried the answer across
# releases and neither is present on every schema, so the file name is kept as a third opinion —
# stated in the report rather than hidden, because a screenshot count is only as good as its test.
SCREENSHOT_SAVED_TYPES = (3,)
SCREENSHOT_SUBTYPES = (10,)
SCREENSHOT_NAME = re.compile(r"^(screenshot|screen shot|cleanshot|shottr|scr-|simulator screen shot)", re.I)

VIDEO_KINDS = (1,)
VIDEO_EXT = (".mov", ".mp4", ".m4v", ".avi", ".mpg", ".mpeg", ".mkv", ".webm", ".3gp")
VIDEO_UTI = ("movie", "video", "mpeg-4", "quicktime")

_ENTITY_PREFIX = re.compile(r"^Z\d+_")
_MIGRATION_SUFFIX = re.compile(r"\d+$")


def blank() -> dict:
    """The normalized asset shape. One definition, so the folder scanner cannot drift from the database."""
    return {
        "id": "", "filename": "", "stem": "", "ext": "", "dir": "", "path": "", "sha256": "",
        "captured": "", "added": "", "viewed": "", "width": 0, "height": 0,
        "favourite": False, "edited": False, "trashed": False, "video": False, "screenshot": False,
        "uti": "", "bytes": 0, "local": True, "burst_id": "", "source": "", "unknown": [],
    }


def asset(**kw) -> dict:
    rec = blank()
    rec.update(kw)
    return rec


# ---------------------------------------------------------------- the probe

def normalise(column: str) -> str:
    """`Z54_DATECREATED` and `ZDATECREATED1` are both the field spelled `ZDATECREATED`."""
    c = str(column or "").upper()
    c = _ENTITY_PREFIX.sub("Z", c)
    return _MIGRATION_SUFFIX.sub("", c)


def table_columns(conn, table: str = TABLE) -> list:
    """The physical column names, in table order, or [] when the table is not there at all."""
    try:
        rows_ = conn.execute('PRAGMA table_info("{0}")'.format(str(table).replace('"', ""))).fetchall()
    except Exception:
        return []
    return [str(r[1]) for r in rows_]


def bind(conn, table: str = TABLE) -> dict:
    """Resolve every logical field against the columns this database actually has.

    Returns {"table", "columns", "map", "missing", "ok", "note"}. `map` is logical -> physical for
    the fields that resolved; `missing` lists the ones that did not, which is the caller's cue to
    report those facts as unknown rather than as zero.
    """
    columns = table_columns(conn, table)
    out = {"table": table, "columns": columns, "map": {}, "missing": [], "ok": bool(columns), "note": ""}
    if not columns:
        out["missing"] = list(LOGICAL)
        out["note"] = "no {0} table in this database".format(table)
        return out

    exact, loose = {}, {}
    for c in columns:
        exact.setdefault(c.upper(), c)
        loose.setdefault(normalise(c), c)

    for logical, candidates in FIELDS:
        chosen = ""
        for cand in candidates:
            if cand.upper() in exact:
                chosen = exact[cand.upper()]
                break
        if not chosen:
            for cand in candidates:
                key = normalise(cand)
                if key in loose:
                    chosen = loose[key]
                    break
        if chosen:
            out["map"][logical] = chosen
        else:
            out["missing"].append(logical)
    if out["missing"]:
        out["note"] = "unresolved on this schema: {0}".format(", ".join(out["missing"]))
    return out


def rows(conn, mapping: dict, budget=None):
    """Yield normalized asset dicts for every row the budget allows.

    Only bound columns are selected, so a schema missing half of them is a shorter SELECT rather
    than a failed one. A query that still fails — a locked page, a corrupt b-tree, a column type
    the driver refuses — ends the generator quietly; the caller already knows how many rows it got.
    """
    m = (mapping or {}).get("map") or {}
    if not m:
        return
    names = sorted(m)
    table = str((mapping or {}).get("table") or TABLE).replace('"', "")
    select = ", ".join('"{0}"'.format(m[n].replace('"', "")) for n in names)
    sql = 'SELECT {0} FROM "{1}"'.format(select, table)
    if "pk" in m:
        sql += ' ORDER BY "{0}"'.format(m["pk"].replace('"', ""))
    try:
        cursor = conn.execute(sql)
    except Exception:
        return
    seq = 0
    while True:
        try:
            batch = cursor.fetchmany(500)
        except Exception:
            return
        if not batch:
            return
        for row in batch:
            seq += 1
            if budget is not None and not budget.spend(0):
                return
            yield _normalize(dict(zip(names, tuple(row))), seq, mapping.get("missing") or [])


def read_library(db_path, budget=None, table: str = TABLE) -> tuple:
    """Copy the database, bind it, drain it, and remove the copy. Returns (mapping, records, note).

    The copy is what makes this read-only in the strong sense: the live library is never opened, so
    it is never locked, never journalled and never migrated to a newer store version by being read.
    Removing that copy afterwards is the only deletion anywhere in photo-debt, and it deletes a file
    this process made moments earlier in a temporary directory. No path from the user's library ever
    reaches it.
    """
    from ..common import open_sqlite_readonly
    con = tmp = None
    try:
        con, tmp = open_sqlite_readonly(db_path)
        mapping = bind(con, table)
        if not mapping["ok"]:
            return mapping, [], mapping["note"]
        records = list(rows(con, mapping, budget))
        bound = len(mapping["map"])
        note = "{0}/{1} fields bound".format(bound, len(LOGICAL))
        if mapping["missing"]:
            note += "; {0}".format(mapping["note"])
        return mapping, records, note
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- normalization

def _normalize(raw: dict, seq: int, missing) -> dict:
    name = _text(raw.get("filename"))
    stem, ext = _split(name)
    uti = _text(raw.get("uti"))
    if "." not in uti:
        # Newer schemas store the type as a foreign key into a separate table rather than as text.
        # An integer is not a type identifier, and pretending otherwise would mislabel every asset.
        uti = ""
    video = _is_video(raw.get("kind"), uti, ext)
    return asset(
        id=_text(raw.get("uuid")) or _text(raw.get("pk")) or "row-{0}".format(seq),
        filename=name, stem=stem, ext=ext, dir=_text(raw.get("directory")),
        captured=iso(from_apple(raw.get("captured"))),
        added=iso(from_apple(raw.get("added"))),
        viewed=iso(from_apple(raw.get("viewed"))),
        width=_int(raw.get("width")), height=_int(raw.get("height")),
        favourite=_flag(raw.get("favourite")), edited=_flag(raw.get("edited")),
        trashed=_flag(raw.get("trashed")), video=video,
        screenshot=(not video) and _is_screenshot(raw.get("saved_type"), raw.get("subtype"), name),
        uti=uti, bytes=_int(raw.get("bytes")),
        local=True if "local" not in raw else _flag(raw.get("local")),
        burst_id=_text(raw.get("burst_id")), source="photos", unknown=sorted(missing),
    )


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", "replace").strip()
        except Exception:
            return ""
    return str(v).strip()


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _flag(v) -> bool:
    """A flag column has been an integer, a boolean and a timestamp. All three mean the same thing."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = _text(v).lower()
    return s not in ("", "0", "false", "no", "none", "null")


def _split(name: str) -> tuple:
    n = str(name or "")
    if "." in n[1:]:
        i = n.rindex(".")
        return n[:i], n[i:].lower()
    return n, ""


def _is_video(kind, uti: str, ext: str) -> bool:
    if _int(kind) in VIDEO_KINDS and kind is not None:
        return True
    low = (uti or "").lower()
    if any(tag in low for tag in VIDEO_UTI):
        return True
    return ext in VIDEO_EXT


def _is_screenshot(saved_type, subtype, name: str) -> bool:
    if saved_type is not None and _int(saved_type) in SCREENSHOT_SAVED_TYPES:
        return True
    if subtype is not None and _int(subtype) in SCREENSHOT_SUBTYPES:
        return True
    return bool(SCREENSHOT_NAME.match(str(name or "").strip()))
