#!/usr/bin/env python3
"""
A Kifli MCP valaszait strukturalt adatta alakitja.

A hivatalos szerver JSON-t ad; a regi rohlik-mcp ember altal olvashato
szoveget. Mindket formatumot ez a modul ertelmezi - ha a szerver
valtozik, ez az egyetlen javitasi pont.
"""

import json
import re


def _json_adat(szoveg):
    """JSON objektum, vagy None, ha a bemenet sima szoveg."""
    if isinstance(szoveg, (dict, list)):
        return szoveg
    if not isinstance(szoveg, str):
        return None
    s = szoveg.strip()
    if not s or s[0] not in "{[":
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _mag(adat):
    """Lefejti a {result: {data: ...}} burkolatot, ha van."""
    if not isinstance(adat, dict):
        return adat
    belso = adat.get("result")
    if isinstance(belso, dict) and (
            "results" in belso or "products" in belso or "data" in belso
            or "items" in belso or "frequent_items" in belso
            or "xtra" in belso or "address" in belso
            or "categories" in belso or "success" in belso):
        return _mag(belso)
    belso = adat.get("data")
    if isinstance(belso, dict) and (
            "items" in belso or "products" in belso or "address" in belso
            or "xtra" in belso or "categories" in belso):
        return belso
    return adat


def _kiszereles_szovegbol(szoveg):
    """'1 l' / '10 db' / 'kb. 120 g' -> (mennyiseg, egyseg)."""
    t = re.search(r"(?:kb\.?\s*)?([\d.,]+)\s*(\S+)", szoveg or "")
    if not t:
        return None, None
    return _szam(t.group(1)), t.group(2).strip().lower()


def _termek_mezok(t):
    """Egy hivatalos MCP termekobjektum a belso formatumra."""
    if not isinstance(t, dict):
        return None
    pid = t.get("productId", t.get("product_id", t.get("id")))
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    nev = t.get("productName") or t.get("name") or t.get("nev")
    if not nev:
        return None
    ar = t.get("price")
    if isinstance(ar, dict):
        ar = ar.get("full") or ar.get("amount")
    eredeti = t.get("originalPrice") or t.get("originalPricePerUnit")
    kedvezmeny = t.get("salePercents") or t.get("discount")
    if kedvezmeny not in (None, 0, 0.0):
        try:
            kedvezmeny = -abs(int(kedvezmeny))
        except (TypeError, ValueError):
            kedvezmeny = None
    else:
        kedvezmeny = None
    if kedvezmeny is None:
        for b in t.get("badges") or []:
            m = re.search(r"(-\d+)\s*%", str(b))
            if m:
                kedvezmeny = int(m.group(1))
                break
    ppu = t.get("pricePerUnit")
    egysegar = None
    if isinstance(ppu, dict):
        egysegar = ppu.get("full", ppu.get("price"))
    elif isinstance(ppu, (int, float)):
        egysegar = ppu
    textual = t.get("textualAmount") or t.get("volume") or ""
    mennyiseg, egyseg = _kiszereles_szovegbol(textual)
    marka = t.get("brand")
    if marka in (None, "", "null"):
        marka = None
    return {
        "nev": nev, "marka": marka, "ar": ar, "eredeti_ar": eredeti,
        "kedvezmeny": kedvezmeny, "egysegar": egysegar,
        "egysegar_egyseg": egyseg, "mennyiseg": mennyiseg, "egyseg": egyseg,
        "id": pid,
    }


def termekek_jsonbol(adat):
    """Hivatalos kereses / akcio JSON -> termeklista."""
    mag = _mag(adat)
    nyers = []
    if isinstance(mag, list):
        nyers = mag
    elif isinstance(mag, dict):
        if mag.get("results"):
            for r in mag["results"]:
                nyers.extend((r or {}).get("products") or [])
        elif mag.get("products"):
            nyers = mag["products"]
        elif mag.get("items"):
            items = mag["items"]
            nyers = list(items.values()) if isinstance(items, dict) else items
    termekek = []
    for t in nyers:
        mezok = _termek_mezok(t)
        if mezok:
            if (mezok["kedvezmeny"] is None and mezok["eredeti_ar"]
                    and mezok["ar"] and mezok["eredeti_ar"] > 0):
                arany = ((mezok["ar"] - mezok["eredeti_ar"])
                         / mezok["eredeti_ar"])
                mezok["kedvezmeny"] = round(arany * 100)
            termekek.append(mezok)
    return termekek

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
    tiszta = str(szoveg).replace("\u00a0", "").replace(" ", "")
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
    A hivatalos MCP JSON-jat is elfogadja.
    """
    json_adat = _json_adat(szoveg)
    if json_adat is not None:
        return termekek_jsonbol(json_adat)

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


def gyakori_jsonbol(adat):
    """Hivatalos get_typical_order JSON -> [{id, nev, rendelesek}]."""
    mag = _mag(adat)
    nyers = []
    if isinstance(mag, dict):
        if mag.get("frequent_items"):
            nyers = mag["frequent_items"]
        elif isinstance(mag.get("items"), dict):
            for kulcs, t in mag["items"].items():
                if isinstance(t, dict):
                    nyers.append({**t, "product_id": t.get("product_id") or kulcs})
        elif isinstance(mag.get("items"), list):
            nyers = mag["items"]
    tetelek = []
    for t in nyers:
        if not isinstance(t, dict):
            continue
        pid = t.get("product_id", t.get("productId", t.get("id")))
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        nev = t.get("name") or t.get("productName") or t.get("nev")
        if not nev:
            continue
        tetelek.append({
            "id": pid, "nev": nev,
            "kategoria": t.get("category"),
            "rendelesek": t.get("frequency") or t.get("rendelesek"),
        })
    return tetelek


def gyakori_ertelmez(szoveg):
    """A get_frequent_items / get_typical_order kimenetet listava alakitja."""
    json_adat = _json_adat(szoveg)
    if json_adat is not None:
        return gyakori_jsonbol(json_adat)

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


# ── A tobbi MCP-valasz ertelmezese ──────────────────────────────────
# Ezek korabban az Asszisztensben eltek, pedig ha a szerver formatuma
# valtozik, ennek a modulnak kell az egyetlen javitasi pontnak maradnia.

RE_KATEGORIA = re.compile(r"[•\-\*]\s*(.+?)\s*\(ID:\s*(\d+)\)")


def kosar_jsonbol(adat):
    """Hivatalos get_cart JSON -> {tetelek, osszesen, rendelheto}."""
    mag = _mag(adat)
    if isinstance(mag, list):
        mag = mag[0] if mag else {}
    items = mag.get("items") if isinstance(mag, dict) else None
    if isinstance(items, dict):
        nyers = list(items.values())
    elif isinstance(items, list):
        nyers = items
    else:
        nyers = []
    tetelek = []
    for t in nyers:
        if not isinstance(t, dict):
            continue
        pid = t.get("productId") or t.get("product_id")
        cart_id = t.get("orderFieldId") or t.get("cart_item_id") or pid
        nev = t.get("productName") or t.get("name")
        if not nev or cart_id is None:
            continue
        tetelek.append({
            "nev": nev,
            "marka": t.get("brand"),
            "darab": int(t.get("quantity") or 1),
            "ar": t.get("price"),
            "kategoria": t.get("primaryCategoryName") or t.get("category"),
            "cart_item_id": str(cart_id),
            "product_id": int(pid) if pid is not None else None,
        })
    osszesen = mag.get("totalPrice") if isinstance(mag, dict) else None
    rendelheto = mag.get("submitConditionPassed") if isinstance(mag, dict) else None
    return {"tetelek": tetelek, "osszesen": osszesen,
            "rendelheto": rendelheto}


def kosar_ertelmez(nyers):
    """
    A kosar ertelmezese.

    A hivatalos MCP JSON-t ad; a regi szerver szoveget, ahol a
    'Cart ID' kell a remove_from_cart-hoz - NEM a termek ID-ja.
    """
    json_adat = _json_adat(nyers)
    if json_adat is not None:
        return kosar_jsonbol(json_adat)

    tetelek = []
    osszesen = None
    rendelheto = None
    aktualis = None
    termeklistaban = False

    def lezar():
        if aktualis and aktualis.get("cart_item_id"):
            tetelek.append(aktualis)

    for sor in (nyers or "").splitlines():
        csupasz = sor.strip()
        if not csupasz:
            continue

        t = re.search(r"Total price:\s*([\d\s.,]+?)\s*(?:HUF|Ft)", csupasz, re.I)
        if t:
            osszesen = _szam(t.group(1))
            continue
        t = re.search(r"Can order:\s*(\w+)", csupasz, re.I)
        if t:
            rendelheto = t.group(1).strip().lower() in ("yes", "true", "igen")
            continue
        if re.search(r"Products in cart", csupasz, re.I):
            termeklistaban = True
            continue

        if csupasz.startswith(("•", "-", "*")) and termeklistaban:
            lezar()
            fej = csupasz.lstrip("•-* ").strip()
            marka = None
            t = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", fej)
            if t:
                fej, marka = t.group(1).strip(), t.group(2).strip()
            aktualis = {"nev": fej, "marka": marka, "darab": 1,
                        "ar": None, "kategoria": None, "cart_item_id": None}
            continue

        if aktualis is None:
            continue

        t = re.search(r"Quantity:\s*(\d+)", csupasz, re.I)
        if t:
            aktualis["darab"] = int(t.group(1))
        t = re.search(r"Price:\s*([\d\s.,]+?)\s*(?:HUF|Ft)", csupasz, re.I)
        if t:
            aktualis["ar"] = _szam(t.group(1))
        t = re.search(r"Category:\s*(.+)$", csupasz, re.I)
        if t:
            aktualis["kategoria"] = t.group(1).strip()
        t = re.search(r"Cart ID:\s*(\d+)", csupasz, re.I)
        if t:
            aktualis["cart_item_id"] = t.group(1)

    lezar()
    return {"tetelek": tetelek, "osszesen": osszesen,
            "rendelheto": rendelheto}


def elofizetes_ertelmez(nyers):
    """A get_premium_info / get_user_info kimenetebol a lenyeg."""
    adatok = {"aktiv": None}
    if not nyers:
        return adatok

    json_adat = _json_adat(nyers)
    if json_adat is not None:
        mag = _mag(json_adat)
        xtra = mag.get("xtra") if isinstance(mag, dict) else None
        if not isinstance(xtra, dict):
            xtra = mag.get("premium") if isinstance(mag, dict) else None
        if isinstance(xtra, dict):
            adatok["aktiv"] = bool(xtra.get("active"))
            if xtra.get("membership_type"):
                adatok["tipus"] = xtra["membership_type"]
            if xtra.get("active_until"):
                adatok["lejar"] = xtra["active_until"]
            if xtra.get("remaining_days") is not None:
                adatok["maradt"] = xtra["remaining_days"]
        elif isinstance(mag, dict) and mag.get("active") is not None:
            adatok["aktiv"] = bool(mag["active"])
        return adatok

    t = re.search(r"PREMIUM STATUS:\s*(\w+)", nyers, re.I)
    if t:
        adatok["aktiv"] = t.group(1).strip().lower() == "active"
    t = re.search(r"Type:\s*(.+)", nyers)
    if t:
        adatok["tipus"] = t.group(1).strip()
    t = re.search(r"End:\s*(.+)", nyers)
    if t:
        adatok["lejar"] = t.group(1).strip()

    for minta, kulcs in (
            (r"(?:free\s*delivery|ingyenes).*?(\d+)", "ingyenes_szallitas"),
            (r"(?:express|expressz).*?(\d+)", "expressz"),
            (r"remaining[^\d]*(\d+)", "maradt")):
        t = re.search(minta, nyers, re.I)
        if t:
            adatok[kulcs] = int(t.group(1))
    return adatok


def cim_ertelmez(nyers):
    """A get_account_data kimenetebol a szallitasi cim."""
    adatok = {}
    if not nyers:
        return adatok

    try:
        json_adat = json.loads(nyers)

        def bejar(csomo):
            if isinstance(csomo, dict):
                if csomo.get("fullAddress"):
                    adatok.setdefault("cim", csomo["fullAddress"])
                    adatok.setdefault("varos", csomo.get("city"))
                    return
                for e in csomo.values():
                    bejar(e)
            elif isinstance(csomo, list):
                for e in csomo:
                    bejar(e)

        bejar(json_adat)
    except (json.JSONDecodeError, TypeError):
        pass

    if not adatok.get("cim"):
        for minta, kulcs in (
                (r'"?fullAddress"?\s*[:=]\s*"?([^",\n]+)', "cim"),
                (r"(?:Address|Cim|Cím)\s*[:=]\s*(.+)", "cim"),
                (r'"?city"?\s*[:=]\s*"?([^",\n]+)', "varos")):
            t = re.search(minta, nyers, re.I)
            if t:
                adatok[kulcs] = t.group(1).strip()
    return adatok


def idosavok_ertelmez(nyers):
    """
    A get_delivery_slots valaszanak ertelmezese.

    A valasz NEM tiszta JSON: egy szoveges fejlec elozi meg, ezert a
    JSON-t ki kell vagni belole.
    """
    if not nyers:
        return []

    eleje = nyers.find("{")
    vege = nyers.rfind("}")
    if eleje == -1 or vege == -1:
        return []
    try:
        adatok = json.loads(nyers[eleje:vege + 1])
    except json.JSONDecodeError:
        return []

    talalt = {}

    def sav_felvesz(csomo, cimke=None):
        kapacitas = csomo.get("timeSlotCapacityDTO") or {}
        uzenet = (kapacitas.get("capacityMessage") or "").lower()
        if csomo.get("capacity") == "RED" or uzenet in ("elkelt", "megtelt"):
            return
        if (kapacitas.get("totalFreeCapacityPercent") or 0) <= 0:
            return

        azonosito = csomo.get("slotId")
        if azonosito in talalt:
            if cimke and not talalt[azonosito].get("cimke"):
                talalt[azonosito]["cimke"] = cimke
            return

        talalt[azonosito] = {
            "nap": str(csomo.get("since", ""))[:10],
            "ido": csomo.get("timeWindow")
                   or f"{str(csomo.get('since'))[11:16]}-"
                      f"{str(csomo.get('till'))[11:16]}",
            "ar": csomo.get("price", 0),
            "tipus": csomo.get("type"),
            "premium": bool(csomo.get("premium")),
            "eco": bool(csomo.get("eco")),
            "szabad": kapacitas.get("capacityMessage"),
        }
        if cimke:
            talalt[azonosito]["cimke"] = cimke

    def bejar(csomo, cimke=None):
        if isinstance(csomo, dict):
            if "slot" in csomo and isinstance(csomo["slot"], dict):
                alcim = (csomo.get("title") or "").strip()
                bejar(csomo["slot"], alcim or cimke)
                return
            if "slotId" in csomo and "since" in csomo:
                sav_felvesz(csomo, cimke)
                return
            for kulcs, ertek in csomo.items():
                alcimke = ("Expressz" if kulcs == "expressSlot" else cimke)
                bejar(ertek, alcimke)
        elif isinstance(csomo, list):
            for elem in csomo:
                bejar(elem, cimke)

    bejar(adatok)
    return sorted(talalt.values(), key=lambda s: (s["nap"], s["ido"]))


def akcio_kategoriak_ertelmez(szoveg):
    """A get_discounted_items list_categories=True kimenete."""
    json_adat = _json_adat(szoveg)
    if json_adat is not None:
        mag = _mag(json_adat)
        kategoriak = []
        for k in (mag.get("categories") or []) if isinstance(mag, dict) else []:
            if isinstance(k, dict) and k.get("id") is not None:
                kategoriak.append({
                    "nev": (k.get("name") or k.get("nev") or "").strip(),
                    "id": int(k["id"]),
                })
        return kategoriak

    kategoriak = []
    for sor in (szoveg or "").splitlines():
        t = RE_KATEGORIA.search(sor)
        if t:
            kategoriak.append({"nev": t.group(1).strip(),
                               "id": int(t.group(2))})
    return kategoriak
