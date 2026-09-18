#!/usr/bin/env python3
"""
A rohlik-mcp szoveges valaszait strukturalt adatta alakitja.

A szerver ember altal olvashato szoveget ad vissza, nem JSON-t, ezert
sorrol sorra kell ertelmezni. Ha a szerver formatuma valtozik, ez a
modul az egyetlen hely, amit modositani kell.
"""

import re

# "• Magyar Tej ESL Tej 2,8% (Magyar)"
# "• Coca-Cola ... multipack (2x1,75l) (-33 % mai szállítással)"
RE_TERMEK_FEJ = re.compile(r"^\s*[•\-\*]\s*(.+?)\s*(?:\(([^)]*)\))?\s*$")
# "Price: 413.1 Ft (was 459 Ft, -10%)"   -> search_products
# "Price: 999 HUF (was 1499 HUF)"        -> get_discounted_items
RE_AR = re.compile(
    r"Price:\s*([\d.,\s]+?)\s*(?:Ft|HUF)"
    r"(?:\s*\(was\s*([\d.,\s]+?)\s*(?:Ft|HUF)(?:\s*,\s*(-?\d+)\s*%)?\s*\))?",
    re.IGNORECASE)
# "Unit price: 285.43 HUF/l"
RE_EGYSEGAR = re.compile(r"Unit price:\s*([\d.,\s]+?)\s*(?:Ft|HUF)\s*/\s*(\S+)",
                         re.IGNORECASE)
# A get_discounted_items a szazalekot a NEVBE teszi: "(-33 % mai szállítással)"
RE_NEV_KEDVEZMENY = re.compile(r"\(\s*(-\d+)\s*%[^)]*\)")
# "  Amount: 1 l" / "Amount: 400 g" / "Amount: kb. 120 g" / "Amount: 3,5 l"
RE_MENNYISEG = re.compile(r"Amount:\s*(?:kb\.?\s*)?([\d.,]+)\s*(\S+)")
# "  ID: 16321"  vagy  "   🆔 1417"
RE_ID = re.compile(r"(?:ID:|🆔)\s*(\d+)")
# "1. Coca-Cola ... • Uncategorized"
RE_GYAKORI_FEJ = re.compile(r"^\s*\d+\.\s*(.+?)\s*•\s*(.*)$")
# "   📊 9× orders • 9 units"
RE_GYAKORISAG = re.compile(r"(\d+)×\s*orders")


def _szam(szoveg):
    """'413.1', '1,5' vagy '1 499' -> float. None, ha nem ertelmezheto."""
    if szoveg is None:
        return None
    tiszta = szoveg.replace("\u00a0", "").replace(" ", "")
    # Magyar tizedesvesszo: csak akkor pont, ha nincs mar pont a szamban
    if "," in tiszta and "." not in tiszta:
        tiszta = tiszta.replace(",", ".")
    else:
        tiszta = tiszta.replace(",", "")
    try:
        return float(tiszta)
    except ValueError:
        return None


def termekek_ertelmez(szoveg):
    """
    A search_products ES a get_discounted_items kimenetet is ertelmezi.
    A ket vegpont mas formatumot ad, ezert mindketto eseteit kezeli.
    """
    termekek = []
    aktualis = None

    def lezar():
        if not aktualis or not aktualis.get("id"):
            return
        # Ha nem volt explicit szazalek, szamoljuk az arakbol
        if (aktualis["kedvezmeny"] is None and aktualis["eredeti_ar"]
                and aktualis["ar"] and aktualis["eredeti_ar"] > 0):
            arany = (aktualis["ar"] - aktualis["eredeti_ar"]) / aktualis["eredeti_ar"]
            aktualis["kedvezmeny"] = round(arany * 100)
        termekek.append(aktualis)

    for sor in szoveg.splitlines():
        csupasz = sor.strip()
        if not csupasz:
            continue

        if csupasz.startswith(("•", "-", "*")) and "Price:" not in csupasz:
            lezar()
            talalat = RE_TERMEK_FEJ.match(csupasz)
            if not talalat:
                aktualis = None
                continue

            nev = talalat.group(1).strip()
            zarojelben = talalat.group(2)

            # A get_discounted_items a szazalekot a nevbe teszi
            kedvezmeny = None
            nev_szazalek = RE_NEV_KEDVEZMENY.search(csupasz)
            if nev_szazalek:
                kedvezmeny = int(nev_szazalek.group(1))
                if zarojelben and nev_szazalek.group(0) == f"({zarojelben})":
                    zarojelben = None  # ez nem marka volt, hanem az akcio
                nev = RE_NEV_KEDVEZMENY.sub("", nev).strip()

            aktualis = {
                "nev": nev,
                "marka": None if zarojelben in (None, "null") else zarojelben,
                "ar": None, "eredeti_ar": None, "kedvezmeny": kedvezmeny,
                "egysegar": None, "egysegar_egyseg": None,
                "mennyiseg": None, "egyseg": None, "id": None,
            }
            continue

        if aktualis is None:
            continue

        t = RE_EGYSEGAR.search(csupasz)
        if t:
            aktualis["egysegar"] = _szam(t.group(1))
            aktualis["egysegar_egyseg"] = t.group(2).strip().lower()
            continue

        t = RE_AR.search(csupasz)
        if t:
            aktualis["ar"] = _szam(t.group(1))
            aktualis["eredeti_ar"] = _szam(t.group(2))
            if t.group(3):
                aktualis["kedvezmeny"] = int(t.group(3))

        t = RE_MENNYISEG.search(csupasz)
        if t:
            aktualis["mennyiseg"] = _szam(t.group(1))
            aktualis["egyseg"] = t.group(2).strip().lower()

        t = RE_ID.search(csupasz)
        if t:
            aktualis["id"] = int(t.group(1))

    lezar()
    return termekek


def gyakori_ertelmez(szoveg):
    """A get_frequent_items kimenetet listava alakitja."""
    tetelek = []
    aktualis = None

    for sor in szoveg.splitlines():
        csupasz = sor.strip()
        if not csupasz:
            continue

        t = RE_GYAKORI_FEJ.match(csupasz)
        if t and not csupasz.startswith(("📊", "🆔")):
            if aktualis and aktualis.get("id"):
                tetelek.append(aktualis)
            kategoria = t.group(2).strip()
            aktualis = {
                "nev": t.group(1).strip(),
                "kategoria": None if kategoria == "Uncategorized" else kategoria,
                "rendelesek": None, "id": None,
            }
            continue

        if aktualis is None:
            continue

        t = RE_GYAKORISAG.search(csupasz)
        if t:
            aktualis["rendelesek"] = int(t.group(1))

        t = RE_ID.search(csupasz)
        if t:
            aktualis["id"] = int(t.group(1))

    if aktualis and aktualis.get("id"):
        tetelek.append(aktualis)
    return tetelek


def kimert_e(termek):
    """Igaz, ha a termek suly szerint megy (hus, zoldseg), nem darabra."""
    nev = (termek.get("nev") or "").lower()
    if "lédig" in nev or "ledig" in nev:
        return True
    if termek.get("egyseg") in ("kg",) and (termek.get("mennyiseg") or 0) == 1:
        return True
    return False
