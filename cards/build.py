"""Génère les cartes SVG du README dans assets/.

Usage : python cards/build.py   (dépendance : pip install fonttools)

GitHub affiche les SVG du README comme des <img> : ils ne peuvent charger ni
police ni image externe. Tout est donc intégré en base64, et les polices sont
réduites aux seuls caractères utilisés par chaque carte.
"""
import base64
import io
import math
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets"

GOLD = "#D4AF37"
GOLD_SOFT = "#B8994A"
INK = "#E4DACB"
MUTED = "#9C9086"
BG = "#0C0909"
WINE = "#670C0C"


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


SERIF = Font("Cinzel", "Cinzel-SemiBold.ttf", 600, "Georgia, serif")
SANS = Font("Manrope", "Manrope-Regular.ttf", 400, "'Segoe UI', Arial, sans-serif")
SANS_SB = Font("Manrope", "Manrope-SemiBold.ttf", 600, "'Segoe UI', Arial, sans-serif")


class Svg:
    def __init__(self, w, h, title, desc):
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.defs, self.body = [], []
        self.used = {}

    def add(self, markup):
        self.body.append(markup)

    def text(self, x, y, s, font, size, fill, spacing=0, anchor="start", opacity=None):
        self.used.setdefault(font, set()).update(s)
        attrs = (f'x="{x:g}" y="{y:g}" font-family="{font.css}" font-weight="{font.weight}" '
                 f'font-size="{size:g}" fill="{fill}"')
        if spacing:
            attrs += f' letter-spacing="{spacing:g}"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if opacity is not None:
            attrs += f' fill-opacity="{opacity:g}"'
        self.add(f"<text {attrs}>{escape(s)}</text>")

    def render(self):
        faces = "".join(font.face(chars) for font, chars in self.used.items())
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="title desc">'
                f'<title id="title">{escape(self.title)}</title><desc id="desc">{escape(self.desc)}</desc>'
                f"<defs><style>{faces}</style>{''.join(self.defs)}</defs>{''.join(self.body)}</svg>")


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


def frame(svg):
    w, h = svg.w, svg.h
    svg.defs.append(
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#170D0D"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        f'<radialGradient id="glow" cx="1" cy="0" r="1">'
        f'<stop offset="0" stop-color="{WINE}" stop-opacity=".5"/>'
        f'<stop offset="1" stop-color="{WINE}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#F7E2A0"/><stop offset=".55" stop-color="{GOLD}"/>'
        f'<stop offset="1" stop-color="#A47E22"/></linearGradient>'
        f'<clipPath id="card"><rect width="{w}" height="{h}" rx="14"/></clipPath>'
    )
    svg.add(f'<rect width="{w}" height="{h}" rx="14" fill="url(#bg)"/>')
    svg.add(f'<rect width="{w}" height="{h}" rx="14" fill="url(#glow)"/>')


def border(svg):
    # Tracée en dernier pour passer au-dessus des visuels.
    w, h, i, n = svg.w, svg.h, 9, 16
    svg.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="13.5" fill="none" '
            f'stroke="{GOLD}" stroke-opacity=".3"/>')
    corners = (f"M{i} {i + n}V{i}H{i + n}M{w - i - n} {i}H{w - i}V{i + n}"
               f"M{w - i} {h - i - n}V{h - i}H{w - i - n}M{i + n} {h - i}H{i}V{h - i - n}")
    svg.add(f'<path d="{corners}" fill="none" stroke="{GOLD}" stroke-opacity=".7" stroke-width="1.2"/>')


def pills(svg, x, y, labels, size=11, h=22, gap=6, pad=10):
    for label in labels:
        w = SANS_SB.width(label, size) + 2 * pad
        svg.add(f'<rect x="{x:g}" y="{y:g}" width="{w:.1f}" height="{h}" rx="{h / 2:g}" fill="{GOLD}" '
                f'fill-opacity=".07" stroke="{GOLD}" stroke-opacity=".35"/>')
        svg.text(x + w / 2, y + h / 2 + size * 0.36, label, SANS_SB, size, "#E9DCB0", anchor="middle")
        x += w + gap
    return x - gap


STATUS = {
    "private": ("CODE PRIVÉ", "#FFFFFF", ".18", "0", MUTED),
    "public": ("DÉPÔT PUBLIC", GOLD, ".5", ".08", GOLD),
    "oss": ("OPEN SOURCE", GOLD, ".5", ".08", GOLD),
}


def status(svg, right, y, kind):
    label, stroke, stroke_op, fill_op, color = STATUS[kind]
    size, spacing, pad, h = 9.5, 1.4, 10, 20
    w = SANS_SB.width(label, size, spacing) + 2 * pad - spacing
    x = right - w
    svg.add(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="{h / 2:g}" fill="{GOLD}" '
            f'fill-opacity="{fill_op}" stroke="{stroke}" stroke-opacity="{stroke_op}"/>')
    svg.text(x + pad, y + h / 2 + size * 0.36, label, SANS_SB, size, color, spacing=spacing)
    return x


def check(what, end, limit):
    if end > limit:
        raise ValueError(f"{what} déborde ({end:.0f} > {limit:.0f})")


# Icônes au trait, dans une boîte de 24 x 24.
ICONS = {
    "voice": "M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4",
    "chart": "M3 19l5-6 4 3 8-10M3 21h18M16 6h4v4",
    "widgets": "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    "phone": "M7 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM10 18h2"
             "M20 8a5 5 0 0 1 0 6M22.5 5.5a9 9 0 0 1 0 11",
}


@dataclass
class Project:
    slug: str
    name: str
    label: str
    desc: str
    tags: list
    icon: str
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
    svg.add(f'<rect x="{pad}" y="{pad}" width="46" height="46" rx="10" fill="{WINE}" fill-opacity=".35" '
            f'stroke="{GOLD}" stroke-opacity=".4"/>')
    svg.add(f'<path transform="translate(35 35)" d="{ICONS[p.icon]}" fill="none" stroke="{GOLD}" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
    status_x = status(svg, svg.w - pad, pad, p.status)
    label = p.label.upper()
    check(f"{p.name} : catégorie", 84 + SANS_SB.width(label, 10, 2), status_x - 10)
    svg.text(84, 40, label, SANS_SB, 10, GOLD_SOFT, spacing=2)
    check(f"{p.name} : titre", 83 + SERIF.width(p.name, 24), status_x - 10)
    svg.text(83, 67, p.name, SERIF, 24, "url(#gold)")
    lines = wrap(p.desc, SANS, 13.5, svg.w - 2 * pad)
    check(f"{p.name} : description (lignes)", len(lines), 3)
    for i, line in enumerate(lines):
        svg.text(pad, 104 + i * 20, line, SANS, 13.5, INK, opacity=0.88)
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


def fan(svg, art, cx):
    # Éventail de trois cartes pivotant autour d'un point situé sous la main.
    w, h, pivot_y, lift = 120, 206, 350, 110
    svg.defs.append(
        f'<radialGradient id="panel" cx=".5" cy=".5" r=".55">'
        f'<stop offset="0" stop-color="{WINE}" stop-opacity=".8"/>'
        f'<stop offset="1" stop-color="{WINE}" stop-opacity="0"/></radialGradient>'
        f'<filter id="shadow" x="-40%" y="-40%" width="180%" height="180%">'
        f'<feDropShadow dx="0" dy="8" stdDeviation="9" flood-color="#000" flood-opacity=".7"/></filter>'
        f'<clipPath id="tarot"><rect x="{-w / 2:g}" y="{-(h + lift)}" width="{w}" height="{h}" rx="7"/></clipPath>'
    )
    svg.add(f'<rect width="{cx * 2}" height="{svg.h}" fill="url(#panel)"/>')
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
        f'<stop offset=".6" stop-color="{BG}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{BG}" stop-opacity=".85"/></linearGradient>'
    )
    svg.add(f'<g clip-path="url(#card)"><g mask="url(#fademask)">'
            f'<image href="{image_uri(art["image"])}" width="{width}" height="{svg.h}" '
            f'preserveAspectRatio="xMidYMid slice"/>'
            f'<rect width="{width}" height="{svg.h}" fill="{BG}" fill-opacity=".18"/>'
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
    label = g.label.upper()
    check(f"{g.name} : catégorie", x + SANS_SB.width(label, 10.5, 2.4), status_x - 12)
    svg.text(x, 52, label, SANS_SB, 10.5, GOLD_SOFT, spacing=2.4)
    svg.text(x - 1, 94, g.name, SERIF, 34, "url(#gold)")

    y = 128
    lines = wrap(g.desc, SANS, 14.5, right - x)
    check(f"{g.name} : description (lignes)", len(lines), 3)
    for line in lines:
        svg.text(x, y, line, SANS, 14.5, INK, opacity=0.9)
        y += 21
    y += 10
    svg.text(x, y, "MON RÔLE", SANS_SB, 9.5, GOLD_SOFT, spacing=2)
    y += 18
    lines = wrap(g.role, SANS, 13, right - x)
    check(f"{g.name} : rôle (lignes)", len(lines), 2)
    for line in lines:
        svg.text(x, y, line, SANS, 13, INK, opacity=0.75)
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
    label = title.upper()
    svg.text(pad, 42, label, SANS_SB, 10.5, GOLD_SOFT, spacing=2.4)
    line_x = pad + SANS_SB.width(label, 10.5, 2.4) + 14
    svg.add(f'<path d="M{line_x:.1f} 38.5H{svg.w - pad}" stroke="{GOLD}" stroke-opacity=".25"/>')
    chip_w = (svg.w - 2 * pad - (cols - 1) * gap) / cols
    for i, (name, sub) in enumerate(items):
        cx = pad + (i % cols) * (chip_w + gap)
        cy = 62 + (i // cols) * (chip_h + 12)
        svg.add(f'<rect x="{cx:.1f}" y="{cy}" width="{chip_w:.1f}" height="{chip_h}" rx="9" fill="#FFFFFF" '
                f'fill-opacity=".025" stroke="{GOLD}" stroke-opacity=".2"/>')
        check(f"{name} : nom", SERIF.width(name, 15), chip_w - 32)
        check(f"{name} : sous-titre", SANS.width(sub, 12), chip_w - 32)
        svg.text(cx + 16, cy + 22, name, SERIF, 15, "url(#gold)")
        svg.text(cx + 16, cy + 39, sub, SANS, 12, MUTED)
    border(svg)
    return svg


NB = " "  # espace insécable avant les deux-points

def banner():
    svg = Svg(860, 250, "Terrenoss",
              "Développeur full-stack et game dev, en France. Apps desktop et web pour les joueurs de "
              "League of Legends, et jeux vidéo sous Unity, seul ou en équipe. "
              "Stack : C#, .NET, Unity, TypeScript, Next.js, Electron.")
    frame(svg)
    cx, cy = 712, 125
    ticks = 2 * math.pi * 88 / 72  # 72 graduations pile sur la circonférence, sans raccord visible
    svg.defs.append(
        f'<radialGradient id="halo"><stop offset="0" stop-color="{WINE}" stop-opacity=".75"/>'
        f'<stop offset="1" stop-color="{WINE}" stop-opacity="0"/></radialGradient>'
        "<style>.spin{transform-box:fill-box;transform-origin:center;animation:spin 90s linear infinite}"
        "@keyframes spin{to{transform:rotate(360deg)}}"
        "@media (prefers-reduced-motion:reduce){.spin{animation:none}}</style>"
    )

    # Emblème : halo, anneau gradué qui tourne, étoile à huit branches, monogramme.
    d, s = 68, 48
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="122" fill="url(#halo)"/>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="97" fill="none" stroke="{GOLD}" stroke-opacity=".22"/>')
    svg.add(f'<circle class="spin" cx="{cx}" cy="{cy}" r="88" fill="none" stroke="{GOLD}" stroke-opacity=".6" '
            f'stroke-width="5" stroke-dasharray="1.4 {ticks - 1.4:.3f}"/>')
    svg.add(f'<path d="M{cx} {cy - d}L{cx + d} {cy}L{cx} {cy + d}L{cx - d} {cy}Z'
            f'M{cx - s} {cy - s}H{cx + s}V{cy + s}H{cx - s}Z" fill="none" stroke="{GOLD}" '
            f'stroke-opacity=".45" stroke-linejoin="round"/>')
    svg.add(f'<circle cx="{cx}" cy="{cy}" r="40" fill="{WINE}" fill-opacity=".45" stroke="{GOLD}" '
            f'stroke-opacity=".6"/>')
    svg.text(cx, cy + 16, "T", SERIF, 46, "url(#gold)", anchor="middle")

    x, limit = 44, cx - 110
    eyebrow = "DÉVELOPPEUR FULL-STACK · GAME DEV · FRANCE"
    check("bannière : sur-titre", x + SANS_SB.width(eyebrow, 11, 2.6), limit)
    svg.text(x, 64, eyebrow, SANS_SB, 11, GOLD_SOFT, spacing=2.6)
    check("bannière : nom", x + SERIF.width("Terrenoss", 60), limit)
    svg.text(x - 2, 122, "Terrenoss", SERIF, 60, "url(#gold)")
    for i, line in enumerate(["Apps desktop & web pour les joueurs de League of Legends,",
                              "et jeux vidéo sous Unity, seul ou en équipe."]):
        check("bannière : accroche", x + SANS.width(line, 15.5), limit)
        svg.text(x, 156 + i * 22, line, SANS, 15.5, INK, opacity=0.9)
    check("bannière : stack", pills(svg, x, 198, ["C#", ".NET", "Unity", "TypeScript", "Next.js", "Electron"]),
          limit)
    border(svg)
    return svg


PROJECTS = [
    Project("porotalk", "PoroTalk", "App desktop",
            f"Chat vocal éphémère pour League of Legends{NB}: connexion automatique avec tes coéquipiers, "
            "en WebRTC P2P, sans lien à partager.",
            ["Electron", "TypeScript", "WebRTC"], "voice", "private"),
    Project("cashback", "CashBack", "Bot Discord + site web",
            f"Paris en fausse monnaie sur les games de tes amis, et Rift, un site de stats façon op.gg. "
            "Monorepo avec worker Riot et app desktop Tauri.",
            ["TypeScript", "Next.js", "Prisma"], "chart", "private", link="rift.ddns.net"),
    Project("widgetforge", "WidgetForge", "Moteur de widgets",
            f"Widgets de profil Discord dynamiques{NB}: connecteurs LoL, Steam et Spotify, "
            "scheduler et rendu de visuels animés.",
            ["TypeScript", "Redis"], "widgets", "private"),
    Project("mimic-reborn", "Mimic Reborn", "Fork modernisé",
            "Le client League sur ton téléphone, du lobby à la sélection des champions. "
            "Connexion directe en LAN, chiffrée de bout en bout.",
            [".NET 9", "React", "TypeScript"], "phone", "oss"),
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
    cards = {f"projet-{p.slug}.svg": project_card(p) for p in PROJECTS}
    cards |= {f"jeu-{g.slug}.svg": game_card(g) for g in GAMES}
    cards["jeux-unity.svg"] = strip("Aussi sur Unity", SMALL_GAMES)
    cards["banniere.svg"] = banner()
    for name, svg in cards.items():
        (OUT / name).write_text(svg.render(), encoding="utf-8")
        print(f"{name:28} {(OUT / name).stat().st_size / 1024:6.1f} Ko")


if __name__ == "__main__":
    main()
