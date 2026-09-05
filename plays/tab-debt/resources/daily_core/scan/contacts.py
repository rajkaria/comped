"""birthday-radar: the birthdays already in your address book, sorted by how soon they are.

Contacts apps store the date and then never mention it again until the morning of. This reads the
address book you already have, three ways, and answers two questions a contact list cannot: whose
birthday is next, and how much of the book has no birthday at all — because a radar that quietly
covers a third of your contacts is worse than one that says which third it cannot see.
"""
import csv as csvmod
import os
import shutil
from datetime import date, timedelta

from ..common import (Budget, Source, expand, from_apple, iso, parse_date, pct, read_text,
                      redact_name, walk)
from ..parsers.vcard import parse as parse_vcard, parse_bday

KINDS = ("addressbook", "vcard", "csv")
ABOOK = "~/Library/Application Support/AddressBook/Sources"


def _person(name, org="", bday="", emails=(), tels=(), updated=None, created=None, source=""):
    return {"name": name or "", "org": org or "", "bday": bday or "", "emails": sorted(set(emails)),
            "tels": sorted(set(tels)), "updated": iso(updated) if updated else "",
            "created": iso(created) if created else "", "source": source}


def read_source(kind: str, budget: Budget, cfg: dict) -> tuple:
    if cfg.get("demo_root"):
        # One fixture, read by one source: letting all three read it would triple every contact.
        if kind != "vcard":
            return [Source(name="{0} (demo)".format(kind)).hit(0, "the demo reads one address book")], []
        return _read_vcard_paths([expand(cfg["demo_root"]) / "contacts.vcf"], budget, "demo")
    if kind == "addressbook":
        return _read_addressbook(budget)
    if kind == "vcard":
        return _read_vcard_dir(cfg.get("vcard_dir") or "~/Documents", budget)
    if kind == "csv":
        return _read_csv_dir(cfg.get("csv_path") or "", budget)
    return [Source(name=kind).miss("unknown source")], []


# ---------------------------------------------------------------- macOS Contacts

def _read_addressbook(budget: Budget) -> tuple:
    """The Contacts database, copied and reopened read-only so the live one is never touched."""
    from ..common import open_sqlite_readonly
    root = expand(ABOOK)
    src = Source(name="macOS Contacts", path=str(root))
    # os.access consults the permission bits, which TCC does not touch: a folder macOS is hiding
    # answers "readable" and then refuses to be listed. Only an actual listdir tells the truth.
    try:
        children = sorted(root.iterdir())
    except PermissionError as exc:
        return [src.miss(_tcc(exc, root))], []
    except (OSError, FileNotFoundError):
        return [src.miss("no Contacts database in this account")], []
    stores = []
    for child in children:
        try:
            stores += sorted(child.glob("AddressBook-v22.abcddb"))
        except PermissionError:
            return [src.miss(_tcc(PermissionError(), root))], []
        except OSError:
            continue
    if not stores:
        return [src.miss("no address book database in this account")], []

    people, notes = [], []
    for store in stores:
        con = tmp = None
        try:
            con, tmp = open_sqlite_readonly(store)
            rows = con.execute(
                "SELECT ZFIRSTNAME, ZLASTNAME, ZORGANIZATION, ZBIRTHDAY, ZCREATIONDATE, ZMODIFICATIONDATE, Z_PK "
                "FROM ZABCDRECORD").fetchall()
            mails = _multi(con, "ZABCDEMAILADDRESS", "ZADDRESS")
            phones = _multi(con, "ZABCDPHONENUMBER", "ZFULLNUMBER")
            for r in rows:
                name = " ".join(x for x in (r["ZFIRSTNAME"], r["ZLASTNAME"]) if x)
                if not name and not r["ZORGANIZATION"]:
                    continue
                bday = from_apple(r["ZBIRTHDAY"])
                people.append(_person(name or r["ZORGANIZATION"], r["ZORGANIZATION"],
                                      bday.strftime("%Y-%m-%d") if bday else "",
                                      mails.get(r["Z_PK"], []), phones.get(r["Z_PK"], []),
                                      from_apple(r["ZMODIFICATIONDATE"]), from_apple(r["ZCREATIONDATE"]),
                                      "macOS Contacts"))
            budget.spend(store.stat().st_size)
        except (OSError, PermissionError) as exc:
            notes.append(_tcc(exc, store))
        except Exception as exc:                       # sqlite3 raises several unrelated types
            notes.append("database unreadable: {0}".format(str(exc)[:70]))
        finally:
            if con is not None:
                con.close()
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
    if not people and notes:
        return [src.miss(notes[0])], []
    return [src.hit(len(people), "{0} store(s)".format(len(stores)))], people


def _multi(con, table: str, column: str) -> dict:
    """Emails and phone numbers hang off the record by owner id; a missing table is not an error."""
    out = {}
    try:
        for row in con.execute("SELECT ZOWNER, {0} FROM {1}".format(column, table)):
            if row[1]:
                out.setdefault(row[0], []).append(str(row[1]).strip().lower())
    except Exception:
        return out
    return out


def _tcc(exc, path) -> str:
    if isinstance(exc, PermissionError) or (path and os.path.exists(path) and not os.access(path, os.R_OK)):
        return "macOS blocked the read; grant Full Disk Access, or point vcard_dir at an export"
    if not os.path.exists(str(path)):
        return "no Contacts database in this account"
    return str(exc)[:100]


# ---------------------------------------------------------------- files

def _read_vcard_dir(where, budget: Budget) -> tuple:
    root = expand(where)
    src = Source(name="vCard files", path=str(root))
    if not root.exists():
        return [src.miss("no folder at {0}".format(where))], []
    if root.is_file():
        return _read_vcard_paths([root], budget, str(root))
    paths = [p for p, st, _ in walk(root, budget) if p.suffix.lower() in (".vcf", ".vcard")]
    if not paths:
        return [src.miss("no .vcf files under {0}".format(where))], []
    return _read_vcard_paths(paths, budget, str(root))


def _read_vcard_paths(paths, budget: Budget, label: str) -> tuple:
    people, files = [], 0
    for p in paths:
        text = read_text(p, 8 * 1024 * 1024)
        if not text:
            continue
        budget.spend(len(text))
        files += 1
        for card in parse_vcard(text):
            people.append(_person(card["name"], card["org"], card["bday"], card["emails"], card["tels"],
                                  parse_date(card["rev"]), None, p.name))
    src = Source(name="vCard files", path=label)
    if not files:
        return [src.miss("no readable .vcf file")], []
    return [src.hit(len(people), "{0} file(s)".format(files))], people


def _read_csv_dir(where, budget: Budget) -> tuple:
    """A contacts export from Google, Outlook or anything else: columns are matched by name."""
    src = Source(name="CSV export", path=str(where or ""))
    if not where:
        return [src.miss("no csv_path given")], []
    path = expand(where)
    if not path.is_file():
        return [src.miss("no file at {0}".format(where))], []
    text = read_text(path, 16 * 1024 * 1024)
    budget.spend(len(text))
    rows = list(csvmod.DictReader(text.splitlines()))
    if not rows:
        return [src.miss("no rows in the export")], []

    def pick(row, *needles):
        for key, value in row.items():
            k = (key or "").strip().lower()
            if value and any(n in k for n in needles):
                return str(value).strip()
        return ""

    people = []
    for row in rows:
        name = pick(row, "display name", "full name") or " ".join(
            x for x in (pick(row, "first name", "given name"), pick(row, "last name", "family name")) if x)
        bday = pick(row, "birthday", "birth date", "bday")
        if not name and not bday:
            continue
        people.append(_person(name, pick(row, "organization", "company"), bday,
                              [e.lower() for e in pick(row, "e-mail", "email").replace(";", " ").split() if "@" in e],
                              [pick(row, "phone")], None, None, path.name))
    return [src.hit(len(people), path.name)], people


# ---------------------------------------------------------------- analysis

def analyse(people: list, now, horizon: int, redact: bool) -> dict:
    today = now.date()
    with_bday, upcoming = [], []
    for person in people:
        parsed = parse_bday(person.get("bday"))
        if not parsed:
            continue
        month, dayn, year = parsed
        with_bday.append(person)
        nxt = _next_occurrence(today, month, dayn)
        if nxt is None:
            continue
        away = (nxt - today).days
        if away <= horizon:
            upcoming.append({"name": redact_name(person["name"], redact), "org": person.get("org", ""),
                             "date": nxt.isoformat(), "weekday": nxt.strftime("%a"), "in_days": away,
                             "turning": (nxt.year - year) if year else None,
                             "today": away == 0, "source": person.get("source", "")})
    upcoming.sort(key=lambda u: (u["in_days"], u["name"]))

    seen, dupes = {}, []
    for person in people:
        key = "".join(ch for ch in person["name"].lower() if ch.isalnum())
        if key:
            seen.setdefault(key, []).append(person)
    for key, group in sorted(seen.items()):
        if len(group) > 1:
            dupes.append({"name": redact_name(group[0]["name"], redact), "copies": len(group),
                          "sources": sorted({g.get("source", "") for g in group})})

    stale = [p for p in people if p.get("updated") and (now - parse_date(p["updated"])).days > 365 * 3]
    no_year = sum(1 for p in with_bday if (parse_bday(p["bday"]) or (0, 0, 1))[2] is None)
    return {
        "people": len(people), "with_birthday": len(with_bday),
        "missing": len(people) - len(with_bday), "missing_share": pct(len(people) - len(with_bday), len(people)),
        "no_year": no_year, "horizon": horizon,
        "today": [u for u in upcoming if u["today"]],
        "upcoming": upcoming[:12], "upcoming_total": len(upcoming),
        "this_month": sum(1 for u in upcoming if u["in_days"] <= 31),
        "next": upcoming[0] if upcoming else None,
        "duplicates": dupes[:8], "duplicate_total": len(dupes),
        "stale": len(stale), "no_contact_detail": sum(1 for p in people if not p["emails"] and not p["tels"]),
        "months": _month_histogram(with_bday),
    }


def _next_occurrence(today: date, month: int, dayn: int):
    """The next time that date comes round, with 29 February landing on the 28th in common years."""
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, dayn)
        except ValueError:
            try:
                candidate = date(year, month, dayn - 1)
            except ValueError:
                return None
        if candidate >= today:
            return candidate
    return None


def _month_histogram(people: list) -> list:
    counts = [0] * 12
    for person in people:
        parsed = parse_bday(person["bday"])
        if parsed:
            counts[parsed[0] - 1] += 1
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return [{"month": n, "count": c} for n, c in zip(names, counts)]


# ---------------------------------------------------------------- presentation

def render(v: dict, cfg: dict) -> str:
    from ..card import Card, sparkline

    c = Card("BIRTHDAY RADAR", "next {0} days".format(v["horizon"]), cfg.get("color"))
    c.blank()
    if v["today"]:
        c.headline("TODAY: {0}".format(", ".join(u["name"] for u in v["today"])), "1;33")
    n = v["next"]
    if n:
        c.headline("{0} in {1}".format(n["name"], "0 days — today" if n["in_days"] == 0 else
                                       "1 day — tomorrow" if n["in_days"] == 1 else
                                       "{0} days, {1} {2}".format(n["in_days"], n["weekday"], n["date"])), "1;36")
        if n["turning"]:
            c.row("  turning {0}".format(n["turning"]))
    else:
        c.headline("no birthday falls in the next {0} days".format(v["horizon"]))
    c.row("{0} contacts · {1} with a birthday · {2} without ({3}%)".format(
        v["people"], v["with_birthday"], v["missing"], v["missing_share"]))
    c.blank()

    if v["upcoming"]:
        c.rule("COMING UP")
        for u in v["upcoming"][:8]:
            when = "today" if u["in_days"] == 0 else "tomorrow" if u["in_days"] == 1 else "{0}d".format(u["in_days"])
            age = "  turns {0}".format(u["turning"]) if u["turning"] else ""
            c.cols("{0}{1}".format(u["name"], age), "{0} {1}".format(u["weekday"], when), 16)
        if v["upcoming_total"] > 8:
            c.row("+{0} more inside the window".format(v["upcoming_total"] - 8))

    c.rule("THE BOOK")
    spark = sparkline([m["count"] for m in v["months"]])
    if spark:
        c.row("birthdays by month  {0}".format(spark))
        c.row("                    J F M A M J J A S O N D")
    if v["no_year"]:
        c.row("{0} carr{1} no year, so no age is shown for {2}".format(
            "1 birthday" if v["no_year"] == 1 else "{0} birthdays".format(v["no_year"]),
            "ies" if v["no_year"] == 1 else "y", "it" if v["no_year"] == 1 else "them"))
    if v["duplicate_total"]:
        c.row("{0} appear{1} more than once".format(
            "1 name" if v["duplicate_total"] == 1 else "{0} names".format(v["duplicate_total"]),
            "s" if v["duplicate_total"] == 1 else ""))
        for d in v["duplicates"][:3]:
            c.cols("  {0}".format(d["name"]), "{0} copies".format(d["copies"]), 12)
    if v["no_contact_detail"]:
        c.row("{0} ha{1} neither an email nor a number".format(
            "1 contact" if v["no_contact_detail"] == 1 else "{0} contacts".format(v["no_contact_detail"]),
            "s" if v["no_contact_detail"] == 1 else "ve"))
    if v["stale"]:
        c.row("{0} untouched for more than three years".format(v["stale"]))

    c.blank()
    c.wrap("Read from your own address book. Names are shown as initials unless redact=false, "
           "and no email address or number is ever printed.")
    return c.close()


def report_markdown(v: dict, cfg: dict, sources: list) -> str:
    L = ["# Birthday radar", "",
         "{0} contacts, {1} with a birthday. {2} fall in the next {3} days.".format(
             v["people"], v["with_birthday"], v["upcoming_total"], v["horizon"]), "",
         "| measure | value |", "|---|---|",
         "| contacts | {0} |".format(v["people"]),
         "| with a birthday | {0} |".format(v["with_birthday"]),
         "| without one | {0} ({1}%) |".format(v["missing"], v["missing_share"]),
         "| birthday with no year | {0} |".format(v["no_year"]),
         "| duplicate names | {0} |".format(v["duplicate_total"]),
         "| no email and no number | {0} |".format(v["no_contact_detail"]), ""]
    if v["upcoming"]:
        L += ["## Coming up", "", "| who | date | in | turning |", "|---|---|---|---|"]
        L += ["| {0} | {1} ({2}) | {3}d | {4} |".format(u["name"], u["date"], u["weekday"], u["in_days"],
                                                        u["turning"] or "-") for u in v["upcoming"]]
        L.append("")
    if v["duplicates"]:
        L += ["## Names that appear more than once", "", "| name | copies |", "|---|---|"]
        L += ["| {0} | {1} |".format(d["name"], d["copies"]) for d in v["duplicates"]]
        L.append("")
    L += ["## Sources", "", "| source | read | detail |", "|---|---|---|"]
    L += ["| {0} | {1} | {2} |".format(s["name"], "yes" if s["found"] else "no", s["note"] or "") for s in sources]
    L += ["", "Read-only. Databases are copied before they are opened, never opened in place. "
          "Email addresses and phone numbers are read to spot duplicates and are never written out.", ""]
    return "\n".join(L)
