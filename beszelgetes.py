#!/usr/bin/env python3
"""
Beszelgetos mod: diktalod a listat, a program javasol, te jovahagysz.

    python3 beszelgetes.py

Terminalban fut, de UGY van megirva, hogy hangra valthato legyen:
  - egy kerdes egyszerre, soha nem harom
  - minden valasznak van rovid (mondhato) es reszletes (kepernyos) alakja
  - a hosszu talalati lista SOHA nem hangzik el, csak a kepernyon van

Parancsok beszelgetes kozben:
    kosar        - mi van eddig
    torold X     - egy tetel eltavolitasa
    kesz / mehet - lezaras es kosarba tetel
    kilep        - kilepes mentes nelkul
"""

import os
import sys

import adat
import arak
import llm
import parser as p
from mcp_kliens import MCPKliens, MCPHiba

Z, PI, S, SZ, HA, ALAP = ("\033[92m", "\033[91m", "\033[93m",
                          "\033[96m", "\033[90m", "\033[0m")

PARANCSOK_KESZ = {"kesz", "kész", "mehet", "ennyi", "vege", "vége"}
PARANCSOK_KILEP = {"kilep", "kilép", "megse", "mégse", "quit", "exit"}
IGEN = {"i", "igen", "ok", "oke", "oké", "jo", "jó", "persze", "aha", "y", "yes"}
NEM = {"n", "nem", "ne", "nope", "no"}


def mond(rovid, reszletes=None):
    """
    Ket kimenet ugyanarra. Most mindketto latszik; hangnal csak a rovid
    hangzik el, a reszletes a kepernyore megy.
    """
    print(f"\n{SZ}{rovid}{ALAP}")
    if reszletes:
        print(reszletes)


def bekér(prompt="> "):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "kilep"


def igen_e(valasz):
    """None, ha nem egyertelmu igen vagy nem."""
    v = valasz.lower().strip().rstrip(".!?")
    if v in IGEN:
        return True
    if v in NEM:
        return False
    return None


def talalati_tabla(termekek, max_sor=6):
    """A reszletes, kepernyos alak. Ez SOHA nem hangzik el."""
    sorok = []
    for i, t in enumerate(termekek[:max_sor], 1):
        ar = f"{t['ar']:,.0f} Ft".replace(",", " ") if t.get("ar") else "?"
        egys = arak.egysegar_szoveg(t)
        kedv = f" {PI}{t['kedvezmeny']}%{ALAP}" if t.get("kedvezmeny") else ""
        jel = f" {Z}<- legolcsobb{ALAP}" if t.get("legolcsobb") else ""
        sorok.append(f"  {i}. {t['nev'][:44]:46} {ar:>10} {HA}{egys:>12}{ALAP}"
                     f"{kedv}{jel}")
    if len(termekek) > max_sor:
        sorok.append(f"  {HA}... es meg {len(termekek) - max_sor} talalat{ALAP}")
    return "\n".join(sorok)


def termeket_javasol(nyers, norm, mcp, tarolo):
    """
    Egy tetel feldolgozasa beszelgetve.
    Visszaad egy kosarsort, vagy None-t ha kihagytuk.
    """
    termek_nev = (norm.get("product") or nyers).lower()

    # Ismert termek: csendben megy, csak visszajelzunk
    ismert = tarolo.keres(termek_nev)
    if ismert:
        tarolo.hasznalat(termek_nev)
        return {"nyers": nyers, "product": termek_nev,
                "kifli_id": ismert["kifli_id"], "kifli_nev": ismert["kifli_nev"],
                "amount_value": ismert["amount_value"],
                "amount_unit": ismert["amount_unit"],
                "bulk": bool(ismert["bulk"]), "mennyiseg": norm.get("quantity"),
                "forras": "elozmeny"}

    # Kereses
    try:
        talalatok = p.termekek_ertelmez(
            mcp.hiv("search_products", {"product_name": termek_nev, "limit": 15}))
    except MCPHiba as e:
        mond(f"Nem tudtam rakeresni erre: {termek_nev}.", f"  {HA}{e}{ALAP}")
        return None

    if not talalatok:
        mond(f"Nincs talalat erre: {termek_nev}.")
        return None

    # Az LLM szur (mi tartozik a keresehez) es valaszt, a program szamol
    rangsorolt = arak.rangsorol(talalatok)
    dontes = llm.termeket_valaszt(norm, rangsorolt)
    valasztott = next((t for t in rangsorolt
                       if t["id"] == dontes.get("kifli_id")), None)

    # Ha az LLM nem dontott, a legolcsobb osszehasonlithato a javaslat
    if valasztott is None:
        valasztott = next((t for t in rangsorolt if t.get("legolcsobb")),
                          rangsorolt[0])

    elutasitottak = []
    while True:
        egys = arak.egysegar_szoveg(valasztott)
        ar = f"{valasztott['ar']:,.0f} Ft".replace(",", " ") if valasztott.get("ar") else ""
        indok = dontes.get("indok") or ""
        if valasztott.get("legolcsobb"):
            indok = "ez a legolcsobb kilonkent" if not indok else indok

        # A rovid, mondhato alak - egy mondat
        reszek = [f"{valasztott['nev']}"]
        if egys:
            reszek.append(egys)
        if valasztott.get("kedvezmeny"):
            reszek.append(f"most {abs(valasztott['kedvezmeny'])}% kedvezmennyel")
        rovid = " - ".join(reszek) + ". Jo lesz?"

        mond(rovid, talalati_tabla(rangsorolt))
        if indok:
            print(f"  {HA}{indok}{ALAP}")

        valasz = bekér()
        dontott = igen_e(valasz)

        if dontott is True:
            break
        if valasz.lower() in PARANCSOK_KILEP:
            return None

        # Sorszammal is lehet valaszolni, ha rangez a kepernyore
        if valasz.isdigit() and 1 <= int(valasz) <= len(rangsorolt[:6]):
            valasztott = rangsorolt[int(valasz) - 1]
            break

        # Nem: adunk EGY alternativat, nem otot
        elutasitottak.append(valasztott["id"])
        kovetkezo = next((t for t in rangsorolt
                          if t["id"] not in elutasitottak), None)
        if kovetkezo is None:
            mond("Elfogytak a talalatok. Kihagyom ezt a tetelt.")
            tarolo.naploz(nyers, "nincs tobb talalat", "kihagyva")
            return None
        valasztott = kovetkezo
        dontes = {"indok": None}

    tarolo.ment(termek_nev, valasztott["id"], valasztott["nev"],
                valasztott.get("mennyiseg"), valasztott.get("egyseg"),
                p.kimert_e(valasztott))
    tarolo.naploz(nyers, "termekvalasztas", valasztott["nev"])

    return {"nyers": nyers, "product": termek_nev, "kifli_id": valasztott["id"],
            "kifli_nev": valasztott["nev"],
            "amount_value": valasztott.get("mennyiseg"),
            "amount_unit": valasztott.get("egyseg"),
            "bulk": p.kimert_e(valasztott), "mennyiseg": norm.get("quantity"),
            "forras": "uj"}


def kosar_kiir(kosar):
    if not kosar:
        print(f"\n{HA}A kosar meg ures.{ALAP}")
        return
    print(f"\n{Z}A kosarban ({len(kosar)}){ALAP}")
    for s in kosar:
        db, tobblet, mj = szinkron_darabszam(s)
        megj = f"  {S}({mj}){ALAP}" if mj else ""
        print(f"  {db}x {s['kifli_nev']}  {HA}<- {s['nyers']}{ALAP}{megj}")


def szinkron_darabszam(sor):
    """A szinkron.py darabszam fuggvenyet hasznaljuk, hogy egy helyen legyen."""
    import szinkron
    return szinkron.darabszam(sor.get("mennyiseg"), sor.get("amount_value"),
                              sor.get("amount_unit"), sor.get("bulk", False))


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Hianyzik a GEMINI_API_KEY.")

    tarolo = adat.Tarolo("kifli.db")
    kosar = []

    print(f"{SZ}Mondd a bevasarlolistat, egyesevel vagy tobbet egyszerre.{ALAP}")
    print(f"{HA}Parancsok: kosar | torold <nev> | kesz | kilep{ALAP}")

    with MCPKliens() as mcp:
        while True:
            bemenet = bekér("\n> ")
            if not bemenet:
                continue

            also = bemenet.lower()

            if also in PARANCSOK_KILEP:
                print("Kilepek, a kosar nem valtozott.")
                return
            if also == "kosar" or also == "kosár":
                kosar_kiir(kosar)
                continue
            if also.startswith(("torold", "töröld", "vedd le")):
                mit = bemenet.split(maxsplit=1)[-1].lower()
                elotte = len(kosar)
                kosar = [s for s in kosar
                         if mit not in s["product"]
                         and mit not in s["kifli_nev"].lower()]
                mond("Levettem." if len(kosar) < elotte else "Ilyet nem talaltam.")
                continue
            if also in PARANCSOK_KESZ:
                break

            # Tobb tetel egy mondatban is johet
            nyers_tetelek = [r.strip() for r in bemenet.replace(",", "\n").splitlines()
                             if r.strip()]
            try:
                normalizalt = llm.normalizal(nyers_tetelek)
            except llm.LLMHiba as e:
                mond("Nem ertettem, probald ujra.", f"  {HA}{e}{ALAP}")
                continue

            for nyers, norm in zip(nyers_tetelek, normalizalt):
                if (norm.get("confidence") or 1.0) < 0.5:
                    mond(f"Ezt nem ertem: {nyers}. Mit keressek helyette?")
                    csere = bekér()
                    if not csere or csere.lower() in PARANCSOK_KILEP:
                        continue
                    norm = {"product": csere.lower(), "quantity": norm.get("quantity")}
                    nyers = csere

                sor = termeket_javasol(nyers, norm, mcp, tarolo)
                if sor:
                    kosar.append(sor)
                    if sor["forras"] == "elozmeny":
                        db, _, _ = szinkron_darabszam(sor)
                        mond(f"{db} {sor['kifli_nev']}, a szokasos.")

        if not kosar:
            print("Ures a kosar, nincs mit betenni.")
            return

        kosar_kiir(kosar)
        mond(f"Osszesen {len(kosar)} tetel. Mehet a Kifli kosarba?")
        if igen_e(bekér()) is not True:
            print("Nem tettem be.")
            return

        tetelek = []
        for s in kosar:
            db, _, _ = szinkron_darabszam(s)
            tetelek.append({"product_id": s["kifli_id"], "quantity": db})
        mcp.hiv("add_to_cart", {"products": tetelek})
        print(f"{Z}Kosarba tettem. A fizetes a Kifli appban.{ALAP}")

    tarolo.close()


if __name__ == "__main__":
    main()
