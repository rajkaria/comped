import shutil, subprocess
from pathlib import Path
from typing import Optional, Tuple, List


def default_renderers() -> List[Tuple[str, list]]:
    r = []
    if shutil.which("rsvg-convert"):
        r.append(("rsvg-convert", ["rsvg-convert", "-w", "1200", "-o", "{png}", "{svg}"]))
    if shutil.which("qlmanage"):
        r.append(("qlmanage", ["qlmanage", "-t", "-s", "1200", "-o", "{dir}", "{svg}"]))
    return r


def render_png(svg_path: Path, out_dir: Path, renderers=None, png_name=None) -> Tuple[Optional[str], str]:
    renderers = default_renderers() if renderers is None else renderers
    png = Path(out_dir) / (png_name or (Path(svg_path).stem + ".png"))
    for name, argv in renderers:
        cmd = [a.format(png=str(png), svg=str(svg_path), dir=str(out_dir)) for a in argv]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        except (subprocess.SubprocessError, OSError):
            continue
        if name == "qlmanage":
            produced = Path(out_dir) / (Path(svg_path).name + ".png")
            if produced.exists():
                produced.replace(png)
        if png.exists():
            return str(png), "PNG rendered with {0}".format(name)
    return None, ("PNG skipped: no renderer found (rsvg-convert or macOS qlmanage); "
                  "the SVG uploads to LinkedIn as-is and can be screenshotted for X")
