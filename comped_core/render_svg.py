"""The shareable card. 1200x675 for X and LinkedIn previews, plus a square cut for renderers
that crop to a thumbnail. Same palette as gotcomped.com so the card and the site read as one
thing: cream and plum, coral for the score, a yellow sticker for the tier."""
from decimal import Decimal
from xml.sax.saxutils import escape

from .render_terminal import pick_rows

THEMES = {
    "dark": {"bg": "#1e1b2e", "panel": "#2a2640", "line": "#3d3859", "fg": "#fff8ee", "muted": "#b3accb",
             "accent": "#ff6b4a", "accent2": "#8f74ff", "yellow": "#ffd23f", "mint": "#3be0b0", "bar": "#3a3556",
             "blob1": "#ff6b4a", "blob2": "#8f74ff", "ink_on_yellow": "#1e1b2e"},
    "light": {"bg": "#fff7ea", "panel": "#ffffff", "line": "#eadfcb", "fg": "#1e1b2e", "muted": "#6b6478",
              "accent": "#e4522f", "accent2": "#6a4bff", "yellow": "#ffd23f", "mint": "#12a37f", "bar": "#f1e7d6",
              "blob1": "#ffb59f", "blob2": "#c9bbff", "ink_on_yellow": "#1e1b2e"},
}
W, H = 1200, 675
FONT = "ui-rounded, 'SF Pro Rounded', 'Arial Rounded MT Bold', Nunito, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def _mult(m) -> str:
    if m is None:
        return "no plan"
    return "{0:.1f}×".format(m) if m < Decimal("10") else "{0:.0f}×".format(m)


def _chips(v: dict, t: dict, y: int) -> str:
    """The providers the run found, as pills. Nobody typed these: they come out of the model ids."""
    det = v.get("detected") or {}
    provs = [p for p in det.get("providers", []) if p.get("records")][:4]
    if not provs:
        return ""
    out, x = [], 72
    total = sum(p["records"] for p in provs) or 1
    colors = [t["accent"], t["accent2"], t["mint"], t["yellow"]]
    for i, p in enumerate(provs):
        label = "{0} {1}%".format(p["talk_to"], int(round(100.0 * p["records"] / total)))
        w = 26 + int(len(label) * 11.4)
        out.append('<rect x="{x}" y="{y}" width="{w}" height="38" rx="19" fill="{fill}" opacity="0.18"/>'
                   '<circle cx="{cx}" cy="{cy}" r="6" fill="{fill}"/>'
                   '<text x="{tx}" y="{ty}" font-size="20" font-weight="700" fill="{fg}">{label}</text>'.format(
                       x=x, y=y, w=w + 12, fill=colors[i % 4], cx=x + 18, cy=y + 19, tx=x + 32, ty=y + 26,
                       fg=t["fg"], label=escape(label)))
        x += w + 24
        if x > 640:
            break
    return "".join(out)


def _ladder(v: dict, t: dict) -> str:
    """Every tier the detected provider sells, priced at once. You read your row."""
    rows = pick_rows(v.get("plan_ladder") or [], 4)
    if len(rows) < 2:
        return ""
    h = 66 + 46 * len(rows)
    out = ['<rect x="716" y="322" width="412" height="{h}" rx="22" fill="{panel}" stroke="{line}" stroke-width="2"/>'
           '<text x="744" y="362" font-size="17" font-weight="800" letter-spacing="3" fill="{muted}">IF YOU\'RE ON</text>'.format(
               h=h, panel=t["panel"], line=t["line"], muted=t["muted"])]
    for i, r in enumerate(rows):
        y = 404 + i * 46
        on = r["assumed"]
        if on:
            out.append('<rect x="730" y="{y}" width="384" height="40" rx="12" fill="{yl}" opacity="0.22"/>'.format(y=y - 28, yl=t["yellow"]))
        out.append('<text x="744" y="{y}" font-size="22" font-weight="{fw}" fill="{c}">{label}</text>'
                   '<text x="1100" y="{y}" font-size="24" font-weight="800" text-anchor="end" fill="{mc}">{m}</text>'.format(
                       y=y, fw="800" if on else "600", c=t["fg"] if on else t["muted"], label=escape(r["label"][:22]),
                       mc=t["accent"] if on else t["muted"], m=_mult(r["multiplier"])))
    return "".join(out)


def _sticker(text: str, t: dict) -> str:
    """The tier, as a slightly crooked yellow sticker in the top right corner."""
    label = text.upper()
    w = 44 + int(len(label) * 14.5)
    x = 1128 - w
    return ('<g transform="rotate(-3 {cx} 84)"><rect x="{x}" y="58" width="{w}" height="52" rx="26" fill="{yl}"/>'
            '<text x="{cx}" y="93" font-size="22" font-weight="800" letter-spacing="1.5" text-anchor="middle" fill="{ink}">{l}</text></g>').format(
                cx=x + w / 2, x=x, w=w, yl=t["yellow"], ink=t["ink_on_yellow"], l=escape(label))


def _body(v: dict, t: dict) -> str:
    e = escape
    total = "${0:,.0f}".format(v["total_usd"])
    m = v.get("multiplier")
    plan = " + ".join(v.get("plan_labels") or []) or "no subscription matched"
    how = {"auto": "worked out from your logs", "remembered": "the plan you told it"}.get(v.get("plan_source"), "the plan you gave")
    if not v.get("plan_labels"):
        how = "no plan"
    tr = v.get("tier") or {}
    badge = _sticker(tr["name"], t) if tr else ""
    det = v.get("detected") or {}
    where = ", ".join(h["label"] for h in det.get("harnesses", []) if h.get("found")) or "no log directory"
    has_ladder = bool(v.get("plan_ladder") and len(v["plan_ladder"]) > 1)
    wide = 560 if has_ladder else 1056
    bars = []
    for i, mm in enumerate(v["per_model"][:3]):
        y = 372 + i * 58
        w = int(wide * float(mm["share"]))
        bars.append('<text x="72" y="{ly}" font-size="20" font-family="{mono}" fill="{muted}">{name}</text>'
                    '<text x="{rx}" y="{ly}" font-size="21" font-weight="800" text-anchor="end" fill="{fg}">${usd:,.0f}</text>'
                    '<rect x="72" y="{y}" width="{ww}" height="18" rx="9" fill="{bar}"/>'
                    '<rect x="72" y="{y}" width="{w}" height="18" rx="9" fill="url(#g1)"/>'.format(
                        y=y, ly=y - 10, w=max(w, 12), ww=wide, bar=t["bar"], muted=t["muted"], mono=MONO,
                        fg=t["fg"], rx=72 + wide, name=e(mm["model"]), usd=mm["usd"]))
    rep = v["repeats"][0]["label"] if v["repeats"] else "none yet"
    score_line = ('<text x="72" y="318" font-size="64" font-weight="800" fill="{accent}">{mult}</text>'
                  '<text x="{sx}" y="318" font-size="26" font-weight="700" fill="{fg}">comp score</text>'
                  '<text x="{px}" y="318" font-size="22" fill="{muted}">vs {plan} · {how}</text>').format(
                      accent=t["accent"], mult=e(_mult(m)), sx=72 + int(len(_mult(m)) * 40) + 16, fg=t["fg"],
                      px=72 + int(len(_mult(m)) * 40) + 178, muted=t["muted"], plan=e(plan[:34]), how=e(how))
    if m is None:
        score_line = ('<text x="72" y="318" font-size="30" font-weight="700" fill="{fg}">no subscription matched, so this is list price only</text>').format(fg=t["fg"])
    return '''<circle cx="1180" cy="-40" r="300" fill="{blob1}" opacity="0.16"/>
<circle cx="40" cy="720" r="260" fill="{blob2}" opacity="0.16"/>
<text x="72" y="96" font-size="34" font-weight="800" letter-spacing="-1" fill="{fg}">comped<tspan fill="{accent}">.</tspan></text>
<text x="212" y="96" font-size="20" font-weight="700" letter-spacing="2" fill="{muted}">LAST {days} DAYS</text>
{badge}<text x="1128" y="138" font-size="17" font-weight="600" text-anchor="end" fill="{muted}">read from {where}</text>
<text x="72" y="238" font-size="128" font-weight="800" letter-spacing="-5" fill="{fg}">{total}</text>
<text x="{ax}" y="238" font-size="44" font-weight="700" fill="{muted}">at full price</text>
{score}
{bars}{chips}{ladder}
<text x="72" y="598" font-size="19" font-family="{mono}" fill="{muted}">cache read {cache}% · {active} of {days} days active · {sessions} sessions · asked again most: {rep}</text>
<text x="72" y="640" font-size="17" font-family="{mono}" fill="{muted}">list price, not a bill · prices as of {as_of}</text>
<text x="1128" y="642" font-size="26" font-weight="800" text-anchor="end" fill="{accent}">{site}</text>'''.format(
        blob1=t["blob1"], blob2=t["blob2"], muted=t["muted"], fg=t["fg"], accent=t["accent"], mono=MONO,
        days=v["window_days"], total=e(total), ax=72 + int(len(total) * 70) + 20, score=score_line,
        where=e(where[:44]), bars="".join(bars), chips=_chips(v, t, 522), ladder=_ladder(v, t),
        cache=int(round(float(v["cache_share"]) * 100)), badge=badge, sessions=v.get("sessions", 0),
        site=e((v.get("site") or "gotcomped.com").replace("https://", "")),
        active=v["active_days"], rep=e(rep[:24]), as_of=e(v["price_as_of"]))


def _defs(t: dict) -> str:
    return ('<defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="0">'
            '<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>'
            '</linearGradient></defs>').format(a=t["accent"], b=t["accent2"])


def render_svg(v: dict, theme: str) -> str:
    """The shareable card: 1200x675, the aspect X and LinkedIn preview without cropping."""
    t = THEMES.get(theme, THEMES["dark"])
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{font}">\n'
            '<rect width="{w}" height="{h}" rx="0" fill="{bg}"/>\n{defs}\n{body}\n</svg>\n').format(
                w=W, h=H, font=FONT, bg=t["bg"], defs=_defs(t), body=_body(v, t))


def render_svg_square(v: dict, theme: str) -> str:
    """The same card on a square canvas. PNG renderers (macOS qlmanage in particular) fit a
    thumbnail into a square box: given the wide card they scale by height and crop the right
    edge. Handing them a square keeps every figure on the image."""
    t = THEMES.get(theme, THEMES["dark"])
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{w}" viewBox="0 0 {w} {w}" font-family="{font}">\n'
            '<rect width="{w}" height="{w}" fill="{bg}"/>\n{defs}\n<g transform="translate(0,{dy})">\n{body}\n</g>\n</svg>\n').format(
                w=W, font=FONT, bg=t["bg"], defs=_defs(t), dy=(W - H) // 2, body=_body(v, t))
