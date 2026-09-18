#!/usr/bin/env python3
"""
Kifli asszisztens - HTTP API a telefonrol.

    python3 api.py

Egy kicsi, mindig futo szerver, amit a telefonod Parancsok (Shortcuts)
alkalmazasa szolit meg. Siri-vel hasznalhato: "Hey Siri, kifli" - es
bemondod, mi kell.

Nem beszelget: egyetlen kereskor. Amit ismer, azt beteszi es visszamondja
egy mondatban. Amirol donteni kellene, azt NEM teszi be, csak jelzi -
azt otthon, a beszelgetos feluleten intezed el.

Vegpontok (Bearer tokennel):
    POST /api/hozzaad    {"szoveg": "ket liter tej meg egy kenyer"}
    GET  /api/kosar
    GET  /api/egeszseg   (token nelkul, csak eletjel)
"""

import argparse
import json
import math
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ITT = Path(__file__).resolve().parent

Z, PI, S, SZ, HA, F, ALAP = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                             "\033[90m", "\033[1m", "\033[0m")

# A telefonrol jovo kerest egyszerre csak egy szal dolgozza fel:
# az MCP kapcsolat es a kosar allapota kozos.
ZAR = threading.Lock()


def token_beszerez():
    """A .env-bol olvassa, vagy general egyet es beleirja."""
    token = os.environ.get("API_TOKEN")
    if token:
        return token

    token = secrets.token_urlsafe(24)
    env = ITT / ".env"
    with env.open("a", encoding="utf-8") as f:
        f.write(f"\n# A telefonos API tokenje (a Parancsok alkalmazashoz)\n")
        f.write(f"API_TOKEN={token}\n")
    os.environ["API_TOKEN"] = token
    print(f"{S}Uj API token keszult, es bekerult a .env fajlba.{ALAP}")
    return token


def nevelo(szo):
    """Magyar hatarozott nevelo: 'az' maganhangzo elott, kulonben 'a'."""
    elso = (szo or "").lstrip("\"'„”").lower()[:1]
    return "az" if elso in "aáeéiíoóöőuúüű" else "a"


def mondatta(darabok):
    """['ket liter tej', 'egy kenyer'] -> 'ket liter tej es egy kenyer'"""
    darabok = [d for d in darabok if d]
    if not darabok:
        return ""
    if len(darabok) == 1:
        return darabok[0]
    return ", ".join(darabok[:-1]) + " és " + darabok[-1]


class Gyorsfelvetel:
    """Egy kereskor feldolgozasa: szoveg -> kosar -> mondat."""

    def __init__(self, asszisztens, tarolo):
        self.asszisztens = asszisztens
        self.tarolo = tarolo

    def hozzaad(self, szoveg):
        import llm
        import parser as p
        import szinkron

        szoveg = (szoveg or "").strip()
        if not szoveg:
            return {"ok": False, "mondat": "Nem értettem, mit kérsz."}

        try:
            normalizalt = llm.normalizal([szoveg])
        except Exception as e:
            return {"ok": False, "mondat": "Most nem tudom feldolgozni.",
                    "hiba": str(e)}

        betett, kerdeses, hibas = [], [], []

        for norm in normalizalt:
            nyers = norm.get("raw") or szoveg
            if (norm.get("confidence") or 1.0) < 0.5:
                kerdeses.append(nyers)
                continue

            nev = (norm.get("product") or "").lower().strip()
            if not nev:
                kerdeses.append(nyers)
                continue

            ismert = self.tarolo.keres(nev)
            if ismert:
                talalat = {"id": ismert["kifli_id"], "nev": ismert["kifli_nev"],
                           "mennyiseg": ismert["amount_value"],
                           "egyseg": ismert["amount_unit"],
                           "ar": None}
                bulk = bool(ismert["bulk"])
            else:
                # Ismeretlen termek: csak akkor tesszuk be, ha egyertelmu
                talalat, bulk = self._egyertelmu_talalat(nev, norm)
                if talalat is None:
                    kerdeses.append(nev)
                    continue

            db, _, _ = szinkron.darabszam(
                norm.get("quantity"), talalat.get("mennyiseg"),
                talalat.get("egyseg"), bulk)

            eredmeny = self.asszisztens.kosarba_tesz(talalat["id"], nev)
            if eredmeny.get("hiba"):
                hibas.append(nev)
                continue
            betett.append({
                "nev": eredmeny.get("betettem", talalat["nev"]),
                "darab": eredmeny.get("darab", db),
                "ar": eredmeny.get("ar"),
                "kertem": nyers,
            })

        return self._valasz(betett, kerdeses, hibas)

    def _egyertelmu_talalat(self, nev, norm):
        """
        Ismeretlen terméknel csak akkor dontunk magunktol, ha az LLM
        biztos benne. Kulonben inkabb nem teszunk be semmit.
        """
        import arak
        import llm
        import parser as p
        from mcp_kliens import MCPHiba

        try:
            nyers = self.asszisztens.mcp.hiv(
                "search_products", {"product_name": nev, "limit": 15})
        except MCPHiba:
            return None, False

        talalatok = arak.rangsorol(p.termekek_ertelmez(nyers))
        if not talalatok:
            return None, False

        self.asszisztens.utolso_talalatok.extend(talalatok)
        for t in talalatok:
            if t.get("ar"):
                self.asszisztens.arak_szerint[t["id"]] = t["ar"]

        try:
            dontes = llm.termeket_valaszt(norm, talalatok)
        except Exception:
            return None, False

        if (dontes.get("confidence") or 0) < 0.75:
            return None, False
        talalat = next((t for t in talalatok
                        if t["id"] == dontes.get("kifli_id")), None)
        if talalat is None:
            return None, False
        return talalat, p.kimert_e(talalat)

    def _valasz(self, betett, kerdeses, hibas):
        reszek = []
        if betett:
            felsorolas = mondatta([
                (f"{b['darab']} {b['nev']}" if (b["darab"] or 1) > 1
                 else b["nev"]) for b in betett])
            osszeg = sum(b["ar"] or 0 for b in betett)
            reszek.append(
                f"Bement {felsorolas}"
                + (f", összesen {osszeg:.0f} forint." if osszeg else "."))
        if kerdeses:
            felsorolas = mondatta(kerdeses)
            reszek.append(f"{nevelo(kerdeses[0]).capitalize()} {felsorolas} "
                          f"nem egyértelmű, azt majd otthon.")
        if hibas:
            felsorolas = mondatta(hibas)
            reszek.append(f"{nevelo(hibas[0]).capitalize()} {felsorolas} "
                          f"nem került be.")
        if not reszek:
            reszek.append("Nem tettem be semmit.")

        return {"ok": bool(betett), "mondat": " ".join(reszek),
                "betett": betett, "kerdeses": kerdeses, "hibas": hibas}

    def kosar(self):
        eredmeny = self.asszisztens.kosar_megmutat()
        tetelek = eredmeny.get("kosar", [])
        if not tetelek:
            return {"ok": True, "mondat": "A kosarad üres.", "kosar": []}

        felsorolas = mondatta([
            (f"{t['darab']} {t['nev']}" if (t.get("darab") or 1) > 1
             else t["nev"]) for t in tetelek[:8]])
        tovabb = (f" és még {len(tetelek) - 8} tétel"
                  if len(tetelek) > 8 else "")
        osszeg = eredmeny.get("osszeg_ft")
        mondat = (f"A kosaradban {felsorolas}{tovabb}."
                  + (f" Összesen {osszeg} forint." if osszeg else ""))
        if eredmeny.get("rendelheto") is False:
            mondat += " Még nincs meg a minimális rendelési érték."
        return {"ok": True, "mondat": mondat, "kosar": tetelek,
                "osszeg_ft": osszeg}


def kezelo_gyar(gyorsfelvetel, token):
    class Kezelo(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "KifliAPI"

        def log_message(self, formatum, *args):
            print(f"{HA}  {self.address_string()} {formatum % args}{ALAP}")

        def _json(self, kod, adat):
            test = json.dumps(adat, ensure_ascii=False).encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(test)))
            self.end_headers()
            self.wfile.write(test)

        def _jogosult(self):
            fejlec = self.headers.get("Authorization", "")
            kapott = fejlec[7:] if fejlec.startswith("Bearer ") else ""
            if secrets.compare_digest(kapott, token):
                return True
            self._json(401, {"ok": False, "mondat": "Nincs jogosultság."})
            return False

        def do_GET(self):
            ut = self.path.split("?", 1)[0]
            if ut == "/api/egeszseg":
                return self._json(200, {"ok": True, "szolgaltatas": "kifli"})
            if not self._jogosult():
                return
            if ut == "/api/kosar":
                with ZAR:
                    return self._json(200, gyorsfelvetel.kosar())
            self._json(404, {"ok": False, "mondat": "Nincs ilyen végpont."})

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/hozzaad":
                return self._json(404, {"ok": False,
                                        "mondat": "Nincs ilyen végpont."})
            if not self._jogosult():
                return

            hossz = int(self.headers.get("Content-Length") or 0)
            if hossz > 8192:
                return self._json(413, {"ok": False, "mondat": "Túl hosszú."})
            nyers = self.rfile.read(hossz).decode("utf-8", errors="replace")

            try:
                szoveg = json.loads(nyers).get("szoveg", "")
            except json.JSONDecodeError:
                szoveg = nyers.strip()  # sima szoveg is jo

            with ZAR:
                eredmeny = gyorsfelvetel.hozzaad(szoveg)
            print(f"  {Z}{eredmeny['mondat']}{ALAP}")
            self._json(200, eredmeny)

    return Kezelo


def main():
    a = argparse.ArgumentParser(description="Kifli asszisztens - telefonos API.")
    a.add_argument("--port", type=int, default=8477)
    a.add_argument("--cim", default="0.0.0.0",
                   help="melyik cimen figyeljen (alap: minden interfesz)")
    a.add_argument("--proba", action="store_true",
                   help="ne irjon a valodi kosarba")
    a.add_argument("--db", default="kifli.db")
    args = a.parse_args()

    import kifli
    kifli.env_betoltes()
    if not kifli.telepitve_e():
        sys.exit("Meg nincs beallitva. Futtasd: python3 telepites.py")

    import adat
    import asszisztens as asz
    from mcp_kliens import MCPKliens

    token = token_beszerez()

    print(f"\n{F}{SZ}  Kifli API{ALAP}")
    print(f"{HA}  http://{args.cim}:{args.port}"
          f"{'  (proba)' if args.proba else ''}{ALAP}")
    print(f"{HA}  Token: {token}{ALAP}")
    print(f"{HA}  Leallitas: Ctrl+C{ALAP}\n")

    tarolo = adat.Tarolo(args.db)
    with MCPKliens() as mcp:
        asszisztens = asz.Asszisztens(mcp, tarolo, args.proba)
        gyors = Gyorsfelvetel(asszisztens, tarolo)
        kiszolgalo = ThreadingHTTPServer(
            (args.cim, args.port), kezelo_gyar(gyors, token))
        try:
            kiszolgalo.serve_forever()
        except KeyboardInterrupt:
            print(f"\n{HA}Viszlat.{ALAP}")
        finally:
            kiszolgalo.server_close()
    tarolo.close()


if __name__ == "__main__":
    main()
