#!/usr/bin/env python3
"""
Bevasarlolista -> Kifli kosar, beszelgetve.

    python3 szinkron.py                        # HA-bol olvas, kosarba tesz
    python3 szinkron.py --szaraz               # mindent megcsinal, de NEM ir kosarba
    python3 szinkron.py --fajl lista.txt       # fajlbol olvas a HA helyett
    python3 szinkron.py --lista                # a megtanult termek_map kiirasa
    python3 szinkron.py --felejts tej          # egy megtanult par torlese

A program CSAK arrol kerdez, amit nem tud eldonteni. Amit egyszer
megmondtal, azt legkozelebb csendben hasznalja.

A lista fajl formatuma: soronkent egy tetel, ugy ahogy diktalnad.
A '#'-tel kezdodo sorok megjegyzesek.
"""

import argparse
import math
import os
import sys
from pathlib import Path

import adat
import llm
import parser as p
from mcp_kliens import MCPKliens, MCPHiba

Z, PI, S, SZ, HA, ALAP = ("\033[92m", "\033[91m", "\033[93m",
                          "\033[96m", "\033[90m", "\033[0m")

# Alapegysegre valtas: minden suly grammban, minden terfogat milliliterben
EGYSEG_SZORZO = {"g": 1, "dkg": 10, "kg": 1000,
                 "ml": 1, "cl": 10, "dl": 100, "l": 1000}


def alapegysegre(ertek, egyseg):
    if ertek is None or egyseg is None:
        return None
    return ertek * EGYSEG_SZORZO.get(egyseg.lower(), 1)


def darabszam(mennyiseg, csomag_ertek, csomag_egyseg, bulk=False):
    """
    Visszaad: (darab, tobblet_arany, megjegyzes)

    A darab az, amit az add_to_cart quantity mezojebe teszunk.
    Ha nem tudjuk biztonsagosan kiszamolni, 1-et adunk vissza es
    megjegyzest, hogy a felhasznalo dontsön. Inkabb keves, mint sok.
    """
    kind = (mennyiseg or {}).get("kind", "unspecified")
    ertek = (mennyiseg or {}).get("value")

    if kind == "unspecified" or ertek is None:
        return 1, None, None

    # Kimert aru (hus, zoldseg): a Kifli kilora arul valtozo sullyal.
    # NEM szamolunk darabot - 1 egyseget kerunk es jelezzuk.
    if bulk:
        kert = alapegysegre(ertek, (mennyiseg or {}).get("unit"))
        sulyszoveg = f"{kert / 1000:g} kg" if kert else f"{ertek:g}"
        return 1, None, f"kimert aru - {sulyszoveg}-ot kertel, ellenorizd a kosarban"

    if kind == "package":
        return max(1, int(ertek)), None, None

    if kind == "piece":
        # "30 darab tojas" + 10 db-os kiszereles = 3 csomag, nem 30!
        if csomag_egyseg and csomag_egyseg.lower() in ("db", "darab", "pcs"):
            csomagban = csomag_ertek or 1
            if csomagban > 1:
                darab = max(1, math.ceil(ertek / csomagban))
                tobblet = (darab * csomagban - ertek) / ertek
                return darab, tobblet, f"{csomagban:g} db/csomag"
        return max(1, int(ertek)), None, None

    kert = alapegysegre(ertek, (mennyiseg or {}).get("unit"))
    csomag = alapegysegre(csomag_ertek, csomag_egyseg)
    if not kert or not csomag:
        return 1, None, "ismeretlen kiszereles - ellenorizd"

    darab = max(1, math.ceil(kert / csomag))
    tobblet = (darab * csomag - kert) / kert
    return darab, tobblet, None


def sorszamot_ker(kerdes, talalatok, max_probalkozas=3):
    """
    Sorszamot olvas be a talalatok kozul. Nem dobja el a tetelt
    az elso elgepeles miatt - visszakerdez.

    Visszaad: index (0-alapu), vagy None ha kihagyas.
    """
    n = len(talalatok)
    for probalkozas in range(max_probalkozas):
        valasz = kerdez(f"{kerdes} (1-{n}, vagy enter = kihagyom)").strip()
        if not valasz:
            return None
        if valasz.lower() in ("k", "kihagy", "skip", "n", "nem"):
            return None
        if valasz.isdigit():
            szam = int(valasz)
            if 1 <= szam <= n:
                return szam - 1
            print(f"  {S}A(z) {szam} nincs a listan. "
                  f"Sorszamot kerek 1 es {n} kozott.{ALAP}")
            continue
        print(f"  {S}Sorszamot kerek 1 es {n} kozott "
              f"(vagy enter a kihagyashoz).{ALAP}")
    print(f"  {HA}Kihagyom.{ALAP}")
    return None


def kerdez(szoveg, alapertelmezett=None):
    """Egy kerdes egyszerre - hangra valthatosag miatt."""
    jel = f" [{alapertelmezett}]" if alapertelmezett else ""
    try:
        valasz = input(f"{SZ}{szoveg}{jel}{ALAP}\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit("Megszakitva.")
    return valasz or (alapertelmezett or "")


def akciok_lekerese(mcp):
    """Akcios termekek ID -> kedvezmeny terkep."""
    terkep = {}
    for tipus in ("sales", "premium-sales"):
        try:
            szoveg = mcp.hiv("get_discounted_items",
                             {"sale_type": tipus, "limit": 50, "sort": "recommended"})
            for t in p.termekek_ertelmez(szoveg):
                if t.get("kedvezmeny"):
                    terkep[t["id"]] = t
        except MCPHiba:
            continue
    return terkep


def feldolgoz(nyers, norm, mcp, tarolo, akciok):
    """Egy tetel feldolgozasa. Visszaad egy sort a kosarhoz vagy None-t."""
    termek_nev = (norm.get("product") or nyers).lower()
    mennyiseg = norm.get("quantity") or {}

    # 0. Bizonytalan mar a normalizalasnal
    if (norm.get("confidence") or 1.0) < 0.5:
        print(f"\n{S}Nem ertem: {nyers!r}{ALAP}")
        valasz = kerdez("Mit keressek helyette? (enter = kihagyom)")
        if not valasz:
            tarolo.naploz(nyers, "ertelmezhetetlen", "kihagyva")
            return None
        termek_nev = valasz.lower()
        norm = {"product": termek_nev, "quantity": mennyiseg}

    # 1. Ismerjuk mar?
    ismert = tarolo.keres(termek_nev)
    if ismert:
        db, tobblet, mj = darabszam(mennyiseg, ismert["amount_value"],
                                    ismert["amount_unit"], bool(ismert["bulk"]))
        tarolo.hasznalat(termek_nev)
        return {"nyers": nyers, "product": termek_nev,
                "kifli_id": ismert["kifli_id"], "kifli_nev": ismert["kifli_nev"],
                "darab": db, "tobblet": tobblet, "megjegyzes": mj,
                "forras": "elozmeny", "akcio": akciok.get(ismert["kifli_id"])}

    # 2. Keresunk, es az LLM valaszt
    try:
        talalatok = p.termekek_ertelmez(
            mcp.hiv("search_products", {"product_name": termek_nev, "limit": 10}))
    except MCPHiba as e:
        print(f"{PI}Kereses sikertelen ({termek_nev}): {e}{ALAP}")
        return None

    dontes = llm.termeket_valaszt(norm, talalatok)
    valasztott = next((t for t in talalatok if t["id"] == dontes.get("kifli_id")), None)

    # 3. Ha bizonytalan, kerdezunk
    if valasztott is None or (dontes.get("confidence") or 0) < 0.5:
        jeloltek = talalatok[:5]
        print(f"\n{S}{nyers!r}{ALAP} - ezt meg nem vetted.")
        for i, t in enumerate(jeloltek, 1):
            ar = f"{t['ar']:.0f} Ft" if t.get("ar") else "?"
            kedv = f" {PI}({t['kedvezmeny']}%){ALAP}" if t.get("kedvezmeny") else ""
            kiszereles = (f"{t['mennyiseg']:g} {t['egyseg']}"
                          if t.get("mennyiseg") else "?")
            print(f"  {i}. {t['nev']}  {HA}{kiszereles} - {ar}{kedv}{ALAP}")

        kerdes = dontes.get("kerdes") or "Melyiket kerjem?"
        index = sorszamot_ker(kerdes, jeloltek)
        if index is None:
            tarolo.naploz(nyers, kerdes, "kihagyva")
            return None
        valasztott = jeloltek[index]
        tarolo.naploz(nyers, kerdes, valasztott["nev"])

    # 4. Megtanuljuk
    tarolo.ment(termek_nev, valasztott["id"], valasztott["nev"],
                valasztott.get("mennyiseg"), valasztott.get("egyseg"),
                p.kimert_e(valasztott))

    db, tobblet, mj = darabszam(mennyiseg, valasztott.get("mennyiseg"),
                                valasztott.get("egyseg"), p.kimert_e(valasztott))
    return {"nyers": nyers, "product": termek_nev, "kifli_id": valasztott["id"],
            "kifli_nev": valasztott["nev"], "darab": db, "tobblet": tobblet,
            "megjegyzes": mj, "forras": "uj",
            "akcio": akciok.get(valasztott["id"]) or
                     (valasztott if valasztott.get("kedvezmeny") else None)}


def duplikatumok_kezelese(sorok):
    """
    Ha tobb lista-sor ugyanarra a termekre mutat, azt kezelni kell,
    kulonben negy doboz tojas kerul a kosarba.

    Alapertelmezes: a LEGNAGYOBB mennyiseget vesszuk, nem az osszeget.
    Az osszeadas a veszelyesebb, mert csendben duplaz.
    """
    csoportok = {}
    for s in sorok:
        csoportok.setdefault(s["kifli_id"], []).append(s)

    duplak = {k: v for k, v in csoportok.items() if len(v) > 1}
    if not duplak:
        return sorok

    print(f"\n{S}{len(duplak)} termek tobbszor is szerepel a listan.{ALAP}")
    vegleges = []

    for kifli_id, csoport in csoportok.items():
        if len(csoport) == 1:
            vegleges.append(csoport[0])
            continue

        legnagyobb = max(csoport, key=lambda s: s["darab"])
        osszeg = sum(s["darab"] for s in csoport)
        nev = csoport[0]["kifli_nev"]

        print(f"\n  {nev}")
        for s in csoport:
            print(f"    {HA}{s['darab']}x  <- {s['nyers']!r}{ALAP}")

        if osszeg == legnagyobb["darab"]:
            valasztott = legnagyobb
        else:
            valasz = kerdez(
                f"  Melyik legyen? [n] {legnagyobb['darab']} db "
                f"(a legnagyobb)  /  [o] {osszeg} db (osszeadva)", "n"
            ).lower()
            if valasz in ("o", "osszeg", "össze", "osszead"):
                valasztott = dict(legnagyobb, darab=osszeg,
                                  nyers=" + ".join(s["nyers"] for s in csoport))
            else:
                valasztott = dict(
                    legnagyobb,
                    nyers=" / ".join(s["nyers"] for s in csoport))

        vegleges.append(valasztott)

    return vegleges


def visszaigazolas(sorok, kihagyott):
    elozmeny = [s for s in sorok if s["forras"] == "elozmeny"]
    ujak = [s for s in sorok if s["forras"] == "uj"]
    akciosok = [s for s in sorok if s.get("akcio")]

    print(f"\n{'=' * 58}")
    print(f"{len(sorok)} tetel a kosarba, {len(kihagyott)} kimaradt")
    print("=" * 58)

    if elozmeny:
        print(f"\n{Z}Elozmenybol ({len(elozmeny)}){ALAP}")
        for s in elozmeny:
            print(f"  {s['darab']}x {s['kifli_nev']}  {HA}({s['nyers']}){ALAP}")

    if ujak:
        print(f"\n{S}Uj illesztes ({len(ujak)}) - nezd at{ALAP}")
        for s in ujak:
            print(f"  {s['darab']}x {s['kifli_nev']}  {HA}({s['nyers']}){ALAP}")

    for s in sorok:
        if s["tobblet"] and s["tobblet"] > 0.5:
            print(f"\n{S}Sok a tobblet:{ALAP} {s['kifli_nev']} - "
                  f"{s['tobblet'] * 100:.0f}% tobb, mint amit kertel")
        if s["megjegyzes"]:
            print(f"  {HA}{s['kifli_nev']}: {s['megjegyzes']}{ALAP}")

    if akciosok:
        print(f"\n{SZ}Akcioban ({len(akciosok)}){ALAP}")
        for s in akciosok:
            kedv = s["akcio"].get("kedvezmeny")
            print(f"  {s['kifli_nev']}  {PI}{kedv}%{ALAP}")

    if kihagyott:
        print(f"\n{PI}Nem tettem be ({len(kihagyott)}){ALAP}")
        for k in kihagyott:
            print(f"  {k}")


def lista_beolvas(args):
    """
    A bevasarlolista beolvasasa: fajlbol vagy a Home Assistantbol.

    Ha a --fajl meg van adva, onnan olvas. Kulonben a HA-t probalja,
    es ha az nem elerheto, jelzi, hogy van fajlos alternativa.
    """
    if args.fajl:
        ut = Path(args.fajl)
        if not ut.exists():
            sys.exit(f"Nincs ilyen fajl: {ut}\n"
                     f"Hozd letre, soronkent egy tetellel, ahogy diktalnad.")
        sorok = []
        for sor in ut.read_text(encoding="utf-8").splitlines():
            sor = sor.strip()
            if sor and not sor.startswith("#"):
                sorok.append(sor)
        print(f"{HA}Forras: {ut}{ALAP}")
        return sorok, None

    try:
        ha = adat.HAKliens()
        tetelek = ha.tetelek()
        print(f"{HA}Forras: Home Assistant ({ha.entitas}){ALAP}")
        return tetelek, ha
    except adat.HAHiba as e:
        sys.exit(f"{PI}A Home Assistant nem elerheto: {e}{ALAP}\n\n"
                 f"Hasznalj fajlt helyette:\n"
                 f"  python3 szinkron.py --fajl lista.txt")


def main():
    a = argparse.ArgumentParser(
        description="Bevasarlolista -> Kifli kosar, beszelgetve.")
    a.add_argument("--fajl", help="lista beolvasasa fajlbol a HA helyett")
    a.add_argument("--szaraz", action="store_true", help="ne irjon a kosarba")
    a.add_argument("--lista", action="store_true", help="a megtanult parok")
    a.add_argument("--felejts", metavar="TERMEK",
                   help="egy megtanult par torlese")
    a.add_argument("--db", default="kifli.db")
    args = a.parse_args()

    tarolo = adat.Tarolo(args.db)

    if args.felejts:
        tarolo.torol(args.felejts)
        print(f"Torolve: {args.felejts}")
        return

    if args.lista:
        sorok = tarolo.osszes()
        if not sorok:
            print("Meg nincs megtanult termek.")
            return
        print(f"{len(sorok)} megtanult termek:\n")
        for s in sorok:
            kiszereles = (f"{s['amount_value']:g} {s['amount_unit']}"
                          if s["amount_value"] else "?")
            print(f"  {s['product']:22} -> {s['kifli_nev']}")
            print(f"  {'':22}    {HA}{kiszereles} | {s['hit_count']}x{ALAP}")
        return

    nyers_tetelek, _ = lista_beolvas(args)
    if not nyers_tetelek:
        print("A bevasarlolista ures.")
        return

    print(f"{len(nyers_tetelek)} tetel a listan. Normalizalas...")
    normalizalt = llm.normalizal(nyers_tetelek)
    if len(normalizalt) != len(nyers_tetelek):
        print(f"{S}FIGYELEM: {len(nyers_tetelek)} tetelt kuldtem, "
              f"{len(normalizalt)} jott vissza.{ALAP}")
        n = min(len(nyers_tetelek), len(normalizalt))
        nyers_tetelek, normalizalt = nyers_tetelek[:n], normalizalt[:n]

    with MCPKliens() as mcp:
        print("Akciok lekerese...")
        akciok = akciok_lekerese(mcp)
        print(f"{len(akciok)} akcios termek.\n")

        sorok, kihagyott = [], []
        for nyers, norm in zip(nyers_tetelek, normalizalt):
            sor = feldolgoz(nyers, norm, mcp, tarolo, akciok)
            (sorok if sor else kihagyott).append(sor if sor else nyers)

        sorok = duplikatumok_kezelese(sorok)
        visszaigazolas(sorok, kihagyott)

        if not sorok:
            return
        if args.szaraz:
            print(f"\n{HA}Szaraz futas - a kosar nem valtozott.{ALAP}")
            return

        if kerdez("\nMehet a kosarba? (i/n)", "n").lower() not in ("i", "igen", "y"):
            print("Kihagyva.")
            return

        mcp.hiv("add_to_cart", {"products": [
            {"product_id": s["kifli_id"], "quantity": s["darab"]} for s in sorok]})
        print(f"{Z}Kosarba tettem. A fizetes a Kifli appban.{ALAP}")

        try:
            print("\n" + mcp.hiv("get_delivery_slots"))
        except MCPHiba:
            pass

    tarolo.close()


if __name__ == "__main__":
    main()
