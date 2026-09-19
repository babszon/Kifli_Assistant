#!/usr/bin/env python3
"""
A rohlik-mcp munkamenet-javitasa.

    python3 mcp_javitas.py

MIERT KELL EZ

A kozzetett rohlik-mcp minden egyes API-hivas elott bejelentkezik, es
a hivas vegen - egy 'finally' agban - rogton ki is jelentkezik:

    await this.login();
    try {
      ...a tenyleges hivas...
    } finally {
      await this.logout();
    }

Tizenhat metodus csinalja ugyanezt. Egy 15 tételes bevasarlolista igy
30-nal is tobb bejelentkezest jelent, es a bejelentkezesi vegpont a
legszigorubban ratakorlatozott - innen jott a HTTP 429 par termek utan.

MIT CSINAL EZ A SCRIPT

Letolti a rohlik-mcp forrasat, alkalmazza a javitast, leforditja, es
beirja a .env-be, hogy innentol ezt hasznaljuk. A javitas:
  - a munkamenetet ujrahasznositja (25 percig ervenyes)
  - a parhuzamos hivasokat egyetlen bejelentkezesbe vonja ossze
  - 401/403 eseten ervenytelenit, tehat lejarat utan ujra belep
  - megszunteti a hivasonkenti kijelentkezest

Eredmeny: 30+ bejelentkezes helyett egy.

A javitas a felmeno agnak is hasznos - erdemes beküldeni oda is:
https://github.com/tomaspavlin/rohlik-mcp
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
CEL = ITT / "rohlik-mcp-javitott"
FORRAS = "https://github.com/tomaspavlin/rohlik-mcp.git"
PATCH = ITT / "mcp-javitas.patch"

Z, PI, S, SZ, HA, F, ALAP = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                             "\033[90m", "\033[1m", "\033[0m")


def fut(parancs, hol=None, csendes=True):
    """Parancs futtatasa, a kimenet elnyomva, ha minden rendben."""
    e = subprocess.run(parancs, cwd=hol, capture_output=True, text=True)
    if e.returncode != 0 and not csendes:
        print(f"{PI}{e.stdout}{e.stderr}{ALAP}")
    return e.returncode == 0, (e.stdout + e.stderr)


def van_e(program):
    return shutil.which(program) is not None


def env_beallit(parancs):
    """A .env-be beirjuk, melyik szervert hasznaljuk."""
    env = ITT / ".env"
    if not env.exists():
        print(f"{S}  Nincs .env - futtasd eloszor: python3 telepites.py{ALAP}")
        return False

    sorok = env.read_text(encoding="utf-8").splitlines()
    sorok = [s for s in sorok if not s.startswith("ROHLIK_MCP_PARANCS=")]
    sorok.append("")
    sorok.append("# A javitott MCP szerver (lasd mcp_javitas.py)")
    sorok.append(f"ROHLIK_MCP_PARANCS={parancs}")
    env.write_text("\n".join(sorok) + "\n", encoding="utf-8")
    os.chmod(env, 0o600)
    return True


def main():
    print(f"\n{F}{SZ}  A rohlik-mcp munkamenet-javitasa{ALAP}\n")

    if not van_e("git") or not van_e("npm"):
        sys.exit(f"{PI}Git es npm kell hozza.{ALAP}")
    if not PATCH.exists():
        sys.exit(f"{PI}Hianyzik a javitas: {PATCH.name}{ALAP}")

    if CEL.exists():
        valasz = input(f"  A(z) {CEL.name} mar letezik. Ujra? [i/N] ")
        if valasz.strip().lower() not in ("i", "igen", "y"):
            print("  Kihagyva.")
            return
        shutil.rmtree(CEL)

    print(f"{HA}  Forras letoltese...{ALAP}")
    ok, kimenet = fut(["git", "clone", "--depth", "1", FORRAS, str(CEL)])
    if not ok:
        sys.exit(f"{PI}Nem sikerult letolteni:\n{kimenet}{ALAP}")

    print(f"{HA}  Javitas alkalmazasa...{ALAP}")
    ok, kimenet = fut(["git", "apply", str(PATCH)], hol=CEL)
    if not ok:
        print(f"{PI}  A javitas nem illeszkedik a jelenlegi verziora.{ALAP}")
        print(f"{HA}  Valoszinuleg frissult a rohlik-mcp. A program a "
              f"kozzetett valtozattal is mukodik, csak lassabban.{ALAP}")
        print(f"{HA}  Reszletek:\n{kimenet[:400]}{ALAP}")
        shutil.rmtree(CEL, ignore_errors=True)
        sys.exit(1)

    print(f"{HA}  Fuggosegek telepitese (ez eltarthat egy percig)...{ALAP}")
    ok, kimenet = fut(["npm", "install", "--silent"], hol=CEL)
    if not ok:
        sys.exit(f"{PI}npm install nem sikerult:\n{kimenet[:400]}{ALAP}")

    print(f"{HA}  Forditas...{ALAP}")
    ok, kimenet = fut(["npm", "run", "build"], hol=CEL)
    if not ok:
        sys.exit(f"{PI}A forditas nem sikerult:\n{kimenet[:400]}{ALAP}")

    belepo = CEL / "dist" / "index.js"
    if not belepo.exists():
        sys.exit(f"{PI}Nem talalom a leforditott szervert: {belepo}{ALAP}")

    parancs = f"node {belepo}"
    if not env_beallit(parancs):
        print(f"\n{S}  Tedd be kezzel a .env-be:{ALAP}")
        print(f"    ROHLIK_MCP_PARANCS={parancs}")
        return

    print(f"\n{Z}  Kesz.{ALAP}")
    print(f"{HA}  A program mostantol a javitott szervert hasznalja.{ALAP}")
    print(f"{HA}  Egy 15 tételes lista: 30+ bejelentkezes helyett 1.{ALAP}")
    print(f"\n{HA}  Vissza a kozzetett valtozatra: vedd ki a "
          f"ROHLIK_MCP_PARANCS sort a .env-bol.{ALAP}\n")


if __name__ == "__main__":
    main()
