#!/usr/bin/env python3
"""
Black & white profile visuals generator.

Reads LIVE data from the GitHub API (contributions, repos, languages, avatar,
followers...) and writes animated SVG panels into assets/generated/.

  python scripts/generate.py            live data (needs GH_TOKEN and GH_USER)
  python scripts/generate.py --mock     fake data, for local layout testing only
  python scripts/generate.py --pending  empty placeholder state

Video slot: drop a file named  assets/video.mp4  (or .webm .mov .mkv .gif)  into the repo.
It is converted to a small grayscale GIF with ffmpeg and embedded in the Statistics panel.
"""
import base64
import datetime as dt
import html
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "generated"

FONT_MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
FONT_SANS = "'Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif"

C = dict(line="#2c2c2c", line2="#474747", text="#e6e6e6", mute="#8c8c8c", dim="#5a5a5a", hi="#ffffff")
LEVELS = ["#181818", "#404040", "#727272", "#b4b4b4", "#ffffff"]
ICON_COL = "#f0f0f0"
W = 900
HEADER_H = 72

esc = html.escape


def fmt(n):
    return f"{int(n):,}"


def short_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


# --------------------------------------------------------------------------- config
def load_config():
    cfg = {
        "username": os.environ.get("GH_USER", "Keydstunna"),
        "role": "BSIT Student | Web Developer",
        "headline": "Third-year BSIT Student",
        "banner_text": "Welcome to Keydstunna's GitHub",
        "extra_tech": ["MySQL", "Git", "GitHub"],
        "hide_tech": [],
        "max_tech": 12,
        "about": ("Hi! I'm Kier Lawrence Ignacio, a third-year BSIT student who enjoys working with technology "
                  "and design. I like creating websites, designing graphics, and learning new things. I'm always "
                  "looking for ways to improve my skills and turn my ideas into something useful."),
        "status": "Building | Learning",
        "hobbies": ["Web design", "Graphic design", "Gaming", "Listening to music", "Watching movies and series"],
        "quote": "you can never be too happy in this life",
        "video_seconds": 6,
    }
    p = ROOT / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    if isinstance(cfg.get("about"), list):
        cfg["about"] = " ".join(cfg["about"])
    return cfg


# --------------------------------------------------------------------------- svg helpers
ICONS = {
    "code": "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16",
    "chart": "M4 20V11M10 20V4M16 20V13M21 20H3",
    "user": "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 7 0 0116 0",
    "target": "M12 3a9 9 0 100 18 9 9 0 000-18zM12 8a4 4 0 100 8 4 4 0 000-8zM12 12h.01",
    "scan": "M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M4 12h16",
    "flame": "M12 3c1 3 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z",
    "play": "M8 5v14l11-7z",
    "diamond": "M12 3l8 9-8 9-8-9z",
    "grid": "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
}


def icon(name, x, y, size, color, sw=2, fill="none"):
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({size / 24:.4f})" fill="{fill}" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"><path d="{ICONS[name]}"/></g>')


def defs_common():
    return f'''
<radialGradient id="vig" cx="0.5" cy="0.35" r="0.9"><stop offset="0" stop-color="#121212"/><stop offset="1" stop-color="#000"/></radialGradient>
<linearGradient id="gHi" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#fff" stop-opacity="0.95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<linearGradient id="gVhi" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#fff" stop-opacity="0.95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="soft"><feGaussianBlur stdDeviation="6"/></filter>'''


def svg_doc(w, h, body, extra_defs="", style=""):
    st = f"<style>{style}</style>" if style else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">\n'
            f'<defs>{defs_common()}{extra_defs}</defs>{st}\n{body}\n</svg>\n')


def panel(w, h, rx=10):
    r = f'x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="{rx}"'
    return (f'<rect {r} fill="url(#vig)" stroke="{C["line"]}" stroke-width="1.5"/>'
            f'<rect {r} fill="none" stroke="#fff" stroke-opacity="0.8" stroke-width="1.6" pathLength="1" stroke-dasharray="0.08 0.92">'
            f'<animate attributeName="stroke-dashoffset" from="1" to="0" dur="9s" repeatCount="indefinite"/></rect>')


def section_svg(title, icon_name, inner_h, inner, extra="", style=""):
    h = HEADER_H + inner_h
    header = f'''<circle cx="48" cy="34" r="16" fill="#0a0a0a" stroke="{C['line2']}" stroke-width="1.5"/>
<circle cx="48" cy="34" r="16" fill="none" stroke="#fff" stroke-width="1.2"><animate attributeName="r" values="16;28" dur="3s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.6;0" dur="3s" repeatCount="indefinite"/></circle>
{icon(icon_name, 38, 24, 20, C['hi'], 1.8)}
<text x="76" y="42" font-family="{FONT_SANS}" font-size="23" font-weight="700" letter-spacing="0.6" fill="{C['hi']}">{esc(title)}</text>
<rect x="30" y="{HEADER_H - 8}" width="{W - 60}" height="1.5" fill="{C['line']}"/>
<rect x="-200" y="{HEADER_H - 9}" width="200" height="3.5" fill="url(#gHi)"><animate attributeName="x" from="-200" to="{W}" dur="5s" repeatCount="indefinite"/></rect>'''
    body = panel(W, h) + header + f'<g transform="translate(0 {HEADER_H})">{inner}</g>'
    return svg_doc(W, h, body, extra, style)


def smooth_path(pts):
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        mx = (x0 + x1) / 2
        d += f" C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
    return d


def sparkle(x, y, sz, dur, begin):
    return (f'<path d="M{x},{y - sz} Q{x},{y} {x + sz},{y} Q{x},{y} {x},{y + sz} Q{x},{y} {x - sz},{y} Q{x},{y} {x},{y - sz}Z" fill="#fff">'
            f'<animate attributeName="opacity" values="0;1;0" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/></path>')


# --------------------------------------------------------------------------- banner
def ribbon_variants(rnd, base_y, amp, n_var=3, segs=5):
    xs = [-80 + i * (W + 160) / segs for i in range(segs + 1)]
    out = []
    for _ in range(n_var):
        ys = [base_y + rnd.uniform(-amp, amp) for _ in xs]
        d = f"M{xs[0]:.0f},{ys[0]:.0f}"
        for i in range(1, len(xs)):
            x0, y0, x1, y1 = xs[i - 1], ys[i - 1], xs[i], ys[i]
            cx = (x0 + x1) / 2
            d += f" C{cx:.0f},{y0 + rnd.uniform(-amp, amp) * 0.7:.0f} {cx:.0f},{y1 + rnd.uniform(-amp, amp) * 0.7:.0f} {x1:.0f},{y1:.0f}"
        out.append(d)
    return out


def banner_svg(cfg, login):
    h = 300
    rnd = random.Random(21)
    text = cfg["banner_text"]
    tw = len(text) * 17.2
    tx = W / 2 - tw / 2

    stars = ""
    for _ in range(140):
        x, y = rnd.uniform(8, W - 8), rnd.uniform(8, h - 8)
        r = rnd.choice([0.7, 0.9, 1.1, 1.5, 2.0])
        stars += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#fff"><animate attributeName="opacity" '
                  f'values="0.1;1;0.1" dur="{rnd.uniform(1.8, 5.5):.1f}s" begin="{rnd.uniform(0, 5):.1f}s" repeatCount="indefinite"/></circle>')

    ribs = ""
    specs = [(150, 70, 38, 0.22, 17, 14), (190, 60, 26, 0.30, 21, 10), (120, 55, 18, 0.34, 15, 7), (215, 45, 10, 0.5, 19, 3)]
    for i, (by, amp, sw, op, dur, blur) in enumerate(specs):
        vs = ribbon_variants(rnd, by, amp)
        values = ";".join(vs + [vs[0]])
        ribs += (f'<path d="{vs[0]}" fill="none" stroke="url(#gRib)" stroke-width="{sw}" stroke-linecap="round" opacity="{op}" filter="url(#b{blur})">'
                 f'<animate attributeName="d" values="{values}" dur="{dur}s" repeatCount="indefinite"/></path>')
    thin = ""
    for i in range(3):
        vs = ribbon_variants(rnd, 130 + i * 38, 60)
        values = ";".join(vs + [vs[0]])
        thin += (f'<path d="{vs[0]}" fill="none" stroke="url(#gRib)" stroke-width="{1.2 + i * 0.5}" stroke-linecap="round" opacity="{0.55 - i * 0.12}" filter="url(#b1)">'
                 f'<animate attributeName="d" values="{values}" dur="{13 + i * 3}s" repeatCount="indefinite"/></path>')

    fx, fy = 748, 96
    flare = f'''<g transform="translate({fx} {fy})">
<circle r="86" fill="url(#flareG)"><animate attributeName="r" values="80;96;80" dur="4s" repeatCount="indefinite"/></circle>
<rect x="-230" y="-1.2" width="460" height="2.4" fill="url(#gHi)" opacity="0.9"><animate attributeName="opacity" values="0.55;1;0.55" dur="3.4s" repeatCount="indefinite"/></rect>
<rect x="-1.2" y="-95" width="2.4" height="190" fill="url(#gVhi)" opacity="0.8"><animate attributeName="opacity" values="0.4;0.95;0.4" dur="3.4s" repeatCount="indefinite"/></rect>
<g opacity="0.5"><rect x="-70" y="-0.8" width="140" height="1.6" fill="url(#gHi)" transform="rotate(45)"/><rect x="-70" y="-0.8" width="140" height="1.6" fill="url(#gHi)" transform="rotate(-45)"/>
<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="40s" repeatCount="indefinite"/></g>
<circle r="3.6" fill="#fff" filter="url(#glow)"/></g>'''

    extra = f'''
<linearGradient id="gRib" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.25" stop-color="#fff" stop-opacity="0.85"/><stop offset="0.7" stop-color="#e8e8e8" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity="0.1"/></linearGradient>
<radialGradient id="flareG" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff" stop-opacity="0.75"/><stop offset="0.25" stop-color="#fff" stop-opacity="0.22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<filter id="b14" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="14"/></filter>
<filter id="b10" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="10"/></filter>
<filter id="b7" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="7"/></filter>
<filter id="b3" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="3"/></filter>
<filter id="b1" x="-20%" y="-120%" width="140%" height="340%"><feGaussianBlur stdDeviation="0.8"/></filter>
<clipPath id="round"><rect x="1.5" y="1.5" width="{W - 3}" height="{h - 3}" rx="10"/></clipPath>
<clipPath id="reveal"><rect x="{tx:.1f}" y="168" width="0" height="48"><animate attributeName="width" from="0" to="{tw:.1f}" dur="2.4s" begin="0.4s" fill="freeze"/></rect></clipPath>'''
    body = f'''<rect width="{W}" height="{h}" fill="#000"/>
<g clip-path="url(#round)">
<rect width="{W}" height="{h}" fill="url(#vig)"/>
{stars}
{ribs}{thin}
{flare}
<rect x="0" y="0" width="{W}" height="{h}" fill="#000" opacity="0.18"/>
<text x="{tx:.1f}" y="200" font-family="{FONT_MONO}" font-size="28" fill="#fff" textLength="{tw:.1f}" lengthAdjust="spacing" clip-path="url(#reveal)" filter="url(#glow)">{esc(text)}</text>
<rect y="172" width="3" height="34" fill="#fff" x="{tx:.1f}"><animate attributeName="x" from="{tx:.1f}" to="{tx + tw:.1f}" dur="2.4s" begin="0.4s" fill="freeze"/><animate attributeName="opacity" values="1;0;1" dur="0.9s" repeatCount="indefinite"/></rect>
<text x="{W / 2}" y="240" text-anchor="middle" font-family="{FONT_MONO}" font-size="14" fill="#bdbdbd" letter-spacing="2" opacity="0">@{esc(login)}  |  {esc(cfg['role'])}<animate attributeName="opacity" from="0" to="0.95" begin="2.8s" dur="1s" fill="freeze"/></text>
</g>
<rect x="1.5" y="1.5" width="{W - 3}" height="{h - 3}" rx="10" fill="none" stroke="{C['line2']}" stroke-width="1.5"/>
<rect x="1.5" y="1.5" width="{W - 3}" height="{h - 3}" rx="10" fill="none" stroke="#fff" stroke-opacity="0.85" stroke-width="1.8" pathLength="1" stroke-dasharray="0.07 0.93"><animate attributeName="stroke-dashoffset" from="1" to="0" dur="8s" repeatCount="indefinite"/></rect>'''
    return svg_doc(W, h, body, extra)


def footer_svg():
    h = 90
    waves = ""
    for i, (op, dur, amp, base) in enumerate([(0.55, 12, 9, 56), (0.35, 8, 11, 64), (0.2, 6, 8, 72)]):
        pts = []
        for k in range(0, 2 * W // 15 + 1):
            x = k * 15
            pts.append((x, base + amp * math.sin(2 * math.pi * (2 * x / W) + i * 1.3)))
        d = "M" + " L".join(f"{x},{y:.1f}" for x, y in pts)
        waves += (f'<path d="{d}" fill="none" stroke="#fff" stroke-opacity="{op}" stroke-width="1.5"><animateTransform attributeName="transform" '
                  f'type="translate" from="0 0" to="-{W} 0" dur="{dur}s" repeatCount="indefinite"/></path>')
    extra = f'<clipPath id="fp"><rect x="1.5" y="1.5" width="{W - 3}" height="{h - 3}" rx="10"/></clipPath>'
    body = (panel(W, h) + f'<g clip-path="url(#fp)">{waves}</g>'
            f'<rect x="300" y="30" width="300" height="1" fill="url(#gHi)" opacity="0.6"/>'
            f'<text x="{W / 2}" y="26" text-anchor="middle" font-family="{FONT_MONO}" font-size="12.5" letter-spacing="4" fill="{C["mute"]}">THANKS FOR VISITING</text>')
    return svg_doc(W, h, body, extra)


# --------------------------------------------------------------------------- split panels (About / Hobbies)
def gray_png_b64(path, maxdim):
    try:
        from PIL import Image, ImageEnhance
        im = Image.open(path).convert("RGBA")
        im = im.crop(im.getbbox())
        im.thumbnail((maxdim, maxdim), Image.LANCZOS)
        a = im.getchannel("A")
        g = ImageEnhance.Contrast(im.convert("L")).enhance(1.15)
        out = Image.merge("LA", (g, a)).convert("RGBA")
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode(), out.size
    except Exception as e:  # noqa
        print("character image skipped:", e, file=sys.stderr)
        return None, (0, 0)


def character_group(path, cx, cy, maxdim, sway=False, fade=False):
    data, (iw, ih) = gray_png_b64(path, maxdim)
    if not data:
        return ""
    x, y = cx - iw / 2, cy - ih / 2
    swy = ""
    if sway:
        swy = (f'<animateTransform attributeName="transform" type="rotate" values="-3 {cx} {y + ih};3 {cx} {y + ih};-3 {cx} {y + ih}" '
               f'dur="5s" repeatCount="indefinite"/>')
    sp = "".join(sparkle(cx + dx, cy + dy, sz, du, be) for dx, dy, sz, du, be in
                 [(-105, -95, 8, 2.6, 0), (110, -105, 10, 3.1, 0.8), (100, 88, 7, 2.4, 1.5), (-100, 82, 6, 2.9, 0.4), (0, -128, 7, 3.4, 2)])
    return f'''<g clip-path="url(#cell)">
<ellipse cx="{cx}" cy="{cy}" rx="150" ry="150" fill="url(#halo)"><animate attributeName="opacity" values="0.6;1;0.6" dur="4s" repeatCount="indefinite"/></ellipse>
<circle cx="{cx}" cy="{cy}" r="128" fill="none" stroke="#fff" stroke-opacity="0.3" stroke-width="1.2" stroke-dasharray="3 9"><animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" dur="34s" repeatCount="indefinite"/></circle>
<circle cx="{cx}" cy="{cy}" r="104" fill="none" stroke="#fff" stroke-opacity="0.16" stroke-width="1"><animate attributeName="r" values="104;112;104" dur="5s" repeatCount="indefinite"/></circle>
<ellipse cx="{cx}" cy="{y + ih + 16}" rx="64" ry="8" fill="#fff" opacity="0.1" filter="url(#soft)"><animate attributeName="rx" values="64;48;64" dur="4s" repeatCount="indefinite"/></ellipse>
<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -11;0 0" dur="4s" repeatCount="indefinite" calcMode="spline" keyTimes="0;0.5;1" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"/>
<g>{swy}<image x="{x:.1f}" y="{y:.1f}" width="{iw}" height="{ih}"{' mask="url(#fadeM)"' if fade else ''} href="data:image/png;base64,{data}" xlink:href="data:image/png;base64,{data}"/></g></g>
{sp}</g>'''


SPLIT_DEFS = ('<linearGradient id="fadeG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="0.78" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>'
              '<mask id="fadeM" maskContentUnits="objectBoundingBox" x="0" y="0" width="1" height="1"><rect x="0" y="0" width="1" height="1" fill="url(#fadeG)"/></mask>'
              '<radialGradient id="halo" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff" stop-opacity="0.16"/>'
              '<stop offset="0.6" stop-color="#fff" stop-opacity="0.05"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>')


def split_frame(inner_h, left, img_path, sway, fade=False):
    """Bordered box: text/rows on the left, floating image on the right (like the inspo tables)."""
    bx, bw, by = 30, 840, 6
    bh = inner_h - 12
    div = 600
    cx, cy = (div + bx + bw) / 2, by + bh / 2
    extra = f'<clipPath id="cell"><rect x="{div + 1}" y="{by + 1}" width="{bx + bw - div - 2}" height="{bh - 2}"/></clipPath>' + SPLIT_DEFS
    body = (f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="8" fill="#030303" stroke="{C["line"]}" stroke-width="1.3"/>'
            f'<line x1="{div}" y1="{by}" x2="{div}" y2="{by + bh}" stroke="{C["line"]}" stroke-width="1.3"/>'
            f'<rect x="{bx}" y="{by + 14}" width="3" height="{bh - 28}" fill="#fff"><animate attributeName="opacity" values="1;0.35;1" dur="3s" repeatCount="indefinite"/></rect>'
            f'{left}{character_group(img_path, cx, cy - 6, 196, sway, fade)}')
    return body, extra


def about_svg(cfg):
    lines = textwrap.wrap(cfg["about"], 56)
    lh = 26
    title_h = 40
    text_h = title_h + len(lines) * lh
    inner_h = int(max(text_h + 64, 290))
    y0 = (inner_h - text_h) / 2 + 20
    left = (f'<text x="62" y="{y0:.1f}" font-family="{FONT_SANS}" font-size="19" font-weight="800" fill="#fff" opacity="0">{esc(cfg["headline"])}'
            f'<animate attributeName="opacity" from="0" to="1" begin="0.2s" dur="0.6s" fill="freeze"/></text>'
            f'<rect x="62" y="{y0 + 10:.1f}" width="0" height="1.6" fill="#fff" opacity="0.8"><animate attributeName="width" from="0" to="120" begin="0.5s" dur="0.9s" fill="freeze"/></rect>')
    for i, ln in enumerate(lines):
        left += (f'<text x="62" y="{y0 + title_h + 6 + i * lh:.1f}" font-family="{FONT_SANS}" font-size="15" fill="{C["text"]}" opacity="0">{esc(ln)}'
                 f'<animate attributeName="opacity" from="0" to="1" begin="{0.7 + i * 0.14:.2f}s" dur="0.6s" fill="freeze"/></text>')
    body, extra = split_frame(inner_h, left, ROOT / "assets" / "about-me.png", False, True)
    return section_svg("About Me", "user", inner_h, body, extra)


def goals_svg(cfg):
    rows = [("Class", [cfg["headline"]]), ("Status", [cfg["status"]]), ("Hobbies", list(cfg["hobbies"]))]
    if cfg.get("quote"):
        rows.append(("Motto", textwrap.wrap('"' + cfg["quote"] + '"', 36)))
    lh, gap = 25, 16
    total_h = sum(len(v) * lh for _k, v in rows) + gap * (len(rows) - 1)
    inner_h = int(max(total_h + 70, 290))
    y = (inner_h - total_h) / 2 + 12
    band_top = y - 22
    left = (f'<rect x="54" y="{band_top:.1f}" width="520" height="{total_h + 30:.1f}" rx="6" fill="#0a0a0a" stroke="{C["line"]}"/>')
    n = 0
    for key, vals in rows:
        b = 0.3 + n * 0.28
        left += (f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{b:.2f}s" dur="0.5s" fill="freeze"/>'
                 f'<animateTransform attributeName="transform" type="translate" from="-12 0" to="0 0" begin="{b:.2f}s" dur="0.5s" fill="freeze"/>'
                 f'{icon("diamond", 66, y - 12, 14, "#fff", 2, "#fff")}'
                 f'<text x="90" y="{y:.1f}" font-family="{FONT_MONO}" font-size="14" font-weight="700" fill="{C["mute"]}">{esc(key)}</text>'
                 f'<path d="M168 {y - 5:.1f} h16 m-5 -4 l5 4 l-5 4" fill="none" stroke="{C["dim"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
        for j, v in enumerate(vals):
            left += (f'<text x="204" y="{y + j * lh:.1f}" font-family="{FONT_MONO}" font-size="14.5" fill="#f2f2f2">{esc(v)}</text>')
        left += '</g>'
        y += len(vals) * lh + gap
        n += 1
    last_line = rows[-1][1][-1]
    cur_y = y - gap - lh
    left += (f'<rect x="{204 + len(last_line) * 8.7 + 6:.1f}" y="{cur_y - 12:.1f}" width="8" height="15" fill="#fff"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>')
    body, extra = split_frame(inner_h, left, ROOT / "assets" / "goals.png", True)
    return section_svg("Hobbies & Goals", "target", inner_h, body, extra)


# --------------------------------------------------------------------------- tech
TECH = {
    "php": ("PHP", "php", "php"), "javascript": ("JAVASCRIPT", "javascript", "javascript"),
    "typescript": ("TYPESCRIPT", "typescript", "typescript"), "html": ("HTML", "html5", "html5"),
    "css": ("CSS", "css3", "css3"), "scss": ("SCSS", "sass", "sass"),
    "python": ("PYTHON", "python", "python"), "java": ("JAVA", "java", "openjdk"),
    "c": ("C", "c", "c"), "c++": ("C++", "cplusplus", "cplusplus"),
    "c#": ("C#", "csharp", "csharp"), "go": ("GO", "go", "go"),
    "rust": ("RUST", "rust", "rust"), "ruby": ("RUBY", "ruby", "ruby"),
    "kotlin": ("KOTLIN", "kotlin", "kotlin"), "swift": ("SWIFT", "swift", "swift"),
    "dart": ("DART", "dart", "dart"), "shell": ("SHELL", "bash", "gnubash"),
    "vue": ("VUE", "vuejs", "vuedotjs"), "blade": ("BLADE", "laravel", "laravel"),
    "jupyter notebook": ("JUPYTER", "jupyter", "jupyter"), "dockerfile": ("DOCKER", "docker", "docker"),
    "docker": ("DOCKER", "docker", "docker"), "mysql": ("MYSQL", "mysql", "mysql"),
    "git": ("GIT", "git", "git"), "github": ("GITHUB", "github", "github"),
    "nodejs": ("NODE.JS", "nodejs", "nodedotjs"), "react": ("REACT", "react", "react"),
    "laravel": ("LARAVEL", "laravel", "laravel"), "tailwindcss": ("TAILWIND", "tailwindcss", "tailwindcss"),
    "bootstrap": ("BOOTSTRAP", "bootstrap", "bootstrap"), "mongodb": ("MONGODB", "mongodb", "mongodb"),
    "postgresql": ("POSTGRESQL", "postgresql", "postgresql"), "firebase": ("FIREBASE", "firebase", "firebase"),
    "figma": ("FIGMA", "figma", "figma"), "vscode": ("VS CODE", "vscode", "visualstudiocode"),
    "linux": ("LINUX", "linux", "linux"), "npm": ("NPM", "npm", "npm"),
    "express": ("EXPRESS", "express", "express"), "nextjs": ("NEXT.JS", "nextjs", "nextdotjs"),
    "wordpress": ("WORDPRESS", "wordpress", "wordpress"), "jquery": ("JQUERY", "jquery", "jquery"),
    "flutter": ("FLUTTER", "flutter", "flutter"), "strapi": ("STRAPI", "strapi", "strapi"),
    "postman": ("POSTMAN", "postman", "postman"), "canva": ("CANVA", "canva", "canva"),
    "photoshop": ("PHOTOSHOP", "photoshop", "adobephotoshop"), "illustrator": ("ILLUSTRATOR", "illustrator", "adobeillustrator"),
}
ALIAS = {"node.js": "nodejs", "node": "nodejs", "tailwind": "tailwindcss", "tailwind css": "tailwindcss",
         "js": "javascript", "ts": "typescript", "html5": "html", "css3": "css", "vs code": "vscode",
         "postgres": "postgresql", "next.js": "nextjs", "vue.js": "vue", "react.js": "react", "c plus plus": "c++"}


def tech_key(name):
    k = name.strip().lower()
    return ALIAS.get(k, k)


def http_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-visuals"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_icon(key):
    """Monochrome brand glyph (simple-icons, then devicon 'plain'); None on failure."""
    meta = TECH.get(key)
    if not meta:
        return None
    _label, dev, simple = meta
    for ver in ("latest", "11.14.0"):
        try:
            txt = http_get(f"https://cdn.jsdelivr.net/npm/simple-icons@{ver}/icons/{simple}.svg").decode("utf-8", "ignore")
            m = re.search(r'<path d="([^"]+)"', txt)
            if m:
                return ("simple", "0 0 24 24", m.group(1))
        except Exception:
            pass
    try:
        txt = http_get(f"https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/{dev}/{dev}-plain.svg").decode("utf-8", "ignore")
        m = re.search(r'<svg[^>]*viewBox="([^"]+)"[^>]*>(.*)</svg>', txt, re.S)
        if m and "<image" not in m.group(2):
            inner = re.sub(r'\sfill="(?!none)[^"]*"', "", m.group(2))
            inner = re.sub(r'\sstyle="[^"]*"', "", inner)
            inner = re.sub(r"<style.*?</style>", "", inner, flags=re.S)
            return ("dev", m.group(1), inner)
    except Exception:
        pass
    return None


def build_tech_items(cfg, langs, fetch_icons=True):
    total = sum(s for _n, s, _c in langs) or 1
    items, seen = [], set()
    hidden = [tech_key(x) for x in cfg["hide_tech"]]

    def add(name):
        key = tech_key(name)
        if key in seen or key in hidden:
            return
        seen.add(key)
        items.append({"key": key, "label": TECH[key][0] if key in TECH else name.upper()})

    for name, size, _col in sorted(langs, key=lambda x: -x[1]):
        key = tech_key(name)
        share = size / total
        if (key in TECH and share >= 0.01) or (key not in TECH and share >= 0.05):
            add(name)
    for extra in cfg["extra_tech"]:
        add(extra)
    items = items[: int(cfg["max_tech"])]
    for it in items:
        it["icon"] = get_icon(it["key"]) if fetch_icons else None
    return items


def tech_svg(items):
    gap_x, gap_y, pad, row_h = 38, 22, 28, 40
    for it in items:
        it["tw"] = len(it["label"]) * 9.4
        it["pw"] = 30 + 12 + it["tw"]
    rows, cur, cur_w = [], [], 0
    for it in items:
        add_w = it["pw"] + (gap_x if cur else 0)
        if cur and cur_w + add_w > 800:
            rows.append(cur)
            cur, cur_w, add_w = [], 0, it["pw"]
        cur.append(it)
        cur_w += add_w
    if cur:
        rows.append(cur)
    inner_h = pad * 2 + len(rows) * row_h + max(0, len(rows) - 1) * gap_y
    body, idx = "", 0
    for r, row in enumerate(rows):
        rw = sum(i["pw"] for i in row) + gap_x * (len(row) - 1)
        x = W / 2 - rw / 2
        y = pad + r * (row_h + gap_y)
        for it in row:
            ic = it["icon"]
            if ic and ic[0] == "dev":
                glyph = f'<svg x="0" y="4" width="30" height="30" viewBox="{ic[1]}"><g fill="{ICON_COL}">{ic[2]}</g></svg>'
            elif ic and ic[0] == "simple":
                glyph = f'<svg x="0" y="4" width="30" height="30" viewBox="0 0 24 24"><path d="{ic[2]}" fill="{ICON_COL}"/></svg>'
            else:
                glyph = (f'<text x="15" y="26" text-anchor="middle" font-family="{FONT_MONO}" font-size="16" '
                         f'font-weight="800" fill="{ICON_COL}">{esc(it["label"][:2])}</text>')
            b = idx * 0.09
            body += f'''
<g opacity="0" transform="translate({x:.1f} {y + 14})">
<animateTransform attributeName="transform" type="translate" from="{x:.1f} {y + 14}" to="{x:.1f} {y}" begin="{b:.2f}s" dur="0.6s" fill="freeze"/>
<animate attributeName="opacity" from="0" to="1" begin="{b:.2f}s" dur="0.6s" fill="freeze"/>
<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -3;0 0" dur="{3.2 + (idx % 4) * 0.5:.1f}s" begin="{0.8 + b:.2f}s" repeatCount="indefinite"/>
{glyph}
<text x="42" y="26" font-family="{FONT_MONO}" font-size="14.5" font-weight="700" fill="{C['text']}" letter-spacing="1" textLength="{it['tw']:.1f}" lengthAdjust="spacing">{esc(it['label'])}</text>
<rect x="0" y="38" width="{it['pw']:.1f}" height="1.5" fill="#fff" opacity="0"><animate attributeName="opacity" values="0;0.8;0" dur="{4 + (idx % 3)}s" begin="{1.5 + b:.2f}s" repeatCount="indefinite"/></rect>
</g></g>'''
            x += it["pw"] + gap_x
            idx += 1
    return section_svg("Technologies", "code", inner_h, body)


# --------------------------------------------------------------------------- stats
def compute_stats(weeks):
    days = [d for wk in weeks for d in wk]
    total = sum(d["count"] for d in days)
    best_len, best_rng, run, start = 0, None, 0, 0
    for i, d in enumerate(days):
        if d["count"] > 0:
            if run == 0:
                start = i
            run += 1
            if run > best_len:
                best_len, best_rng = run, (days[start]["date"], d["date"])
        else:
            run = 0
    end = len(days) - 1
    if end >= 0 and days[end]["count"] == 0:
        end -= 1
    cur, i = 0, end
    while i >= 0 and days[i]["count"] > 0:
        cur += 1
        i -= 1
    cur_rng = (days[i + 1]["date"], days[end]["date"]) if cur else None
    busiest = max(days, key=lambda d: d["count"]) if days else {"count": 0, "date": ""}
    return dict(total=total, longest=best_len, longest_range=best_rng, current=cur, current_range=cur_rng,
                best=busiest, days=days, first=days[0]["date"] if days else None)


def level_of(count, mx):
    if count <= 0:
        return 0
    if mx <= 4:
        return min(4, count)
    return min(4, math.ceil(4 * count / mx))


def month_labels(weeks):
    out, last_m, last_i = [], None, -10
    for i, wk in enumerate(weeks):
        date = dt.date.fromisoformat(wk[0]["date"])
        if date.month != last_m and i - last_i >= 3:
            out.append((i, date.strftime("%b")))
            last_m, last_i = date.month, i
        elif date.month != last_m:
            last_m = date.month
    return out


def nice_ticks(maxv):
    step = max(1, math.ceil(maxv / 4))
    return step, [step * k for k in range(5)]


def find_video_source():
    for ext in ("mp4", "webm", "mov", "mkv", "gif"):
        p = ROOT / "assets" / f"video.{ext}"
        if p.exists():
            return p
    return None


def load_video_gif(cfg):
    """Convert the user's video to a small grayscale GIF sized for the 296x190 slot (None if absent)."""
    src = find_video_source()
    if not src:
        return None
    ff = shutil.which("ffmpeg")
    if not ff:
        print("ffmpeg not found", file=sys.stderr)
        return src.read_bytes() if src.suffix == ".gif" else None
    secs = int(cfg.get("video_seconds", 6))
    tries = [(592, 380, 12, secs, 48), (444, 285, 10, max(3, secs - 1), 40), (296, 190, 8, max(3, secs - 2), 32)]
    last = None
    for w, h, fps, dur, colors in tries:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "o.gif"
            vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=gray,split[a][b];"
                  f"[a]palettegen=max_colors={colors}[p];[b][p]paletteuse=dither=bayer:bayer_scale=5")
            r = subprocess.run([ff, "-y", "-v", "error", "-t", str(dur), "-i", str(src), "-vf", vf, "-loop", "0", str(out)],
                               capture_output=True, text=True, timeout=240)
            if r.returncode != 0 or not out.exists():
                print("ffmpeg failed:", r.stderr[:300], file=sys.stderr)
                continue
            last = out.read_bytes()
            if len(last) <= 2_000_000:
                return last
    return last


def video_slot(x, y, w, h, gif):
    cid = "vclip"
    clip = f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/></clipPath>'
    if gif:
        b64 = base64.b64encode(gif).decode()
        inner = (f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" '
                 f'href="data:image/gif;base64,{b64}" xlink:href="data:image/gif;base64,{b64}"/>')
    else:
        stripes = "".join(f'<rect x="{x - 60 + i * 26}" y="{y - 10}" width="9" height="{h + 20}" fill="#fff" opacity="0.05" transform="skewX(-20)"/>' for i in range(18))
        inner = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#0b0b0b"/>'
                 f'<g><animateTransform attributeName="transform" type="translate" from="0 0" to="26 0" dur="1.6s" repeatCount="indefinite"/>{stripes}</g>'
                 f'<circle cx="{x + w / 2}" cy="{y + h / 2 - 12}" r="26" fill="none" stroke="#fff" stroke-width="2"/>'
                 f'{icon("play", x + w / 2 - 11, y + h / 2 - 24, 24, "#fff", 1.5, "#fff")}'
                 f'<text x="{x + w / 2}" y="{y + h / 2 + 38}" text-anchor="middle" font-family="{FONT_MONO}" font-size="11.5" fill="{C["mute"]}">add assets/video.mp4</text>')
    scan = (f'<rect x="{x}" y="{y - 40}" width="{w}" height="40" fill="url(#gVhi)" opacity="0.10"><animate attributeName="y" values="{y - 40};{y + h}" dur="4s" repeatCount="indefinite"/></rect>')
    brackets = ""
    for bx, by, sx, sy in [(x + 8, y + 8, 1, 1), (x + w - 8, y + 8, -1, 1), (x + 8, y + h - 8, 1, -1), (x + w - 8, y + h - 8, -1, -1)]:
        brackets += (f'<path d="M{bx},{by + 14 * sy} L{bx},{by} L{bx + 14 * sx},{by}" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round">'
                     f'<animate attributeName="opacity" values="1;0.35;1" dur="2.6s" repeatCount="indefinite"/></path>')
    return clip, f'<g clip-path="url(#{cid})">{inner}{scan}</g>{brackets}<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{C["line2"]}" stroke-width="1.3"/>'


def stats_svg(d, gif):
    weeks, pending = d["weeks"], d["pending"]
    st = compute_stats(weeks)
    nW = len(weeks)
    mx = max((x["count"] for wk in weeks for x in wk), default=0)

    def val(v, suffix=""):
        return "--" if pending else f"{fmt(v)}{suffix}"

    rng_total = f"{short_date(st['first'])} - Present" if st["first"] else "-"
    rng_cur = f"{short_date(st['current_range'][0])} - {short_date(st['current_range'][1])}" if st["current_range"] and not pending else "-"
    rng_best = f"{short_date(st['longest_range'][0])} - {short_date(st['longest_range'][1])}" if st["longest_range"] and not pending else "-"
    busiest = st["best"]
    inner_defs = ""
    body = ""

    # ---- video + cards
    vclip, vsvg = video_slot(30, 16, 296, 190, gif)
    inner_defs += vclip
    body += vsvg
    cards = [("Total Contributions", val(st["total"]), rng_total),
             ("Current Streak", val(st["current"]), rng_cur),
             ("Longest Streak", val(st["longest"]), rng_best)]
    for i, (label, value, cap) in enumerate(cards):
        x = 342 + i * 180
        cx = x + 84
        b = i * 0.18
        body += f'''<g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{b}s" dur="0.6s" fill="freeze"/>
<animateTransform attributeName="transform" type="translate" from="0 10" to="0 0" begin="{b}s" dur="0.6s" fill="freeze"/>
<rect x="{x}" y="16" width="168" height="190" rx="8" fill="#030303" stroke="{C['line']}" stroke-width="1.3"/>
<rect x="{x + 34}" y="16" width="100" height="1.6" fill="url(#gHi)" opacity="0.8"/>'''
        if i == 1:
            frac = 0 if pending or not st["longest"] else min(1.0, st["current"] / max(1, st["longest"]))
            body += f'''<circle cx="{cx}" cy="86" r="42" fill="none" stroke="#262626" stroke-width="4"/>
<circle cx="{cx}" cy="86" r="42" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" pathLength="1" stroke-dasharray="0 1" transform="rotate(-90 {cx} 86)" filter="url(#glow)"><animate attributeName="stroke-dasharray" from="0 1" to="{max(frac, 0.02):.3f} 1" begin="0.4s" dur="1.6s" fill="freeze"/></circle>
<rect x="{cx - 14}" y="38" width="28" height="14" fill="#030303"/>
<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -2;0 0" dur="1.8s" repeatCount="indefinite"/>{icon("flame", cx - 11, 32, 22, "#fff", 1.8)}</g>
<text x="{cx}" y="98" text-anchor="middle" font-family="{FONT_SANS}" font-size="34" font-weight="800" fill="#fff">{esc(value)}</text>'''
        else:
            body += f'<text x="{cx}" y="98" text-anchor="middle" font-family="{FONT_SANS}" font-size="42" font-weight="800" fill="#fff">{esc(value)}</text>'
        body += f'''<text x="{cx}" y="156" text-anchor="middle" font-family="{FONT_SANS}" font-size="14.5" font-weight="700" fill="{C['text']}">{esc(label)}</text>
<text x="{cx}" y="177" text-anchor="middle" font-family="{FONT_MONO}" font-size="11.5" fill="{C['mute']}">{esc(cap)}</text></g>'''

    # ---- heatmap + jet
    body += f'<rect x="30" y="226" width="{W - 60}" height="1.2" fill="{C["line"]}"/>'
    body += icon("grid", 30, 242, 18, "#fff", 1.8) + f'<text x="56" y="257" font-family="{FONT_SANS}" font-size="17" font-weight="700" fill="#fff">Contribution Activity</text>'
    step = min(16.0, (W - 60) / max(1, nW))
    cell = step - 3
    x0 = (W - (nW * step - 3)) / 2
    y0 = 296
    for i, name in month_labels(weeks):
        body += f'<text x="{x0 + i * step:.1f}" y="{y0 - 8}" font-family="{FONT_MONO}" font-size="11" fill="{C["mute"]}">{name}</text>'
    ranked = sorted(((x["count"], ci, x["wd"]) for ci, wk in enumerate(weeks) for x in wk), reverse=True)
    targets = [(c, ci, wd) for c, ci, wd in ranked if c > 0][:6]
    for ci, wk in enumerate(weeks):
        for x in wk:
            lv = level_of(x["count"], mx)
            px, py = x0 + ci * step, y0 + x["wd"] * step
            beg = ci * 0.028 + x["wd"] * 0.01
            pulse = ""
            if lv >= 3:
                pulse = (f'<animate attributeName="fill-opacity" values="1;0.4;1" dur="{2.4 + (ci % 5) * 0.3:.1f}s" '
                         f'begin="{beg + 1.5:.2f}s" repeatCount="indefinite"/>')
            stroke = ' stroke="#262626" stroke-width="0.8"' if lv == 0 else ""
            body += (f'<rect x="{px:.1f}" y="{py:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{LEVELS[lv]}"{stroke} opacity="0">'
                     f'<animate attributeName="opacity" from="0" to="1" begin="{beg:.2f}s" dur="0.35s" fill="freeze"/>{pulse}</rect>')
    jy = y0 + 7 * step + 22
    xj0, xj1 = x0 + cell / 2, x0 + (nW - 1) * step + cell / 2
    D = 14
    body += f'''<g><g>
<polygon points="-2,9 0,15 2,9" fill="#fff"><animate attributeName="points" values="-2,9 0,14 2,9;-3,9 0,21 3,9;-2,9 0,14 2,9" dur="0.25s" repeatCount="indefinite"/></polygon>
<path d="M0,-12 L6,6 L2,4 L0,9 L-2,4 L-6,6 Z" fill="#fff" stroke="#bbb" stroke-width="1" filter="url(#glow)"/>
<circle cy="-2" r="2" fill="#000"/></g>
<animateTransform attributeName="transform" type="translate" from="{xj0:.1f} {jy}" to="{xj1:.1f} {jy}" dur="{D}s" repeatCount="indefinite"/></g>'''
    for c, ci, wd in ([] if pending else targets):
        cx = x0 + ci * step + cell / 2
        cy = y0 + wd * step + cell / 2
        t = ci / max(1, nW - 1)
        t1 = min(0.985, t + 0.02)
        t0 = min(t, t1 - 0.005)
        kt = f"0;{t0:.4f};{t1:.4f};1"
        body += (f'<line x1="{cx:.1f}" y1="{jy - 14}" x2="{cx:.1f}" y2="{cy + 8:.1f}" stroke="#fff" stroke-width="2.4" stroke-linecap="round" opacity="0" filter="url(#glow)">'
                 f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="{kt}" calcMode="discrete" dur="{D}s" repeatCount="indefinite"/></line>'
                 f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="11" fill="none" stroke="#fff" stroke-width="2" opacity="0">'
                 f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="{kt}" calcMode="discrete" dur="{D}s" repeatCount="indefinite"/></circle>')
    cap_y = jy + 36
    body += (f'<text x="30" y="{cap_y}" font-family="{FONT_SANS}" font-size="12.5" fill="{C["mute"]}">'
             f'A jet flies the length of the year and fires at your busiest days. Give it a few seconds.</text>')
    lx = W - 30 - 5 * 17 - 70
    body += f'<text x="{lx - 6}" y="{cap_y}" text-anchor="end" font-family="{FONT_MONO}" font-size="11" fill="{C["mute"]}">Less</text>'
    for k, col in enumerate(LEVELS):
        body += f'<rect x="{lx + k * 17}" y="{cap_y - 11}" width="12" height="12" rx="3" fill="{col}" stroke="#262626" stroke-width="0.6"/>'
    body += f'<text x="{lx + 5 * 17 + 4}" y="{cap_y}" font-family="{FONT_MONO}" font-size="11" fill="{C["mute"]}">More</text>'

    # ---- 30-day contribution graph
    ty = cap_y + 22
    body += f'<rect x="30" y="{ty}" width="{W - 60}" height="1.2" fill="{C["line"]}"/>'
    body += icon("chart", 30, ty + 16, 18, "#fff", 1.8) + f'<text x="56" y="{ty + 31}" font-family="{FONT_SANS}" font-size="17" font-weight="700" fill="#fff">Contribution Graph</text>'
    last = st["days"][-30:]
    n = len(last)
    counts = [x["count"] for x in last]
    step_y, ticks = nice_ticks(max(counts) if counts else 1)
    top = ticks[-1]
    px0, px1 = 96, 862
    py0, py1 = ty + 96, ty + 96 + 150
    body += (f'<text x="{(px0 + px1) / 2}" y="{ty + 66}" text-anchor="middle" font-family="{FONT_SANS}" font-size="13.5" font-weight="700" fill="#fff">'
             f'{esc(d["login"])}\'s Contribution Graph</text>')
    for t in ticks:
        gy = py1 - t / top * (py1 - py0)
        body += (f'<line x1="{px0}" y1="{gy:.1f}" x2="{px1}" y2="{gy:.1f}" stroke="#2a2a2a" stroke-width="1"/>'
                 f'<text x="{px0 - 10}" y="{gy + 4:.1f}" text-anchor="end" font-family="{FONT_MONO}" font-size="11" fill="{C["mute"]}">{t}</text>')
    pts = [(px0 + i * (px1 - px0) / max(1, n - 1), py1 - v / top * (py1 - py0)) for i, v in enumerate(counts)]
    for i, (px, _py) in enumerate(pts):
        dd = dt.date.fromisoformat(last[i]["date"]).day
        body += (f'<line x1="{px:.1f}" y1="{py0}" x2="{px:.1f}" y2="{py1}" stroke="#1d1d1d" stroke-width="1"/>'
                 f'<text x="{px:.1f}" y="{py1 + 17}" text-anchor="middle" font-family="{FONT_MONO}" font-size="10.5" font-weight="700" fill="{C["mute"]}">{dd}</text>')
    body += (f'<text x="{(px0 + px1) / 2}" y="{py1 + 38}" text-anchor="middle" font-family="{FONT_MONO}" font-size="11" font-weight="700" fill="{C["mute"]}">Days</text>'
             f'<text transform="translate(44 {(py0 + py1) / 2}) rotate(-90)" text-anchor="middle" font-family="{FONT_MONO}" font-size="11" font-weight="700" fill="{C["mute"]}">Contributions</text>')
    if len(pts) >= 2:
        line = smooth_path(pts)
        area = line + f" L{pts[-1][0]:.1f},{py1} L{pts[0][0]:.1f},{py1} Z"
        body += f'''<path d="{area}" fill="url(#areaG)" opacity="0"><animate attributeName="opacity" from="0" to="1" begin="1.4s" dur="1.2s" fill="freeze"/></path>
<path d="{line}" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" filter="url(#glow)"><animate attributeName="stroke-dashoffset" from="1" to="0" dur="2.6s" begin="0.3s" fill="freeze"/></path>'''
        for i, (px, py) in enumerate(pts):
            body += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.6" fill="#000" stroke="#fff" stroke-width="1.5" opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{0.3 + 2.6 * i / max(1, n - 1):.2f}s" dur="0.3s" fill="freeze"/></circle>'
        if not pending and counts and max(counts) > 0:
            pi = counts.index(max(counts))
            px, py = pts[pi]
            body += f'''<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#fff" filter="url(#glow)"/>
<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="none" stroke="#fff" stroke-width="1.6"><animate attributeName="r" values="5;17" dur="2.2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.9;0" dur="2.2s" repeatCount="indefinite"/></circle>
<circle r="3.4" fill="#fff" filter="url(#glow)"><animateMotion dur="9s" begin="3s" repeatCount="indefinite" path="{line}"/></circle>'''
    if pending:
        body += (f'<rect x="{W / 2 - 230}" y="{y0 + 30}" width="460" height="48" rx="24" fill="#000" stroke="#fff" stroke-width="1.5"/>'
                 f'<text x="{W / 2}" y="{y0 + 60}" text-anchor="middle" font-family="{FONT_MONO}" font-size="14" fill="#fff">Waiting for first sync: run the workflow once</text>')
    inner_h = int(py1 + 56)
    inner_defs += '<linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.28"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
    return section_svg("Statistics", "chart", inner_h, body, inner_defs)


# --------------------------------------------------------------------------- scan (visual map + system info)
def avatar_grid(img_bytes, n=36):
    cells = []
    R = n / 2
    if img_bytes:
        try:
            from PIL import Image, ImageOps
            im = Image.open(io.BytesIO(img_bytes)).convert("L")
            s = min(im.size)
            im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
            im = ImageOps.autocontrast(im.resize((n, n), Image.LANCZOS), cutoff=2)
            px = im.load()
            for j in range(n):
                for i in range(n):
                    if math.hypot(i + 0.5 - R, j + 0.5 - R) <= R - 0.3:
                        cells.append((i, j, px[i, j] / 255))
            return cells
        except Exception as e:  # noqa
            print("avatar processing failed:", e, file=sys.stderr)
    for j in range(n):
        for i in range(n):
            dd = math.hypot(i + 0.5 - R, j + 0.5 - R)
            if dd <= R - 0.3:
                gx, gy = (i + 0.5 - R) / R, (j + 0.5 - R) / R
                k = (-0.42 <= gx <= -0.24 and abs(gy) <= 0.52) or (-0.24 < gx <= 0.42 and abs(gy) <= 0.52 and abs(abs(gy) - (gx + 0.24) * 0.8) <= 0.1)
                cells.append((i, j, 0.95 if k else 0.18 + 0.3 * (1 - dd / R)))
    return cells


def trunc(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "..."


def scan_svg(d):
    inner_h = 352
    pending = d["pending"]
    st = compute_stats(d["weeks"])
    langs = ", ".join(n for n, _s, _c in sorted(d["langs"], key=lambda x: -x[1])[:4]) or "-"
    joined = dt.date.fromisoformat(d["created"][:10]).strftime("%b %Y") if d.get("created") else "-"
    rows = [
        ("Subject", d["name"] or d["login"]),
        ("Handle", "@" + d["login"]),
        ("Role", d["role"]),
        ("Bio", d["bio"] or ("syncing..." if pending else "-")),
        ("Languages", langs),
        ("Repositories", "--" if pending else fmt(d["repos"])),
        ("Contributions", "--" if pending else f"{fmt(st['total'])} this year"),
        ("Stars", "--" if pending else fmt(d["stars"])),
        ("Followers", "--" if pending else f"{fmt(d['followers'])}  |  following {fmt(d['following'])}"),
        ("Joined", joined if not pending else "--"),
    ]
    n, cell = 36, 6.3
    cxm, cym = 183, 196
    ox, oy = cxm - n * cell / 2, cym - n * cell / 2
    rnd = random.Random(5)
    dots = ""
    for i, j, v in avatar_grid(d.get("avatar"), n):
        v = v ** 0.9
        r = 0.7 + v * 2.55
        cls = f"c{min(5, int(v * 5.99))}"
        op = 0.3 + 0.7 * v
        shim = ""
        if rnd.random() < 0.07:
            shim = (f'<animate attributeName="opacity" values="{op:.2f};1;{op:.2f}" dur="{rnd.uniform(1.6, 3.6):.1f}s" '
                    f'begin="{rnd.uniform(0, 3):.1f}s" repeatCount="indefinite"/>')
        dots += f'<circle class="{cls}" cx="{ox + (i + 0.5) * cell:.1f}" cy="{oy + (j + 0.5) * cell:.1f}" r="{r:.2f}" opacity="{op:.2f}">{shim}</circle>'
    style = ".c0{fill:#2a2a2a}.c1{fill:#4a4a4a}.c2{fill:#757575}.c3{fill:#a5a5a5}.c4{fill:#d4d4d4}.c5{fill:#fff}"
    extra = f'''
<clipPath id="disc"><circle cx="{cxm}" cy="{cym}" r="{n * cell / 2}"/></clipPath>
<linearGradient id="scanG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.85" stop-color="#fff" stop-opacity="0.4"/><stop offset="1" stop-color="#fff" stop-opacity="0.95"/></linearGradient>'''
    body = f'<text x="30" y="14" font-family="{FONT_MONO}" font-size="12.5" fill="{C["mute"]}">{esc(d["login"].lower())}@github ~ $ ./profile-scan --live</text>'
    body += f'<g transform="translate(0 6)"><rect x="30" y="22" width="310" height="300" rx="8" fill="#030303" stroke="{C["line"]}" stroke-width="1.3"/>'
    body += f'<text x="46" y="44" font-family="{FONT_MONO}" font-size="11" letter-spacing="2" fill="{C["mute"]}">VISUAL.MAP</text>'
    body += (f'<g clip-path="url(#disc)">{dots}<rect x="{cxm - 120}" y="{cym - n * cell / 2 - 24}" width="240" height="24" fill="url(#scanG)">'
             f'<animate attributeName="y" values="{cym - n * cell / 2 - 24};{cym + n * cell / 2}" dur="3.4s" repeatCount="indefinite"/></rect></g>')
    body += (f'<circle cx="{cxm}" cy="{cym}" r="{n * cell / 2 + 7}" fill="none" stroke="#fff" stroke-opacity="0.5" stroke-width="1.3" stroke-dasharray="4 9">'
             f'<animateTransform attributeName="transform" type="rotate" from="0 {cxm} {cym}" to="360 {cxm} {cym}" dur="18s" repeatCount="indefinite"/></circle>')
    for (bx, by, sx, sy) in [(46, 58, 1, 1), (324, 58, -1, 1), (46, 308, 1, -1), (324, 308, -1, -1)]:
        body += (f'<path d="M{bx},{by + 14 * sy} L{bx},{by} L{bx + 14 * sx},{by}" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round">'
                 f'<animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite"/></path>')
    body += f'<rect x="358" y="22" width="512" height="300" rx="8" fill="#030303" stroke="{C["line"]}" stroke-width="1.3"/>'
    body += f'<text x="374" y="44" font-family="{FONT_MONO}" font-size="11" letter-spacing="2" fill="{C["mute"]}">SYSTEM.INFO</text>'
    body += (f'<circle cx="846" cy="40" r="4" fill="#fff"><animate attributeName="opacity" values="1;0.2;1" dur="1.4s" repeatCount="indefinite"/></circle>'
             f'<text x="836" y="44" text-anchor="end" font-family="{FONT_MONO}" font-size="11" fill="#fff">LIVE</text>')
    y = 76
    for k, (key, value) in enumerate(rows):
        b = 0.3 + k * 0.22
        body += (f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{b:.2f}s" dur="0.4s" fill="freeze"/>'
                 f'<text x="374" y="{y}" font-family="{FONT_MONO}" font-size="13.5" font-weight="700" fill="{C["mute"]}">{key}</text>'
                 f'<text x="520" y="{y}" font-family="{FONT_MONO}" font-size="13.5" fill="#f2f2f2">{esc(trunc(value, 38))}</text>'
                 f'<line x1="374" y1="{y + 9}" x2="854" y2="{y + 9}" stroke="#1f1f1f"/></g>')
        y += 24
    body += f'<rect x="374" y="{y - 10}" width="9" height="15" fill="#fff"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect></g>'
    return section_svg("Profile Scan", "scan", inner_h, body, extra, style)


# --------------------------------------------------------------------------- data sources
QUERY = """
query($login:String!){
  user(login:$login){
    name login bio avatarUrl createdAt
    followers{totalCount} following{totalCount}
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC, orderBy:{field:PUSHED_AT,direction:DESC}){
      totalCount
      nodes{ stargazerCount languages(first:8, orderBy:{field:SIZE,direction:DESC}){ edges{ size node{ name color } } } }
    }
    contributionsCollection{ contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount weekday } } } }
  }
}"""


def fetch_live(cfg):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    login = cfg["username"]
    if not token:
        sys.exit("GH_TOKEN is missing")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-visuals"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())
    if "errors" in res or not res.get("data", {}).get("user"):
        sys.exit(f"GitHub API error: {res.get('errors') or 'user not found'}")
    u = res["data"]["user"]
    langs, stars = {}, 0
    for repo in u["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            s, _c = langs.get(n, (0, e["node"]["color"]))
            langs[n] = (s + e["size"], e["node"]["color"])
    weeks = [[{"date": x["date"], "count": x["contributionCount"], "wd": x["weekday"]} for x in wk["contributionDays"]]
             for wk in u["contributionsCollection"]["contributionCalendar"]["weeks"]]
    avatar = None
    try:
        url = u["avatarUrl"] + ("&" if "?" in u["avatarUrl"] else "?") + "s=300"
        avatar = http_get(url, 20)
    except Exception as e:
        print("avatar download failed:", e, file=sys.stderr)
    return dict(login=u["login"], name=u["name"], bio=u["bio"], created=u["createdAt"], avatar=avatar,
                followers=u["followers"]["totalCount"], following=u["following"]["totalCount"],
                repos=u["repositories"]["totalCount"], stars=stars,
                langs=[(n, s, c) for n, (s, c) in langs.items()], weeks=weeks, pending=False, role=cfg["role"])


def empty_weeks():
    today = dt.date.today()
    start = today - dt.timedelta(days=(today.weekday() + 1) % 7) - dt.timedelta(weeks=52)
    weeks, d = [], start
    while d <= today:
        wk = []
        for _ in range(7):
            if d <= today:
                wk.append({"date": d.isoformat(), "count": 0, "wd": (d.weekday() + 1) % 7})
            d += dt.timedelta(days=1)
        weeks.append(wk)
    return weeks


def pending_data(cfg):
    return dict(login=cfg["username"], name=None, bio=None, created=None, avatar=None, followers=0, following=0,
                repos=0, stars=0, langs=[("PHP", 4, ""), ("JavaScript", 3, ""), ("CSS", 2, ""), ("HTML", 2, "")],
                weeks=empty_weeks(), pending=True, role=cfg["role"])


def mock_data(cfg):
    rnd = random.Random(2)
    weeks = empty_weeks()
    for wk in weeks:
        for x in wk:
            x["count"] = rnd.choice([0, 0, 0, 1, 2, 3, 5, 8, 13]) if x["wd"] not in (0, 6) else rnd.choice([0, 0, 0, 1, 2])
    avatar = None
    p = os.environ.get("MOCK_AVATAR")
    if p and Path(p).exists():
        avatar = Path(p).read_bytes()
    return dict(login=cfg["username"], name="Mock Name", bio="you can never be too happy in this life",
                created="2024-03-05T00:00:00Z", avatar=avatar, followers=3, following=4, repos=10, stars=2,
                langs=[("PHP", 5000, ""), ("JavaScript", 3000, ""), ("CSS", 1500, ""), ("HTML", 2500, ""), ("Blade", 400, "")],
                weeks=weeks, pending=False, role=cfg["role"])


# --------------------------------------------------------------------------- main
def main():
    cfg = load_config()
    mode = "live"
    if "--mock" in sys.argv:
        mode = "mock"
    if "--pending" in sys.argv:
        mode = "pending"
    d = {"live": fetch_live, "mock": mock_data, "pending": pending_data}[mode](cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    items = build_tech_items(cfg, d["langs"], fetch_icons=(mode == "live" or "--icons" in sys.argv))
    gif = load_video_gif(cfg)
    files = {
        "banner.svg": banner_svg(cfg, d["login"]),
        "about.svg": about_svg(cfg),
        "goals.svg": goals_svg(cfg),
        "tech.svg": tech_svg(items),
        "stats.svg": stats_svg(d, gif),
        "scan.svg": scan_svg(d),
        "footer.svg": footer_svg(),
    }
    for stale in ("h-tech.svg", "h-stats.svg", "h-scan.svg", "h-about.svg", "h-goals.svg"):
        (OUT / stale).unlink(missing_ok=True)
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
    print(f"[{mode}] wrote {len(files)} files to {OUT}" + (f" (video {len(gif) // 1024} KB)" if gif else " (no video)"))


if __name__ == "__main__":
    main()
