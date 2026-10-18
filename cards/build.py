"""Génère les visuels SVG du README dans assets/.

Usage : python cards/build.py   (dépendance : pip install fonttools)

GitHub affiche les SVG du README comme des <img> : ils ne peuvent charger ni
police ni image externe. Tout est donc intégré en base64, et les polices sont
réduites aux seuls caractères utilisés par chaque visuel.

DA : noir, or hextech, blanc chaud et rouge, cadres à coins coupés façon client
League of Legends. Clins d'œil dessinés : feu-renard d'Ahri, lune de Ranni,
fleur écarlate de Malenia, braises du feu de camp de la Gardienne du Feu.
"""
import base64
import io
import math
import random
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets"

BLACK = "#08080A"
GOLD = "#C8AA6E"
GOLD_DIM = "#A08A5C"
WHITE = "#F0E6D2"
TEXT = "#E4DDCF"
MUTED = "#8F877A"
RED = "#D3202C"
EMBER = "#F08A2C"
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
        tt = TTFont(self.path)
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


def diamond(x, y, r, fill):
    return f'<path d="M{x:g} {y - r:g}L{x + r:g} {y:g}L{x:g} {y + r:g}L{x - r:g} {y:g}Z" fill="{fill}"/>'


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


@dataclass
class Project:
    slug: str
    name: str
    label: str
    desc: str
    tags: list
    status: str
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
    status_x = status(svg, svg.w - pad, pad, p.status)
    check(f"{p.name} : titre", pad + SERIF.width(p.name, 26), status_x - 10)
    svg.text(pad, 50, p.name, SERIF, 26, GOLD)
    svg.text(pad, 71, p.label, SANS, 12.5, GOLD_DIM)
    lines = wrap(p.desc, SANS, 13.5, svg.w - 2 * pad)
    check(f"{p.name} : description (lignes)", len(lines), 3)
    for i, line in enumerate(lines):
        svg.text(pad, 102 + i * 20, line, SANS, 13.5, TEXT, opacity=0.9)
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
    # Éventail de trois cartes pivotant autour d'un point situé sous la main.
    w, h, pivot_y, lift = 120, 206, 350, 110
    svg.defs.append(
        f'<filter id="shadow" x="-40%" y="-40%" width="180%" height="180%">'
        f'<feDropShadow dx="0" dy="8" stdDeviation="9" flood-color="#000" flood-opacity=".7"/></filter>'
        f'<clipPath id="tarot"><rect x="{-w / 2:g}" y="{-(h + lift)}" width="{w}" height="{h}" rx="7"/></clipPath>'
    )
    panel_glow(svg, cx * 2)
    for name, angle in art["cards"]:
        svg.add(
            f'<g transform="translate({cx} {pivot_y}) rotate({angle})" filter="url(#shadow)">'
            f'<image href="{image_uri(name)}" x="{-w / 2:g}" y="{-(h + lift)}" width="{w}" height="{h}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#tarot)"/>'
            f'<rect x="{-w / 2:g}" y="{-(h + lift)}" width="{w}" height="{h}" rx="7" fill="none" '
            f'stroke="{GOLD}" stroke-opacity=".55"/></g>'
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


def game_card(g):
    svg = Svg(860, 300, g.name,
              f"{g.label}. {g.desc} Mon rôle : {g.role} {g.meta}. Technologies : {', '.join(g.tags)}. {g.credit}.")
    frame(svg)
    panel = 340
    if "cards" in g.art:
        fan(svg, g.art, panel // 2)
    else:
        shot(svg, g.art, panel)
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


def strip(title, items):
    cols, gap, pad, chip_h = 3, 14, 28, 50
    svg = Svg(860, 196, title, " ; ".join(f"{name} : {sub}" for name, sub in items) + ".")
    frame(svg)
    svg.text(pad, 44, title, SERIF, 16, GOLD)
    line_x = pad + SERIF.width(title, 16) + 16
    svg.add(f'<path d="M{line_x:.1f} 39.5H{svg.w - pad}" stroke="{GOLD}" stroke-opacity=".25"/>')
    chip_w = (svg.w - 2 * pad - (cols - 1) * gap) / cols
    for i, (name, sub) in enumerate(items):
        cx = pad + (i % cols) * (chip_w + gap)
        cy = 62 + (i // cols) * (chip_h + 12)
        svg.add(f'<path d="{chamfer(cx, cy, chip_w, chip_h, 6)}" fill="#FFFFFF" fill-opacity=".025" '
                f'stroke="{GOLD}" stroke-opacity=".22"/>')
        check(f"{name} : nom", SERIF.width(name, 15), chip_w - 32)
        check(f"{name} : sous-titre", SANS.width(sub, 12), chip_w - 32)
        svg.text(cx + 16, cy + 22, name, SERIF, 15, GOLD)
        svg.text(cx + 16, cy + 39, sub, SANS, 12, MUTED)
    border(svg)
    return svg


def arsenal(groups):
    svg = Svg(860, 146, "Arsenal", " ; ".join(f"{t} : {', '.join(items)}" for t, items in groups) + ".")
    frame(svg)
    pad, gap = 28, 28
    col_w = (svg.w - 2 * pad - 2 * gap) / 3
    for i, (title, items) in enumerate(groups):
        x0 = pad + i * (col_w + gap)
        if i:
            svg.add(f'<path d="M{x0 - gap / 2:.1f} 32V{svg.h - 32}" stroke="{GOLD}" stroke-opacity=".15"/>')
        svg.text(x0, 50, title, SERIF, 16, GOLD)
        x, y = x0, 66
        for label in items:
            if x + pill_width(label) > x0 + col_w:
                x, y = x0, y + 30
            x = pills(svg, x, y, [label]) + 6
        check(f"arsenal : {title}", y + 22, svg.h - pad)
    border(svg)
    return svg


def heading(title):
    svg = Svg(640, 64, title, title)
    w, cy, size, spacing = svg.w, 34, 24, 7
    tw = SERIF_BLACK.width(title, size, spacing) - spacing
    # letter-spacing ajoute un blanc après la dernière lettre : on recentre d'une demi-chasse.
    svg.text(w / 2 + spacing / 2, cy + 8.5, title, SERIF_BLACK, size, GOLD, spacing=spacing, anchor="middle")
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
    svg.css.append("@keyframes spin{to{transform:rotate(360deg)}}"
                   ".bloom{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite}"
                   ".r{animation-direction:reverse}")
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
        '<filter id="spark" x="-10%" y="-10%" width="120%" height="120%">'
        '<feGaussianBlur stdDeviation="1.4" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
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
    rise = "0%{transform:translate(0,0);opacity:0}12%{opacity:.95}"
    svg.css.append(
        "@keyframes spin{to{transform:rotate(360deg)}}"
        "@keyframes flicker{0%{opacity:.7}40%{opacity:1}70%{opacity:.82}100%{opacity:.95}}"
        "@keyframes breathe{50%{opacity:.35}}"
        "@keyframes sweep{0%{transform:translateX(0)}30%,100%{transform:translateX(720px)}}"
        f"@keyframes rise-a{{{rise}100%{{transform:translate(26px,-240px);opacity:0}}}}"
        f"@keyframes rise-b{{{rise}100%{{transform:translate(-30px,-270px);opacity:0}}}}"
        f"@keyframes rise-c{{{rise}50%{{transform:translate(-14px,-100px)}}"
        "100%{transform:translate(10px,-200px);opacity:0}}"
        f".ring,.orbit{{transform-box:view-box;transform-origin:{cx}px {cy}px}}"
        ".ring{animation:spin 120s linear infinite}.orbit{animation:spin 9s linear infinite}"
        ".fire{animation:flicker 3.2s ease-in-out infinite alternate}"
        ".halo{animation:breathe 6s ease-in-out infinite}"
        ".sweep{animation:sweep 9s cubic-bezier(.45,0,.25,1) 1s infinite}"
        ".ember{opacity:0;animation-timing-function:linear;animation-iteration-count:infinite}"
        ".a{animation-name:rise-a}.b{animation-name:rise-b}.c{animation-name:rise-c}"
    )

    # Feu de camp de la Gardienne du Feu : lueur qui vacille et braises qui montent.
    svg.add(f'<rect class="fire" width="{w}" height="{h}" fill="url(#fire)" clip-path="url(#card)"/>')
    rng = random.Random(7)  # graine fixe : le SVG ne change pas d'une génération à l'autre
    embers = []
    for _ in range(26):
        x = rng.uniform(590, 840) if rng.random() < .6 else rng.uniform(24, 590)
        dur = rng.uniform(5.5, 11)
        embers.append(
            f'<circle class="ember {rng.choice("abc")}" cx="{x:.1f}" cy="{h + rng.uniform(2, 16):.1f}" '
            f'r="{rng.uniform(.7, 1.9):.2f}" fill="{rng.choice((RED, EMBER, EMBER, WHITE))}" '
            f'style="animation-duration:{dur:.1f}s;animation-delay:{-rng.uniform(0, dur):.1f}s"/>')
    embers = "".join(embers)
    svg.add(f'<g clip-path="url(#card)" filter="url(#spark)">{embers}</g>')

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


NB = " "  # espace insécable avant les deux-points

HEADINGS = {"projets": "PROJETS", "game-dev": "GAME DEV", "arsenal": "ARSENAL", "activite": "ACTIVITÉ"}

STACK = [
    ("Desktop & jeu", ["C#", ".NET", "Avalonia", "Unity", "C++"]),
    ("Web", ["TypeScript", "React", "Next.js", "Node.js", "Electron"]),
    ("Données & outils", ["Python", "PostgreSQL", "Redis", "Docker", "Git"]),
]

PROJECTS = [
    Project("porotalk", "PoroTalk", "App desktop",
            f"Chat vocal éphémère pour League of Legends{NB}: connexion automatique avec tes coéquipiers, "
            "en WebRTC P2P, sans lien à partager.",
            ["Electron", "TypeScript", "WebRTC"], "private"),
    Project("cashback", "CashBack", "Bot Discord + site web",
            f"Paris en fausse monnaie sur les games de tes amis, et Rift, un site de stats façon op.gg. "
            "Monorepo avec worker Riot et app desktop Tauri.",
            ["TypeScript", "Next.js", "Prisma"], "private", link="rift.ddns.net"),
    Project("widgetforge", "WidgetForge", "Moteur de widgets",
            f"Widgets de profil Discord dynamiques{NB}: connecteurs LoL, Steam et Spotify, "
            "scheduler et rendu de visuels animés.",
            ["TypeScript", "Redis"], "private"),
    Project("mimic-reborn", "Mimic Reborn", "Fork modernisé",
            "Le client League sur ton téléphone, du lobby à la sélection des champions. "
            "Connexion directe en LAN, chiffrée de bout en bout.",
            [".NET 9", "React", "TypeScript"], "oss"),
]

GAMES = [
    Game("ascensio", "Ascensio", "Jeu de cartes · Roguelike · 3D",
         "Former des mains de poker sur une grille 5×5 (lignes, colonnes, diagonales) avec un jeu classique "
         "et des atouts de tarot. Inspiré de Balatro et CloverPit, en vue à la première personne.",
         "Gameplay des cartes (drag & drop, main, croupier, tours de jeu), calcul du score et détection "
         "des mains de poker, boutique, sauvegarde.",
         ["Unity 6", "C#", "DOTween"], "Projet d'équipe · 2026", "private",
         "Illustrations : équipe artistique d'Ascensio",
         {"cards": [("ascensio-dos.jpg", -17), ("ascensio-roi.jpg", 17), ("ascensio-monde.jpg", 0)]}),
    Game("turkeyshowdown", "TurkeyShowdown", "Multijoueur en ligne · Arène",
         f"Deathmatch en vue du dessus entre dindons armés{NB}: armes, grappin, objets à ramasser "
         "et plusieurs maps (Arène, Ferme, Verger).",
         "Modes de jeu (deathmatch, équipes), kill feed et classement des scores synchronisés en réseau.",
         ["Unity 6", "C#", "Netcode for GameObjects"], "Projet d'équipe · 2025", "public",
         "Map « Ferme » · art de l'équipe TurkeyShowdown",
         {"image": "turkey-ferme.jpg"}),
]

SMALL_GAMES = [
    ("Super Meat Boy", "Remake · plateforme 2D, 3 niveaux"),
    ("World of Goo", "Remake · structures physiques"),
    ("Zelda-like", "Quêtes, inventaire, sauvegarde"),
    ("Factorio-like", "Convoyeurs, inserteurs, production"),
    ("ShroomWitch Garden", "God game · colonies d'IA, en équipe"),
    ("Tower Defense", "Codé depuis un diagramme UML"),
]


def main():
    OUT.mkdir(exist_ok=True)
    cards = {"banniere.svg": banner(), "arsenal.svg": arsenal(STACK)}
    cards |= {f"titre-{slug}.svg": heading(title) for slug, title in HEADINGS.items()}
    cards |= {f"projet-{p.slug}.svg": project_card(p) for p in PROJECTS}
    cards |= {f"jeu-{g.slug}.svg": game_card(g) for g in GAMES}
    cards["jeux-unity.svg"] = strip("Aussi sur Unity", SMALL_GAMES)
    for name, svg in cards.items():
        (OUT / name).write_text(svg.render(), encoding="utf-8")
        print(f"{name:28} {(OUT / name).stat().st_size / 1024:6.1f} Ko")


if __name__ == "__main__":
    main()
