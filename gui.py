#!/usr/bin/env python3
"""
Kifli asszisztens - grafikus felulet.

    python3 gui.py

Elindit egy helyi webszervert, es megnyitja a bongeszoben. A bongeszo
veszi a mikrofont es jatssza a hangot; a Python oldal vegzi a Kifli
kapcsolatot, a tanulast es az OpenAI realtime hidat.

Miert bongeszo: a WebRTC HARDVERES visszhangtorlest ad. Ettol hangszoron
is hasznalhato, nem csak fejhallgatoval - a terminalos valtozat ezt
szoftveresen kerulte meg.

Az API kulcs a Python oldalon marad, nem kerul ki a bongeszobe.
"""

import argparse
import asyncio
import base64
import json
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ITT = Path(__file__).resolve().parent
WEBUI = ITT / "webui"

Z, PI, S, SZ, HA, F, ALAP = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                             "\033[90m", "\033[1m", "\033[0m")

MINTA_HZ = 24000


def szabad_port(kezdet=8420):
    for port in range(kezdet, kezdet + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return kezdet


class Hid:
    """Egy bongeszo-kapcsolat es a hozza tartozo OpenAI realtime session."""

    def __init__(self, bongeszo_ws, asszisztens, beallitasok):
        self.bongeszo = bongeszo_ws
        self.asszisztens = asszisztens
        self.beallitasok = beallitasok
        self.nyitott = None
        self.allapot = {"valasz_fut": False, "var_uj_valaszra": False,
                        "fuggo_eszkozok": 0}

    async def kuld_ui(self, tipus, **mezok):
        """Esemeny a bongeszonek (JSON)."""
        try:
            await self.bongeszo.send(json.dumps({"type": tipus, **mezok}))
        except Exception:
            pass

    async def valaszt_ker(self):
        if self.allapot["valasz_fut"]:
            self.allapot["var_uj_valaszra"] = True
            return
        self.allapot["var_uj_valaszra"] = False
        self.allapot["valasz_fut"] = True
        await self.nyitott.send(json.dumps({"type": "response.create"}))

    async def eszkoz_hiv(self, esemeny):
        nev = esemeny.get("name")
        try:
            argumentumok = json.loads(esemeny.get("arguments") or "{}")
        except json.JSONDecodeError:
            argumentumok = {}

        await self.kuld_ui("tool_start", name=nev, args=argumentumok)
        self.allapot["fuggo_eszkozok"] += 1
        try:
            # A hivas() sosem dob kivetelt, de a szal maga elszallhat
            try:
                eredmeny = await asyncio.to_thread(
                    self.asszisztens.hivas, nev, argumentumok)
            except Exception as e:
                eredmeny = {"hiba": f"Nem sikerult: {e}"}

            await self.kuld_ui("tool_done", name=nev, result=eredmeny)
            # A valasz MINDIG menjen vissza, kulonben a modell orokre var
            await self.nyitott.send(json.dumps({
                "type": "conversation.item.create",
                "item": {"type": "function_call_output",
                         "call_id": esemeny.get("call_id"),
                         "output": json.dumps({"eredmeny": eredmeny},
                                              ensure_ascii=False)},
            }))
        finally:
            self.allapot["fuggo_eszkozok"] -= 1

        if self.allapot["fuggo_eszkozok"] == 0:
            await self.valaszt_ker()

    async def openai_esemenyek(self):
        async for nyers in self.nyitott:
            e = json.loads(nyers)
            t = e.get("type", "")

            if t == "response.output_audio.delta":
                await self.bongeszo.send(base64.b64decode(e["delta"]))

            elif t == "response.created":
                self.allapot["valasz_fut"] = True
                await self.kuld_ui("allapot", allapot="gondolkodik")

            elif t in ("response.done", "response.cancelled"):
                self.allapot["valasz_fut"] = False
                await self.kuld_ui("allapot", allapot="kesz")
                if (self.allapot["var_uj_valaszra"]
                        and self.allapot["fuggo_eszkozok"] == 0):
                    await self.valaszt_ker()

            elif t == "input_audio_buffer.speech_started":
                await self.kuld_ui("allapot", allapot="hallgat")

            elif t == "input_audio_buffer.speech_stopped":
                await self.kuld_ui("allapot", allapot="gondolkodik")

            elif t == ("conversation.item.input_audio_transcription"
                       ".completed"):
                szoveg = (e.get("transcript") or "").strip()
                if szoveg:
                    await self.kuld_ui("user_text", text=szoveg)

            elif t == "response.output_audio_transcript.delta":
                await self.kuld_ui("ai_delta", text=e.get("delta", ""))

            elif t == "response.output_audio_transcript.done":
                szoveg = (e.get("transcript") or "").strip()
                if szoveg:
                    await self.kuld_ui("ai_text", text=szoveg)

            elif t == "response.function_call_arguments.done":
                asyncio.create_task(self.eszkoz_hiv(e))

            elif t == "error":
                uzenet = e.get("error", {}).get("message", str(e))
                if "active response" in uzenet:
                    self.allapot["valasz_fut"] = True
                    self.allapot["var_uj_valaszra"] = True
                else:
                    await self.kuld_ui("hiba", text=uzenet)

    async def bongeszo_esemenyek(self):
        async for uzenet in self.bongeszo:
            if isinstance(uzenet, bytes):
                await self.nyitott.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(uzenet).decode(),
                }))
                continue

            parancs = json.loads(uzenet)
            tipus = parancs.get("type")

            if tipus == "szoveg":
                await self.nyitott.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {"type": "message", "role": "user",
                             "content": [{"type": "input_text",
                                          "text": parancs.get("text", "")}]},
                }))
                await self.valaszt_ker()

            elif tipus == "kosar_frissit":
                eredmeny = await asyncio.to_thread(
                    self.asszisztens.hivas, "kosar_megmutat", {})
                await self.kuld_ui("tool_done", name="kosar_megmutat",
                                   result=eredmeny)

    async def fut(self):
        import websockets

        modell = self.beallitasok.get("modell", "gpt-realtime")
        url = f"wss://api.openai.com/v1/realtime?model={modell}"
        fejlec = {"Authorization":
                  f"Bearer {os.environ['OPENAI_API_KEY']}"}

        import realtime as rt

        async with websockets.connect(url, additional_headers=fejlec,
                                      max_size=None) as openai_ws:
            self.nyitott = openai_ws
            beall = rt.session_beallitas(
                self.asszisztens,
                self.beallitasok.get("proba", False),
                nem_szakit=False,          # a bongeszo torli a visszhangot
                erzekenyseg=self.beallitasok.get("erzekenyseg", 0.6),
                csend_ms=self.beallitasok.get("csend", 900))
            beall["session"]["audio"]["output"]["voice"] = \
                self.beallitasok.get("hang", "marin")
            await openai_ws.send(json.dumps(beall))

            await self.kuld_ui("kapcsolodva",
                               modell=modell,
                               hang=self.beallitasok.get("hang", "marin"),
                               proba=self.beallitasok.get("proba", False))

            # Indulaskor megmutatjuk, mi van mar a kosarban
            eredmeny = await asyncio.to_thread(
                self.asszisztens.hivas, "kosar_megmutat", {})
            await self.kuld_ui("tool_done", name="kosar_megmutat",
                               result=eredmeny)

            await asyncio.gather(self.openai_esemenyek(),
                                 self.bongeszo_esemenyek())


TIPUSOK = {".html": "text/html; charset=utf-8",
           ".json": "application/json; charset=utf-8",
           ".webmanifest": "application/manifest+json",
           ".js": "text/javascript; charset=utf-8",
           ".css": "text/css; charset=utf-8",
           ".svg": "image/svg+xml",
           ".png": "image/png",
           ".ico": "image/x-icon"}


def statikus_szerver(port, ws_port, cim="127.0.0.1"):
    """
    Egyszeru HTTP szerver a felulet fajljainak, sajat szalon.

    Kulon fut a WebSocket szervertol: a websockets konyvtar HTTP
    kiszolgalasa verzionkent valtozik, ez viszont mindig mukodik.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Kezelo(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass  # ne szemeteljen a konzolra

        def do_GET(self):
            ut = self.path.split("?", 1)[0].split("#", 1)[0]

            if ut == "/beallitas.json":
                # HTTPS mogott (forditott proxy) a WebSocket masik
                # porton vagy masik utvonalon lehet - a .env mondja meg
                beall = {"ws_port": ws_port}
                kulso = os.environ.get("WS_KULSO_PORT")
                if kulso:
                    beall["ws_kulso_port"] = int(kulso)
                utvonal = os.environ.get("WS_UTVONAL")
                if utvonal:
                    beall["ws_utvonal"] = utvonal
                return self._kuld(200, "application/json",
                                  json.dumps(beall).encode())

            if ut in ("/", ""):
                # Telefonon a mobil feluletet adjuk, gepen az asztalit
                ua = (self.headers.get("User-Agent") or "").lower()
                mobil = any(j in ua for j in
                            ("iphone", "ipod", "android", "ipad"))
                ut = "/mobil.html" if mobil else "/index.html"

            fajl = (WEBUI / ut.lstrip("/")).resolve()
            if (not str(fajl).startswith(str(WEBUI.resolve()))
                    or not fajl.is_file()):
                return self._kuld(404, "text/plain; charset=utf-8",
                                  "Nincs ilyen oldal.".encode())
            self._kuld(200, TIPUSOK.get(fajl.suffix,
                                        "application/octet-stream"),
                       fajl.read_bytes())

        def _kuld(self, kod, tipus, test):
            self.send_response(kod)
            self.send_header("Content-Type", tipus)
            self.send_header("Content-Length", str(len(test)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(test)

    kiszolgalo = ThreadingHTTPServer((cim, port), Kezelo)
    szal = threading.Thread(target=kiszolgalo.serve_forever, daemon=True)
    szal.start()
    return kiszolgalo


async def szerver(asszisztens, beallitasok, ws_port,
                  cim="127.0.0.1"):
    import websockets

    async def kezelo(ws):
        try:
            await Hid(ws, asszisztens, beallitasok).fut()
        except Exception as e:
            try:
                await ws.send(json.dumps({"type": "hiba", "text": str(e)}))
            except Exception:
                pass

    async with websockets.serve(kezelo, cim, ws_port, max_size=None):
        await asyncio.Future()


def main():
    a = argparse.ArgumentParser(description="Kifli asszisztens - grafikus.")
    a.add_argument("--proba", action="store_true",
                   help="ne irjon a valodi Kifli kosarba")
    a.add_argument("--port", type=int, help="melyik porton figyeljen")
    a.add_argument("--hang", help="melyik hang")
    a.add_argument("--nyitas-nelkul", action="store_true",
                   help="ne nyissa meg automatikusan a bongeszot")
    a.add_argument("--cim", default="127.0.0.1",
                   help="melyik cimen figyeljen; szerveren/konteneren "
                        "0.0.0.0 kell (alap: csak helyben)")
    a.add_argument("--db", default="kifli.db")
    args = a.parse_args()

    import kifli
    kifli.env_betoltes()
    if not kifli.telepitve_e():
        print(f"{PI}Meg nincs beallitva.{ALAP}")
        print(f"Futtasd eloszor: {SZ}python3 telepites.py{ALAP}")
        sys.exit(1)

    try:
        import websockets  # noqa: F401
    except ImportError:
        print(f"{PI}Hianyzik a websockets csomag.{ALAP}")
        print(f"  pip install websockets")
        sys.exit(1)

    import adat
    import asszisztens as asz
    from mcp_kliens import MCPKliens

    port = args.port or szabad_port()
    ws_port = szabad_port(port + 1)
    cim = f"http://127.0.0.1:{port}"
    beallitasok = {
        "proba": args.proba,
        "hang": args.hang or os.environ.get("OPENAI_REALTIME_VOICE", "marin"),
        "modell": os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime"),
        "erzekenyseg": float(os.environ.get("VAD_KUSZOB", "0.6")),
        "csend": int(os.environ.get("VAD_CSEND_MS", "900")),
    }

    tarolo = adat.Tarolo(args.db)
    print(f"\n{F}{SZ}  Kifli asszisztens{ALAP}")
    if args.cim not in ("127.0.0.1", "localhost"):
        print(f"{HA}  {args.cim}:{port} (minden interfeszen)"
              f"{'  (proba)' if args.proba else ''}{ALAP}")
        print(f"{S}  Figyelem: a mikrofon csak HTTPS-en vagy localhoston "
              f"mukodik.{ALAP}")
    else:
        print(f"{HA}  {cim}{'  (proba)' if args.proba else ''}{ALAP}")
    print(f"\n{HA}  Telefonrol (HTTPS kell a mikrofonhoz):{ALAP}")
    print(f"    {SZ}tailscale serve --bg {port}{ALAP}")
    print(f"    {SZ}tailscale serve --bg --set-path=/ws {ws_port}{ALAP}")
    print(f"{HA}  Mindketto kell - a masodik a hangkapcsolat.{ALAP}")
    print(f"\n{HA}  Leallitas: Ctrl+C{ALAP}\n")

    with MCPKliens() as mcp:
        asszisztens = asz.Asszisztens(mcp, tarolo, args.proba)
        kiszolgalo = statikus_szerver(port, ws_port, args.cim)
        if not args.nyitas_nelkul:
            threading.Timer(1.0, lambda: webbrowser.open(cim)).start()
        try:
            asyncio.run(szerver(asszisztens, beallitasok, ws_port,
                                args.cim))
        except KeyboardInterrupt:
            print(f"{HA}Viszlat.{ALAP}")
        finally:
            kiszolgalo.shutdown()

    tarolo.close()


if __name__ == "__main__":
    main()
