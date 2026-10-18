"""Génère les visuels SVG du README dans assets/.

Usage : python cards/build.py [fichier.svg ...]   (dépendance : pip install fonttools)
La carte de série (streak.svg) interroge l'API GitHub : il faut GITHUB_TOKEN, par
exemple GITHUB_TOKEN=$(gh auth token) python cards/build.py. Le workflow
profile-3d.yml la régénère chaque jour.

GitHub affiche les SVG du README comme des <img> : ils ne peuvent charger ni
police ni image externe. Tout est donc intégré en base64, et les polices sont
réduites aux seuls caractères utilisés par chaque visuel.

DA : noir, or hextech, blanc chaud et rouge, cadres à coins coupés façon client
League of Legends. Clins d'œil dessinés : feu-renard d'Ahri, lune de Ranni,
fleur écarlate de Malenia, feu de camp de Dark Souls.

Logos (icons.json) : Simple Icons (CC0), logo C# de Devicon (MIT, voir LICENSE-devicon.txt).
"""
import base64
import io
import json
import math
import os
import random
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Callable

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets"
ICONS = json.loads((HERE / "icons.json").read_text(encoding="utf-8"))

BLACK = "#08080A"
GOLD = "#C8AA6E"
GOLD_DIM = "#A08A5C"
WHITE = "#F0E6D2"
TEXT = "#E4DDCF"
MUTED = "#8F877A"
RED = "#D3202C"
EMBER = "#F08A2C"
STEEL = "#CFC8BA"
CUT = 12  # coin coupé des cadres


class Font:
    def __init__(self, family, file, weight, fallback):
        self.family, self.weight = family, weight
        self.css = f"'{family}', {fallback}"
        self.path = HERE / "fonts" / file
        tt = TTFont(self.path)
        self.upm = tt["head"].unitsPerEm
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"].metrics

    def width(self, text, size, spacing=0):
        units = 0
        for ch in text:
            glyph = self.cmap.get(ord(ch))
            if glyph is None:
                raise ValueError(f"{self.family} {self.weight} : caractère absent {ch!r}")
            units += self.hmtx[glyph][0]
        return units * size / self.upm + spacing * len(text)

    def face(self, chars):
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga"]
        tt = TTFont(self.path, recalcTimestamp=False)  # sinon chaque génération change tous les SVG
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(sorted(chars)) + " ")
        sub.subset(tt)
        buf = io.BytesIO()
        subset.save_font(tt, buf, opts)
        data = base64.b64encode(buf.getvalue()).decode()
        return (f"@font-face{{font-family:'{self.family}';font-weight:{self.weight};"
                f"src:url(data:font/woff;base64,{data}) format('woff')}}")


DISPLAY = Font("Cinzel Decorative", "CinzelDecorative-Black.ttf", 900, "Georgia, serif")
SERIF = Font("Cinzel", "Cinzel-Bold.ttf", 700, "Georgia, serif")
SERIF_BLACK = Font("Cinzel", "Cinzel-Black.ttf", 900, "Georgia, serif")
SANS = Font("Manrope", "Manrope-Regular.ttf", 400, "'Segoe UI', Arial, sans-serif")
SANS_SB = Font("Manrope", "Manrope-SemiBold.ttf", 600, "'Segoe UI', Arial, sans-serif")


class Svg:
    def __init__(self, w, h, title, desc):
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.defs, self.body, self.css = [], [], []
        self.used = {}

    def add(self, markup):
        self.body.append(markup)

    def markup(self, x, y, s, font, size, fill, spacing=0, anchor="start", opacity=None, extra=""):
        self.used.setdefault(font, set()).update(s)
        attrs = (f'x="{x:g}" y="{y:g}" font-family="{font.css}" font-weight="{font.weight}" '
                 f'font-size="{size:g}" fill="{fill}"')
        if spacing:
            attrs += f' letter-spacing="{spacing:g}"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if opacity is not None:
            attrs += f' fill-opacity="{opacity:g}"'
        if extra:
            attrs += f" {extra}"
        return f"<text {attrs}>{escape(s)}</text>"

    def text(self, *args, **kwargs):
        self.add(self.markup(*args, **kwargs))

    def render(self):
        faces = "".join(font.face(chars) for font, chars in self.used.items())
        motion = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}" if self.css else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="title desc">'
                f'<title id="title">{escape(self.title)}</title><desc id="desc">{escape(self.desc)}</desc>'
                f"<defs><style>{faces}{''.join(self.css)}{motion}</style>{''.join(self.defs)}</defs>"
                f"{''.join(self.body)}</svg>")


def wrap(text, font, size, max_width):
    # Coupe uniquement sur les espaces normales : les insécables (avant « : ») restent collées.
    lines, current = [], ""
    for word in text.split(" "):
        trial = f"{current} {word}".strip()
        if current and font.width(trial, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)
    return lines


def image_uri(name):
    data = base64.b64encode((HERE / "img" / name).read_bytes()).decode()
    return f"data:image/jpeg;base64,{data}"


def check(what, end, limit):
    if end > limit:
        raise ValueError(f"{what} déborde ({end:.0f} > {limit:.0f})")


def chamfer(x, y, w, h, k=CUT):
    # Rectangle à coins coupés, comme les cadres du client LoL.
    return (f"M{x + k:g} {y:g}H{x + w - k:g}L{x + w:g} {y + k:g}V{y + h - k:g}L{x + w - k:g} {y + h:g}"
            f"H{x + k:g}L{x:g} {y + h - k:g}V{y + k:g}Z")


def tag_shape(x, y, w, h, k=5):
    # Pastille à bouts en pointe.
    return (f"M{x + k:.1f} {y:g}H{x + w - k:.1f}L{x + w:.1f} {y + h / 2:g}L{x + w - k:.1f} {y + h:g}"
            f"H{x + k:.1f}L{x:.1f} {y + h / 2:g}Z")


def diamond(x, y, r, fill, extra=""):
    return f'<path d="M{x:g} {y - r:g}L{x + r:g} {y:g}L{x:g} {y + r:g}L{x - r:g} {y:g}Z" fill="{fill}"{extra}/>'


def icon(name, x, y, size, fill, extra=""):
    view = float(ICONS[name]["viewBox"].split()[2])
    return (f'<path transform="translate({x:g} {y:g}) scale({size / view:.4f})" d="{ICONS[name]["d"]}" '
            f'fill="{fill}"{extra}/>')


def aeonia(x, y, cls, r=7):
    # Fleur écarlate de Malenia : six pétales autour d'un cœur doré.
    petals = "".join(f'<ellipse cy="{-r * .55:.2f}" rx="{r * .34:.2f}" ry="{r * .6:.2f}" transform="rotate({a})"/>'
                     for a in range(0, 360, 60))
    return (f'<g transform="translate({x:g} {y:g})"><g class="{cls}" fill="{RED}">{petals}</g>'
            f'<circle r="{r * .22:.2f}" fill="{GOLD}"/></g>')


def frame(svg):
    w, h = svg.w, svg.h
    svg.defs.append(
        f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#121014"/><stop offset="1" stop-color="{BLACK}"/></linearGradient>'
        f'<radialGradient id="glow" cx="1" cy="0" r=".8">'
        f'<stop offset="0" stop-color="{RED}" stop-opacity=".16"/>'
        f'<stop offset="1" stop-color="{RED}" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="card"><path d="{chamfer(0, 0, w, h)}"/></clipPath>'
    )
    svg.add(f'<path d="{chamfer(0, 0, w, h)}" fill="url(#bg)"/>')
    svg.add(f'<path d="{chamfer(0, 0, w, h)}" fill="url(#glow)"/>')


def border(svg):
    # Tracé en dernier pour passer au-dessus des visuels : double filet or, losanges, trait rouge.
    w, h = svg.w, svg.h
    svg.add(f'<path d="{chamfer(.5, .5, w - 1, h - 1)}" fill="none" stroke="{GOLD}" stroke-opacity=".6"/>')
    svg.add(f'<path d="{chamfer(5.5, 5.5, w - 11, h - 11, CUT - 3)}" fill="none" stroke="{GOLD}" '
            f'stroke-opacity=".15"/>')
    svg.add(f'<path d="M{CUT + 10} 1.5H{CUT + 64}" stroke="{RED}" stroke-width="3"/>')
    for y in (.5, h - .5):
        svg.add(diamond(w / 2, y, 4.5, GOLD))


def embers(svg, n, spots, y0, rise, seed):
    # Braises du feu de camp : elles montent, dérivent et s'éteignent.
    svg.defs.append('<filter id="spark" x="-10%" y="-10%" width="120%" height="120%">'
                    '<feGaussianBlur stdDeviation="1.4" result="b"/>'
                    '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    start = "0%{transform:translate(0,0);opacity:0}12%{opacity:.95}"
    svg.css.append(
        f"@keyframes rise-a{{{start}100%{{transform:translate(26px,{-rise}px);opacity:0}}}}"
        f"@keyframes rise-b{{{start}100%{{transform:translate(-30px,{-rise * 1.12:.0f}px);opacity:0}}}}"
        f"@keyframes rise-c{{{start}50%{{transform:translate(-14px,{-rise * .42:.0f}px)}}"
        f"100%{{transform:translate(10px,{-rise * .83:.0f}px);opacity:0}}}}"
        ".ember{opacity:0;animation-timing-function:linear;animation-iteration-count:infinite}"
        ".a{animation-name:rise-a}.b{animation-name:rise-b}.c{animation-name:rise-c}"
    )
    rng = random.Random(seed)  # graine fixe : le SVG ne change pas d'une génération à l'autre
    dots = []
    for _ in range(n):
        lo, hi = rng.choice(spots)
        dur = rng.uniform(5.5, 11) * rise / 240
        dots.append(
            f'<circle class="ember {rng.choice("abc")}" cx="{rng.uniform(lo, hi):.1f}" '
            f'cy="{y0 + rng.uniform(2, 16):.1f}" r="{rng.uniform(.7, 1.9):.2f}" '
            f'fill="{rng.choice((RED, EMBER, EMBER, WHITE))}" '
            f'style="animation-duration:{dur:.1f}s;animation-delay:{-rng.uniform(0, dur):.1f}s"/>')
    dots = "".join(dots)
    svg.add(f'<g clip-path="url(#card)" filter="url(#spark)">{dots}</g>')


FLAME_CSS = ("@keyframes flame{0%,100%{transform:scale(1,1) skewX(0)}30%{transform:scale(.92,1.12) skewX(3deg)}"
             "65%{transform:scale(1.05,.9) skewX(-3deg)}}"
             ".flame{transform-box:fill-box;transform-origin:50% 100%;animation:flame 1s ease-in-out infinite}")


def flames(cx, ground, tongues):
    # Langues de feu (dx, hauteur, largeur, couleur, durée) qui vacillent depuis leur base.
    out = []
    for dx, fh, fw, color, dur in tongues:
        x = cx + dx
        d = (f"M{x:g} {ground:g}C{x - fw:g} {ground - fh * .3:g} {x - fw * .35:g} {ground - fh * .7:g} "
             f"{x:g} {ground - fh:g}C{x + fw * .35:g} {ground - fh * .7:g} {x + fw:g} {ground - fh * .3:g} "
             f"{x:g} {ground:g}Z")
        out.append(f'<path class="flame" d="{d}" fill="{color}" fill-opacity=".92" style="animation-duration:{dur}s"/>')
    return "".join(out)


def pill_width(label, size=11, pad=11):
    return SANS_SB.width(label, size) + 2 * pad


def pills(svg, x, y, labels, size=11, h=22, gap=6):
    for label in labels:
        w = pill_width(label, size)
        svg.add(f'<path d="{tag_shape(x, y, w, h)}" fill="{GOLD}" fill-opacity=".07" stroke="{GOLD}" '
                f'stroke-opacity=".4"/>')
        svg.text(x + w / 2, y + h / 2 + size * 0.36, label, SANS_SB, size, WHITE, anchor="middle")
        x += w + gap
    return x - gap


STATUS = {
    "private": ("CODE PRIVÉ", MUTED, ".45", "0", MUTED),
    "public": ("DÉPÔT PUBLIC", RED, ".9", ".14", WHITE),
    "oss": ("OPEN SOURCE", RED, ".9", ".14", WHITE),
}


def status(svg, right, y, kind):
    label, stroke, stroke_op, fill_op, color = STATUS[kind]
    size, spacing, pad, h = 9.5, 1.4, 12, 20
    w = SANS_SB.width(label, size, spacing) - spacing + 2 * pad
    x = right - w
    svg.add(f'<path d="{tag_shape(x, y, w, h)}" fill="{stroke}" fill-opacity="{fill_op}" stroke="{stroke}" '
            f'stroke-opacity="{stroke_op}"/>')
    svg.text(x + pad, y + h / 2 + size * 0.36, label, SANS_SB, size, color, spacing=spacing)
    return x


# Animations des cartes projets : chacune montre ce que fait le produit.
# Chaque fonction dessine dans la boîte (x, y, w, h) et renvoie (balisage, css).

def anim_voice(x, y, w, h):
    # PoroTalk : onde vocale.
    rng = random.Random(3)
    n = 14
    bars = []
    for i in range(n):
        dur = rng.uniform(.55, 1.2)
        bars.append(f'<rect class="talk" x="{x + (i + .5) * w / n - 1.5:.1f}" y="{y:g}" width="3" height="{h:g}" '
                    f'rx="1.5" fill="{GOLD}" style="animation-duration:{dur:.2f}s;'
                    f'animation-delay:{-rng.uniform(0, dur):.2f}s"/>')
    return "".join(bars), ("@keyframes talk{0%,100%{transform:scaleY(.15)}50%{transform:scaleY(1)}}"
                           ".talk{transform-box:fill-box;transform-origin:center;"
                           "animation:talk 1s ease-in-out infinite}")


def anim_chart(x, y, w, h):
    # CashBack : la cote grimpe, la courbe se trace.
    pts = [(0, .85), (.14, .65), (.26, .78), (.4, .45), (.54, .58), (.68, .3), (.82, .38), (1, .05)]
    d = "M" + "L".join(f"{x + px * w:.1f} {y + py * h:.1f}" for px, py in pts)
    return (f'<path d="M{x:g} {y + h:g}H{x + w:g}" stroke="{GOLD}" stroke-opacity=".2"/>'
            f'<path class="draw" d="{d}" pathLength="1" fill="none" stroke="{GOLD}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle class="dot" cx="{x + w:g}" cy="{y + .05 * h:.1f}" r="2.6" fill="{RED}"/>',
            "@keyframes draw{0%{stroke-dashoffset:1;opacity:1}55%{stroke-dashoffset:0}85%{opacity:1}"
            "100%{stroke-dashoffset:0;opacity:0}}"
            "@keyframes dot{0%,52%{opacity:0;transform:scale(0)}60%{opacity:1;transform:scale(1.5)}"
            "66%,85%{opacity:1;transform:scale(1)}100%{opacity:0}}"
            ".draw{stroke-dasharray:1;animation:draw 4s ease-out infinite}"
            ".dot{transform-box:fill-box;transform-origin:center;animation:dot 4s ease-out infinite}")


def anim_widgets(x, y, w, h):
    # WidgetForge : trois widgets qui se rafraîchissent (lecture Spotify, stats, rang).
    gap = 7
    tw = (w - 2 * gap) / 3
    x1, x2, x3 = x, x + tw + gap, x + 2 * (tw + gap)
    tiles = "".join(f'<path d="{chamfer(tx, y, tw, h, 4)}" fill="#000" fill-opacity=".35" stroke="{GOLD}" '
                    f'stroke-opacity=".35"/>' for tx in (x1, x2, x3))
    seek = (f'<rect x="{x1 + 5:.1f}" y="{y + 5:g}" width="7" height="7" fill="{RED}"/>'
            f'<path d="M{x1 + 5:.1f} {y + h - 7:g}H{x1 + tw - 5:.1f}" stroke="{GOLD}" stroke-opacity=".25" '
            f'stroke-width="2"/>'
            f'<rect class="seek" x="{x1 + 5:.1f}" y="{y + h - 8:g}" width="{tw - 10:.1f}" height="2" fill="{GOLD}"/>')
    stats = "".join(f'<rect class="stat" x="{x2 + 6 + i * 5.5:.1f}" y="{y + 6:g}" width="3" height="{h - 11:g}" '
                    f'fill="{GOLD}" style="animation-delay:{-i * .5:.1f}s"/>' for i in range(4))
    cx, cy = x3 + tw / 2, y + h / 2
    rank = (f'<path d="M{cx:.1f} {cy - 8:g}L{cx + 8:.1f} {cy:g}L{cx:.1f} {cy + 8:g}L{cx - 8:.1f} {cy:g}Z" '
            f'fill="none" stroke="{GOLD}"/>' + diamond(cx, cy, 4, RED, ' class="rank"'))
    return (tiles + seek + stats + rank,
            "@keyframes seek{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
            ".seek{transform-box:fill-box;transform-origin:0 50%;animation:seek 4s linear infinite}"
            "@keyframes stat{0%,100%{transform:scaleY(.35)}50%{transform:scaleY(1)}}"
            ".stat{transform-box:fill-box;transform-origin:50% 100%;animation:stat 2s ease-in-out infinite}"
            "@keyframes rank{0%,70%,100%{opacity:.3}80%{opacity:1}}.rank{animation:rank 3s ease-in-out infinite}")


def anim_lan(x, y, w, h):
    # Mimic Reborn : paquets chiffrés entre le PC et le téléphone, en LAN.
    cy, a, b = y + h / 2, x + 30, x + w - 18
    mid = (a + b) / 2
    return (f'<rect x="{x:g}" y="{y + 3:g}" width="24" height="15" rx="1.5" fill="none" stroke="{GOLD}"/>'
            f'<path d="M{x + 12:g} {y + 18:g}V{y + 22:g}M{x + 7:g} {y + 22.5:g}H{x + 17:g}" stroke="{GOLD}"/>'
            f'<rect x="{x + w - 12:g}" y="{y + 1:g}" width="12" height="22" rx="2" fill="none" stroke="{GOLD}"/>'
            f'<path d="M{a:g} {cy:g}H{b:g}" stroke="{GOLD}" stroke-opacity=".35" stroke-dasharray="2 3"/>'
            f'<path d="M{mid - 2.2:g} {cy - 10:g}v-1.8a2.2 2.2 0 0 1 4.4 0v1.8" fill="none" stroke="{GOLD}" '
            f'stroke-width="1.2"/><rect x="{mid - 3.5:g}" y="{cy - 10:g}" width="7" height="5.5" rx="1" '
            f'fill="{GOLD}"/>'
            f'<circle class="to-r" cx="{a:g}" cy="{cy:g}" r="2" fill="{RED}"/>'
            f'<circle class="to-l" cx="{b:g}" cy="{cy:g}" r="2" fill="{WHITE}"/>',
            f"@keyframes to-r{{0%{{transform:translateX(0);opacity:0}}15%,85%{{opacity:1}}"
            f"100%{{transform:translateX({b - a:g}px);opacity:0}}}}"
            f"@keyframes to-l{{0%{{transform:translateX(0);opacity:0}}15%,85%{{opacity:1}}"
            f"100%{{transform:translateX({a - b:g}px);opacity:0}}}}"
            ".to-r{animation:to-r 2s linear infinite}.to-l{animation:to-l 2s linear 1s infinite backwards}")


@dataclass
class Project:
    slug: str
    name: str
    label: str
    desc: str
    tags: list
    status: str
    anim: Callable
    link: str = ""


@dataclass
class Game:
    slug: str
    name: str
    label: str
    desc: str
    role: str
    tags: list
    meta: str
    status: str
    credit: str
    art: dict = field(default_factory=dict)


def project_card(p):
    svg = Svg(410, 214, p.name, f"{p.label}. {p.desc} Technologies : {', '.join(p.tags)}.")
    frame(svg)
    pad = 24
    status(svg, svg.w - pad, pad, p.status)
    box_x, box_w = svg.w - pad - 110, 110
    check(f"{p.name} : titre", pad + SERIF.width(p.name, 26), box_x - 12)
    svg.text(pad, 50, p.name, SERIF, 26, GOLD)
    svg.text(pad, 71, p.label, SANS, 12.5, GOLD_DIM)
    markup, css = p.anim(box_x, 54, box_w, 24)
    svg.add(markup)
    svg.css.append(css)
    lines = wrap(p.desc, SANS, 13.5, svg.w - 2 * pad)
    check(f"{p.name} : description (lignes)", len(lines), 3)
    for i, line in enumerate(lines):
        svg.text(pad, 104 + i * 20, line, SANS, 13.5, TEXT, opacity=0.9)
    tags_end = pills(svg, pad, svg.h - pad - 22, p.tags)
    if p.link:
        # Flèche « lien externe » dessinée : Manrope n'a pas le glyphe ↗.
        arrow_x, base = svg.w - pad - 7, svg.h - pad - 7
        svg.add(f'<path transform="translate({arrow_x} {base - 8})" d="M0 7L7 0M2 0h5v5" fill="none" '
                f'stroke="{GOLD}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>')
        text_end = arrow_x - 6
        check(f"{p.name} : tags + lien", tags_end + 12, text_end - SANS_SB.width(p.link, 11.5))
        svg.text(text_end, base, p.link, SANS_SB, 11.5, GOLD, anchor="end")
    else:
        check(f"{p.name} : tags", tags_end, svg.w - pad)
    border(svg)
    return svg


def panel_glow(svg, width):
    svg.defs.append(
        f'<radialGradient id="panel" cx=".5" cy=".5" r=".55">'
        f'<stop offset="0" stop-color="{RED}" stop-opacity=".3"/>'
        f'<stop offset="1" stop-color="{RED}" stop-opacity="0"/></radialGradient>'
    )
    svg.add(f'<rect width="{width}" height="{svg.h}" fill="url(#panel)"/>')


def fan(svg, art, cx):
    # Éventail de trois cartes : les côtés oscillent comme une main qu'on tient, la carte du centre se retourne.
    w, h, pivot_y, lift = 120, 206, 350, 110
    box = f'x="{-w / 2:g}" y="{-(h + lift)}" width="{w}" height="{h}"'
    faces = sorted({name for name, _ in art["cards"]} | {art["back"]})
    svg.defs.append(
        f'<filter id="shadow" x="-40%" y="-40%" width="180%" height="180%">'
        f'<feDropShadow dx="0" dy="8" stdDeviation="9" flood-color="#000" flood-opacity=".7"/></filter>'
        f'<clipPath id="tarot"><rect {box} rx="7"/></clipPath>'
        + "".join(f'<image id="{Path(n).stem}" href="{image_uri(n)}" {box} preserveAspectRatio="xMidYMid slice"/>'
                  for n in faces)
    )
    panel_glow(svg, cx * 2)
    edge = f'<rect {box} rx="7" fill="none" stroke="{GOLD}" stroke-opacity=".55"/>'
    for name, angle in art["cards"]:
        face = f'<use href="#{Path(name).stem}" clip-path="url(#tarot)"/>'
        if angle:
            inner = f'<g class="sway {"l" if angle < 0 else "r"}">{face}{edge}</g>'
        else:
            back = f'<use href="#{Path(art["back"]).stem}" clip-path="url(#tarot)"/>'
            inner = f'<g class="flip"><g class="front">{face}</g><g class="back">{back}</g>{edge}</g>'
        svg.add(f'<g transform="translate({cx} {pivot_y}) rotate({angle})" filter="url(#shadow)">{inner}</g>')
    svg.css.append(
        "@keyframes sway-l{to{transform:rotate(-4deg)}}@keyframes sway-r{to{transform:rotate(4deg)}}"
        ".sway{animation:5s ease-in-out infinite alternate}.l{animation-name:sway-l}.r{animation-name:sway-r}"
        # La carte s'aplatit (scaleX 0) au moment où l'on échange recto et verso.
        "@keyframes flip{0%,58%{transform:translateY(0) scaleX(1)}63%{transform:translateY(-14px) scaleX(0)}"
        "68%,84%{transform:translateY(-14px) scaleX(1)}89%{transform:translateY(-14px) scaleX(0)}"
        "94%,100%{transform:translateY(0) scaleX(1)}}"
        "@keyframes front{0%{opacity:1}63%{opacity:0}89%{opacity:1}}"
        "@keyframes back{0%{opacity:0}63%{opacity:1}89%{opacity:0}}"
        ".flip{transform-box:fill-box;transform-origin:center;animation:flip 8s ease-in-out infinite}"
        ".front{animation:front 8s step-end infinite}.back{opacity:0;animation:back 8s step-end infinite}"
    )


def shot(svg, art, width):
    # Capture plein cadre à gauche, fondue par masque dans le fond de la carte.
    svg.defs.append(
        f'<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset=".4" stop-color="#FFF"/><stop offset="1" stop-color="#000"/></linearGradient>'
        f'<mask id="fademask"><rect width="{width}" height="{svg.h}" fill="url(#fade)"/></mask>'
        f'<linearGradient id="foot" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset=".6" stop-color="{BLACK}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{BLACK}" stop-opacity=".85"/></linearGradient>'
    )
    svg.add(f'<g clip-path="url(#card)"><g mask="url(#fademask)">'
            f'<image href="{image_uri(art["image"])}" width="{width}" height="{svg.h}" '
            f'preserveAspectRatio="xMidYMid slice"/>'
            f'<rect width="{width}" height="{svg.h}" fill="{BLACK}" fill-opacity=".18"/>'
            f'<rect width="{width}" height="{svg.h}" fill="url(#foot)"/></g></g>')


def killfeed(svg, right, top, entries):
    # Kill feed façon jeu, posé sur la map : chaque ligne entre, reste 5 s puis s'efface.
    size, h = 10.5, 20
    rows = []
    for i, (killer, victim) in enumerate(entries):
        kw, vw = SANS_SB.width(killer, size), SANS_SB.width(victim, size)
        w = kw + vw + 50
        x, y = right - w, top + i * (h + 5)
        ix, iy = x + 10 + kw + 15, y + h / 2
        rows.append(
            f'<g class="feed" style="animation-delay:{i * 1.4:.1f}s">'
            f'<path d="{chamfer(x, y, w, h, 4)}" fill="#000" fill-opacity=".72" stroke="{GOLD}" stroke-opacity=".3"/>'
            + svg.markup(x + 10, y + 14, killer, SANS_SB, size, GOLD if killer == "Terrenoss" else TEXT)
            + f'<g fill="none" stroke="{RED}" stroke-width="1.3"><circle cx="{ix:.1f}" cy="{iy:g}" r="3.6"/>'
            f'<path d="M{ix - 6.5:.1f} {iy:g}h3M{ix + 3.5:.1f} {iy:g}h3M{ix:.1f} {iy - 6.5:g}v3'
            f'M{ix:.1f} {iy + 3.5:g}v3"/></g>'
            + svg.markup(x + w - 10, y + 14, victim, SANS_SB, size, RED if victim == "Terrenoss" else TEXT,
                         anchor="end")
            + "</g>")
    svg.add("".join(rows))
    svg.css.append("@keyframes feed{0%{opacity:0;transform:translateX(14px)}4%{opacity:1;transform:translateX(0)}"
                   "55%{opacity:1}60%,100%{opacity:0}}"
                   ".feed{animation:feed 9s cubic-bezier(.2,.8,.2,1) infinite backwards}")


def game_card(g):
    svg = Svg(860, 300, g.name,
              f"{g.label}. {g.desc} Mon rôle : {g.role} {g.meta}. Technologies : {', '.join(g.tags)}. {g.credit}.")
    frame(svg)
    panel = 340
    if "cards" in g.art:
        fan(svg, g.art, panel // 2)
    else:
        shot(svg, g.art, panel)
    if "feed" in g.art:
        killfeed(svg, panel - 14, 18, g.art["feed"])
    svg.text(panel // 2, svg.h - 16, g.credit, SANS, 9.5, MUTED, anchor="middle", opacity=0.8)

    x, right, pad = 372, svg.w - 28, 28
    status_x = status(svg, right, pad, g.status)
    check(f"{g.name} : titre", x + SERIF.width(g.name, 32), status_x - 12)
    svg.text(x - 1, 72, g.name, SERIF, 32, GOLD)
    svg.text(x, 96, g.label, SANS, 13, GOLD_DIM)

    y = 126
    lines = wrap(g.desc, SANS, 14.5, right - x)
    check(f"{g.name} : description (lignes)", len(lines), 3)
    for line in lines:
        svg.text(x, y, line, SANS, 14.5, TEXT, opacity=0.9)
        y += 21
    y += 8
    svg.text(x, y, "MON RÔLE", SANS_SB, 9.5, GOLD_DIM, spacing=2)
    y += 17
    lines = wrap(g.role, SANS, 13, right - x)
    check(f"{g.name} : rôle (lignes)", len(lines), 2)
    for line in lines:
        svg.text(x, y, line, SANS, 13, TEXT, opacity=0.75)
        y += 18

    tags_y = svg.h - pad - 22
    check(f"{g.name} : hauteur du texte", y - 8, tags_y)
    tags_end = pills(svg, x, tags_y, g.tags)
    check(f"{g.name} : tags + mention", tags_end + 12, right - SANS.width(g.meta, 12))
    svg.text(right, tags_y + 15, g.meta, SANS, 12, MUTED, anchor="end")
    border(svg)
    return svg


# Scènes des petits jeux Unity : chaque fonction dessine dans (0, 0, w, h) et renvoie (balisage, css).
# Les noms d'animation sont uniques car toutes les scènes partagent la même feuille de style.

def scene_meatboy(w, h):
    # Le cube de viande saute par-dessus une scie circulaire.
    ground, dx = h - 6, w - 60
    teeth = "".join(f'<path d="M0 -12L2.5 -8.5H-2.5Z" transform="rotate({a})"/>' for a in range(0, 360, 30))
    arc = "".join(f"{p * 25}%{{transform:translate({dx * p / 4:.0f}px,{-27 * p * (4 - p) / 4:.0f}px)}}"
                  for p in range(5))
    return (f'<path d="M14 {ground}H48M{w - 48:g} {ground}H{w - 14:g}" stroke="{GOLD}" stroke-width="2"/>'
            f'<g transform="translate({w / 2:g} {ground + 2})"><g class="saw" fill="{STEEL}">{teeth}'
            f'<circle r="9"/></g><circle r="2" fill="{BLACK}"/></g>'
            f'<rect class="meat" x="26" y="{ground - 9}" width="9" height="9" rx="1.5" fill="{RED}"/>',
            "@keyframes saw{to{transform:rotate(360deg)}}"
            ".saw{transform-box:fill-box;transform-origin:center;animation:saw 1.2s linear infinite}"
            f"@keyframes jump{{{arc}}}.meat{{animation:jump 1.4s linear infinite alternate}}")


def scene_goo(w, h):
    # Une structure de boules de Goo qui oscille.
    cx, base = w / 2, h - 6
    nodes = [(-30, 0), (0, 0), (30, 0), (-15, -14), (15, -14), (0, -28)]
    edges = [(0, 1), (1, 2), (0, 3), (1, 3), (1, 4), (2, 4), (3, 4), (3, 5), (4, 5)]
    struts = "".join(f'<path d="M{cx + nodes[a][0]:g} {base + nodes[a][1]}L{cx + nodes[b][0]:g} {base + nodes[b][1]}"/>'
                     for a, b in edges)
    balls = "".join(f'<circle cx="{cx + x:g}" cy="{base + y}" r="4.2"/>' for x, y in nodes)
    return (f'<path d="M10 {base + 4.5}H{w - 10:g}" stroke="{GOLD}" stroke-opacity=".4"/>'
            f'<g class="wob"><g stroke="#6E655A" stroke-width="2">{struts}</g>'
            f'<g fill="#141216" stroke="{GOLD}" stroke-opacity=".7">{balls}</g>'
            f'<circle cx="{cx - 1.5:g}" cy="{base - 29}" r="1" fill="#FFF"/>'
            f'<circle cx="{cx + 1.5:g}" cy="{base - 29}" r="1" fill="#FFF"/></g>',
            "@keyframes wob{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)}}"
            ".wob{transform-box:fill-box;transform-origin:50% 100%;animation:wob 2.6s ease-in-out infinite}")


def scene_zelda(w, h):
    # Trois cœurs (le dernier clignote) et un coffre qui s'ouvre sur un objet.
    heart = "M0 3.2C-3.4 1-4-1.6-2-2.8C-.9-3.4 0-2.6 0-1.6C0-2.6.9-3.4 2-2.8C4-1.6 3.4 1 0 3.2Z"
    hearts = "".join(f'<path d="{heart}" transform="translate({18 + i * 14} {h / 2:g}) scale(1.4)" fill="{RED}"'
                     f'{" class=\"low\"" if i == 2 else ""}/>' for i in range(3))
    x, y = w - 64, h - 18
    return (hearts
            + f'<rect x="{x}" y="{y}" width="24" height="13" fill="#5A3C1C" stroke="{GOLD}"/>'
            f'<path d="M{x + 12} {y}v13" stroke="{GOLD}"/>'
            f'<rect class="lid" x="{x}" y="{y - 6}" width="24" height="6" fill="#6E4A22" stroke="{GOLD}"/>'
            + diamond(x + 12, y - 12, 4, GOLD, ' class="loot"'),
            "@keyframes low{0%,100%{opacity:1}50%{opacity:.25}}.low{animation:low .9s steps(1) infinite}"
            "@keyframes lid{0%,30%{transform:rotate(0)}42%,80%{transform:rotate(-38deg)}92%,100%{transform:rotate(0)}}"
            ".lid{transform-box:fill-box;transform-origin:0% 100%;animation:lid 4s ease-in-out infinite}"
            "@keyframes loot{0%,38%{opacity:0;transform:translateY(6px) scale(.4)}"
            "52%,78%{opacity:1;transform:translateY(-4px) scale(1)}86%,100%{opacity:0;transform:translateY(-4px)}}"
            ".loot{transform-box:fill-box;transform-origin:center;animation:loot 4s ease-out infinite}")


def scene_factorio(w, h):
    # Tapis roulant : plaques transportées au rythme du tapis, engrenage qui tourne.
    y, x1, x2 = h / 2 + 6, 32, w - 12
    run, period = x2 - x1 - 12, 8
    speed = run / 4  # px/s : le tapis et les plaques avancent ensemble
    teeth = "".join(f'<rect x="-1.5" y="-10" width="3" height="4" transform="rotate({a})"/>' for a in range(0, 360, 45))
    items = "".join(f'<rect class="item" x="{x1 + 3}" y="{y - 12:g}" width="7" height="7" '
                    f'fill="{GOLD if i % 2 else RED}" style="animation-delay:{-i:.0f}s"/>' for i in range(4))
    return (f'<g transform="translate(16 {y:g})"><g class="gear" fill="{GOLD}">{teeth}<circle r="7"/></g>'
            f'<circle r="2.5" fill="{BLACK}"/></g>'
            f'<rect x="{x1}" y="{y - 5:g}" width="{x2 - x1:g}" height="10" rx="2" fill="#1B1917" stroke="{GOLD}" '
            f'stroke-opacity=".45"/>'
            f'<path class="belt" d="M{x1 + 3} {y:g}H{x2 - 3:g}" stroke="{GOLD}" stroke-opacity=".5" stroke-width="6" '
            f'stroke-dasharray="2 6"/>' + items,
            f"@keyframes belt{{to{{stroke-dashoffset:{-period}}}}}.belt{{animation:belt {period / speed:.2f}s linear infinite}}"
            f"@keyframes item{{0%{{transform:translateX(0);opacity:0}}5%,95%{{opacity:1}}"
            f"100%{{transform:translateX({run:.0f}px);opacity:0}}}}.item{{animation:item 4s linear infinite}}"
            "@keyframes gear{to{transform:rotate(360deg)}}"
            ".gear{transform-box:fill-box;transform-origin:center;animation:gear 3s linear infinite}")


def scene_shrooms(w, h):
    # Des champignons qui poussent par vagues, et un petit habitant qui se promène.
    base = h - 5
    shrooms = []
    for i, (x, sh, r) in enumerate([(36, 12, 7), (66, 18, 9), (104, 14, 7), (150, 22, 10), (196, 15, 8)]):
        top = base - sh
        shrooms.append(
            f'<g class="grow" style="animation-delay:{i * .5:.1f}s">'
            f'<rect x="{x - 2}" y="{top}" width="4" height="{sh}" fill="{WHITE}" fill-opacity=".9"/>'
            f'<path d="M{x - r} {top}A{r} {r * .8:g} 0 0 1 {x + r} {top}Z" fill="{RED}"/>'
            f'<circle cx="{x - r * .35:g}" cy="{top - r * .4:g}" r="1.2" fill="#FFF"/>'
            f'<circle cx="{x + r * .3:g}" cy="{top - r * .2:g}" r="1" fill="#FFF"/></g>')
    return ("".join(shrooms)
            + f'<path d="M10 {base + .5}H{w - 10:g}" stroke="{GOLD}" stroke-opacity=".4"/>'
            f'<circle class="walk" cx="20" cy="{base - 3}" r="3" fill="{GOLD}"/>',
            "@keyframes grow{0%{transform:scaleY(0)}12%{transform:scaleY(1.08)}18%,80%{transform:scaleY(1)}"
            "92%,100%{transform:scaleY(0)}}"
            ".grow{transform-box:fill-box;transform-origin:50% 100%;animation:grow 5s ease-out infinite backwards}"
            f"@keyframes walk{{to{{transform:translateX({w - 40:g}px)}}}}"
            ".walk{animation:walk 7s ease-in-out infinite alternate}")


def scene_td(w, h):
    # Tower defense : les ennemis suivent le chemin, la tour tire.
    road, tx = h - 9, w / 2
    foes = "".join(f'<circle class="foe" cx="{w - 14:g}" cy="{road}" r="4" fill="{RED}" '
                   f'style="animation-delay:{-i * 2}s"/>' for i in range(3))
    return (f'<path d="M10 {road}H{w - 10:g}" stroke="#2A2420" stroke-width="9"/>'
            f'<path d="M10 {road}H{w - 10:g}" stroke="{GOLD}" stroke-opacity=".25" stroke-dasharray="3 5"/>'
            + foes
            + f'<rect x="{tx - 6:g}" y="{road - 30}" width="12" height="14" fill="#3A3127" stroke="{GOLD}"/>'
            + diamond(tx, road - 33, 5, GOLD)
            + f'<circle class="shot" cx="{tx:g}" cy="{road - 33}" r="1.6" fill="#FFF"/>',
            f"@keyframes march{{to{{transform:translateX({28 - w:g}px)}}}}.foe{{animation:march 6s linear infinite}}"
            "@keyframes shot{0%{transform:translate(0,0);opacity:1}80%{opacity:1}"
            "100%{transform:translate(-18px,24px);opacity:0}}.shot{animation:shot .7s ease-in infinite}")


def strip(title, items):
    cols, gap, pad, chip_h = 3, 14, 28, 100
    rows = math.ceil(len(items) / cols)
    svg = Svg(860, 62 + rows * (chip_h + 12) + 22, title,
              " ; ".join(f"{name} : {sub}" for name, sub, _ in items) + ".")
    frame(svg)
    svg.text(pad, 44, title, SERIF, 16, GOLD)
    line_x = pad + SERIF.width(title, 16) + 16
    svg.add(f'<path d="M{line_x:.1f} 39.5H{svg.w - pad}" stroke="{GOLD}" stroke-opacity=".25"/>')
    chip_w = (svg.w - 2 * pad - (cols - 1) * gap) / cols
    sw, sh = chip_w - 16, 44
    for i, (name, sub, scene) in enumerate(items):
        cx = pad + (i % cols) * (chip_w + gap)
        cy = 62 + (i // cols) * (chip_h + 12)
        svg.add(f'<path d="{chamfer(cx, cy, chip_w, chip_h, 6)}" fill="#FFFFFF" fill-opacity=".025" '
                f'stroke="{GOLD}" stroke-opacity=".22"/>')
        # Petit écran de jeu animé en haut de la vignette.
        svg.add(f'<path d="{chamfer(cx + 8, cy + 8, sw, sh, 4)}" fill="#000" fill-opacity=".4" stroke="{GOLD}" '
                f'stroke-opacity=".18"/>')
        svg.defs.append(f'<clipPath id="scene{i}"><rect width="{sw:.1f}" height="{sh}"/></clipPath>')
        markup, css = scene(sw, sh)
        svg.add(f'<g transform="translate({cx + 8:.1f} {cy + 8})" clip-path="url(#scene{i})">{markup}</g>')
        svg.css.append(css)
        check(f"{name} : nom", SERIF.width(name, 15), chip_w - 32)
        check(f"{name} : sous-titre", SANS.width(sub, 12), chip_w - 32)
        svg.text(cx + 16, cy + 74, name, SERIF, 15, GOLD)
        svg.text(cx + 16, cy + 91, sub, SANS, 12, MUTED)
    border(svg)
    return svg


def arsenal(groups):
    # Une rangée par domaine ; chaque logo s'allume tour à tour dans sa vraie couleur.
    row_h, top, pad, label_w = 74, 26, 32, 190
    svg = Svg(860, 2 * top + len(groups) * row_h, "Arsenal",
              " ; ".join(f"{t} : {', '.join(label for _, label, _ in items)}" for t, items in groups) + ".")
    frame(svg)
    total = sum(len(items) for _, items in groups)
    step = 1.2
    cycle = total * step
    fade, hold, end = (s / cycle * 100 for s in (.3, .9, 1.2))
    svg.css.append(f"@keyframes pass{{0%{{opacity:0}}{fade:.2f}%,{hold:.2f}%{{opacity:1}}{end:.2f}%,100%{{opacity:0}}}}"
                   f".pass{{opacity:0;animation:pass {cycle:g}s ease-in-out infinite}}")
    order = 0
    for r, (title, items) in enumerate(groups):
        y0 = top + r * row_h
        if r:
            svg.add(f'<path d="M{pad} {y0}H{svg.w - pad}" stroke="{GOLD}" stroke-opacity=".12"/>')
        svg.text(pad, y0 + row_h / 2 + 6, title, SERIF, 16, GOLD)
        pitch = (svg.w - 2 * pad - label_w) / len(items)
        for k, (slug, label, color) in enumerate(items):
            cx = pad + label_w + pitch * (k + .5)
            svg.add(icon(slug, cx - 15, y0 + 12, 30, GOLD))
            svg.add(icon(slug, cx - 15, y0 + 12, 30, color,
                         f' class="pass" style="animation-delay:{order * step:.1f}s"'))
            check(f"arsenal : {label}", SANS_SB.width(label, 11), pitch - 8)
            svg.text(cx, y0 + 60, label, SANS_SB, 11, TEXT, anchor="middle")
            order += 1
    border(svg)
    return svg


def heading(title, index):
    svg = Svg(640, 64, title, title)
    w, cy, size, spacing = svg.w, 34, 24, 7
    svg.defs.append('<filter id="glint" x="-300%" y="-300%" width="700%" height="700%">'
                    '<feGaussianBlur stdDeviation="1.6" result="b"/>'
                    '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    tw = SERIF_BLACK.width(title, size, spacing) - spacing
    # letter-spacing ajoute un blanc après la dernière lettre : on recentre d'une demi-chasse.
    svg.text(w / 2 + spacing / 2, cy + 8.5, title, SERIF_BLACK, size, GOLD, spacing=spacing, anchor="middle",
             extra='class="t"')
    flower, inner, outer = tw / 2 + 20, tw / 2 + 34, w / 2 - 20
    for side, sign in (("l", -1), ("r", 1)):
        a, b = w / 2 + sign * inner, w / 2 + sign * outer
        svg.defs.append(
            f'<linearGradient id="{side}" gradientUnits="userSpaceOnUse" x1="{a:g}" y1="0" x2="{b:g}" y2="0">'
            f'<stop offset="0" stop-color="{GOLD}" stop-opacity=".8"/>'
            f'<stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></linearGradient>'
        )
        svg.add(f'<path d="M{a:g} {cy}H{b:g}" stroke="url(#{side})"/>')
        svg.add(diamond(b - sign * 10, cy, 2.5, GOLD))
        svg.add(aeonia(w / 2 + sign * flower, cy, f"bloom {side}"))
        # Étincelle qui part de la fleur et file le long du filet ; décalée d'un titre à l'autre.
        svg.add(f'<circle class="spark {side}" cx="{a:g}" cy="{cy}" r="1.8" fill="#FFF4D6" filter="url(#glint)" '
                f'style="animation-delay:{index * 1.5:g}s"/>')
    run = outer - inner - 14
    svg.css.append("@keyframes spin{to{transform:rotate(360deg)}}"
                   ".bloom{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite}"
                   ".bloom.r{animation-direction:reverse}"
                   + "".join(f"@keyframes spark-{side}{{0%{{transform:translateX(0);opacity:0}}5%{{opacity:1}}"
                             f"38%{{transform:translateX({sign * run:.0f}px);opacity:0}}100%{{opacity:0}}}}"
                             for side, sign in (("l", -1), ("r", 1)))
                   + ".spark{opacity:0;animation:6s cubic-bezier(.3,0,.2,1) infinite}"
                   ".spark.l{animation-name:spark-l}.spark.r{animation-name:spark-r}"
                   # Titre sans cadre : sur le thème clair de GitHub, l'or clair manquerait de contraste.
                   "@media (prefers-color-scheme:light){.t{fill:#785A28}}")
    return svg


def banner():
    w, h = 860, 280
    svg = Svg(w, h, "Terrenoss",
              "Développeur full-stack et game dev, en France. Apps pour les joueurs de League of Legends, "
              "jeux sous Unity. Stack : C#, .NET, Unity, TypeScript, Next.js, Electron.")
    frame(svg)
    cx, cy = 716, 132
    ticks = 2 * math.pi * 96 / 72  # 72 graduations pile sur la circonférence, sans raccord visible
    svg.defs.append(
        f'<radialGradient id="fire" cx=".83" cy="1.08" r=".55">'
        f'<stop offset="0" stop-color="{RED}" stop-opacity=".5"/>'
        f'<stop offset=".5" stop-color="{RED}" stop-opacity=".12"/>'
        f'<stop offset="1" stop-color="{RED}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="wisp"><stop offset="0" stop-color="#FFF6E4"/>'
        f'<stop offset=".35" stop-color="{EMBER}" stop-opacity=".75"/>'
        f'<stop offset="1" stop-color="{RED}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="moon" cx=".35" cy=".4"><stop offset="0" stop-color="#FFFFFF"/>'
        f'<stop offset="1" stop-color="{WHITE}"/></radialGradient>'
        f'<mask id="crescent"><rect width="{w}" height="{h}" fill="#FFF"/>'
        f'<circle cx="{cx + 15}" cy="{cy - 10}" r="35" fill="#000"/></mask>'
        '<filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>'
        '<filter id="lift" x="-5%" y="-20%" width="110%" height="150%">'
        '<feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="#000" flood-opacity=".9"/></filter>'
        '<linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#FFF7E2"/><stop offset=".42" stop-color="#EED394"/>'
        f'<stop offset=".6" stop-color="{GOLD}"/><stop offset=".85" stop-color="#8A672C"/>'
        '<stop offset="1" stop-color="#C9AA6A"/></linearGradient>'
        '<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#FFF" stop-opacity="0"/><stop offset=".5" stop-color="#FFF" stop-opacity=".8"/>'
        '<stop offset="1" stop-color="#FFF" stop-opacity="0"/></linearGradient>'
    )
    svg.css.append(
        "@keyframes spin{to{transform:rotate(360deg)}}"
        "@keyframes flicker{0%{opacity:.7}40%{opacity:1}70%{opacity:.82}100%{opacity:.95}}"
        "@keyframes breathe{50%{opacity:.35}}"
        "@keyframes sweep{0%{transform:translateX(0)}30%,100%{transform:translateX(720px)}}"
        f".ring,.orbit{{transform-box:view-box;transform-origin:{cx}px {cy}px}}"
        ".ring{animation:spin 120s linear infinite}.orbit{animation:spin 9s linear infinite}"
        ".fire{animation:flicker 3.2s ease-in-out infinite alternate}"
        ".halo{animation:breathe 6s ease-in-out infinite}"
        ".sweep{animation:sweep 9s cubic-bezier(.45,0,.25,1) 1s infinite}"
    )

    # Feu de camp : lueur qui vacille et braises qui montent.
    svg.add(f'<rect class="fire" width="{w}" height="{h}" fill="url(#fire)" clip-path="url(#card)"/>')
    embers(svg, 26, [(590, 840)] * 3 + [(24, 590)] * 2, h, 240, 7)

    # Emblème : anneau gradué, lune de Ranni, feu-renard d'Ahri en orbite.
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="104" fill="none" stroke="{GOLD}" stroke-opacity=".25"/>')
    svg.add(f'<circle class="ring" cx="{cx}" cy="{cy}" r="96" fill="none" stroke="{GOLD}" stroke-opacity=".5" '
            f'stroke-width="6" stroke-dasharray="1.2 {ticks - 1.2:.3f}"/>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="82" fill="{BLACK}" fill-opacity=".55" stroke="{GOLD}" '
            f'stroke-opacity=".5"/>')
    for dx, dy in ((0, -82), (82, 0), (0, 82), (-82, 0)):
        svg.add(diamond(cx + dx, cy + dy, 5, GOLD))
    svg.add(f'<g class="halo" filter="url(#blur)"><circle cx="{cx}" cy="{cy}" r="40" fill="{WHITE}" '
            f'opacity=".4" mask="url(#crescent)"/></g>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="40" fill="url(#moon)" mask="url(#crescent)"/>')
    orbs = []
    for i in range(3):
        for j, (r, op) in enumerate(((7.5, 1), (2.4, .5), (1.8, .32), (1.2, .18))):
            a = math.radians(i * 120 - j * 8)  # traînée derrière l'orbe, sens horaire
            fill = "url(#wisp)" if j == 0 else EMBER
            orbs.append(f'<circle cx="{cx + 64 * math.cos(a):.1f}" cy="{cy + 64 * math.sin(a):.1f}" r="{r}" '
                        f'fill="{fill}" opacity="{op}"/>')
        a = math.radians(i * 120)
        orbs.append(f'<circle cx="{cx + 64 * math.cos(a):.1f}" cy="{cy + 64 * math.sin(a):.1f}" r="2.2" '
                    f'fill="#FFF"/>')
    orbs = "".join(orbs)
    svg.add(f'<g class="orbit">{orbs}</g>')

    # Nom en or métallique (écran VICTORY), avec un reflet qui passe de temps en temps.
    x, limit = 48, cx - 116
    name = "Terrenoss"
    check("bannière : nom", x + DISPLAY.width(name, 58), limit)
    svg.defs.append(f'<clipPath id="name">{svg.markup(x - 2, 128, name, DISPLAY, 58, "#000")}</clipPath>')
    svg.text(x - 2, 128, name, DISPLAY, 58, "url(#metal)", extra='filter="url(#lift)"')
    svg.add('<g clip-path="url(#name)"><g class="sweep">'
            '<rect x="-150" y="60" width="110" height="90" fill="url(#shine)" transform="skewX(-20)"/></g></g>')
    svg.add(f'<path d="M{x} 150H{x + 58}" stroke="{RED}" stroke-width="2"/>')
    svg.add(diamond(x + 64, 150, 3.5, RED))
    for i, line in enumerate(("Développeur full-stack et game dev, en France.",
                              "Apps pour les joueurs de League of Legends, jeux sous Unity.")):
        check("bannière : accroche", x + SANS.width(line, 15.5), limit)
        svg.text(x, 182 + i * 22, line, SANS, 15.5, TEXT, opacity=0.92)
    check("bannière : stack", pills(svg, x, 226, ["C#", ".NET", "Unity", "TypeScript", "Next.js", "Electron"]),
          limit)
    border(svg)
    return svg


def footer():
    # Feu de camp de Dark Souls et son message « BONFIRE LIT ».
    w, h = 860, 206
    svg = Svg(w, h, "Bonfire lit",
              "Feu de camp de Dark Souls avec son épée enroulée, et le message BONFIRE LIT. "
              "Merci d'être passé, repose-toi au feu avant de reprendre la route.")
    frame(svg)
    cx, ground = w / 2, 100
    svg.defs.append(
        f'<radialGradient id="hearth"><stop offset="0" stop-color="{EMBER}" stop-opacity=".5"/>'
        f'<stop offset="1" stop-color="{RED}" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="band" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#000" stop-opacity=".6"/><stop offset="1" stop-color="#000" stop-opacity="0"/>'
        '</linearGradient>'
        f'<linearGradient id="rule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{GOLD}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{GOLD}" stop-opacity=".7"/><stop offset="1" stop-color="{GOLD}" '
        f'stop-opacity="0"/></linearGradient>'
        '<filter id="soft" x="-10%" y="-50%" width="120%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>'
    )
    svg.css.append(
        "@keyframes flicker{0%{opacity:.7}40%{opacity:1}70%{opacity:.82}100%{opacity:.95}}"
        ".fire{animation:flicker 2.4s ease-in-out infinite alternate}" + FLAME_CSS +
        "@keyframes lit{0%{opacity:0}12%,82%{opacity:1}96%,100%{opacity:0}}.lit{animation:lit 10s ease-in-out infinite}"
    )
    svg.add(f'<ellipse class="fire" cx="{cx:g}" cy="{ground - 8}" rx="80" ry="46" fill="url(#hearth)"/>')
    svg.add(f'<ellipse cx="{cx:g}" cy="{ground + 3}" rx="30" ry="6" fill="#2A2420"/>')
    # Épée enroulée plantée dans les cendres, légèrement penchée.
    coil = "".join(f'<ellipse cx="{cx:g}" cy="{ground - 48 + k * 9}" rx="6.5" ry="2" fill="none" stroke="#7A7064" '
                   f'stroke-width="1.6" transform="rotate(-14 {cx:g} {ground - 48 + k * 9})"/>' for k in range(5))
    svg.add(f'<g transform="rotate(6 {cx:g} {ground})">'
            f'<path d="M{cx - 2.6:g} {ground}L{cx - 3:g} {ground - 58}H{cx + 3:g}L{cx + 2.6:g} {ground}Z" '
            f'fill="{STEEL}"/>'
            f'<path d="M{cx:g} {ground - 56}V{ground - 2}" stroke="{MUTED}" stroke-width=".8"/>'
            f'<rect x="{cx - 11:g}" y="{ground - 62}" width="22" height="4" rx="1" fill="{GOLD}"/>'
            f'<rect x="{cx - 1.6:g}" y="{ground - 74}" width="3.2" height="12" fill="#6E5630"/>'
            f'<circle cx="{cx:g}" cy="{ground - 76}" r="3" fill="{GOLD}"/>{coil}</g>')
    svg.add(flames(cx, ground, ((-13, 22, 9, RED, 1.3), (12, 26, 10, RED, 1.1), (-5, 34, 10, EMBER, .9),
                                (6, 30, 8, EMBER, 1.2), (0, 20, 6, "#FFD58A", .8))))
    embers(svg, 14, [(cx - 22, cx + 22)], ground - 16, 90, 11)

    band_y, band_h = 118, 44
    msg = "BONFIRE LIT"
    svg.add(f'<g class="lit"><rect y="{band_y}" width="{w}" height="{band_h}" fill="url(#band)"/>'
            f'<path d="M120 {band_y}H{w - 120}M120 {band_y + band_h}H{w - 120}" stroke="url(#rule)"/>'
            + svg.markup(cx + 4, band_y + 31, msg, SERIF, 28, EMBER, spacing=8, anchor="middle", opacity=.55,
                         extra='filter="url(#soft)"')
            + svg.markup(cx + 4, band_y + 31, msg, SERIF, 28, "#F3D9A4", spacing=8, anchor="middle")
            + "</g>")
    svg.text(cx, 188, "Merci d'être passé. Repose-toi au feu avant de reprendre la route.", SANS, 12.5, MUTED,
             anchor="middle")
    border(svg)
    return svg


NB = " "  # espace insécable avant les deux-points

def contact_button(label):
    # Bouton à bouts en pointe ; fond noir pour rester lisible sur le thème clair de GitHub.
    size, spacing, pad, h = 12, 2.2, 24, 44
    w = round(SANS_SB.width(label, size, spacing) - spacing + 2 * pad + 20)
    svg = Svg(w, h, label, label)
    svg.add(f'<path d="{tag_shape(.5, .5, w - 1, h - 1, 12)}" fill="{BLACK}" stroke="{GOLD}" stroke-opacity=".7"/>')
    svg.text(pad, h / 2 + size * .36, label, SANS_SB, size, WHITE, spacing=spacing)
    svg.add(f'<path transform="translate({w - pad - 8} {h / 2 - 4:g})" d="M0 8L8 0M2.5 0H8V5.5" fill="none" '
            f'stroke="{GOLD}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
    return svg


MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def fr_date(d, year=False):
    return f"{d.day} {MONTHS[d.month - 1]}" + (f" {d.year}" if year else "")


def contributions(login="Terrenoss"):
    # Calendrier complet depuis la création du compte ; l'API limite chaque collection à un an.
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None

    def user(fields):
        query = json.dumps({"query": f'{{user(login:"{login}"){{{fields}}}}}'}).encode()
        req = urllib.request.Request("https://api.github.com/graphql", data=query,
                                     headers={"Authorization": f"bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        if "errors" in data:
            raise RuntimeError(data["errors"])
        return data["data"]["user"]

    created = date.fromisoformat(user("createdAt")["createdAt"][:10])
    today = datetime.now(timezone.utc).date()
    years = "".join(
        f'y{y}:contributionsCollection(from:"{max(created, date(y, 1, 1))}T00:00:00Z",'
        f'to:"{min(today, date(y, 12, 31))}T23:59:59Z")'
        "{contributionCalendar{weeks{contributionDays{date contributionCount}}}}"
        for y in range(created.year, today.year + 1))
    days = {date.fromisoformat(d["date"]): d["contributionCount"]
            for c in user(years).values() for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]}
    return created, today, days


def streaks(days, today):
    # (longueur, début, fin) de la série en cours et du record. Aujourd'hui à zéro ne casse pas encore la série.
    best, run, start = (0, None, None), 0, None
    for d in sorted(days):
        if days[d]:
            start = d if run == 0 else start
            run += 1
            if run > best[0]:
                best = (run, start, d)
        else:
            run = 0
    end = today if days.get(today) else today - timedelta(1)
    first, current = end, 0
    while days.get(first):
        current += 1
        first -= timedelta(1)
    return (current, first + timedelta(1), end), best


def streak_card():
    data = contributions()
    if data is None:
        return None
    created, today, days = data
    total = sum(days.values())
    (cur, cur_start, cur_end), (best, best_start, best_end) = streaks(days, today)

    def span(n, a, b):
        if not n:
            return "—"
        year = a.year != today.year
        return fr_date(a, year) if a == b else f"{fr_date(a, year)} – {fr_date(b, year)}"

    svg = Svg(860, 200, "Activité GitHub",
              f"{total} contributions depuis le {fr_date(created, True)}. Série en cours : {cur} jours, "
              f"l'arc rouge montre la progression vers le record. Plus longue série : {best} jours.")
    frame(svg)
    cx, cy, r = 430, 86, 44
    ticks = 2 * math.pi * 56 / 60
    progress = min(cur / best, 1) * 100 if best else 0
    svg.css.append(
        "@keyframes spin{to{transform:rotate(360deg)}}"
        f".ring{{transform-box:view-box;transform-origin:{cx}px {cy}px;animation:spin 90s linear infinite}}"
        "@keyframes arc{from{stroke-dasharray:0 100}}"
        ".arc{animation:arc 1.8s cubic-bezier(.2,.8,.2,1) .3s backwards}" + FLAME_CSS)
    for x in (290, 570):
        svg.add(f'<path d="M{x} 40V164" stroke="{GOLD}" stroke-opacity=".15"/>')
    for x, value, label, dates in ((150, total, "Contributions au total", f"depuis le {fr_date(created, True)}"),
                                   (710, best, "Plus longue série", span(best, best_start, best_end))):
        svg.text(x, 106, f"{value:,}".replace(",", NB), SERIF_BLACK, 40, GOLD, anchor="middle")
        svg.text(x, 160, label, SANS_SB, 12.5, TEXT, anchor="middle")
        svg.text(x, 180, dates, SANS, 11.5, MUTED, anchor="middle")

    # Série en cours : anneau gradué, arc rouge = progression vers le record, flamme posée dessus.
    svg.add(f'<circle class="ring" cx="{cx}" cy="{cy}" r="56" fill="none" stroke="{GOLD}" stroke-opacity=".45" '
            f'stroke-width="5" stroke-dasharray="1.2 {ticks - 1.2:.3f}"/>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{BLACK}" fill-opacity=".6" stroke="{GOLD}" '
            f'stroke-opacity=".2" stroke-width="4"/>')
    svg.add(f'<circle class="arc" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{RED}" stroke-width="4" '
            f'stroke-linecap="round" pathLength="100" stroke-dasharray="{progress:.1f} 100" '
            f'transform="rotate(-90 {cx} {cy})"/>')
    svg.text(cx, cy + 14, str(cur), SERIF_BLACK, 40, WHITE, anchor="middle")
    top = cy - r
    svg.add(f'<ellipse cx="{cx}" cy="{top}" rx="12" ry="9" fill="{BLACK}"/>')
    svg.add(flames(cx, top + 6, ((-5, 16, 6, RED, 1.2), (5, 18, 6, RED, 1), (0, 24, 7, EMBER, .9),
                                 (0, 13, 4, "#FFD58A", .8))))
    embers(svg, 8, [(cx - 8, cx + 8)], top - 14, 60, 5)
    svg.text(cx, 160, "Série en cours", SANS_SB, 12.5, TEXT, anchor="middle")
    svg.text(cx, 180, span(cur, cur_start, cur_end), SANS, 11.5, MUTED, anchor="middle")
    border(svg)
    return svg


HEADINGS = {"projets": "PROJETS", "game-dev": "GAME DEV", "arsenal": "ARSENAL", "activite": "ACTIVITÉ"}

# (logo, nom, couleur de marque éclaircie si besoin pour rester lisible sur fond noir)
STACK = [
    ("Desktop & jeu", [("csharp", "C#", "#A179DC"), ("dotnet", ".NET", "#7B5CF0"), ("avaloniaui", "Avalonia", "#9B5BC8"),
                       ("unity", "Unity", "#FFFFFF"), ("cplusplus", "C++", "#3C8BD6")]),
    ("Web", [("typescript", "TypeScript", "#3B8EEA"), ("react", "React", "#61DAFB"), ("nextdotjs", "Next.js", "#FFFFFF"),
             ("nodedotjs", "Node.js", "#5FA04E"), ("electron", "Electron", "#9FEAF9")]),
    ("Données & outils", [("python", "Python", "#FFD43B"), ("postgresql", "PostgreSQL", "#5B87E8"),
                          ("redis", "Redis", "#FF4438"), ("docker", "Docker", "#2496ED"), ("git", "Git", "#F05032")]),
]

PROJECTS = [
    Project("porotalk", "PoroTalk", "App desktop",
            f"Chat vocal éphémère pour League of Legends{NB}: connexion automatique avec tes coéquipiers, "
            "en WebRTC P2P, sans lien à partager.",
            ["Electron", "TypeScript", "WebRTC"], "private", anim_voice),
    Project("cashback", "CashBack", "Bot Discord + site web",
            f"Paris en fausse monnaie sur les games de tes amis, et Rift, un site de stats façon op.gg. "
            "Monorepo avec worker Riot et app desktop Tauri.",
            ["TypeScript", "Next.js", "Prisma"], "private", anim_chart, link="rift.ddns.net"),
    Project("widgetforge", "WidgetForge", "Moteur de widgets",
            f"Widgets de profil Discord dynamiques{NB}: connecteurs LoL, Steam et Spotify, "
            "scheduler et rendu de visuels animés.",
            ["TypeScript", "Redis"], "private", anim_widgets),
    Project("mimic-reborn", "Mimic Reborn", "Fork modernisé",
            "Le client League sur ton téléphone, du lobby à la sélection des champions. "
            "Connexion directe en LAN, chiffrée de bout en bout.",
            [".NET 9", "React", "TypeScript"], "oss", anim_lan),
]

GAMES = [
    Game("ascensio", "Ascensio", "Jeu de cartes · Roguelike · 3D",
         "Former des mains de poker sur une grille 5×5 (lignes, colonnes, diagonales) avec un jeu classique "
         "et des atouts de tarot. Inspiré de Balatro et CloverPit, en vue à la première personne.",
         "Gameplay des cartes (drag & drop, main, croupier, tours de jeu), calcul du score et détection "
         "des mains de poker, boutique, sauvegarde.",
         ["Unity 6", "C#", "DOTween"], "Projet d'équipe · 2026", "private",
         "Illustrations : équipe artistique d'Ascensio",
         {"cards": [("ascensio-dos.jpg", -17), ("ascensio-roi.jpg", 17), ("ascensio-monde.jpg", 0)],
          "back": "ascensio-dos.jpg"}),
    Game("turkeyshowdown", "TurkeyShowdown", "Multijoueur en ligne · Arène",
         f"Deathmatch en vue du dessus entre dindons armés{NB}: armes, grappin, objets à ramasser "
         "et plusieurs maps (Arène, Ferme, Verger).",
         "Modes de jeu (deathmatch, équipes), kill feed et classement des scores synchronisés en réseau.",
         ["Unity 6", "C#", "Netcode for GameObjects"], "Projet d'équipe · 2025", "public",
         "Map « Ferme » · art de l'équipe TurkeyShowdown",
         {"image": "turkey-ferme.jpg",
          "feed": [("Terrenoss", "Dindon_42"), ("Plumeau", "GlouGlou"), ("Terrenoss", "Plumeau")]}),
]

SMALL_GAMES = [
    ("Super Meat Boy", "Remake · plateforme 2D, 3 niveaux", scene_meatboy),
    ("World of Goo", "Remake · structures physiques", scene_goo),
    ("Zelda-like", "Quêtes, inventaire, sauvegarde", scene_zelda),
    ("Factorio-like", "Convoyeurs, inserteurs, production", scene_factorio),
    ("ShroomWitch Garden", "God game · colonies d'IA, en équipe", scene_shrooms),
    ("Tower Defense", "Codé depuis un diagramme UML", scene_td),
]


def main(names):
    builders = {"banniere.svg": banner, "arsenal.svg": lambda: arsenal(STACK), "footer.svg": footer,
                "streak.svg": streak_card, "contact.svg": lambda: contact_button("ME CONTACTER SUR LINKEDIN")}
    builders |= {f"titre-{slug}.svg": (lambda t=title, i=i: heading(t, i))
                 for i, (slug, title) in enumerate(HEADINGS.items())}
    builders |= {f"projet-{p.slug}.svg": (lambda p=p: project_card(p)) for p in PROJECTS}
    builders |= {f"jeu-{g.slug}.svg": (lambda g=g: game_card(g)) for g in GAMES}
    builders["jeux-unity.svg"] = lambda: strip("Aussi sur Unity", SMALL_GAMES)
    OUT.mkdir(exist_ok=True)
    for name in names or builders:
        svg = builders[name]()
        if svg is None:
            print(f"{name:28} ignoré : GITHUB_TOKEN absent")
            continue
        (OUT / name).write_text(svg.render(), encoding="utf-8")
        print(f"{name:28} {(OUT / name).stat().st_size / 1024:6.1f} Ko")


if __name__ == "__main__":
    main(sys.argv[1:])
