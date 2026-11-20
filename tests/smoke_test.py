#!/usr/bin/env python3
"""End-to-end smoketest: start een server op 127.0.0.1:8765 en doorloop de belangrijkste flows."""

import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
)


def request(method, path, data=None, headers=None, follow=False):
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler() if follow else _NoRedirect())
    try:
        with opener.open(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def form(data):
    from urllib.parse import urlencode
    return urlencode(data).encode(), {"Content-Type": "application/x-www-form-urlencoded"}


def multipart(veld, bestandsnaam, mime, data):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{veld}"; filename="{bestandsnaam}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def check(naam, conditie):
    if not conditie:
        raise AssertionError(f"FAAL: {naam}")
    print(f"  ok - {naam}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, HOST="127.0.0.1", PORT="8765", CONCERTIO_DATA=tmp)
        proc = subprocess.Popen([sys.executable, str(ROOT / "app.py")], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for _ in range(50):
                try:
                    status, body, _ = request("GET", "/")
                    if status == 200:
                        break
                except Exception:
                    time.sleep(0.2)
            else:
                raise AssertionError("Server startte niet binnen 10 seconden")

            print("Smoketest Concertio")
            status, body, _ = request("GET", "/")
            check("overzicht laadt", status == 200 and "Concertio" in body.decode())

            status, body, _ = request("GET", "/static/style.css")
            check("static css", status == 200 and b"--accent" in body)

            data, headers = form({
                "titel": "Rock Werchter dag 1", "datum": "2025-07-04", "venue": "Werchter",
                "plaats": "Werchter", "met_wie": "Sanne, Peter", "headliner": "Metallica",
                "bands": "Ghost\nAirbourne", "notities": "Geweldige dag!\nSetlist top.",
                "beoordeling": "5",
            })
            status, _, headers = request("POST", "/concerten", data=data, headers=headers)
            check("concert aangemaakt (303)", status == 303)
            locatie = headers.get("Location", "")
            check("redirect naar detail", locatie == "/concerten/1")

            status, body, _ = request("GET", "/concerten/1")
            tekst = body.decode()
            check("detail toont gegevens", status == 200 and "Metallica" in tekst and "Sanne, Peter" in tekst
                  and "★" in tekst and "vr 4 jul 2025" in tekst)

            status, body, _ = request("GET", "/?q=metallica")
            check("zoekfunctie vindt concert", status == 200 and "Rock Werchter" in body.decode())
            status, body, _ = request("GET", "/?q=onzinxyz")
            check("zoekfunctie zonder hit", status == 200 and "Nog geen concerten" in body.decode())

            body_m, headers_m = multipart("bestanden", "foto.png", "image/png", PNG)
            status, _, headers = request("POST", "/concerten/1/media", data=body_m, headers=headers_m)
            check("foto upload (303)", status == 303)

            body_v, headers_v = multipart("bestanden", "clip.mp4", "video/mp4", b"ftyp" + b"\0" * 100)
            status, _, _ = request("POST", "/concerten/1/media", data=body_v, headers=headers_v)
            check("video upload (303)", status == 303)

            status, body, _ = request("GET", "/media/1/bestand")
            check("foto wordt gestreamd", status == 200 and body == PNG)
            status, body, hdrs = request("GET", "/media/2/bestand", headers={"Range": "bytes=0-3"})
            check("range request video (206)", status == 206 and body == b"ftyp"
                  and hdrs.get("Content-Range") == "bytes 0-3/104")

            status, body, _ = request("GET", "/concerten/1")
            check("media Verschijnt in galerij", status == 200 and "/media/1/bestand" in body.decode()
                  and "/media/2/bestand" in body.decode())
            status, body, _ = request("GET", "/")
            check("coverfoto op kaart", status == 200 and "/media/1/bestand" in body.decode())

            data, headers = form({
                "titel": "Rock Werchter dag 1 (aangepast)", "datum": "2025-07-05", "venue": "Werchter",
                "plaats": "Werchter", "met_wie": "Sanne", "headliner": "Metallica",
                "bands": "Ghost", "notities": "Aangepast.", "oordeling": "4",
            })
            status, _, headers = request("POST", "/concerten/1/" + "bewer" + "ken", data=data, headers=headers)
            check("concert bewerken (303)", status == 303)
            status, body, _ = request("GET", "/concerten/1")
            check("wijziging zichtbaar", "aangepast" in body.decode() and "za 5 jul 2025" in body.decode()
                  and "Airbourne" not in body.decode())

            data, headers = form({"datum": "31-12-2025"})
            status, body, _ = request("POST", "/concerten", data=data, headers=headers)
            check("ongeldige datum geweigerd (400)", status == 400 and "datum" in body.decode().lower())

            status, _, headers = request("POST", "/media/2/verwijder", data=b"", headers={"Content-Type": "application/x-www-form-urlencoded"})
            check("media verwijderen (303)", status == 303 and headers.get("Location", "").endswith("#media"))
            status, _, _ = request("GET", "/media/2/bestand")
            check("verwijderde media is 404", status == 404)

            status, _, _ = request("POST", "/concerten/1/verwijder", data=b"", headers={"Content-Type": "application/x-www-form-urlencoded"})
            check("concert verwijderen (303)", status == 303)
            status, _, _ = request("GET", "/concerten/1")
            check("verwijderd concert is 404", status == 404)
            media_map = Path(tmp) / "media"
            check("media-bestanden opgeruimd", not any(media_map.iterdir()))

            status, _, _ = request("GET", "/bestaat-niet")
            check("onbekende pagina is 404", status == 404)

            print("Alle checks geslaagd.")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
