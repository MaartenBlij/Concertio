"""SQLite-opslaglaag voor Concertio."""

import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CONCERTIO_DATA", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "concertio.db"
MEDIA_DIR = DATA_DIR / "media"

SCHEMA = """
CREATE TABLE IF NOT EXISTS concerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL DEFAULT '',
    datum TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT '',
    plaats TEXT NOT NULL DEFAULT '',
    met_wie TEXT NOT NULL DEFAULT '',
    notities TEXT NOT NULL DEFAULT '',
    beoordeling INTEGER,
    aangemaakt_op TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS bands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concert_id INTEGER NOT NULL REFERENCES concerts(id) ON DELETE CASCADE,
    naam TEXT NOT NULL,
    headliner INTEGER NOT NULL DEFAULT 0,
    volgorde INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concert_id INTEGER NOT NULL REFERENCES concerts(id) ON DELETE CASCADE,
    bestandsnaam TEXT NOT NULL,
    originele_naam TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT 'application/octet-stream',
    soort TEXT NOT NULL DEFAULT 'bestand',
    geupload_op TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bands_concert ON bands(concert_id);
CREATE INDEX IF NOT EXISTS idx_media_concert ON media(concert_id);
"""


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(SCHEMA)


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _valideer(velden):
    datum = (velden.get("datum") or "").strip()
    try:
        datetime.strptime(datum, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Kies een geldige datum (jjjj-mm-dd).")
    beoordeling_raw = (velden.get("beoordeling") or "").strip()
    beoordeling = None
    if beoordeling_raw:
        try:
            beoordeling = int(beoordeling_raw)
            if not 1 <= beoordeling <= 5:
                raise ValueError
        except ValueError:
            raise ValueError("De beoordeling moet een getal van 1 t/m 5 zijn.")
    return {
        "titel": (velden.get("titel") or "").strip(),
        "datum": datum,
        "venue": (velden.get("venue") or "").strip(),
        "plaats": (velden.get("plaats") or "").strip(),
        "met_wie": (velden.get("met_wie") or "").strip(),
        "notities": (velden.get("notities") or "").strip(),
        "beoordeling": beoordeling,
        "headliner": (velden.get("headliner") or "").strip(),
        "bands": [ln.strip() for ln in (velden.get("bands") or "").splitlines() if ln.strip()],
    }


def _sla_bands_op(con, concert_id, headliner, band_namen):
    con.execute("DELETE FROM bands WHERE concert_id = ?", (concert_id,))
    volgorde = 0
    if headliner:
        con.execute(
            "INSERT INTO bands (concert_id, naam, headliner, volgorde) VALUES (?, ?, 1, ?)",
            (concert_id, headliner, volgorde),
        )
        volgorde += 1
    for naam in band_namen:
        con.execute(
            "INSERT INTO bands (concert_id, naam, headliner, volgorde) VALUES (?, ?, 0, ?)",
            (concert_id, naam, volgorde),
        )
        volgorde += 1


def maak_concert(velden):
    v = _valideer(velden)
    with connect() as con:
        cur = con.execute(
            "INSERT INTO concerts (titel, datum, venue, plaats, met_wie, notities, beoordeling)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (v["titel"], v["datum"], v["venue"], v["plaats"], v["met_wie"], v["notities"], v["beoordeling"]),
        )
        concert_id = cur.lastrowid
        _sla_bands_op(con, concert_id, v["headliner"], v["bands"])
    return concert_id


def werk_concert_bij(concert_id, velden):
    v = _valideer(velden)
    with connect() as con:
        cur = con.execute(
            "UPDATE concerts SET titel = ?, datum = ?, venue = ?, plaats = ?, met_wie = ?,"
            " notities = ?, beoordeling = ? WHERE id = ?",
            (v["titel"], v["datum"], v["venue"], v["plaats"], v["met_wie"], v["notities"], v["beoordeling"], concert_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Concert niet gevonden.")
        _sla_bands_op(con, concert_id, v["headliner"], v["bands"])


def concert_bestaat(concert_id):
    with connect() as con:
        return con.execute("SELECT 1 FROM concerts WHERE id = ?", (concert_id,)).fetchone() is not None


def get_concert(concert_id):
    with connect() as con:
        row = con.execute("SELECT * FROM concerts WHERE id = ?", (concert_id,)).fetchone()
        if row is None:
            return None
        concert = dict(row)
        concert["bands"] = [
            dict(b)
            for b in con.execute(
                "SELECT * FROM bands WHERE concert_id = ? ORDER BY headliner DESC, volgorde, id",
                (concert_id,),
            )
        ]
        concert["media"] = [
            dict(m)
            for m in con.execute(
                "SELECT * FROM media WHERE concert_id = ? ORDER BY id", (concert_id,)
            )
        ]
    return concert


def lijst_concerten(zoekterm=""):
    where = ""
    params = []
    if zoekterm:
        like = f"%{zoekterm}%"
        where = (
            "WHERE c.titel LIKE ? OR c.venue LIKE ? OR c.plaats LIKE ? OR c.met_wie LIKE ?"
            " OR c.notities LIKE ? OR EXISTS (SELECT 1 FROM bands b WHERE b.concert_id = c.id AND b.naam LIKE ?)"
        )
        params = [like] * 6
    with connect() as con:
        rows = con.execute(
            "SELECT c.id, c.titel, c.datum, c.venue, c.plaats, c.met_wie, c.beoordeling,"
            " (SELECT COUNT(*) FROM media m WHERE m.concert_id = c.id) AS media_aantal,"
            " (SELECT COUNT(*) FROM media m WHERE m.concert_id = c.id AND m.soort = 'foto') AS foto_aantal,"
            " (SELECT COUNT(*) FROM media m WHERE m.concert_id = c.id AND m.soort = 'video') AS video_aantal,"
            " (SELECT m2.id FROM media m2 WHERE m2.concert_id = c.id AND m2.soort = 'foto'"
            "  ORDER BY m2.id LIMIT 1) AS cover_id"
            " FROM concerts c " + where + " ORDER BY c.datum DESC, c.id DESC",
            params,
        ).fetchall()
        concerten = [dict(r) for r in rows]
        band_rows = con.execute(
            "SELECT concert_id, naam, headliner FROM bands ORDER BY headliner DESC, volgorde, id"
        ).fetchall()
    per_concert = {}
    for b in band_rows:
        per_concert.setdefault(b["concert_id"], []).append(dict(b))
    for c in concerten:
        c["bands"] = per_concert.get(c["id"], [])
    return concerten


def statistieken():
    with connect() as con:
        def tel(sql, params=()):
            return con.execute(sql, params).fetchone()[0]
        return {
            "concerten": tel("SELECT COUNT(*) FROM concerts"),
            "bands": tel("SELECT COUNT(DISTINCT naam) FROM bands"),
            "venues": tel("SELECT COUNT(DISTINCT venue) FROM concerts WHERE venue != ''"),
            "fotos": tel("SELECT COUNT(*) FROM media WHERE soort = 'foto'"),
            "videos": tel("SELECT COUNT(*) FROM media WHERE soort = 'video'"),
        }


def _media_soort(mime):
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("image/"):
        return "foto"
    return "bestand"


def _veilige_naam(naam):
    naam = os.path.basename(naam.replace("\\", "/"))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", naam) or "bestand"


def media_pad(bestandsnaam):
    return MEDIA_DIR / bestandsnaam


def voeg_media_toe(concert_id, originele_naam, mime, data):
    bestandsnaam = f"{uuid.uuid4().hex}_{_veilige_naam(originele_naam)}"
    pad = media_pad(bestandsnaam)
    pad.write_bytes(data)
    with connect() as con:
        cur = con.execute(
            "INSERT INTO media (concert_id, bestandsnaam, originele_naam, mime, soort) VALUES (?, ?, ?, ?, ?)",
            (concert_id, bestandsnaam, originele_naam, mime or "application/octet-stream", _media_soort(mime or "")),
        )
        return cur.lastrowid


def get_media(media_id):
    with connect() as con:
        row = con.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return dict(row) if row else None


def verwijder_media(media_id):
    with connect() as con:
        row = con.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        if row is None:
            return None
        con.execute("DELETE FROM media WHERE id = ?", (media_id,))
        concert_id = row["concert_id"]
    pad = media_pad(row["bestandsnaam"])
    if pad.exists():
        pad.unlink()
    return concert_id


def verwijder_concert(concert_id):
    with connect() as con:
        rows = con.execute("SELECT bestandsnaam FROM media WHERE concert_id = ?", (concert_id,)).fetchall()
        con.execute("DELETE FROM concerts WHERE id = ?", (concert_id,))
    for row in rows:
        pad = media_pad(row["bestandsnaam"])
        if pad.exists():
            pad.unlink()
