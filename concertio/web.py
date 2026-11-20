"""HTTP-server en routing voor Concertio (alleen Python-standaardbibliotheek)."""

import base64
import hmac
import os
import re
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import db, views

MAX_BODY = 2 * 1024 * 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


class ConcertioHandler(BaseHTTPRequestHandler):
    server_version = "Concertio/1.0"

    def do_GET(self):
        if not self._auth_ok():
            return
        try:
            self._dispatch("GET")
        except BrokenPipeError:
            pass
        except Exception as exc:
            self._html(views.fout_pagina(str(exc)), 500)

    def do_POST(self):
        if not self._auth_ok():
            return
        try:
            self._dispatch("POST")
        except BrokenPipeError:
            pass
        except ValueError as exc:
            self._html(views.fout_pagina(str(exc)), 400)
        except Exception as exc:
            self._html(views.fout_pagina(str(exc)), 500)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if method == "GET":
            if path == "/":
                return self._index(query.get("q", [""])[0].strip())
            m = re.fullmatch(r"/static/([\w.\-]+)", path)
            if m:
                return self._static(m.group(1))
            if path == "/concerten/nieuw":
                return self._formulier()
            m = re.fullmatch(r"/concerten/(\d+)", path)
            if m:
                return self._detail(int(m.group(1)))
            m = re.fullmatch(r"/concerten/(\d+)/bewerken", path)
            if m:
                return self._formulier(int(m.group(1)))
            m = re.fullmatch(r"/media/(\d+)/bestand", path)
            if m:
                return self._media_bestand(int(m.group(1)))
        else:
            if re.fullmatch(r"/concerten", path):
                return self._maak_concert()
            m = re.fullmatch(r"/concerten/(\d+)/bewerken", path)
            if m:
                return self._werk_bij(int(m.group(1)))
            m = re.fullmatch(r"/concerten/(\d+)/verwijder", path)
            if m:
                return self._verwijder_concert(int(m.group(1)))
            m = re.fullmatch(r"/concerten/(\d+)/media", path)
            if m:
                return self._upload_media(int(m.group(1)))
            m = re.fullmatch(r"/media/(\d+)/verwijder", path)
            if m:
                return self._verwijder_media(int(m.group(1)))
        self._html(views.fout_pagina("Pagina niet gevonden: " + path, "404 niet gevonden"), 404)

    def _auth_ok(self):
        gebruiker = os.environ.get("CONCERTIO_GEBRUIKER")
        wachtwoord = os.environ.get("CONCERTIO_WACHTWOORD")
        if not gebruiker or not wachtwoord:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                u, _, p = decoded.partition(":")
                if hmac.compare_digest(u, gebruiker) and hmac.compare_digest(p, wachtwoord):
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Concertio"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1 style='font-family:sans-serif'>Inloggen vereist</h1>".encode("utf-8"))
        return False

    def _html(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, locatie):
        self.send_response(303)
        self.send_header("Location", locatie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _lees_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Aanvraag is te groot (max 2 GB).")
        data = b""
        while len(data) < length:
            chunk = self.rfile.read(min(65536, length - len(data)))
            if not chunk:
                break
            data += chunk
        return data

    def _lees_formulier(self):
        ctype = self.headers.get("Content-Type", "")
        body = self._lees_body()
        if ctype.startswith("multipart/form-data"):
            msg = BytesParser(policy=email_policy).parsebytes(
                b"Content-Type: " + ctype.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
            )
            velden = {}
            bestanden = []
            for part in msg.iter_parts():
                naam = part.get_param("name", header="content-disposition")
                if naam is None:
                    continue
                payload = part.get_payload(decode=True) or b""
                bestandsnaam = part.get_filename()
                if bestandsnaam:
                    bestanden.append(
                        {
                            "veld": naam,
                            "bestandsnaam": bestandsnaam,
                            "mime": part.get_content_type(),
                            "data": payload,
                        }
                    )
                else:
                    velden.setdefault(naam, []).append(payload.decode("utf-8", "replace"))
            return {k: (v[0] if len(v) == 1 else v) for k, v in velden.items()}, bestanden
        params = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        return {k: (v[0] if len(v) == 1 else v) for k, v in params.items()}, []

    def _index(self, q):
        concerten = db.lijst_concerten(q)
        stats = db.statistieken()
        self._html(views.index_pagina(concerten, stats, q))

    def _detail(self, concert_id):
        concert = db.get_concert(concert_id)
        if concert is None:
            return self._html(views.fout_pagina("Concert niet gevonden.", "404 niet gevonden"), 404)
        self._html(views.detail_pagina(concert))

    def _formulier(self, concert_id=None):
        concert = db.get_concert(concert_id) if concert_id is not None else None
        if concert_id is not None and concert is None:
            return self._html(views.fout_pagina("Concert niet gevonden.", "404 niet gevonden"), 404)
        self._html(views.formulier_pagina(concert))

    def _maak_concert(self):
        velden, _ = self._lees_formulier()
        concert_id = db.maak_concert(velden)
        self._redirect(f"/concerten/{concert_id}")

    def _werk_bij(self, concert_id):
        velden, _ = self._lees_formulier()
        db.werk_concert_bij(concert_id, velden)
        self._redirect(f"/concerten/{concert_id}")

    def _verwijder_concert(self, concert_id):
        db.verwijder_concert(concert_id)
        self._redirect("/")

    def _upload_media(self, concert_id):
        if not db.concert_bestaat(concert_id):
            return self._html(views.fout_pagina("Concert niet gevonden.", "404 niet gevonden"), 404)
        _, bestanden = self._lees_formulier()
        for f in bestanden:
            if f["veld"] == "bestanden" and f["bestandsnaam"] and f["data"]:
                db.voeg_media_toe(concert_id, f["bestandsnaam"], f["mime"], f["data"])
        self._redirect(f"/concerten/{concert_id}#media")

    def _verwijder_media(self, media_id):
        concert_id = db.verwijder_media(media_id)
        if concert_id is None:
            return self._html(views.fout_pagina("Media niet gevonden.", "404 niet gevonden"), 404)
        self._redirect(f"/concerten/{concert_id}#media")

    def _media_bestand(self, media_id):
        item = db.get_media(media_id)
        if item is None:
            return self._html(views.fout_pagina("Media niet gevonden.", "404 niet gevonden"), 404)
        pad = db.media_pad(item["bestandsnaam"])
        if not pad.is_file():
            return self._html(views.fout_pagina("Bestand ontbreekt op schijf.", "404 niet gevonden"), 404)
        size = pad.stat().st_size
        mime = item["mime"] or "application/octet-stream"
        naam = item["originele_naam"] or item["bestandsnaam"]

        start, end, status = 0, max(size - 1, 0), 200
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                spec = range_header[6:].split(",")[0]
                s, _, e = spec.partition("-")
                start = int(s) if s else 0
                end = int(e) if e else size - 1
                end = min(end, size - 1)
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            except ValueError:
                start, end, status = 0, max(size - 1, 0), 200

        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(naam)}")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with pad.open("rb") as fh:
            fh.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = fh.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _static(self, naam):
        pad = (STATIC_DIR / naam).resolve()
        if pad.parent != STATIC_DIR or not pad.is_file():
            return self._html(views.fout_pagina("Statisch bestand niet gevonden.", "404 niet gevonden"), 404)
        data = pad.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES.get(pad.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def run():
    db.init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), ConcertioHandler)
    print(f"Concertio draait op http://{host}:{port}")
    print("Druk op Ctrl+C om te stoppen.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
