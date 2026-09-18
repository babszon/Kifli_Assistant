#!/usr/bin/env python3
"""
Kifli asszisztens - inditó.

    python3 kifli.py                 grafikus felulet (bongeszoben)
    python3 kifli.py --terminal      hangvezerelt, terminalban
    python3 kifli.py --gepelt        gepelt beszelgetes, terminalban
    python3 kifli.py --proba         nem ir a valodi kosarba
    python3 kifli.py --tanultak      mit tanult meg eddig
    python3 kifli.py --felejts tej   egy megtanult par torlese

Elso inditaskor automatikusan elinditja a telepitot.
"""

import os
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
ENV_UT = ITT / ".env"

Z, PI, S, SZ, HA, F, ALAP = ("\033[92m", "\033[91m", "\033[93m", "\033[96m",
                             "\033[90m", "\033[1m", "\033[0m")

KOTELEZO = ("OPENAI_API_KEY", "ROHLIK_USERNAME", "ROHLIK_PASSWORD")


def env_betoltes():
    """A .env fajl beolvasasa a kornyezetbe."""
    if not ENV_UT.exists():
        return False
    for sor in ENV_UT.read_text(encoding="utf-8").splitlines():
        sor = sor.strip()
        if not sor or sor.startswith("#") or "=" not in sor:
            continue
        kulcs, ertek = sor.split("=", 1)
        kulcs, ertek = kulcs.strip(), ertek.strip().strip('"\'')
        if ertek and kulcs not in os.environ:
            os.environ[kulcs] = ertek
    return True


def telepitve_e():
    return all(os.environ.get(k) for k in KOTELEZO)


def telepitot_indit():
    print(f"\n{S}Ugy tunik, meg nincs beallitva a rendszer.{ALAP}")
    print(f"{HA}Elinditom a telepitot - par perc az egesz.{ALAP}\n")
    try:
        if input("  Mehet? (I/n): ").strip().lower() in ("", "i", "y"):
            import telepites
            telepites.main()
            env_betoltes()
            return telepitve_e()
    except (EOFError, KeyboardInterrupt):
        print()
    return False


def main():
    env_betoltes()

    argumentumok = sys.argv[1:]
    if "--telepites" in argumentumok:
        import telepites
        telepites.main()
        return

    if not telepitve_e():
        if not telepitot_indit():
            print(f"\n{PI}Nincs beallitva. Futtasd: "
                  f"python3 telepites.py{ALAP}\n")
            sys.exit(1)

    proba = "--proba" in argumentumok

    # Karbantarto parancsok
    if "--tanultak" in argumentumok:
        sys.argv = ["szinkron.py", "--lista"]
        import szinkron
        szinkron.main()
        return
    if "--felejts" in argumentumok:
        i = argumentumok.index("--felejts")
        if i + 1 >= len(argumentumok):
            sys.exit("Mit felejtsek el? Peldaul: --felejts tej")
        sys.argv = ["szinkron.py", "--felejts", argumentumok[i + 1]]
        import szinkron
        szinkron.main()
        return

    if "--terminal" in argumentumok:
        try:
            import numpy, sounddevice, websockets  # noqa: F401
        except Exception as e:
            hang_hianyzik(e)
        sys.argv = ["realtime.py"] + (["--szaraz"] if proba else []) \
            + argumentumum_szures(argumentumok)
        import realtime
        realtime.main()
        return

    if "--gepelt" in argumentumok:
        sys.argv = ["asszisztens.py"] + (["--szaraz"] if proba else [])
        import asszisztens
        asszisztens.main()
        return

    # Alapertelmezes: grafikus felulet.
    # A bongeszo veszi a mikrofont, ezert sem a sounddevice, sem a
    # PortAudio nem kell hozza - csak a websockets.
    try:
        import websockets  # noqa: F401
    except ImportError:
        print(f"\n{S}Hianyzik a websockets csomag.{ALAP}")
        print(f"  pip install websockets\n")
        sys.exit(1)

    sys.argv = ["gui.py"] + (["--proba"] if proba else []) \
        + argumentumum_szures(argumentumok)
    import gui
    gui.main()


def hang_hianyzik(e):
    print(f"\n{S}A terminalos hangvezerleshez hianyzik valami:{ALAP} {e}\n")
    print(f"  {HA}Telepites:{ALAP}")
    print(f"    brew install portaudio")
    print(f"    pip install sounddevice numpy websockets\n")
    print(f"  {HA}A grafikus felulet ezek nelkul is megy:{ALAP}")
    print(f"    python3 kifli.py\n")
    sys.exit(1)


def argumentumum_szures(argumentumok):
    """A sajat kapcsoloinkat kiszurjuk, a tobbit tovabbadjuk."""
    sajat = {"--proba", "--gepelt", "--terminal", "--tanultak",
             "--telepites"}
    kimenet, kihagy = [], False
    for a in argumentumok:
        if kihagy:
            kihagy = False
            continue
        if a == "--felejts":
            kihagy = True
            continue
        if a not in sajat:
            kimenet.append(a)
    return kimenet


if __name__ == "__main__":
    main()
