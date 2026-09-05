from decimal import Decimal
from xml.sax.saxutils import escape

from .render_terminal import pick_rows

THEMES = {"dark": {"bg": "#0b0f14", "panel": "#121821", "line": "#1e2733", "fg": "#f2f5f7", "muted": "#8a94a0",
                   "accent": "#5cf2a0", "accent2": "#7cc7ff", "bar": "#2a3440", "glow": "#12452f"},
          "light": {"bg": "#ffffff", "panel": "#f4f7f9", "line": "#dfe6ec", "fg": "#0b0f14", "muted": "#5b6570",
                    "accent": "#0f9d58", "accent2": "#2f6fdd", "bar": "#e6eaee", "glow": "#d8f5e6"}}
W, H = 1200, 675
FONT = "-apple-system, Inter, Segoe UI, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def _mult(m) -> str:
    if m is None:
        return "—"
    return "{0:.1f}×".format(m) if m < Decimal("10") else "{0:.0f}×".format(m)


def _chips(v: dict, t: dict) -> str:
    """The providers the run found, as pills. Nobody typed these: they come out of the model ids."""
    det = v.get("detected") or {}
    provs = [p for p in det.get("providers", []) if p.get("records")][:4]
    if not provs:
        return ""
    out, x = [], 80
    total = sum(p["records"] for p in provs) or 1
    for i, p in enumerate(provs):
        label = "{0} {1}%".format(p["talk_to"], int(round(100.0 * p["records"] / total)))
        w = 22 + int(len(label) * 11.6)
        fill = t["accent"] if i == 0 else t["accent2"]
        out.append('<rect x="{x}" y="528" width="{w}" height="40" rx="20" fill="{fill}" opacity="{op}"/>'
                   '<text x="{tx}" y="555" font-size="21" font-family="{mono}" fill="{fg}">{label}</text>'.format(
                       x=x, w=w, fill=fill, op="0.20" if i else "0.28", tx=x + 16, mono=MONO,
                       fg=t["fg"], label=escape(label)))
        x += w + 12
        if x > 640:
            break
    return "".join(out)


def _ladder(v: dict, t: dict) -> str:
    """The plan ladder on the card: every tier the detected provider sells, priced at once."""
    rows = pick_rows(v.get("plan_ladder") or [], 4)
    if len(rows) < 2:
        return ""
    out = ['<rect x="700" y="330" width="420" height="{h}" rx="18" fill="{panel}" stroke="{line}"/>'
           '<text x="728" y="370" font-size="19" letter-spacing="3" font-family="{mono}" fill="{muted}">IF YOU\'RE ON</text>'.format(
               h=64 + 44 * len(rows), panel=t["panel"], line=t["line"], mono=MONO, muted=t["muted"])]
    for i, r in enumerate(rows):
        y = 408 + i * 44
        on = r["assumed"]
        out.append('<text x="728" y="{y}" font-size="23" fill="{c}">{label}</text>'
                   '<text x="1092" y="{y}" font-size="23" text-anchor="end" font-family="{mono}" fill="{mc}">{m}</text>'.format(
                       y=y, c=t["fg"] if on else t["muted"], label=escape(r["label"][:22]), mono=MONO,
                       mc=t["accent"] if on else t["muted"], m=_mult(r["multiplier"])))
    return "".join(out)


def _body(v: dict, t: dict) -> str:
    t_ = t
    e = escape
    total = "${0:,.0f}".format(v["total_usd"])
    mult = _mult(v.get("multiplier")) if v.get("multiplier") is not None else "list price"
    plan = " + ".join(v.get("plan_labels") or []) or "no subscription matched"
    how = {"auto": "assumed from your logs", "remembered": "your plan"}.get(v.get("plan_source"), "the plan you gave")
    if not v.get("plan_labels"):
        how = "no plan"
    tr = v.get("tier") or {}
    badge = ""
    if tr:
        label = tr["name"].upper()
        bw = 36 + int(len(label) * 15)
        badge = ('<rect x="{x}" y="56" width="{w}" height="46" rx="23" fill="{a}"/>'
                 '<text x="{tx}" y="87" font-size="21" font-weight="700" letter-spacing="1.5" text-anchor="middle" font-family="{mono}" fill="{bg}">{l}</text>').format(
                     x=1120 - bw, w=bw, a=t_["accent"], tx=1120 - bw // 2, mono=MONO, bg=t_["bg"], l=escape(label))
    det = v.get("detected") or {}
    where = ", ".join(h["label"] for h in det.get("harnesses", []) if h.get("found")) or "no log directory"
    wide = 560 if (v.get("plan_ladder") and len(v["plan_ladder"]) > 1) else 700
    bars = []
    for i, m in enumerate(v["per_model"][:3]):
        y = 356 + i * 60
        w = int(wide * float(m["share"]))
        bars.append('<rect x="80" y="{y}" width="{ww}" height="28" rx="6" fill="{bar}"/>'
                    '<rect x="80" y="{y}" width="{w}" height="28" rx="6" fill="url(#g1)"/>'
                    '<text x="80" y="{ly}" font-size="22" font-family="{mono}" fill="{muted}">{name}</text>'
                    '<text x="{rx}" y="{ty}" font-size="22" text-anchor="end" fill="{fg}">${usd:,.0f}</text>'.format(
                        y=y, ly=y - 10, ty=y + 21, w=max(w, 4), ww=wide, bar=t["bar"], muted=t["muted"], mono=MONO,
                        fg=t["fg"], rx=80 + wide, name=e(m["model"]), usd=m["usd"]))
    rep = v["repeats"][0]["label"] if v["repeats"] else "no repeat offenders yet"
    return '''<circle cx="1140" cy="70" r="230" fill="{glow}" opacity="0.38"/>
<text x="80" y="90" font-size="28" letter-spacing="6" font-family="{mono}" fill="{muted}">COMPED · LAST {days} DAYS</text>
{badge}<text x="1120" y="134" font-size="19" text-anchor="end" font-family="{mono}" fill="{muted}">via {where}</text>
<text x="80" y="230" font-size="120" font-weight="700" fill="{fg}">{total} <tspan fill="{accent}">comped</tspan></text>
<text x="80" y="300" font-size="48" fill="{fg}">{mult} <tspan fill="{muted}" font-size="32">vs {plan} · {how}</tspan></text>
{bars}{chips}{ladder}
<text x="80" y="602" font-size="20" font-family="{mono}" fill="{muted}">cache read {cache}% · active days {active}/{days} · top repeat: {rep}</text>
<text x="80" y="642" font-size="18" font-family="{mono}" fill="{muted}">list-price equivalent, not a bill · prices as of {as_of}</text>
<text x="1120" y="642" font-size="22" text-anchor="end" font-weight="700" fill="{accent}">{site}</text>'''.format(
        muted=t["muted"], fg=t["fg"], accent=t["accent"], glow=t["glow"], mono=MONO, days=v["window_days"],
        total=e(total), mult=e(mult), plan=e(plan), how=e(how), where=e(where[:44]), bars="".join(bars),
        chips=_chips(v, t), ladder=_ladder(v, t), cache=int(round(float(v["cache_share"]) * 100)), badge=badge,
        site=e((v.get("site") or "gotcomped.com").replace("https://", "")),
        active=v["active_days"], rep=e(rep[:26]), as_of=e(v["price_as_of"]))


def _defs(t: dict) -> str:
    return ('<defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="0">'
            '<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>'
            '</linearGradient></defs>').format(a=t["accent"], b=t["accent2"])


def render_svg(v: dict, theme: str) -> str:
    """The shareable card: 1200x675, the aspect X and LinkedIn preview without cropping."""
    t = THEMES.get(theme, THEMES["dark"])
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{font}">\n'
            '<rect width="{w}" height="{h}" fill="{bg}"/>\n{defs}\n{body}\n</svg>\n').format(
                w=W, h=H, font=FONT, bg=t["bg"], defs=_defs(t), body=_body(v, t))


def render_svg_square(v: dict, theme: str) -> str:
    """The same card on a square canvas. PNG renderers (macOS qlmanage in particular) fit a
    thumbnail into a square box: given the wide card they scale by height and crop the right
    edge. Handing them a square keeps every figure on the image."""
    t = THEMES.get(theme, THEMES["dark"])
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{w}" viewBox="0 0 {w} {w}" font-family="{font}">\n'
            '<rect width="{w}" height="{w}" fill="{bg}"/>\n{defs}\n<g transform="translate(0,{dy})">\n{body}\n</g>\n</svg>\n').format(
                w=W, font=FONT, bg=t["bg"], defs=_defs(t), dy=(W - H) // 2, body=_body(v, t))
