"""HTML-weergave voor Concertio (Nederlandstalig)."""

from datetime import datetime
from html import escape
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def _render(template, **ctx):
    html = (TEMPLATES_DIR / template).read_text("utf-8")
    for key, value in ctx.items():
        html = html.replace("{{ " + key + " }}", value).replace("{{" + key + "}}", value)
    return html


def _base(titel, inhoud, zoekwaarde=""):
    return _render("base.html", titel=escape(titel), inhoud=inhoud, zoekwaarde=escape(zoekwaarde))


def fmt_datum(datum):
    try:
        d = datetime.strptime(datum, "%Y-%m-%d")
        return f"{DAGEN[d.weekday()]} {d.day} {MAANDEN[d.month - 1]} {d.year}"
    except ValueError:
        return datum


def _sterren(beoordeling):
    if not beoordeling:
        return ""
    return f'<span class="sterren" title="Beoordeling {int(beoordeling)}/5">{"★" * int(beoordeling)}</span>'


def _kaart(c):
    cid = c["id"]
    titel = c["titel"] or (c["bands"][0]["naam"] if c["bands"] else "Concert zonder titel")
    bands = ", ".join(b["naam"] for b in c["bands"])
    if c["cover_id"]:
        afbeelding = f'<img loading="lazy" src="/media/{c["cover_id"]}/bestand" alt="">'
    else:
        afbeelding = '<div class="geen-afbeelding">🎵</div>'
    venue = ", ".join(p for p in [c["venue"], c["plaats"]] if p)
    meta = []
    if c["foto_aantal"]:
        meta.append(f"🖼 {c['foto_aantal']}")
    if c["video_aantal"]:
        meta.append(f"🎬 {c['video_aantal']}")
    sterren = _sterren(c.get("beoordeling"))
    if sterren and meta:
        meta.insert(0, sterren)
    elif sterren:
        meta.append(sterren)
    return f"""
    <a class="kaart" href="/concerten/{cid}">
      <div class="kaart-afbeelding">{afbeelding}</div>
      <div class="kaart-inhoud">
        <div class="kaart-datum">{escape(fmt_datum(c["datum"]))}</div>
        <h2>{escape(titel)}</h2>
        {f'<div class="kaart-venue">📍 {escape(venue)}</div>' if venue else ""}
        {f'<div class="kaart-bands">{escape(bands)}</div>' if bands else ""}
        {f'<div class="kaart-meta">{" · ".join(meta)}</div>' if meta else ""}
      </div>
    </a>"""


def index_pagina(concerten, stats, q):
    kaarten = "\n".join(_kaart(c) for c in concerten)
    if not kaarten:
        kaarten = '<p class="leeg">Nog geen concerten vastgelegd. <a href="/concerten/nieuw">Leg je eerste concert vast!</a></p>'
    inhoud = _render(
        "index.html",
        totaal_concerten=str(stats["concerten"]),
        totaal_bands=str(stats["bands"]),
        totaal_venues=str(stats["venues"]),
        totaal_fotos=str(stats["fotos"]),
        totaal_videos=str(stats["videos"]),
        concert_kaarten=kaarten,
    )
    return _base("Overzicht", inhoud, q)


def _media_item(m):
    mid = m["id"]
    if m["soort"] == "video":
        media = f'<video controls preload="metadata" src="/media/{mid}/bestand"></video>'
    elif m["soort"] == "foto":
        media = f'<img loading="lazy" src="/media/{mid}/bestand" alt="{escape(m["originele_naam"])}">'
    else:
        media = '<div class="geen-afbeelding">📎</div>'
    return f"""
    <figure class="media-item">
      <a href="/media/{mid}/bestand" target="_blank">{media}</a>
      <figcaption>
        <span class="naam">{escape(m["originele_naam"] or m["bestandsnaam"])}</span>
        <form method="post" action="/media/{mid}/verwijder" onsubmit="return confirm('Dit bestand verwijderen?');">
          <button class="verwijder" type="submit" title="Verwijderen">✕</button>
        </form>
      </figcaption>
    </figure>"""


def detail_pagina(c):
    cid = c["id"]
    headliner = next((b["naam"] for b in c["bands"] if b["headliner"]), None)
    titel = c["titel"] or headliner or "Concert zonder titel"
    band_items = "".join(
        f'<li>{"<strong>★ " + escape(b["naam"]) + "</strong> (headliner)" if b["headliner"] else escape(b["naam"])}</li>'
        for b in c["bands"]
    ) or '<li class="leeg-lijst">Geen artiesten eingetragen.</li>'
    venue = ", ".join(p for p in [c["venue"], c["plaats"]] if p)
    met_wie = f'<span class="badge">👥 met {escape(c["met_wie"])}</span>' if c["met_wie"] else ""
    notities = escape(c["notities"]).replace("\n", "<br>") if c["notities"] else '<em class="leeg-lijst">Nog geen notities.</em>'
    media_items = "\n".join(_media_item(m) for m in c["media"])
    if not media_items:
        media_items = '<p class="leeg-lijst">Nog geen foto\'s of video\'s. Upload ze hieronder.</p>'
    inhoud = _render(
        "detail.html",
        id=str(cid),
        titel=escape(titel),
        datum_lang=escape(fmt_datum(c["datum"])),
        venue=escape(venue),
        met_wie_badge=met_wie,
        sterren=_sterren(c["beoordeling"]),
        band_items=band_items,
        notities=notities,
        media_items=media_items,
    )
    return _base(titel, inhoud)


def formulier_pagina(concert):
    nieuw = concert is None
    cid = str(concert["id"]) if concert else ""
    headliner = next((b["naam"] for b in concert["bands"] if b["headliner"]), "") if concert else ""
    bands = "\n".join(b["naam"] for b in concert["bands"] if not b["headliner"]) if concert else ""
    g = concert or {}
    beoordeling = g.get("beoordeling") or ""
    opties = ['<option value="">–</option>']
    for n in range(1, 6):
        sel = " selected" if str(beoordeling) == str(n) else ""
        opties.append(f'<option value="{n}"{sel}>{"★" * n} ({n}/5)</option>')
    actie = "/concerten" if nieuw else "/concerten/" + cid + "/bewerken"
    terug = f"/concerten/{cid}" if not nieuw else "/"
    inhoud = _render(
        "formulier.html",
        titel_pagina="Nieuw concert" if nieuw else "Concert bewerken",
        actie=actie,
        titel=escape(g.get("titel") or ""),
        datum=escape(g.get("datum") or ""),
        venue=escape(g.get("venue") or ""),
        plaats=escape(g.get("plaats") or ""),
        met_wie=escape(g.get("met_wie") or ""),
        headliner=escape(headliner),
        beoordeling_opties="".join(opties),
        bands=escape(bands),
        notities=escape(g.get("notities") or ""),
        terug=terug,
    )
    return _base("Nieuw concert" if nieuw else "Concert bewerken", inhoud)


def fout_pagina(melding, titel="Er ging iets mis"):
    inhoud = (
        f'<h1>{escape(titel)}</h1>'
        f'<p class="fout">{escape(melding)}</p>'
        '<p><a class="knop" href="/">Terug naar het overzicht</a></p>'
    )
    return _base(titel, inhoud)
