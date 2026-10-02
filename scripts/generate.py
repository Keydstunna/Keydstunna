#!/usr/bin/env python3
"""
Profile visuals generator.

Reads LIVE data from the GitHub API (contributions, repos, languages, avatar,
followers...) and writes animated, responsive SVG panels into assets/generated/.

  python scripts/generate.py            live data (needs GH_TOKEN and GH_USER)
  python scripts/generate.py --mock     fake data, for local layout testing only
  python scripts/generate.py --pending  empty placeholder state (before 1st sync)
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
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "generated"

FONT_MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
FONT_SANS = "'Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif"

C = dict(bg1="#050a17", bg2="#0b1633", a1="#3b82f6", a2="#38bdf8", a3="#818cf8",
         text="#dbeafe", mute="#7f9cc9", hi="#e0f2fe")
LEVELS = ["#0f1b36", "#1e40af", "#2563eb", "#38bdf8", "#e0f2fe"]

esc = html.escape


def fmt(n):
    return f"{int(n):,}"


# --------------------------------------------------------------------------- config
def load_config():
    cfg = {
        "username": os.environ.get("GH_USER", "Keydstunna"),
        "role": "BSIT Student | Web Developer",
        "banner_text": "Welcome to Keydstunna's GitHub",
        "extra_tech": ["MySQL", "Git", "GitHub"],
        "hide_tech": [],
        "max_tech": 12,
    }
    p = ROOT / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


# --------------------------------------------------------------------------- svg helpers
ICONS = {
    "code": "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16",
    "chart": "M4 20V11M10 20V4M16 20V13M21 20H3",
    "user": "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 7 0 0116 0",
    "target": "M12 3a9 9 0 100 18 9 9 0 000-18zM12 8a4 4 0 100 8 4 4 0 000-8zM12 12h.01",
    "scan": "M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M4 12h16",
    "commit": "M3 12h5M16 12h5M8 12a4 4 0 108 0 4 4 0 10-8 0",
    "flame": "M12 3c1 3 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z",
    "bolt": "M13 2L4 14h7l-1 8 9-12h-7z",
    "star": "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
}


def icon(name, x, y, size, color, sw=2):
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({size / 24:.4f})" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"><path d="{ICONS[name]}"/></g>')


def defs_common():
    return f'''
<linearGradient id="gBg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C['bg2']}"/><stop offset="1" stop-color="{C['bg1']}"/></linearGradient>
<linearGradient id="gBd" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C['a1']}"/><stop offset="0.55" stop-color="{C['a2']}"/><stop offset="1" stop-color="{C['a3']}"/></linearGradient>
<linearGradient id="gTx" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#93c5fd"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#1e3a8a" stroke-opacity="0.18" stroke-width="1"/></pattern>'''


def svg_doc(w, h, body, extra_defs="", style=""):
    st = f"<style>{style}</style>" if style else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">\n'
            f'<defs>{defs_common()}{extra_defs}</defs>{st}\n{body}\n</svg>\n')


def panel(w, h, rx=20):
    r = f'x="3" y="3" width="{w - 6}" height="{h - 6}" rx="{rx}"'
    return (f'<rect {r} fill="url(#gBg)"/><rect {r} fill="url(#grid)"/>'
            f'<rect {r} fill="none" stroke="url(#gBd)" stroke-width="2.5">'
            f'<animate attributeName="stroke-opacity" values="1;0.5;1" dur="5s" repeatCount="indefinite"/></rect>')


def titlebar(w, text):
    return (f'<circle cx="30" cy="28" r="6" fill="#ff5f56"/><circle cx="50" cy="28" r="6" fill="#ffbd2e"/>'
            f'<circle cx="70" cy="28" r="6" fill="#27c93f"/>'
            f'<text x="{w / 2}" y="33" text-anchor="middle" font-family="{FONT_MONO}" font-size="12.5" '
            f'fill="{C["a2"]}" opacity="0.85">{esc(text)}</text>')


def smooth_path(pts):
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        mx = (x0 + x1) / 2
        d += f" C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
    return d


# --------------------------------------------------------------------------- headings
def heading_svg(title, icon_name):
    w, h = 900, 66
    tw = len(title) * 16.5
    total = 44 + 14 + tw
    x0 = 450 - total / 2
    cx, cy = x0 + 22, 30
    extra = f'''
<linearGradient id="lineG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{C['a1']}" stop-opacity="0"/><stop offset="0.5" stop-color="{C['a2']}" stop-opacity="0.7"/><stop offset="1" stop-color="{C['a1']}" stop-opacity="0"/></linearGradient>
<linearGradient id="shineG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#fff" stop-opacity="0.95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'''
    extra += f'''
<clipPath id="hp"><rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="18"/></clipPath>'''
    body = f'''
<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="18" fill="url(#gBg)"/>
<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="18" fill="url(#grid)"/>
<g clip-path="url(#hp)">
<circle cx="{cx:.1f}" cy="{cy}" r="19" fill="#0b1a3d" stroke="url(#gBd)" stroke-width="2"/>
<circle cx="{cx:.1f}" cy="{cy}" r="19" fill="none" stroke="{C['a2']}" stroke-width="1.5"><animate attributeName="r" values="19;31" dur="2.8s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.7;0" dur="2.8s" repeatCount="indefinite"/></circle>
{icon(icon_name, cx - 11, cy - 11, 22, C['a2'])}
<text x="{x0 + 58:.1f}" y="{cy + 10}" font-family="{FONT_SANS}" font-size="28" font-weight="800" font-style="italic" fill="{C['hi']}" textLength="{tw:.1f}" lengthAdjust="spacingAndGlyphs">{esc(title)}</text>
<rect x="40" y="54" width="820" height="2" rx="1" fill="url(#lineG)"/>
<rect x="-180" y="53" width="180" height="4" rx="2" fill="url(#shineG)"><animate attributeName="x" from="-180" to="900" dur="4.6s" repeatCount="indefinite"/></rect>
</g>
<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="18" fill="none" stroke="url(#gBd)" stroke-width="2.2"><animate attributeName="stroke-opacity" values="1;0.5;1" dur="5s" repeatCount="indefinite"/></rect>'''
    return svg_doc(w, h, body, extra)


# --------------------------------------------------------------------------- banner
def banner_svg(cfg, login):
    w, h = 900, 270
    rnd = random.Random(11)
    text = cfg["banner_text"]
    n = len(text)
    tw = n * 17.5
    tx = 450 - tw / 2

    stars = ""
    for _ in range(80):
        x, y = rnd.uniform(8, w - 8), rnd.uniform(8, 165)
        r = rnd.choice([0.8, 1.0, 1.2, 1.7])
        stars += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#dbeafe"><animate attributeName="opacity" '
                  f'values="0.12;1;0.12" dur="{rnd.uniform(1.8, 4.8):.1f}s" begin="{rnd.uniform(0, 4):.1f}s" repeatCount="indefinite"/></circle>')

    def shooting(delay, x0, y0, dur):
        x1, y1 = x0 + 280, y0 + 105
        return (f'<g opacity="0"><line x1="0" y1="0" x2="-80" y2="-30" stroke="url(#shootG)" stroke-width="2.2" stroke-linecap="round"/>'
                f'<circle r="2.3" fill="#fff"/>'
                f'<animateTransform attributeName="transform" type="translate" values="{x0} {y0};{x1} {y1};{x1} {y1}" keyTimes="0;0.16;1" dur="{dur}s" begin="{delay}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="0;0.02;0.16;1" dur="{dur}s" begin="{delay}s" repeatCount="indefinite"/></g>')

    def aurora(color, base, amp, phase_list, op):
        variants = []
        for ph in phase_list:
            top, bot = [], []
            for i in range(0, 31):
                x = i * 30
                y = base + amp * math.sin(i * 0.38 + ph) + amp * 0.5 * math.sin(i * 0.9 + ph * 1.7)
                top.append((x, y))
                bot.append((x, y + 46 + 14 * math.sin(i * 0.5 + ph)))
            pts = top + bot[::-1]
            variants.append("M" + " L".join(f"{x},{y:.1f}" for x, y in pts) + " Z")
        values = ";".join(variants + [variants[0]])
        return (f'<path d="{variants[0]}" fill="{color}" opacity="{op}" filter="url(#blur14)">'
                f'<animate attributeName="d" values="{values}" dur="14s" repeatCount="indefinite"/></path>')

    def ridge(base, amp, k1, k2, fill, dur, seed):
        r = random.Random(seed)
        p1, p2, p3 = r.random(), r.random(), r.random()
        pts = []
        for i in range(0, 2 * w // 10 + 1):
            x = i * 10
            y = base - amp * (0.55 * math.sin(2 * math.pi * (k1 * x / w + p1))
                              + 0.30 * math.sin(2 * math.pi * (k2 * x / w + p2))
                              + 0.15 * math.sin(2 * math.pi * (5 * x / w + p3)))
            pts.append((x, y))
        d = f"M0,{h} " + " ".join(f"L{x},{y:.1f}" for x, y in pts) + f" L{2 * w},{h} Z"
        return (f'<path d="{d}" fill="{fill}"><animateTransform attributeName="transform" type="translate" '
                f'from="0 0" to="-{w} 0" dur="{dur}s" repeatCount="indefinite"/></path>')

    code_icon = (f'<g transform="translate(450 168)" fill="none" stroke="#7dd3fc" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)">'
                 f'<path d="M-9,-8 L-19,0 L-9,8"/><path d="M9,-8 L19,0 L9,8"/><path d="M3,-11 L-3,11"/>'
                 f'<animate attributeName="opacity" values="0.55;1;0.55" dur="2.6s" repeatCount="indefinite"/></g>')
    extra = f'''
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#030712"/><stop offset="0.55" stop-color="#0b1a3f"/><stop offset="1" stop-color="#1e3a8a"/></linearGradient>
<linearGradient id="shootG" x1="1" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="blur14" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="14"/></filter>
<clipPath id="round"><rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="20"/></clipPath>
<clipPath id="reveal"><rect x="{tx:.1f}" y="70" width="0" height="56"><animate attributeName="width" from="0" to="{tw:.1f}" dur="2.4s" begin="0.4s" fill="freeze"/></rect></clipPath>'''
    body = f'''
<g clip-path="url(#round)">
<rect width="{w}" height="{h}" fill="url(#sky)"/>
{stars}
{shooting(1.5, 70, 18, 9)}{shooting(5.5, 380, 6, 11)}
{aurora('#38bdf8', 70, 16, [0, 1.6, 3.2], 0.34)}
{aurora('#6366f1', 96, 14, [2, 3.6, 5.2], 0.28)}
{ridge(196, 34, 2, 3, '#10245a', 90, 5)}
{ridge(222, 30, 3, 4, '#0c1b45', 60, 9)}
{ridge(246, 22, 2, 5, '#071230', 40, 13)}
<text x="{tx:.1f}" y="108" font-family="{FONT_MONO}" font-size="28" fill="#bfdbfe" textLength="{tw:.1f}" lengthAdjust="spacing" clip-path="url(#reveal)" filter="url(#glow)">{esc(text)}</text>
<rect y="82" width="3" height="32" fill="#7dd3fc" x="{tx:.1f}"><animate attributeName="x" from="{tx:.1f}" to="{tx + tw:.1f}" dur="2.4s" begin="0.4s" fill="freeze"/><animate attributeName="opacity" values="1;0;1" dur="0.9s" repeatCount="indefinite"/></rect>
{code_icon}
<text x="450" y="206" text-anchor="middle" font-family="{FONT_MONO}" font-size="14" fill="#93c5fd" letter-spacing="2" opacity="0">@{esc(login)}  |  {esc(cfg['role'])}<animate attributeName="opacity" from="0" to="0.9" begin="2.6s" dur="1s" fill="freeze"/></text>
</g>
<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="20" fill="none" stroke="url(#gBd)" stroke-width="2.5"/>'''
    return svg_doc(w, h, body, extra)


# --------------------------------------------------------------------------- footer
def footer_svg():
    w, h = 900, 110
    waves = ""
    for i, (col, op, dur, amp, base) in enumerate([("#1e3a8a", 0.55, 11, 10, 52), ("#2563eb", 0.4, 8, 12, 62), ("#38bdf8", 0.3, 6, 9, 74)]):
        pts = []
        for k in range(0, 2 * w // 15 + 1):
            x = k * 15
            pts.append((x, base + amp * math.sin(2 * math.pi * (2 * x / w) + i)))
        d = f"M0,{h} " + " ".join(f"L{x},{y:.1f}" for x, y in pts) + f" L{2 * w},{h} Z"
        waves += (f'<path d="{d}" fill="{col}" opacity="{op}"><animateTransform attributeName="transform" type="translate" '
                  f'from="0 0" to="-{w} 0" dur="{dur}s" repeatCount="indefinite"/></path>')
    extra = f'<clipPath id="fp"><rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="20"/></clipPath>'
    body = (f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="20" fill="url(#gBg)"/>'
            f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="20" fill="url(#grid)"/>'
            f'<g clip-path="url(#fp)">{waves}</g>'
            f'<text x="{w / 2}" y="40" text-anchor="middle" font-family="{FONT_MONO}" font-size="13" letter-spacing="3" fill="{C["a2"]}" opacity="0.85">THANKS FOR VISITING</text>'
            f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="20" fill="none" stroke="url(#gBd)" stroke-width="2.5"/>')
    return svg_doc(w, h, body, extra)


# --------------------------------------------------------------------------- tech
TECH = {
    "php": ("PHP", "php", "php", "777BB4"), "javascript": ("JAVASCRIPT", "javascript", "javascript", "F7DF1E"),
    "typescript": ("TYPESCRIPT", "typescript", "typescript", "3178C6"), "html": ("HTML", "html5", "html5", "E34F26"),
    "css": ("CSS", "css3", "css3", "1572B6"), "scss": ("SCSS", "sass", "sass", "CC6699"),
    "python": ("PYTHON", "python", "python", "3776AB"), "java": ("JAVA", "java", "openjdk", "ED8B00"),
    "c": ("C", "c", "c", "A8B9CC"), "c++": ("C++", "cplusplus", "cplusplus", "00599C"),
    "c#": ("C#", "csharp", "csharp", "512BD4"), "go": ("GO", "go", "go", "00ADD8"),
    "rust": ("RUST", "rust", "rust", "CE422B"), "ruby": ("RUBY", "ruby", "ruby", "CC342D"),
    "kotlin": ("KOTLIN", "kotlin", "kotlin", "7F52FF"), "swift": ("SWIFT", "swift", "swift", "F05138"),
    "dart": ("DART", "dart", "dart", "0175C2"), "shell": ("SHELL", "bash", "gnubash", "4EAA25"),
    "vue": ("VUE", "vuejs", "vuedotjs", "4FC08D"), "blade": ("BLADE", "laravel", "laravel", "FF2D20"),
    "jupyter notebook": ("JUPYTER", "jupyter", "jupyter", "F37626"), "dockerfile": ("DOCKER", "docker", "docker", "2496ED"),
    "docker": ("DOCKER", "docker", "docker", "2496ED"), "mysql": ("MYSQL", "mysql", "mysql", "4479A1"),
    "git": ("GIT", "git", "git", "F05032"), "github": ("GITHUB", "github", "github", "FFFFFF"),
    "nodejs": ("NODE.JS", "nodejs", "nodedotjs", "5FA04E"), "react": ("REACT", "react", "react", "61DAFB"),
    "laravel": ("LARAVEL", "laravel", "laravel", "FF2D20"), "tailwindcss": ("TAILWIND", "tailwindcss", "tailwindcss", "06B6D4"),
    "bootstrap": ("BOOTSTRAP", "bootstrap", "bootstrap", "7952B3"), "mongodb": ("MONGODB", "mongodb", "mongodb", "47A248"),
    "postgresql": ("POSTGRESQL", "postgresql", "postgresql", "4169E1"), "firebase": ("FIREBASE", "firebase", "firebase", "FFCA28"),
    "figma": ("FIGMA", "figma", "figma", "F24E1E"), "vscode": ("VS CODE", "vscode", "visualstudiocode", "007ACC"),
    "linux": ("LINUX", "linux", "linux", "FCC624"), "npm": ("NPM", "npm", "npm", "CB3837"),
    "express": ("EXPRESS", "express", "express", "FFFFFF"), "nextjs": ("NEXT.JS", "nextjs", "nextdotjs", "FFFFFF"),
    "wordpress": ("WORDPRESS", "wordpress", "wordpress", "21759B"), "jquery": ("JQUERY", "jquery", "jquery", "0769AD"),
    "flutter": ("FLUTTER", "flutter", "flutter", "02569B"), "strapi": ("STRAPI", "strapi", "strapi", "4945FF"),
    "postman": ("POSTMAN", "postman", "postman", "FF6C37"), "canva": ("CANVA", "canva", "canva", "00C4CC"),
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


def get_icon(key, uid):
    """Real brand icon from devicon (multicolor) or simple-icons; None on any failure."""
    meta = TECH.get(key)
    if not meta:
        return None
    _label, dev, simple, color = meta
    for variant in ("original", "plain"):
        try:
            txt = http_get(f"https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/{dev}/{dev}-{variant}.svg").decode("utf-8", "ignore")
            m = re.search(r'<svg[^>]*viewBox="([^"]+)"[^>]*>(.*)</svg>', txt, re.S)
            if m and "<style" not in m.group(2) and "<image" not in m.group(2):
                vb, inner = m.group(1), m.group(2)
                inner = re.sub(r'(?<![\w-])id="([^"]+)"', lambda mm: f'id="{uid}{mm.group(1)}"', inner)
                inner = re.sub(r"url\(#([^)]+)\)", lambda mm: f"url(#{uid}{mm.group(1)})", inner)
                inner = re.sub(r'(xlink:)?href="#([^"]+)"', lambda mm: f'{mm.group(1) or ""}href="#{uid}{mm.group(2)}"', inner)
                return ("dev", vb, inner)
        except Exception:
            pass
    try:
        txt = http_get(f"https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{simple}.svg").decode("utf-8", "ignore")
        m = re.search(r'<path d="([^"]+)"', txt)
        if m:
            return ("simple", "0 0 24 24", m.group(1), color)
    except Exception:
        pass
    return None


def build_tech_items(cfg, langs, fetch_icons=True):
    total = sum(s for _n, s, _c in langs) or 1
    items, seen = [], set()

    def add(name, label=None):
        key = tech_key(name)
        if key in seen or key in [tech_key(x) for x in cfg["hide_tech"]]:
            return
        seen.add(key)
        lab = label or (TECH[key][0] if key in TECH else name.upper())
        items.append({"key": key, "label": lab})

    for name, size, _col in sorted(langs, key=lambda x: -x[1]):
        key = tech_key(name)
        share = size / total
        if key in TECH and share >= 0.01:
            add(name)
        elif key not in TECH and share >= 0.05:
            add(name)
    for extra in cfg["extra_tech"]:
        add(extra)
    items = items[: int(cfg["max_tech"])]
    for i, it in enumerate(items):
        it["icon"] = get_icon(it["key"], f"i{i}_") if fetch_icons else None
    return items


def tech_svg(items):
    w = 900
    pill_h, gap_x, gap_y = 46, 12, 14
    for it in items:
        it["tw"] = len(it["label"]) * 8.8
        it["pw"] = 10 + 30 + 10 + it["tw"] + 18
    rows, cur, cur_w = [], [], 0
    for it in items:
        add_w = it["pw"] + (gap_x if cur else 0)
        if cur and cur_w + add_w > 840:
            rows.append(cur)
            cur, cur_w = [], 0
            add_w = it["pw"]
        cur.append(it)
        cur_w += add_w
    if cur:
        rows.append(cur)
    h = 30 + len(rows) * pill_h + max(0, len(rows) - 1) * gap_y + 30
    body, idx = "", 0
    for r, row in enumerate(rows):
        rw = sum(i["pw"] for i in row) + gap_x * (len(row) - 1)
        x = 450 - rw / 2
        y = 30 + r * (pill_h + gap_y)
        for it in row:
            ic = it["icon"]
            if ic and ic[0] == "dev":
                glyph = f'<svg x="11" y="11" width="24" height="24" viewBox="{ic[1]}">{ic[2]}</svg>'
            elif ic and ic[0] == "simple":
                glyph = f'<svg x="11" y="11" width="24" height="24" viewBox="0 0 24 24"><path d="{ic[2]}" fill="#{ic[3]}"/></svg>'
            else:
                glyph = (f'<text x="23" y="29" text-anchor="middle" font-family="{FONT_MONO}" font-size="15" '
                         f'font-weight="800" fill="#1d4ed8">{esc(it["label"][:2])}</text>')
            b = idx * 0.09
            body += f'''
<g opacity="0" transform="translate({x:.1f} {y + 14})">
<animateTransform attributeName="transform" type="translate" from="{x:.1f} {y + 14}" to="{x:.1f} {y}" begin="{b:.2f}s" dur="0.6s" fill="freeze"/>
<animate attributeName="opacity" from="0" to="1" begin="{b:.2f}s" dur="0.6s" fill="freeze"/>
<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -3;0 0" dur="{3.2 + (idx % 4) * 0.5:.1f}s" begin="{0.8 + b:.2f}s" repeatCount="indefinite"/>
<rect width="{it['pw']:.1f}" height="{pill_h}" rx="12" fill="#0d1a3f" stroke="#2a4fa8" stroke-width="1.5"/>
<rect x="8" y="8" width="30" height="30" rx="8" fill="#e8f1ff"/>
{glyph}
<text x="48" y="29" font-family="{FONT_MONO}" font-size="13.5" font-weight="700" fill="{C['hi']}" textLength="{it['tw']:.1f}" lengthAdjust="spacing">{esc(it['label'])}</text>
<rect width="{it['pw']:.1f}" height="{pill_h}" rx="12" fill="none" stroke="{C['a2']}" stroke-width="1.5" opacity="0"><animate attributeName="opacity" values="0;0.9;0" dur="{4 + (idx % 3)}s" begin="{1.5 + b:.2f}s" repeatCount="indefinite"/></rect>
</g></g>'''
            x += it["pw"] + gap_x
            idx += 1
    return svg_doc(w, h, body)


# --------------------------------------------------------------------------- stats
def compute_stats(weeks):
    days = [d for wk in weeks for d in wk]
    total = sum(d["count"] for d in days)
    longest = run = 0
    for d in days:
        run = run + 1 if d["count"] > 0 else 0
        longest = max(longest, run)
    cur = 0
    seq = list(reversed(days))
    if seq and seq[0]["count"] == 0:
        seq = seq[1:]
    for d in seq:
        if d["count"] > 0:
            cur += 1
        else:
            break
    best = max(days, key=lambda d: d["count"]) if days else {"count": 0, "date": ""}
    wk_tot = [sum(d["count"] for d in wk) for wk in weeks]
    return dict(total=total, longest=longest, current=cur, best=best, wk_tot=wk_tot,
                active=sum(1 for d in days if d["count"] > 0))


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


def stats_svg(d):
    W, H = 900, 545
    weeks, pending = d["weeks"], d["pending"]
    st = compute_stats(weeks)
    nW = len(weeks)
    mx = max((x["count"] for wk in weeks for x in wk), default=0)

    # --- cards
    def val(v, suffix=""):
        return "--" if pending else f"{fmt(v)}{suffix}"
    best = st["best"]
    best_cap = "" if pending or not best["count"] else dt.date.fromisoformat(best["date"]).strftime("%b %d, %Y")
    cards = [
        ("commit", "CONTRIBUTIONS", val(st["total"]), "in the last year"),
        ("flame", "CURRENT STREAK", val(st["current"], " d"), "consecutive days"),
        ("bolt", "LONGEST STREAK", val(st["longest"], " d"), "best run this year"),
        ("star", "BUSIEST DAY", val(best["count"]), best_cap or "-"),
    ]
    body = panel(W, H)
    for i, (ic, label, value, cap) in enumerate(cards):
        x = 28 + i * 214
        b = i * 0.15
        body += f'''
<g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{b}s" dur="0.6s" fill="freeze"/>
<rect x="{x}" y="22" width="200" height="72" rx="14" fill="#0d1a3f" stroke="#26478f" stroke-width="1.3"/>
<circle cx="{x + 30}" cy="58" r="17" fill="#13265a"/>{icon(ic, x + 19, 47, 22, C['a2'])}
<text x="{x + 58}" y="44" font-family="{FONT_MONO}" font-size="10.5" font-weight="700" letter-spacing="1.5" fill="{C['mute']}">{label}</text>
<text x="{x + 58}" y="69" font-family="{FONT_SANS}" font-size="25" font-weight="800" fill="{C['hi']}">{esc(value)}</text>
<text x="{x + 58}" y="85" font-family="{FONT_SANS}" font-size="11" fill="{C['mute']}">{esc(cap)}</text></g>'''

    # --- heatmap
    cell, gap = 13, 3
    step = cell + gap
    x0 = (W - (nW * step - gap)) / 2
    y0 = 136
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
                pulse = (f'<animate attributeName="fill-opacity" values="1;0.45;1" dur="{2.4 + (ci % 5) * 0.3:.1f}s" '
                         f'begin="{beg + 1.5:.2f}s" repeatCount="indefinite"/>')
            stroke = ' stroke="#17306b" stroke-width="0.8"' if lv == 0 else ""
            body += (f'<rect x="{px:.1f}" y="{py:.1f}" width="{cell}" height="{cell}" rx="3" fill="{LEVELS[lv]}"{stroke} opacity="0">'
                     f'<animate attributeName="opacity" from="0" to="1" begin="{beg:.2f}s" dur="0.35s" fill="freeze"/>{pulse}</rect>')

    # --- jet
    jy = y0 + 7 * step + 22
    xj0, xj1 = x0 + cell / 2, x0 + (nW - 1) * step + cell / 2
    D = 14
    body += f'''<g><g>
<polygon points="-2,9 0,15 2,9" fill="#fb923c"><animate attributeName="points" values="-2,9 0,14 2,9;-3,9 0,21 3,9;-2,9 0,14 2,9" dur="0.25s" repeatCount="indefinite"/></polygon>
<path d="M0,-12 L6,6 L2,4 L0,9 L-2,4 L-6,6 Z" fill="{C['hi']}" stroke="{C['a2']}" stroke-width="1" filter="url(#glow)"/>
<circle cy="-2" r="2" fill="#0b1a3d"/></g>
<animateTransform attributeName="transform" type="translate" from="{xj0:.1f} {jy}" to="{xj1:.1f} {jy}" dur="{D}s" repeatCount="indefinite"/></g>'''
    for c, ci, wd in ([] if pending else targets):
        cx = x0 + ci * step + cell / 2
        cy = y0 + wd * step + cell / 2
        t = ci / max(1, nW - 1)
        t1 = min(0.985, t + 0.02)
        t0 = min(t, t1 - 0.005)
        kt = f"0;{t0:.4f};{t1:.4f};1"
        body += (f'<line x1="{cx:.1f}" y1="{jy - 14}" x2="{cx:.1f}" y2="{cy + 8:.1f}" stroke="#7dd3fc" stroke-width="2.6" stroke-linecap="round" opacity="0" filter="url(#glow)">'
                 f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="{kt}" calcMode="discrete" dur="{D}s" repeatCount="indefinite"/></line>'
                 f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="11" fill="none" stroke="#fff" stroke-width="2" opacity="0">'
                 f'<animate attributeName="opacity" values="0;1;0;0" keyTimes="{kt}" calcMode="discrete" dur="{D}s" repeatCount="indefinite"/></circle>')

    cap_y = jy + 36
    body += (f'<text x="28" y="{cap_y}" font-family="{FONT_SANS}" font-size="12.5" fill="{C["mute"]}">'
             f'A jet flies the length of the year and fires at your busiest days. Give it a few seconds.</text>')
    lx = W - 28 - 5 * 17 - 70
    body += f'<text x="{lx - 6}" y="{cap_y}" text-anchor="end" font-family="{FONT_MONO}" font-size="11" fill="{C["mute"]}">Less</text>'
    for k, col in enumerate(LEVELS):
        body += f'<rect x="{lx + k * 17}" y="{cap_y - 11}" width="12" height="12" rx="3" fill="{col}"/>'
    body += f'<text x="{lx + 5 * 17 + 4}" y="{cap_y}" font-family="{FONT_MONO}" font-size="11" fill="{C["mute"]}">More</text>'

    # --- trend chart
    ty = cap_y + 22
    body += f'<rect x="28" y="{ty}" width="844" height="1.5" fill="#1e3a8a" opacity="0.55"/>'
    body += (f'<text x="28" y="{ty + 30}" font-family="{FONT_SANS}" font-size="17" font-weight="800" fill="{C["hi"]}">Weekly contributions</text>')
    wk = st["wk_tot"]
    peak_i = max(range(nW), key=lambda i: wk[i]) if nW else 0
    if not pending and wk and wk[peak_i] > 0:
        pd_ = dt.date.fromisoformat(weeks[peak_i][0]["date"]).strftime("%b %d")
        body += (f'<text x="872" y="{ty + 30}" text-anchor="end" font-family="{FONT_MONO}" font-size="11.5" fill="{C["mute"]}">'
                 f'peak: {fmt(wk[peak_i])} in the week of {pd_}</text>')
    cx0, cx1 = 62, 872
    cy0, cy1 = ty + 52, ty + 52 + 118
    maxv = max(1, max(wk) if wk else 1)
    top = maxv * 1.12
    for g in range(4):
        gy = cy1 - g * (cy1 - cy0) / 3
        body += f'<line x1="{cx0}" y1="{gy:.1f}" x2="{cx1}" y2="{gy:.1f}" stroke="#1e3a8a" stroke-opacity="0.45" stroke-dasharray="3 5"/>'
        body += (f'<text x="{cx0 - 8}" y="{gy + 4:.1f}" text-anchor="end" font-family="{FONT_MONO}" font-size="10.5" fill="{C["mute"]}">'
                 f'{fmt(round(top * g / 3))}</text>')
    pts = [(cx0 + i * (cx1 - cx0) / max(1, nW - 1), cy1 - v / top * (cy1 - cy0)) for i, v in enumerate(wk)]
    for i, name in month_labels(weeks):
        body += (f'<text x="{pts[i][0]:.1f}" y="{cy1 + 20}" font-family="{FONT_MONO}" font-size="10.5" fill="{C["mute"]}">{name}</text>')
    if len(pts) >= 2:
        line = smooth_path(pts)
        area = line + f" L{pts[-1][0]:.1f},{cy1} L{pts[0][0]:.1f},{cy1} Z"
        body += f'''
<path d="{area}" fill="url(#areaG)" opacity="0"><animate attributeName="opacity" from="0" to="1" begin="1.6s" dur="1.2s" fill="freeze"/></path>
<path d="{line}" fill="none" stroke="url(#lineStroke)" stroke-width="3" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1" filter="url(#glow)"><animate attributeName="stroke-dashoffset" from="1" to="0" dur="2.6s" begin="0.3s" fill="freeze"/></path>'''
        if not pending:
            px, py = pts[peak_i]
            body += f'''
<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="#fff" filter="url(#glow)"/>
<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="none" stroke="{C['a2']}" stroke-width="2"><animate attributeName="r" values="5;16" dur="2.2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.9;0" dur="2.2s" repeatCount="indefinite"/></circle>
<circle r="3.5" fill="#e0f2fe" filter="url(#glow)"><animateMotion dur="9s" begin="3s" repeatCount="indefinite" path="{line}"/></circle>'''
    if pending:
        body += (f'<g><rect x="{W / 2 - 235}" y="{y0 + 30}" width="470" height="50" rx="25" fill="#0b1a3d" stroke="url(#gBd)" stroke-width="2"/>'
                 f'<text x="{W / 2}" y="{y0 + 61}" text-anchor="middle" font-family="{FONT_MONO}" font-size="14" fill="{C["hi"]}">'
                 f'Waiting for first sync: run the workflow once</text></g>')
    extra = f'''
<linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C['a2']}" stop-opacity="0.42"/><stop offset="1" stop-color="{C['a1']}" stop-opacity="0"/></linearGradient>
<linearGradient id="lineStroke" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{C['a1']}"/><stop offset="0.6" stop-color="{C['a2']}"/><stop offset="1" stop-color="#a5b4fc"/></linearGradient>'''
    return svg_doc(W, H, body, extra)


# --------------------------------------------------------------------------- scan (visual map + system info)
def avatar_grid(img_bytes, n=36):
    """Dot-matrix brightness grid from the real GitHub avatar (None -> placeholder 'K')."""
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
    w, h = 900, 350
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
    n = 36
    cell = 6.3
    cxm, cym = 183, 190
    ox, oy = cxm - n * cell / 2, cym - n * cell / 2
    rnd = random.Random(5)
    dots = ""
    for i, j, v in avatar_grid(d.get("avatar"), n):
        v = v ** 0.9
        r = 0.7 + v * 2.55
        cls = f"c{min(5, int(v * 5.99))}"
        op = 0.28 + 0.72 * v
        shim = ""
        if rnd.random() < 0.07:
            shim = (f'<animate attributeName="opacity" values="{op:.2f};1;{op:.2f}" dur="{rnd.uniform(1.6, 3.6):.1f}s" '
                    f'begin="{rnd.uniform(0, 3):.1f}s" repeatCount="indefinite"/>')
        dots += f'<circle class="{cls}" cx="{ox + (i + 0.5) * cell:.1f}" cy="{oy + (j + 0.5) * cell:.1f}" r="{r:.2f}" opacity="{op:.2f}">{shim}</circle>'
    style = ".c0{fill:#10286b}.c1{fill:#1d4ed8}.c2{fill:#2563eb}.c3{fill:#38bdf8}.c4{fill:#7dd3fc}.c5{fill:#e0f2fe}"
    extra = f'''
<clipPath id="disc"><circle cx="{cxm}" cy="{cym}" r="{n * cell / 2}"/></clipPath>
<linearGradient id="scanG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C['a2']}" stop-opacity="0"/><stop offset="0.85" stop-color="{C['a2']}" stop-opacity="0.55"/><stop offset="1" stop-color="#e0f2fe" stop-opacity="0.95"/></linearGradient>'''
    body = panel(w, h) + titlebar(w, f"{d['login'].lower()}@github ~ $ ./profile-scan --live")
    body += f'<rect x="28" y="56" width="310" height="268" rx="12" fill="#050e24" stroke="#1e40af" stroke-width="1.5"/>'
    body += f'<text x="44" y="78" font-family="{FONT_MONO}" font-size="11" letter-spacing="2" fill="{C["a2"]}">VISUAL.MAP</text>'
    body += f'<g clip-path="url(#disc)">{dots}<rect x="{cxm - 120}" y="{cym - n * cell / 2 - 24}" width="240" height="24" fill="url(#scanG)"><animate attributeName="y" values="{cym - n * cell / 2 - 24};{cym + n * cell / 2}" dur="3.4s" repeatCount="indefinite"/></rect></g>'
    body += (f'<circle cx="{cxm}" cy="{cym}" r="{n * cell / 2 + 6}" fill="none" stroke="{C["a2"]}" stroke-width="1.5" stroke-dasharray="5 9" opacity="0.8">'
             f'<animateTransform attributeName="transform" type="rotate" from="0 {cxm} {cym}" to="360 {cxm} {cym}" dur="18s" repeatCount="indefinite"/></circle>')
    for (bx, by, sx, sy) in [(44, 92, 1, 1), (322, 92, -1, 1), (44, 308, 1, -1), (322, 308, -1, -1)]:
        body += (f'<path d="M{bx},{by + 14 * sy} L{bx},{by} L{bx + 14 * sx},{by}" fill="none" stroke="{C["a2"]}" stroke-width="2.2" stroke-linecap="round">'
                 f'<animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite"/></path>')
    body += f'<rect x="358" y="56" width="514" height="268" rx="12" fill="#050e24" stroke="#1e40af" stroke-width="1.5"/>'
    body += f'<text x="374" y="78" font-family="{FONT_MONO}" font-size="11" letter-spacing="2" fill="{C["a2"]}">SYSTEM.INFO</text>'
    body += f'<circle cx="848" cy="73" r="4" fill="#22c55e"><animate attributeName="opacity" values="1;0.2;1" dur="1.4s" repeatCount="indefinite"/></circle><text x="838" y="77" text-anchor="end" font-family="{FONT_MONO}" font-size="11" fill="#86efac">LIVE</text>'
    y = 106
    for k, (key, value) in enumerate(rows):
        b = 0.3 + k * 0.22
        body += (f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="{b:.2f}s" dur="0.4s" fill="freeze"/>'
                 f'<text x="374" y="{y}" font-family="{FONT_MONO}" font-size="13.5" font-weight="700" fill="{C["a2"]}">{key}</text>'
                 f'<text x="520" y="{y}" font-family="{FONT_MONO}" font-size="13.5" fill="{C["hi"]}">{esc(trunc(value, 38))}</text>'
                 f'<line x1="374" y1="{y + 8}" x2="856" y2="{y + 8}" stroke="#1e3a8a" stroke-opacity="0.45"/></g>')
        y += 22
    body += (f'<rect x="374" y="{y - 8}" width="9" height="15" fill="{C["a2"]}"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>')
    return svg_doc(w, h, body, extra, style)


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
    langs = {}
    stars = 0
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
    items = build_tech_items(cfg, d["langs"], fetch_icons=(mode == "live"))
    files = {
        "banner.svg": banner_svg(cfg, d["login"]),
        "footer.svg": footer_svg(),
        "h-tech.svg": heading_svg("Technologies", "code"),
        "h-stats.svg": heading_svg("Statistics", "chart"),
        "h-scan.svg": heading_svg("Profile Scan", "scan"),
        "h-about.svg": heading_svg("About Me", "user"),
        "h-goals.svg": heading_svg("Hobbies & Goals", "target"),
        "tech.svg": tech_svg(items),
        "stats.svg": stats_svg(d),
        "scan.svg": scan_svg(d),
    }
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
    print(f"[{mode}] wrote {len(files)} files to {OUT}")


if __name__ == "__main__":
    main()
