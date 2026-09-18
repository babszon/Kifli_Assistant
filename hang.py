#!/usr/bin/env python3
"""
Hangreteg: mikrofon -> Whisper -> asszisztens -> OpenAI TTS -> hangszoro.

Fuggosegek (egyszer kell telepiteni):
    brew install ffmpeg sox
    pip3 install sounddevice numpy   # vagy hasznaljuk a sox-ot

A felvetel ket modon mehet:
  1. sounddevice (Python) - pontosabb, de telepitest igenyel
  2. sox 'rec' parancs   - egyszerubb, ha a sounddevice nem megy

Onteszt:
    python3 hang.py --teszt      # felvesz 5 masodpercet, leirja, felolvassa
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HA, SZ, Z, PI, ALAP = "\033[90m", "\033[96m", "\033[92m", "\033[91m", "\033[0m"

STT_MODELL = os.environ.get("OPENAI_STT_MODEL", "whisper-1")
TTS_MODELL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
TTS_HANG = os.environ.get("OPENAI_TTS_VOICE", "nova")

# A Whisper hajlamos a markaneveket foneikusan leirni. Ez a szoveg
# elore megadja neki a varhato szavakat - jelentosen javit a pontossagon.
WHISPER_SUGO = (
    "Bevásárlólista magyarul. Gyakori szavak: Kifli, ketchup, majonéz, "
    "olívaolaj, öblítő, mosószer, mosogatógép tabletta, dezodor, trappista, "
    "tejföl, túró, kefir, párizsi, virsli, felvágott, deka, dekagramm, kiló, "
    "liter, doboz, üveg, zacskó, csomag, tábla, fej saláta, gerezd fokhagyma. "
    "Márkák: Old Spice, Nivea, Hellmann's, Univer, Globus, Heinz, Finish, "
    "Somat, Silan, Lenor, Persil, Ariel, Monini, Mizo, Pick, Coca-Cola."
)


TTS_UTASITAS = os.environ.get("OPENAI_TTS_INSTRUCTIONS") or (
    "Magyar anyanyelvu asszisztens vagy, aki egy ismerosevel beszelget a "
    "konyhaban, menet kozben. NEM felolvasol - beszelsz.\n\n"
    "HANGVETEL:\n"
    "Kozvetlen, meleg, nyugodt. Olyan valaki, aki segit, de nem "
    "szolgalatkeszkedik. Magabiztos, de nem szaraz.\n\n"
    "RITMUS - EZ TESZI ELOVE:\n"
    "- Ne egyenletes tempoban mondd a mondatot. Ahol egy ember "
    "  levegot venne vagy gondolkodna, ott legyen egy pici szunet.\n"
    "- A mondat vegen ne ess le mereven. A kerdesek vegen emelkedj, "
    "  a kozlesek vegen lagyan zarj.\n"
    "- A fontos reszt - a terméknevet es az arat - hangsulyozd ki "
    "  egy kicsit, mint aki azt akarja, hogy a masik megjegyezze.\n"
    "- A kotoszavakat ('akkor', 'meg', 'es mar csak') mondd "
    "  konnyeden, gyorsabban, ahogy beszedben szoktuk.\n"
    "- Beszelj kicsit gyorsabban a szokasos felolvasasnal, ahogy "
    "  elo beszedben szoktunk.\n\n"
    "KIEJTES - EZ NAGYON FONTOS:\n"
    "A magyar szavakat magyar kiejtessel mondd. Az angol markaneveket "
    "es idegen szavakat viszont az EREDETI nyelvuk szerint ejtsd, ahogy "
    "egy muvelt magyar ember tenne beszed kozben:\n"
    "- 'Old Spice' = 'old szpajsz', nem 'old szpice'\n"
    "- \"Hellmann's\" = 'helmensz'\n"
    "- 'Heinz' = 'hajnc'\n"
    "- 'Finish' = 'finis'\n"
    "- 'Coca-Cola' = 'koka-kola'\n"
    "- 'Kitchin' = 'kicsin'\n"
    "- 'Silan' = magyarosan 'szilan'\n"
    "A magyar termeknevek (trappista, tejfol, vekni, melyalmos) "
    "maradnak teljesen magyarosak.\n\n"
    "SZAMOK:\n"
    "A forintosszegeket mondd ki szavakkal, magyarul, ahogy beszedben "
    "szoktuk: '2249 forint' = 'kettoezer-ketszaznegyvenkilenc forint'. "
    "A '0.75 l' = 'het es fel deci'. A '500 g' = 'fel kilo'."
)


class HangHiba(Exception):
    pass


# --------------------------------------------------------------- felvetel

def _van(parancs):
    return shutil.which(parancs) is not None


def felvetel_sox(utvonal, max_masodperc=30):
    """Felvetel a sox 'rec' paranccsal, Enterre all le."""
    if not _van("rec"):
        raise HangHiba("Nincs 'rec' parancs. Telepitsd: brew install sox")

    proc = subprocess.Popen(
        ["rec", "-q", "-c", "1", "-r", "16000", str(utvonal),
         "trim", "0", str(max_masodperc)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    return utvonal


def felvetel_sounddevice(utvonal, max_masodperc=30):
    """Felvetel a sounddevice csomaggal, Enterre all le."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        raise HangHiba("Nincs sounddevice. Telepitsd: "
                       "pip3 install sounddevice numpy")

    import queue
    import threading
    import wave

    minta_hz = 16000
    darabok = queue.Queue()
    fut = threading.Event()
    fut.set()

    def visszahivas(adat, keretek, ido, allapot):
        if fut.is_set():
            darabok.put(adat.copy())

    with sd.InputStream(samplerate=minta_hz, channels=1, dtype="int16",
                        callback=visszahivas):
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        fut.clear()

    keretek = []
    while not darabok.empty():
        keretek.append(darabok.get())
    if not keretek:
        raise HangHiba("Nem vettem fel semmit.")

    hang = np.concatenate(keretek)
    with wave.open(str(utvonal), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(minta_hz)
        f.writeframes(hang.tobytes())
    return utvonal


def felvetel(utvonal, max_masodperc=30):
    """A rendelkezesre allo modszerrel vesz fel."""
    try:
        return felvetel_sounddevice(utvonal, max_masodperc)
    except Exception:
        # sounddevice hianyzik vagy a PortAudio nincs telepitve
        return felvetel_sox(utvonal, max_masodperc)


# -------------------------------------------------------- beszedfelismeres

def _multipart(mezok, fajl_mezo, fajl_ut, fajl_tipus):
    """Egyszeru multipart/form-data osszeallitas, fuggoseg nelkul."""
    hatar = f"----kifli{uuid.uuid4().hex}"
    darabok = []
    for kulcs, ertek in mezok.items():
        darabok.append(
            f"--{hatar}\r\n"
            f'Content-Disposition: form-data; name="{kulcs}"\r\n\r\n'
            f"{ertek}\r\n".encode("utf-8"))
    nev = Path(fajl_ut).name
    darabok.append(
        f"--{hatar}\r\n"
        f'Content-Disposition: form-data; name="{fajl_mezo}"; '
        f'filename="{nev}"\r\n'
        f"Content-Type: {fajl_tipus}\r\n\r\n".encode("utf-8"))
    darabok.append(Path(fajl_ut).read_bytes())
    darabok.append(f"\r\n--{hatar}--\r\n".encode("utf-8"))
    return b"".join(darabok), f"multipart/form-data; boundary={hatar}"


def felismer(hang_ut, nyelv="hu"):
    """Hangfajl -> magyar szoveg, OpenAI Whisper API-val."""
    kulcs = os.environ.get("OPENAI_API_KEY")
    if not kulcs:
        raise HangHiba("Hianyzik az OPENAI_API_KEY.")

    test, tipus = _multipart(
        {"model": STT_MODELL, "language": nyelv, "prompt": WHISPER_SUGO,
         "temperature": "0"},
        "file", hang_ut, "audio/wav")

    keres = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=test,
        headers={"Authorization": f"Bearer {kulcs}", "Content-Type": tipus},
        method="POST")
    try:
        with urllib.request.urlopen(keres, timeout=120) as v:
            return json.loads(v.read().decode()).get("text", "").strip()
    except urllib.error.HTTPError as h:
        raise HangHiba(f"Whisper HTTP {h.code}: {h.read().decode()[:300]}")
    except urllib.error.URLError as h:
        raise HangHiba(f"Halozati hiba: {h}")


# ----------------------------------------------------------------- felolvasas

def felolvas(szoveg, hang=None, lejatszas=True):
    """Szoveg -> beszed, OpenAI TTS-szel. Visszaadja a fajl utvonalat."""
    kulcs = os.environ.get("OPENAI_API_KEY")
    if not kulcs:
        raise HangHiba("Hianyzik az OPENAI_API_KEY.")
    szoveg = (szoveg or "").strip()
    if not szoveg:
        return None

    payload = {"model": TTS_MODELL, "voice": hang or TTS_HANG,
               "input": szoveg, "response_format": "mp3"}
    # A gpt-4o-mini-tts es ujabb modellek stilus-utasitast is elfogadnak.
    # Itt kerjuk a ketnyelvu kiejtest: magyar szavak magyarul, angol
    # markanevek angolul.
    if "gpt-4o" in TTS_MODELL or "gpt-5" in TTS_MODELL:
        payload["instructions"] = TTS_UTASITAS

    keres = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {kulcs}",
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(keres, timeout=120) as v:
            adat = v.read()
    except urllib.error.HTTPError as h:
        raise HangHiba(f"TTS HTTP {h.code}: {h.read().decode()[:300]}")
    except urllib.error.URLError as h:
        raise HangHiba(f"Halozati hiba: {h}")

    ut = Path(tempfile.gettempdir()) / f"kifli_{uuid.uuid4().hex}.mp3"
    ut.write_bytes(adat)
    if lejatszas:
        lejatszik(ut)
    return ut


def lejatszik(ut):
    for parancs in (["afplay", str(ut)],          # macOS
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel",
                     "quiet", str(ut)],
                    ["play", "-q", str(ut)]):     # sox
        if _van(parancs[0]):
            subprocess.run(parancs, check=False)
            return
    print(f"{PI}Nincs lejatszo (afplay/ffplay/play). A fajl: {ut}{ALAP}")


# ----------------------------------------------------------------- onteszt

HANGOK = {
    "nova":    "semleges noi, tiszta",
    "shimmer": "lagyabb noi, melegebb",
    "coral":   "baratsagos noi, elenkebb",
    "sage":    "nyugodt noi, halkabb",
    "alloy":   "semleges, kozepes",
    "ash":     "nyugodt ferfi",
    "echo":    "melyebb ferfi",
    "onyx":    "melyebb ferfi, komolyabb",
    "ballad":  "lagy ferfi, mesélős",
    "verse":   "termeszetes ferfi, kotetlen",
}


def hangokat_probal(szoveg=None):
    """Vegigjatssza ugyanazt a mondatot minden hangon."""
    szoveg = szoveg or (
        "Bement a Kitchin olivaolaj, het es fel deci, negyezer-"
        "szazhatvanhat forintert. Akkor a trappista sajtbol harminc "
        "dekat kerek, es mar csak a Hellmann's majonez van hatra."
    )
    for nev, leiras in HANGOK.items():
        print(f"\n{SZ}{nev}{ALAP} {HA}- {leiras}{ALAP}")
        try:
            felolvas(szoveg, hang=nev)
        except HangHiba as e:
            print(f"  {PI}{e}{ALAP}")
            return
        try:
            if input(f"{HA}  Enter = kovetkezo, 'q' = eleg > {ALAP}").strip().lower() == "q":
                return
        except (EOFError, KeyboardInterrupt):
            return


def kornyezet_ellenoriz():
    print("Kornyezet:")
    print(f"  OPENAI_API_KEY: "
          f"{'megvan' if os.environ.get('OPENAI_API_KEY') else 'HIANYZIK'}")
    try:
        import sounddevice  # noqa: F401
        felvevo = "sounddevice"
    except Exception:
        # A sounddevice OSError-t dob, ha a PortAudio konyvtar hianyzik
        felvevo = "sox (rec)" if _van("rec") else "NINCS"
    print(f"  felvetel:       {felvevo}")
    lejatszo = next((p for p in ("afplay", "ffplay", "play") if _van(p)), None)
    print(f"  lejatszas:      {lejatszo or 'NINCS'}")
    print(f"  STT modell:     {STT_MODELL}")
    print(f"  TTS modell:     {TTS_MODELL} / {TTS_HANG}")
    if felvevo == "NINCS":
        print(f"\n{PI}Nincs felveteli mod. Telepitsd valamelyiket:{ALAP}")
        print("  brew install sox")
        print("  pip3 install sounddevice numpy")


if __name__ == "__main__":
    kornyezet_ellenoriz()

    if "--hangok" in sys.argv:
        print(f"\n{SZ}Vegigjatszom ugyanazt a mondatot minden hangon.{ALAP}")
        print(f"{HA}Amelyik tetszik, tedd a .env-be: "
              f"OPENAI_TTS_VOICE=<nev>{ALAP}")
        hangokat_probal()
        sys.exit(0)

    if "--teszt" not in sys.argv:
        print("\nTeszthez:  python3 hang.py --teszt")
        print("Hangokhoz: python3 hang.py --hangok")
        sys.exit(0)

    print(f"\n{SZ}Beszelj, aztan nyomj Entert.{ALAP}")
    ut = Path(tempfile.gettempdir()) / f"teszt_{uuid.uuid4().hex}.wav"
    try:
        felvetel(ut)
    except HangHiba as e:
        sys.exit(f"{PI}{e}{ALAP}")

    print(f"{HA}Felismeres...{ALAP}")
    szoveg = felismer(ut)
    print(f"\n{Z}Ezt hallottam:{ALAP} {szoveg!r}")

    if szoveg:
        print(f"{HA}Felolvasas...{ALAP}")
        felolvas(f"Ezt hallottam: {szoveg}")
