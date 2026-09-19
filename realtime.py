#!/usr/bin/env python3
"""
Realtime Kifli asszisztens - valodi beszed-beszed, nincs gombnyomas.

    python3 realtime.py
    python3 realtime.py --szaraz      # nem ir a valodi kosarba
    python3 realtime.py --hang marin  # masik hang

A kulonbseg a hangos.py-hoz kepest: ott a hang -> szoveg -> LLM ->
szoveg -> hang lancolat futott, kozte Enterrel. Itt a modell KOZVETLENUL
hallgat es beszel, ezert termeszetes a hangja, es kozbe is lehet vagni.

Fuggosegek:
    brew install portaudio
    pip3 install sounddevice numpy websockets

Az eszkozok, a tanulas es a Kifli kapcsolat valtozatlan - ugyanaz az
Asszisztens osztaly fut, mint eddig.
"""

import argparse
import asyncio
import base64
import json
import os
import queue
import sys
import threading

import adat
import asszisztens as asz
from mcp_kliens import MCPKliens

Z, PI, S, SZ, HA, ALAP = ("\033[92m", "\033[91m", "\033[93m",
                          "\033[96m", "\033[90m", "\033[0m")

MODELL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime")
HANG = os.environ.get("OPENAI_REALTIME_VOICE", "marin")
MINTA_HZ = 24000

# Egy eszkozhivas soha nem foghatja meg a beszelgetest
ESZKOZ_IDOKORLAT = 100.0   # masodperc
KERET = 480  # 20 ms

HANG_KIEGESZITES = """

HANGOS BESZELGETES - EZ ELHANGZIK, NEM IRAS
Most valodi hangon beszelgetsz, nem szoveget irsz. Ezert:

- Beszelj ugy, ahogy egy ember beszel: kotetlenul, elo ritmussal.
  Hasznalj atvezeteseket - "akkor", "meg", "es mar csak", "kesz is".
- Az angol markaneveket az eredeti nyelvuk szerint ejtsd: az Old Spice
  "old szpajsz", a Hellmann's "helmensz", a Heinz "hajnc", a Kitchin
  "kicsin", a Finish "finis". A magyar neveket magyarosan.
- A forintosszegeket mondd ki szavakkal.
- SOHA ne olvass fel hosszu talalati listat. Ket-harom lehetoseg a
  maximum, amit egyszerre mondasz.
- Ha a felhasznalo kozbevag, allj le es hallgasd meg.
- Ha egy eszkoz sokaig fut, mondj kozben valamit: "egy pillanat,
  megnezem" - ne hallgass nemaan.
"""


class HangIO:
    """
    Mikrofon es hangszoro, sounddevice-szal.

    A 'nem_szakit' modban a mikrofont NEM kuldjuk tovabb, amig a modell
    beszel. Igy fizikailag nem tudja visszahallani sajat magat, es nem
    szakitja meg magat. Cserebe kozbevagni sem lehet.
    """

    def __init__(self, nem_szakit=False):
        import numpy as np
        import sounddevice as sd
        self.np = np
        self.sd = sd
        self.be = queue.Queue()
        self.ki = queue.Queue()
        self.bemeno = None
        self.kimeno = None
        self.nem_szakit = nem_szakit
        self.modell_beszel = threading.Event()

    def indit(self):
        def be_visszahivas(adat_be, keretek, ido, allapot):
            # Amig a modell beszel, eldobjuk a mikrofon adatait, hogy
            # ne hallja vissza sajat magat a hangszorobol
            if self.nem_szakit and self.modell_beszel.is_set():
                return
            self.be.put(bytes(adat_be))

        def ki_visszahivas(adat_ki, keretek, ido, allapot):
            szukseges = keretek * 2  # int16 mono
            puffer = b""
            while len(puffer) < szukseges:
                try:
                    puffer += self.ki.get_nowait()
                except queue.Empty:
                    break
            if not puffer:
                # Nincs mit jatszani: a modell elhallgatott
                self.modell_beszel.clear()
            if len(puffer) < szukseges:
                puffer += b"\x00" * (szukseges - len(puffer))
            elif len(puffer) > szukseges:
                self.ki.queue.appendleft(puffer[szukseges:])
                puffer = puffer[:szukseges]
            adat_ki[:] = self.np.frombuffer(
                puffer, dtype="int16").reshape(-1, 1)

        self.bemeno = self.sd.InputStream(
            samplerate=MINTA_HZ, channels=1, dtype="int16",
            blocksize=KERET, callback=be_visszahivas)
        self.kimeno = self.sd.OutputStream(
            samplerate=MINTA_HZ, channels=1, dtype="int16",
            blocksize=KERET, callback=ki_visszahivas)
        self.bemeno.start()
        self.kimeno.start()

    def hangot_ad(self, darab):
        self.modell_beszel.set()
        self.ki.put(darab)

    def leallit(self):
        for folyam in (self.bemeno, self.kimeno):
            if folyam:
                folyam.stop()
                folyam.close()

    def urit_kimenet(self):
        """Kozbevagaskor eldobjuk a meg le nem jatszott hangot."""
        with self.ki.mutex:
            self.ki.queue.clear()
        self.modell_beszel.clear()


def session_beallitas(asszisztens, szaraz, nem_szakit=False,
                      erzekenyseg=0.6, csend_ms=900):
    eszkozok = [{
        "type": "function",
        "name": e["name"],
        "description": e["description"],
        "parameters": e["parameters"],
    } for e in asz.ESZKOZOK]

    utasitas = asz.RENDSZERPROMPT + HANG_KIEGESZITES
    if szaraz:
        utasitas += ("\n\nFIGYELEM: SZARAZ FUTAS. A termekek NEM kerulnek "
                     "be a valodi kosarba, ez csak proba. Ha a felhasznalo "
                     "rakerdez, mondd meg neki.")

    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "instructions": utasitas,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": MINTA_HZ},
                    "transcription": {"model": "whisper-1", "language": "hu"},
                    "turn_detection": {
                        "type": "server_vad",
                        # magasabb kuszob = kevesbe erzekeny, kevesebb
                        # teves megszakitas hattérzajra vagy visszhangra
                        "threshold": erzekenyseg,
                        "prefix_padding_ms": 300,
                        # ennyi csend utan dönti el, hogy befejezted
                        "silence_duration_ms": csend_ms,
                        "create_response": True,
                        "interrupt_response": not nem_szakit,
                    },
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": MINTA_HZ},
                    "voice": HANG,
                },
            },
            "tools": eszkozok,
            "tool_choice": "auto",
        },
    }


async def fut(asszisztens, szaraz, nem_szakit, erzekenyseg, csend_ms):
    try:
        import websockets
    except ImportError:
        sys.exit("Hianyzik a websockets csomag:\n"
                 "  pip3 install websockets sounddevice numpy")

    kulcs = os.environ.get("OPENAI_API_KEY")
    if not kulcs:
        sys.exit("Hianyzik az OPENAI_API_KEY.")

    args_nem_szakit = nem_szakit
    try:
        hangio = HangIO(nem_szakit=nem_szakit)
    except Exception as e:
        sys.exit(f"Hangeszkoz hiba: {e}\n"
                 "  brew install portaudio && pip3 install sounddevice numpy")

    url = f"wss://api.openai.com/v1/realtime?model={MODELL}"
    fejlecek = {"Authorization": f"Bearer {kulcs}"}

    async with websockets.connect(url, additional_headers=fejlecek,
                                  max_size=None) as ws:
        await ws.send(json.dumps(session_beallitas(
            asszisztens, szaraz, nem_szakit, erzekenyseg, csend_ms)))
        hangio.indit()
        print(f"{Z}Kapcsolodva. Beszelj - nem kell gombot nyomni.{ALAP}")
        print(f"{HA}Kilepes: Ctrl+C{ALAP}\n")

        # A szerver egyszerre csak EGY valaszt tud generalni. Ha tobb
        # eszkozt hivott egyszerre (pl. het termek keresese), akkor az
        # eredmenyeket be kell gyujteni, es CSAK A VEGEN kerni egy uj
        # valaszt - kulonben "active response in progress" hibat kapunk.
        allapot = {"valasz_fut": False, "var_uj_valaszra": False,
                   "fuggo_eszkozok": 0}

        async def valaszt_ker():
            """Uj valasz keres, ha nincs epp folyamatban."""
            if allapot["valasz_fut"]:
                allapot["var_uj_valaszra"] = True
                return
            allapot["var_uj_valaszra"] = False
            allapot["valasz_fut"] = True
            await ws.send(json.dumps({"type": "response.create"}))

        async def mikrofon():
            """A mikrofon adatait folyamatosan kuldi."""
            while True:
                try:
                    darab = hangio.be.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.005)
                    continue
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(darab).decode(),
                }))

        async def esemenyek():
            async for nyers in ws:
                esemeny = json.loads(nyers)
                tipus = esemeny.get("type", "")

                if tipus == "response.output_audio.delta":
                    hangio.hangot_ad(base64.b64decode(esemeny["delta"]))

                elif tipus == "input_audio_buffer.speech_started":
                    # Kozbevagas: dobjuk el a meg le nem jatszott valaszt.
                    # nem_szakit modban ez nem is fordulhat elo, mert a
                    # mikrofon nemitva van, amig a modell beszel.
                    if not args_nem_szakit:
                        hangio.urit_kimenet()

                elif tipus == ("conversation.item.input_audio_transcription"
                               ".completed"):
                    szoveg = (esemeny.get("transcript") or "").strip()
                    if szoveg:
                        print(f"{Z}Te: {szoveg}{ALAP}")

                elif tipus == "response.output_audio_transcript.done":
                    szoveg = (esemeny.get("transcript") or "").strip()
                    if szoveg:
                        print(f"{SZ}{szoveg}{ALAP}\n")

                elif tipus == "response.created":
                    allapot["valasz_fut"] = True

                elif tipus in ("response.done", "response.cancelled"):
                    allapot["valasz_fut"] = False
                    # Ha kozben eszkozeredmenyek erkeztek, most kerunk
                    # ra uj valaszt - de csak ha mar nincs fuggo eszkoz
                    if (allapot["var_uj_valaszra"]
                            and allapot["fuggo_eszkozok"] == 0):
                        await valaszt_ker()

                elif tipus == "response.function_call_arguments.done":
                    asyncio.create_task(eszkoz_hiv(esemeny))

                elif tipus == "error":
                    hiba = esemeny.get("error", {})
                    uzenet = hiba.get("message", str(esemeny))
                    # Az "active response" hibat mar kezeljuk, ne ijesszuk
                    # meg vele a felhasznalot
                    if "active response" in uzenet:
                        allapot["valasz_fut"] = True
                        allapot["var_uj_valaszra"] = True
                    else:
                        print(f"{PI}Hiba: {uzenet}{ALAP}")

        async def eszkoz_hiv(esemeny):
            nev = esemeny.get("name")
            try:
                argumentumok = json.loads(esemeny.get("arguments") or "{}")
            except json.JSONDecodeError:
                argumentumok = {}

            allapot["fuggo_eszkozok"] += 1
            try:
                # Az eszkozok halozatot hivnak, ezert kulon szalon futnak,
                # hogy ne blokkoljak a hangfolyamot
                try:
                    eredmeny = await asyncio.wait_for(
                        asyncio.to_thread(
                            asszisztens.hivas, nev, argumentumok),
                        timeout=ESZKOZ_IDOKORLAT)
                except asyncio.TimeoutError:
                    eredmeny = {"hiba": (f"A(z) {nev} tul sokaig tartott. "
                                         f"A Kifli valoszinuleg lassit.")}
                except Exception as e:
                    eredmeny = {"hiba": f"Nem sikerult: {e}"}

                # A valasz MINDIG menjen vissza, kulonben a modell orokre var
                await ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": esemeny.get("call_id"),
                        "output": json.dumps({"eredmeny": eredmeny},
                                             ensure_ascii=False),
                    },
                }))
            finally:
                allapot["fuggo_eszkozok"] -= 1

            # Csak akkor kerunk uj valaszt, ha mar MINDEN eszkoz vegzett
            if allapot["fuggo_eszkozok"] == 0:
                await valaszt_ker()

        try:
            await asyncio.gather(mikrofon(), esemenyek())
        finally:
            hangio.leallit()


def main():
    a = argparse.ArgumentParser(description="Realtime Kifli asszisztens.")
    a.add_argument("--szaraz", action="store_true",
                   help="ne irjon a valodi Kifli kosarba")
    a.add_argument("--hang", help="melyik hang (alap: marin)")
    a.add_argument("--modell", help="realtime modell")
    a.add_argument("--szakithato", action="store_true",
                   help="lehessen kozbevagni (visszhangot okozhat "
                        "hangszoron)")
    a.add_argument("--erzekenyseg", type=float, default=0.75,
                   help="0.0-1.0; magasabb = kevesbe kapkodos (alap: 0.75)")
    a.add_argument("--csend", type=int, default=1100,
                   help="ennyi ezredmasodperc csend utan valaszol "
                        "(alap: 1100)")
    a.add_argument("--db", default="kifli.db")
    args = a.parse_args()

    global HANG, MODELL
    if args.hang:
        HANG = args.hang
    if args.modell:
        MODELL = args.modell

    tarolo = adat.Tarolo(args.db)
    print(f"{SZ}Kifli asszisztens - realtime.{ALAP}")
    print(f"{HA}Modell: {MODELL} / {HANG}"
          f"{'  [szaraz]' if args.szaraz else ''}"
          f"{'  [kozbevaghato]' if args.szakithato else '  [nem szakithato]'}"
          f"  erzekenyseg={args.erzekenyseg}{ALAP}")

    with MCPKliens() as mcp:
        asszisztens = asz.Asszisztens(mcp, tarolo, args.szaraz)
        try:
            asyncio.run(fut(asszisztens, args.szaraz,
                            nem_szakit=not args.szakithato,
                            erzekenyseg=args.erzekenyseg,
                            csend_ms=args.csend))
        except KeyboardInterrupt:
            print(f"\n{HA}Viszlat.{ALAP}")

    tarolo.close()


if __name__ == "__main__":
    main()
