#!/usr/bin/env python3
"""
Telepito varazslo - vegigvezet a beallitason.

    python3 telepites.py

Ellenorzi a rendszert, bekeri a szukseges adatokat, teszteli a
kapcsolatokat, es letrehozza a .env fajlt. Barmikor ujra futtathato.
"""

import getpass
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ITT = Path(__file__).resolve().parent
ENV_UT = ITT / ".env"

Z, PI, S, SZ, HA, F, ALAP = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                             "\033[90m", "\033[1m", "\033[0m")
PIPA, X, NYIL = "✓", "✗", "→"


def cim(szoveg):
    print(f"\n{F}{SZ}{szoveg}{ALAP}")
    print(f"{HA}{'─' * min(len(szoveg), 60)}{ALAP}")


def ok(szoveg):
    print(f"  {Z}{PIPA}{ALAP} {szoveg}")


def hiba(szoveg):
    print(f"  {PI}{X}{ALAP} {szoveg}")


def figyelem(szoveg):
    print(f"  {S}!{ALAP} {szoveg}")


def info(szoveg):
    print(f"  {HA}{szoveg}{ALAP}")


def kerdez(kerdes, alapertelmezett=None, titkos=False):
    jel = f" {HA}[{alapertelmezett}]{ALAP}" if alapertelmezett else ""
    try:
        if titkos:
            valasz = getpass.getpass(f"  {kerdes}{jel}: ").strip()
        else:
            valasz = input(f"  {kerdes}{jel}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\nMegszakitva.")
        sys.exit(1)
    return valasz or (alapertelmezett or "")


def igen_e(kerdes, alap=True):
    jel = "I/n" if alap else "i/N"
    valasz = kerdez(f"{kerdes} ({jel})").lower()
    if not valasz:
        return alap
    return valasz[0] in ("i", "y", "1")


def van(parancs):
    return shutil.which(parancs) is not None


# ------------------------------------------------------------ ellenorzesek

def python_ellenoriz():
    cim("1. Python")
    v = sys.version_info
    print(f"  Verzio: {v.major}.{v.minor}.{v.micro}")
    if v < (3, 9):
        hiba("Python 3.9 vagy ujabb kell.")
        return False
    ok("Megfelelo verzio.")

    venvben = (hasattr(sys, "real_prefix")
               or sys.prefix != getattr(sys, "base_prefix", sys.prefix))
    if venvben:
        ok("Virtualis kornyezetben futsz.")
    else:
        figyelem("Nem virtualis kornyezetben futsz.")
        info("Ajanlott:  python3 -m venv .venv && source .venv/bin/activate")
    return True


def rendszer_ellenoriz():
    cim("2. Rendszereszkozok")
    macos = sys.platform == "darwin"
    rendben = True

    lejatszo = next((p for p in ("afplay", "ffplay", "play") if van(p)), None)
    if lejatszo:
        ok(f"Hanglejatszas: {lejatszo}")
    else:
        hiba("Nincs hanglejatszo.")
        info("brew install ffmpeg" if macos else "sudo apt install ffmpeg")
        rendben = False

    if van("node") or van("npx"):
        ok("Node.js megvan (a Kifli kapcsolathoz kell).")
    else:
        hiba("Nincs Node.js - enelkul nem megy a Kifli kapcsolat.")
        info("brew install node" if macos else "sudo apt install nodejs npm")
        rendben = False

    return rendben


def csomagok_ellenoriz():
    cim("3. Python csomagok")
    print(f"  {HA}Ezek csak a hangvezerleshez kellenek. Nelkuluk a gepelt")
    print(f"  valtozat (asszisztens.py) tokeletesen mukodik.{ALAP}\n")

    hianyzo = []
    macos = sys.platform == "darwin"
    for nev, mire in (("sounddevice", "mikrofon"),
                      ("numpy", "hangfeldolgozas"),
                      ("websockets", "realtime kapcsolat")):
        try:
            __import__(nev)
            ok(f"{nev} ({mire})")
        except Exception as e:
            if "PortAudio" in str(e):
                hiba(f"{nev}: a PortAudio rendszerkonyvtar hianyzik")
                info("brew install portaudio" if macos
                     else "sudo apt install portaudio19-dev")
                info("utana:  pip install --force-reinstall sounddevice")
                continue
            hiba(f"{nev} ({mire}) - hianyzik")
            hianyzo.append(nev)

    if hianyzo and igen_e("\n  Telepitsem oket most?", True):
        parancs = [sys.executable, "-m", "pip", "install"] + hianyzo
        print()
        eredmeny = subprocess.run(parancs)
        if eredmeny.returncode == 0:
            ok("Telepitve.")
        else:
            hiba("A telepites nem sikerult.")
            info("Probald kezzel: pip install " + " ".join(hianyzo))
    return True


# -------------------------------------------------------------- kapcsolatok

def openai_teszt(kulcs):
    keres = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {kulcs}"})
    try:
        with urllib.request.urlopen(keres, timeout=30) as v:
            adat = json.loads(v.read().decode())
        return True, f"{len(adat.get('data', []))} modell elerheto"
    except urllib.error.HTTPError as h:
        return False, f"HTTP {h.code} - valoszinuleg rossz a kulcs"
    except Exception as e:
        return False, str(e)


def kifli_teszt(email, jelszo, url="https://www.kifli.hu"):
    """A rohlik-mcp szerveren keresztul probal bejelentkezni."""
    kornyezet = {**os.environ, "ROHLIK_BASE_URL": url,
                 "ROHLIK_USERNAME": email, "ROHLIK_PASSWORD": jelszo}
    uzenetek = "\n".join(json.dumps(u) for u in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "telepito", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "search_products",
                    "arguments": {"product_name": "tej", "limit": 1}}},
    ])
    try:
        eredmeny = subprocess.run(
            ["npx", "-y", "@tomaspavlin/rohlik-mcp"],
            input=uzenetek, capture_output=True, text=True,
            env=kornyezet, timeout=180)
    except FileNotFoundError:
        return False, "Nincs npx (Node.js kell)."
    except subprocess.TimeoutExpired:
        return False, "Idotullepes - az elso inditas lassu lehet, probald ujra."

    for sor in eredmeny.stdout.splitlines():
        if not sor.strip().startswith("{"):
            continue
        try:
            valasz = json.loads(sor)
        except json.JSONDecodeError:
            continue
        if valasz.get("id") != 2:
            continue
        r = valasz.get("result", {})
        szoveg = " ".join(d.get("text", "") for d in r.get("content", []))
        if r.get("isError"):
            if "401" in szoveg or "Unauthorized" in szoveg:
                return False, "Hibas email vagy jelszo."
            return False, szoveg[:150]
        return True, szoveg.splitlines()[0] if szoveg else "kapcsolat rendben"
    return False, "Nem kaptam ertelmes valaszt a szervertol."


# ------------------------------------------------------------------ beallitas

def beallitasok_bekerese(meglevo):
    cim("4. OpenAI hozzaferes")
    print(f"  {HA}Kulcs: https://platform.openai.com/api-keys{ALAP}\n")

    kulcs = meglevo.get("OPENAI_API_KEY", "")
    if kulcs:
        info(f"Mar van beallitva ({kulcs[:7]}...{kulcs[-4:]})")
        if not igen_e("Lecsereljem?", False):
            pass
        else:
            kulcs = ""
    while not kulcs:
        kulcs = kerdez("OpenAI API kulcs", titkos=True)
        if not kulcs:
            hiba("Ez kotelezo.")
            continue
        print(f"  {HA}Tesztelem...{ALAP}")
        sikeres, uzenet = openai_teszt(kulcs)
        if sikeres:
            ok(uzenet)
        else:
            hiba(uzenet)
            if not igen_e("Ujra probalod?", True):
                sys.exit(1)
            kulcs = ""

    cim("5. Kifli.hu fiok")
    print(f"  {HA}A bevasarlashoz a sajat Kifli fiokod kell.")
    print(f"  A jelszo a .env fajlba kerul, helyben, a gepeden.")
    print(f"  {S}Ne hasznald ugyanazt a jelszot mashol.{ALAP}\n")

    email = meglevo.get("ROHLIK_USERNAME", "")
    jelszo = meglevo.get("ROHLIK_PASSWORD", "")
    if email and jelszo:
        info(f"Mar van beallitva ({email})")
        if igen_e("Lecsereljem?", False):
            email = jelszo = ""

    while not (email and jelszo):
        email = kerdez("Kifli email", email or None)
        jelszo = kerdez("Kifli jelszo", titkos=True)
        if not (email and jelszo):
            hiba("Mindketto kell.")
            continue
        print(f"  {HA}Bejelentkezes... (elso alkalommal 1-2 perc){ALAP}")
        sikeres, uzenet = kifli_teszt(email, jelszo)
        if sikeres:
            ok(uzenet)
        else:
            hiba(uzenet)
            if not igen_e("Ujra probalod?", True):
                sys.exit(1)
            jelszo = ""

    cim("6. Hang")
    hangok = {"1": ("marin", "noi, termeszetes"),
              "2": ("cedar", "ferfi, nyugodt"),
              "3": ("alloy", "semleges")}
    for k, (nev, leiras) in hangok.items():
        print(f"  {k}) {nev:8} {HA}{leiras}{ALAP}")
    valasztott = kerdez("\n  Melyiket", "1")
    hang = hangok.get(valasztott, hangok["1"])[0]
    ok(f"Hang: {hang}")

    return {
        "OPENAI_API_KEY": kulcs,
        "ROHLIK_BASE_URL": "https://www.kifli.hu",
        "ROHLIK_USERNAME": email,
        "ROHLIK_PASSWORD": jelszo,
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": meglevo.get("LLM_MODEL", "gpt-5.6-terra"),
        "OPENAI_REALTIME_VOICE": hang,
        "GEMINI_API_KEY": meglevo.get("GEMINI_API_KEY", ""),
    }


def env_beolvas():
    if not ENV_UT.exists():
        return {}
    ertekek = {}
    for sor in ENV_UT.read_text(encoding="utf-8").splitlines():
        sor = sor.strip()
        if not sor or sor.startswith("#") or "=" not in sor:
            continue
        kulcs, ertek = sor.split("=", 1)
        ertekek[kulcs.strip()] = ertek.strip().strip('"\'')
    return ertekek


def env_ir(beallitasok):
    sorok = ["# Kifli asszisztens beallitasok",
             "# Ezt a fajlt a telepites.py hozta letre.",
             "# NE tedd verziokezelesbe - jelszot tartalmaz!", ""]
    for kulcs, ertek in beallitasok.items():
        if ertek:
            sorok.append(f"{kulcs}={ertek}")
    ENV_UT.write_text("\n".join(sorok) + "\n", encoding="utf-8")
    os.chmod(ENV_UT, 0o600)


def elozmeny_betoltes(beallitasok):
    cim("7. Vasarlasi elozmenyek")
    print(f"  {HA}Az asszisztens megtanulja, melyik terméket melyik neven")
    print(f"  hivod. Ha most betoltjuk a korabbi rendeleseidet, sokkal")
    print(f"  kevesebbet fog kerdezni.{ALAP}\n")

    if not igen_e("Betoltsem most?", True):
        info("Kihagyva - menet kozben is megtanulja.")
        return

    for kulcs, ertek in beallitasok.items():
        if ertek:
            os.environ[kulcs] = ertek

    try:
        import adat
        import parser as p
        from mcp_kliens import MCPKliens
    except ImportError as e:
        hiba(f"Hianyzo modul: {e}")
        return

    print(f"  {HA}Lekerem a rendeleseidet...{ALAP}")
    try:
        with MCPKliens() as mcp:
            nyers = mcp.hiv("get_frequent_items",
                            {"orders_to_analyze": 20, "top_items": 30,
                             "show_categories": False})
            gyakori = p.gyakori_ertelmez(nyers)
            if not gyakori:
                figyelem("Nincs eleg rendelestortenet.")
                return

            tarolo = adat.Tarolo(ITT / "kifli.db")
            print(f"\n  {F}A {len(gyakori)} leggyakoribb termeked:{ALAP}")
            print(f"  {HA}Add meg, hogyan hivod oket. Enter = kihagyom.{ALAP}\n")

            mentve = 0
            for i, g in enumerate(gyakori, 1):
                print(f"  {HA}{i}/{len(gyakori)}{ALAP} {g['nev'][:58]}")
                nev = kerdez("     Hogy hivod", titkos=False)
                if not nev:
                    continue
                reszletek = p.termekek_ertelmez(
                    mcp.hiv("search_products",
                            {"product_name": g["nev"][:60], "limit": 5}))
                talalat = next((t for t in reszletek if t["id"] == g["id"]),
                               None)
                tarolo.ment(nev, g["id"], g["nev"],
                            talalat.get("mennyiseg") if talalat else None,
                            talalat.get("egyseg") if talalat else None,
                            p.kimert_e(talalat) if talalat else False)
                mentve += 1
            tarolo.close()
            ok(f"{mentve} termek elmentve.")
    except Exception as e:
        hiba(f"Nem sikerult: {e}")


def main():
    print(f"\n{F}{SZ}  Kifli asszisztens - telepito{ALAP}")
    print(f"{HA}  Vegigvezetlek a beallitason. Barmikor megszakithatod "
          f"(Ctrl+C).{ALAP}")

    if not python_ellenoriz():
        sys.exit(1)
    rendszer_ellenoriz()
    csomagok_ellenoriz()

    meglevo = env_beolvas()
    beallitasok = beallitasok_bekerese(meglevo)
    env_ir(beallitasok)

    cim("Beallitasok mentve")
    ok(f"{ENV_UT} (csak te olvashatod)")

    elozmeny_betoltes(beallitasok)

    print(f"\n{F}{Z}  Kesz!{ALAP}\n")
    print(f"  {F}Inditas:{ALAP}")
    print(f"    {SZ}python3 kifli.py{ALAP}          {HA}hangvezerelt{ALAP}")
    print(f"    {SZ}python3 kifli.py --gepelt{ALAP}  {HA}gepelt{ALAP}")
    print(f"    {SZ}python3 kifli.py --proba{ALAP}   "
          f"{HA}proba, nem ir a kosarba{ALAP}")
    print()


if __name__ == "__main__":
    main()
