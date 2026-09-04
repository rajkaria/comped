from decimal import Decimal
from xml.sax.saxutils import escape

THEMES = {"dark": {"bg": "#0b0f14", "fg": "#f2f5f7", "muted": "#8a94a0", "accent": "#5cf2a0", "bar": "#2a3440"},
          "light": {"bg": "#ffffff", "fg": "#0b0f14", "muted": "#5b6570", "accent": "#0f9d58", "bar": "#e6eaee"}}


def render_svg(v: dict, theme: str) -> str:
    t = THEMES.get(theme, THEMES["dark"])
    e = escape
    total = "${0:,.0f}".format(v["total_usd"])
    mult = "{0:.0f}×".format(v["multiplier"]) if v.get("multiplier") is not None else "list price"
    plan = " + ".join(v.get("plan_labels") or []) or "no plan given"
    bars = []
    for i, m in enumerate(v["per_model"][:3]):
        y = 380 + i * 60
        w = int(700 * float(m["share"]))
        bars.append('<rect x="80" y="{y}" width="700" height="28" rx="6" fill="{bar}"/>'
                    '<rect x="80" y="{y}" width="{w}" height="28" rx="6" fill="{accent}"/>'
                    '<text x="80" y="{ly}" font-size="22" fill="{muted}">{name}</text>'
                    '<text x="1120" y="{ty}" font-size="22" text-anchor="end" fill="{fg}">${usd:,.0f}</text>'.format(
                        y=y, ly=y - 10, ty=y + 21, w=max(w, 4), bar=t["bar"], accent=t["accent"], muted=t["muted"], fg=t["fg"],
                        name=e(m["model"]), usd=m["usd"]))
    rep = v["repeats"][0]["label"] if v["repeats"] else "no repeat offenders yet"
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" font-family="-apple-system, Inter, Segoe UI, Helvetica, Arial, sans-serif">
<rect width="1200" height="675" fill="{bg}"/>
<text x="80" y="90" font-size="28" letter-spacing="6" fill="{muted}">COMPED · LAST {days} DAYS</text>
<text x="80" y="230" font-size="120" font-weight="700" fill="{fg}">{total} <tspan fill="{accent}">comped</tspan></text>
<text x="80" y="300" font-size="48" fill="{fg}">{mult} <tspan fill="{muted}" font-size="32">vs {plan}</tspan></text>
{bars}
<text x="80" y="580" font-size="22" fill="{muted}">cache read {cache}% · active days {active}/{days} · top repeat: {rep}</text>
<text x="80" y="630" font-size="20" fill="{muted}">list-price equivalent, not a bill · prices as of {as_of} · {uri}</text>
</svg>
'''.format(bg=t["bg"], muted=t["muted"], fg=t["fg"], accent=t["accent"], days=v["window_days"], total=e(total), mult=e(mult),
           plan=e(plan), bars="".join(bars), cache=int(round(float(v["cache_share"]) * 100)), active=v["active_days"],
           rep=e(rep[:48]), as_of=e(v["price_as_of"]), uri=e(v["play_uri"].replace("https://", "")))
