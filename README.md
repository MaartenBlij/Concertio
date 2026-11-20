# 🎸 Concertio

Concertio is een persoonlijk concertarchief dat je draait in je **eigen lokale netwerk**. Leg per concert vast wanneer het was, waar het was, welke artiesten speelden, met wie je er was, wat je ervan vond — en upload foto's en video's om er later op terug te kijken.

Alles draait lokaal: geen cloud, geen account, geen externe diensten. De app gebruikt alleen de Python-standaardbibliotheek, dus er hoeft niets geïnstalleerd te worden.

## Wat kun je vastleggen?

- **Datum, venue en plaats** van het concert
- **Artiesten**: headliner + support acts
- **Met wie** je er was geweest
- **Notities**: setlist, hoogtepunten, anekdotes
- **Beoordeling** (1–5 sterren)
- **Foto's en video's** (meerdere tegelijk uploaden)
- Overzicht met statistieken (aantal concerten, artiesten, locaties, media) en zoekfunctie

## Snel starten

### Met Docker Compose (aanbevolen)

```bash
docker compose up -d
```

Open daarna [http://localhost:8080](http://localhost:8080).

### Zonder Docker

Vereist: Python 3.10+ (geen extra packages nodig).

```bash
python3 app.py
```

Open daarna [http://localhost:8080](http://localhost:8080).

## Bereikbaar maken in je lokale netwerk

De server luistert standaard op `0.0.0.0:8080`, dus elk apparaat in je netwerk kan erbij via het IP-adres van de computer waar Concertio draait, bijvoorbeeld:

```
http://192.168.1.25:8080
```

Vind het IP-adres met `ip addr` (Linux), `ipconfig` (Windows) of `ifconfig` (macOS).

Handig: zet Concertio op een vaste machine (bijv. een Raspberry Pi of NAS) en maak in de browser van je telefoon een bladwijzer naar dat adres.

## Instellingen (omgevingsvariabelen)

| Variabele | Standaard | Beschrijving |
|---|---|---|
| `HOST` | `0.0.0.0` | Adres waarop de server luistert |
| `PORT` | `8080` | Poort |
| `CONCERTIO_DATA` | `./data` | Map voor database + media |
| `CONCERTIO_GEBRUIKER` | *(leeg)* | Zet samen met wachtwoord een login op de app (HTTP Basic Auth) |
| `CONCERTIO_WACHTWOORD` | *(leeg)* | Wachtwoord voor de login |

Voorbeeld met login:

```bash
CONCERTIO_GEBRUIKER=maarten CONCERTIO_WACHTWOORD=geheim python3 app.py
```

## Back-up

Alle gegevens staan in de map `data/` (SQLite-database `concertio.db` + map `media/` met je foto's en video's). Kopieer die map regelmatig naar een veilige plek — bij Docker is dat de volume `./data`.

## Projectstructuur

```
app.py                  Entrypoint
concertio/
  web.py                HTTP-server, routing, upload, media-streaming
  db.py                 SQLite-opslaglaag
  views.py              HTML-weergave (Nederlands)
  templates/            HTML-sjablonen
  static/               CSS en favicon
data/                   Database + media (lokaal, niet in git)
tests/smoke_test.py     End-to-end test tegen een draaiende server
```

## Testen

```bash
python3 tests/smoke_test.py
```

De test start tijdelijk een server op poort 8765 met een tijdelijke datamap en doorloopt aanmaken, bewerken, uploaden, streamen en verwijderen.
