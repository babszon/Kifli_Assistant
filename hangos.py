#!/usr/bin/env python3
"""
Hangvezerelt Kifli asszisztens.

    python3 hangos.py              # hangbevitel, hangvalasz
    python3 hangos.py --szaraz     # nem ir a valodi kosarba
    python3 hangos.py --nema       # hangbevitel, de nem olvas fel

Hasznalat: nyomj Entert, beszelj, nyomj ujra Entert. A valasz
elhangzik, es a kepernyon ott a reszletes lista.

Barmikor gepelhetsz is: ha a felvetel elott beirsz valamit, azt
hasznalja hang helyett.
"""

import argparse
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import adat
import asszisztens as asz
import hang
import motor as motor_modul
from mcp_kliens import MCPKliens

Z, PI, S, SZ, HA, ALAP = ("\033[92m", "\033[91m", "\033[93m",
                          "\033[96m", "\033[90m", "\033[0m")

KILEPES = {"kilep", "kilépés", "kilépek", "vege", "vége", "viszlat",
           "viszlát", "eleg", "elég", "quit", "exit"}


def bemenet_olvas(nema_bevitel=False):
    """
    Visszaad: (szoveg, hangbol_jott)

    Enter -> felvetel indul. Ha inkabb gepelnel, csak ird be a szoveget
    es nyomj Entert.
    """
    if nema_bevitel:
        try:
            return input(f"\n{SZ}> {ALAP}").strip(), False
        except (EOFError, KeyboardInterrupt):
            return "kilep", False

    try:
        elso = input(f"\n{SZ}[Enter = beszelek, vagy gepelj] > {ALAP}").strip()
    except (EOFError, KeyboardInterrupt):
        return "kilep", False

    if elso:
        return elso, False

    ut = Path(tempfile.gettempdir()) / f"kifli_{uuid.uuid4().hex}.wav"
    print(f"{PI}  ● Felvetel... (Enter = kesz){ALAP}")
    try:
        hang.felvetel(ut)
    except hang.HangHiba as e:
        print(f"{PI}  {e}{ALAP}")
        return "", False

    print(f"{HA}  Felismeres...{ALAP}")
    kezdet = time.time()
    try:
        szoveg = hang.felismer(ut)
    except hang.HangHiba as e:
        print(f"{PI}  {e}{ALAP}")
        return "", False
    finally:
        ut.unlink(missing_ok=True)

    print(f"{HA}  ({time.time() - kezdet:.1f} mp){ALAP}")
    if szoveg:
        print(f"{Z}  Te: {szoveg}{ALAP}")
    return szoveg, True


def main():
    a = argparse.ArgumentParser(description="Hangvezerelt Kifli asszisztens.")
    a.add_argument("--szaraz", action="store_true",
                   help="ne irjon a valodi Kifli kosarba")
    a.add_argument("--nema", action="store_true",
                   help="ne olvassa fel a valaszokat")
    a.add_argument("--gepelos", action="store_true",
                   help="ne vegyen fel hangot, csak gepeles")
    a.add_argument("--szolgaltato", choices=["openai", "gemini"])
    a.add_argument("--model")
    a.add_argument("--db", default="kifli.db")
    args = a.parse_args()

    if not os.environ.get("OPENAI_API_KEY") and not args.gepelos:
        sys.exit("A hanghoz OPENAI_API_KEY kell.")

    tarolo = adat.Tarolo(args.db)
    try:
        motor = motor_modul.motor_valaszt(
            asz.RENDSZERPROMPT, asz.ESZKOZOK,
            szolgaltato=args.szolgaltato, model=args.model)
    except motor_modul.MotorHiba as e:
        sys.exit(str(e))

    print(f"{SZ}Kifli asszisztens. Mondd, mire van szukseg.{ALAP}")
    print(f"{HA}Motor: {motor.nev} / {motor.model}"
          f"{'  [szaraz]' if args.szaraz else ''}"
          f"{'  [nema]' if args.nema else ''}{ALAP}")
    print(f"{HA}Kilepes: mondd, hogy 'vege', vagy Ctrl+C{ALAP}")

    with MCPKliens() as mcp:
        asszisztens = asz.Asszisztens(mcp, tarolo, args.szaraz)

        while not asszisztens.lezarva:
            szoveg, hangbol = bemenet_olvas(args.gepelos)

            if not szoveg:
                continue
            if szoveg.lower().strip(".!? ") in KILEPES:
                print("Viszlat.")
                break

            try:
                valasz = motor.beszelget(szoveg, asszisztens)
            except motor_modul.MotorHiba as e:
                print(f"\n{PI}Nem sikerult a hivas: {e}{ALAP}")
                continue

            print(f"\n{SZ}{valasz}{ALAP}")

            if not args.nema and valasz and not valasz.startswith("("):
                try:
                    hang.felolvas(valasz)
                except hang.HangHiba as e:
                    print(f"{HA}  (felolvasas nem ment: {e}){ALAP}")

        zaro = "Kesz, minden a Kifli kosaradban van."
        print(f"\n{Z}{zaro}{ALAP}")
        print(f"{HA}Az idosav es a fizetes a Kifli appban.{ALAP}")
        if args.szaraz:
            print(f"{HA}(Szaraz futas volt - a kosar nem valtozott.){ALAP}")
        elif not args.nema:
            try:
                hang.felolvas(zaro + " Az idosavot es a fizetest a Kifli "
                                     "appban tudod befejezni.")
            except hang.HangHiba:
                pass

    tarolo.close()


if __name__ == "__main__":
    main()
