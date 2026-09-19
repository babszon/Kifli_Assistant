#!/usr/bin/env python3
"""
Funkcionalis tesztek - halozat nelkul, hamis MCP szerverrel.

    python3 tesztek.py

Minden modul valodi kodutjait jarja vegig, a Kifli tenyleges
valaszformatumaival. Ha ez zold, az app mukodokepes.
"""

import json
import sys
import tempfile
import threading
from pathlib import Path

Z, PI, S, HA, ALAP = "\033[92m", "\033[91m", "\033[93m", "\033[90m", "\033[0m"

eredmenyek = []


def teszt(nev):
    def dekorator(fuggveny):
        try:
            fuggveny()
            eredmenyek.append((True, nev, ""))
            print(f"  {Z}✓{ALAP} {nev}")
        except AssertionError as e:
            eredmenyek.append((False, nev, str(e)))
            print(f"  {PI}✗{ALAP} {nev}\n      {e}")
        except Exception as e:
            eredmenyek.append((False, nev, f"{type(e).__name__}: {e}"))
            print(f"  {PI}✗{ALAP} {nev}\n      {type(e).__name__}: {e}")
        return fuggveny
    return dekorator


def fejezet(cim):
    print(f"\n{cim}")


# ─────────────────────────────────────────────── valódi Kifli válaszok

KERESES = """Found 4 products:

• Magyar Tej ESL Tej 2,8% (Magyar)
  Price: 397 Ft
  Amount: 1 l
  ID: 16321

• Miil ESL teljes tej 3,5% zsírtartalommal (Miil)
  Price: 413.1 Ft (was 459 Ft, -10%)
  Amount: 1 l
  ID: 97506

• "A" minőségű Farm Prémium Mélyalmos Tojás "M" méret (Farm)
  Price: 839 Ft
  Amount: 10 db
  ID: 30553

• Étkezési paprika, lédig (null)
  Price: 105.09 Ft
  Unit price: 899 Ft/kg
  Amount: kb. 120 g
  ID: 72883"""

AKCIOK = """Found 3 all deals (page 0):

• Coca-Cola colaízű szénsavas üdítőital multipack (2x1,75l) (-33 % mai szállítással)
  Price: 999 HUF (was 1499 HUF)
  Unit price: 285.43 HUF/l
  Amount: 3,5 l
  ID: 1417

• "B" típusú piros héjú újburgonya, csomagolt (-30 % 9. 20. -ig)
  Price: 356.3 HUF (was 509 HUF)
  Unit price: 712.6 HUF/kg
  Amount: 500 g
  ID: 72956

• Magyar kerek paradicsom
  Price: 105.09 HUF
  Unit price: 899 HUF/kg
  Amount: kb. 120 g
  ID: 24526"""

KOSAR = """Cart Summary:
• Total items: 3
• Total price: 6067 HUF
• Can order: No

Products in cart:
• "A" minőségű Farm Prémium Mélyalmos Tojás "M" méret (Farm Tojás)
  Quantity: 2
  Price: 1678 HUF
  Category: Tejtermék és tojás
  Cart ID: 123456789

• Kitchin Extra szűz olívaolaj (Kitchin)
  Quantity: 1
  Price: 4629 HUF
  Category: Tartós élelmiszer
  Cart ID: 123456110

• Házi vekni (Rádi)
  Quantity: 1
  Price: 599 HUF
  Category: Pékség és cukrászat
  Cart ID: 123456615"""

GYAKORI = """🛒 MOST FREQUENTLY PURCHASED ITEMS

1. Coca-Cola colaízű szénsavas üdítőital multipack (2x1,75l) • Uncategorized
   📊 9× orders • 9 units
   🆔 1417

2. Jacobs Classico Lungo (6) - Nespresso kávékapszula • Uncategorized
   📊 8× orders • 8 units
   🆔 60476"""

KATEGORIAK = """Available sales categories:

• Ments meg! (ID: 300118)
• Akció a hét minden napján (ID: 300119)
• Tejtermék és tojás (ID: 300120)"""

PREMIUM = """⭐ PREMIUM STATUS: Active

📅 SUBSCRIPTION:
   Type: MONTHLY
   Start: 2026. aug. 23.
   End: 2026. szept. 22.

🎁 BENEFITS:
   • Free delivery: 4 remaining
   • Express delivery: 3 remaining"""

FIOK = json.dumps({
    "delivery": {"address": {
        "id": 6236413, "fullAddress": "Példa utca 1, 1011 Budapest",
        "city": "Budapest", "postalCode": "1011"}},
    "cart": {"total_price": 6067, "can_make_order": False},
})

# A valodi Kifli valasz: szoveges fejlec + JSON, kulon expressSlot es
# cimkezett preselectedSlots
IDOSAVOK = "⏰ DELIVERY SLOTS:\n" + json.dumps({
    "announcements": [],
    "expressSlot": {
        "slotId": 273103, "type": "EXPRESS",
        "since": "2026-09-19 11:45", "till": "2026-09-19 12:00",
        "premium": False, "eco": False, "capacity": "GREEN",
        "timeSlotCapacityDTO": {"totalFreeCapacityPercent": 0,
                                "capacityMessage": "Elkelt"},
        "price": 0, "timeWindow": "11:45 – 12:00"},
    "preselectedSlots": [{
        "title": "Leggyorsabb hagyományos",
        "slot": {
            "slotId": 273099, "type": "ON_TIME",
            "since": "2026-09-19 12:45", "till": "2026-09-19 13:00",
            "premium": False, "eco": False, "capacity": "GREEN",
            "timeSlotCapacityDTO": {"totalFreeCapacityPercent": 82,
                                    "capacityMessage": "Szabad"},
            "price": 0, "timeWindow": "12:45 – 13:00"}}],
    "slots": [{"days": [{"slots": [
        {"slotId": 273099, "type": "ON_TIME", "since": "2026-09-19 12:45",
         "till": "2026-09-19 13:00", "premium": False, "eco": False,
         "capacity": "GREEN", "price": 0, "timeWindow": "12:45 – 13:00",
         "timeSlotCapacityDTO": {"totalFreeCapacityPercent": 82,
                                 "capacityMessage": "Szabad"}},
        {"slotId": 273200, "type": "ON_TIME", "since": "2026-09-19 20:00",
         "till": "2026-09-19 22:00", "premium": True, "eco": False,
         "capacity": "GREEN", "price": 490, "timeWindow": "20:00 – 22:00",
         "timeSlotCapacityDTO": {"totalFreeCapacityPercent": 95,
                                 "capacityMessage": "Szabad"}},
        {"slotId": 273300, "type": "ON_TIME", "since": "2026-09-20 08:00",
         "till": "2026-09-20 10:00", "premium": False, "eco": False,
         "capacity": "RED", "price": 0, "timeWindow": "08:00 – 10:00",
         "timeSlotCapacityDTO": {"totalFreeCapacityPercent": 0,
                                 "capacityMessage": "Megtelt"}},
    ]}]}],
})



class HamisMCP:
    """A valodi Kifli valaszformatumaival."""

    def __init__(self, kosar=KOSAR):
        self.kosar = kosar
        self.naplo = []
        self.hibas_toolok = set()

    def hiv(self, nev, args=None):
        self.naplo.append((nev, args))
        if nev in self.hibas_toolok:
            from mcp_kliens import MCPHiba
            raise MCPHiba(f"{nev}: szandekos hiba")
        if nev == "get_discounted_items" and (args or {}).get("list_categories"):
            return KATEGORIAK
        return {
            "search_products": KERESES,
            "get_discounted_items": AKCIOK,
            "get_cart_content": self.kosar,
            "get_frequent_items": GYAKORI,
            "get_delivery_slots": IDOSAVOK,
            "get_order_history": "Rendelesek:\n1. 2026-09-10 - ID: 88001",
            "get_order_detail": "Rendeles 88001:\n• Tej 2x",
            "get_upcoming_orders": "Nincs beutemezett rendeles.",
            "get_meal_suggestions": "Reggeli:\n• Kenyér\n• Tojás",
            "get_premium_info": PREMIUM,
            "_kategoriak": KATEGORIAK,
            "get_account_data": FIOK,
        }.get(nev, "ok")


def uj_asszisztens(mcp=None, szaraz=False):
    import adat
    import asszisztens as asz
    return asz.Asszisztens(mcp or HamisMCP(), adat.Tarolo(":memory:"), szaraz)


# ───────────────────────────────────────────────────────── parserek

fejezet("Parserek")


@teszt("kereses: nev, ar, kedvezmeny, kiszereles, ID")
def _():
    import parser as p
    t = p.termekek_ertelmez(KERESES)
    assert len(t) == 4, f"{len(t)} termek, 4 kellene"
    tej = t[0]
    assert tej["id"] == 16321 and tej["ar"] == 397.0
    assert tej["mennyiseg"] == 1 and tej["egyseg"] == "l"
    assert t[1]["kedvezmeny"] == -10, t[1]
    assert t[2]["egyseg"] == "db" and t[2]["mennyiseg"] == 10
    assert t[3]["mennyiseg"] == 120, "a 'kb.' elotag zavart"


@teszt("akciok: HUF, nevbe agyazott szazalek, egysegar")
def _():
    import parser as p
    t = p.termekek_ertelmez(AKCIOK)
    assert len(t) == 3
    kola = t[0]
    assert kola["id"] == 1417 and kola["ar"] == 999.0
    assert kola["kedvezmeny"] == -33, "a nevbe agyazott szazalek"
    assert "-33" not in kola["nev"], "a szazalek bent maradt a nevben"
    assert kola["mennyiseg"] == 3.5, "magyar tizedesvesszo"
    assert t[2]["kedvezmeny"] is None, "nincs kedvezmeny, megis lett"


@teszt("kosar: Cart ID, darab, rendelhetoseg")
def _():
    import asszisztens as asz
    r = asz.Asszisztens._kosar_ertelmez(KOSAR)
    assert len(r["tetelek"]) == 3
    assert r["osszesen"] == 6067
    assert r["rendelheto"] is False
    assert r["tetelek"][0]["cart_item_id"] == "123456789", "NEM a termek ID"
    assert r["tetelek"][0]["darab"] == 2


@teszt("gyakori tetelek")
def _():
    import parser as p
    g = p.gyakori_ertelmez(GYAKORI)
    assert len(g) == 2 and g[0]["id"] == 1417
    assert g[0]["rendelesek"] == 9


@teszt("idosavok: szoveges fejlec, betelt savok, cimkek")
def _():
    import asszisztens as asz
    s = asz.Asszisztens._idosavok_ertelmez(IDOSAVOK)
    # A valasz nem tiszta JSON - a fejlec nem akaszthatja meg
    assert s, "a szoveges fejlec miatt nem ertelmezte a JSON-t"
    assert len(s) == 2, f"{len(s)} sav, 2 kellene"
    idok = [x["ido"] for x in s]
    assert "11:45 – 12:00" not in idok, "az Elkelt expressz bekerult"
    assert "08:00 – 10:00" not in idok, "a Megtelt sav bekerult"
    # ugyanaz a slotId ketszer szerepel, csak egyszer kerulhet be
    assert len([x for x in s if x["ido"] == "12:45 – 13:00"]) == 1
    cimkezett = next(x for x in s if x["ido"] == "12:45 – 13:00")
    assert cimkezett["cimke"] == "Leggyorsabb hagyományos"
    assert any(x["premium"] for x in s), "a premium jelzes elveszett"


@teszt("ertelmetlen bemenet nem szall el")
def _():
    import asszisztens as asz
    import parser as p
    for rossz in ("", "   ", "nem json", "{}", "• csonka"):
        p.termekek_ertelmez(rossz)
        p.gyakori_ertelmez(rossz)
        asz.Asszisztens._kosar_ertelmez(rossz)
        asz.Asszisztens._idosavok_ertelmez(rossz)


# ──────────────────────────────────────────────────────── egysegar

fejezet("Egysegar")


@teszt("kulonbozo egysegek nem keverednek")
def _():
    import arak
    r = arak.rangsorol([
        {"nev": "Tej 1l", "ar": 397, "mennyiseg": 1, "egyseg": "l", "id": 1},
        {"nev": "Sajt 400g", "ar": 1200, "mennyiseg": 400, "egyseg": "g", "id": 2},
        {"nev": "Tojás 10db", "ar": 999, "mennyiseg": 10, "egyseg": "db", "id": 3},
    ])
    egysegek = {t["id"]: t["alapegyseg"] for t in r}
    assert egysegek == {1: "l", 2: "kg", 3: "db"}, egysegek


@teszt("a Kifli sajat egysegara elsobbseget elvez")
def _():
    import arak
    t = {"ar": 356.3, "mennyiseg": 500, "egyseg": "g",
         "egysegar": 712.6, "egysegar_egyseg": "kg"}
    ar, egys = arak.egysegar(t)
    assert abs(ar - 712.6) < 0.1 and egys == "kg", (ar, egys)


@teszt("hianyzo adat nem szall el")
def _():
    import arak
    assert arak.egysegar({}) == (None, None)
    assert arak.rangsorol([]) == []
    r = arak.rangsorol([{"nev": "X", "ar": None, "id": 1}])
    assert r[0]["egysegar_szamitott"] is None


# ─────────────────────────────────────────────────────── darabszam

fejezet("Darabszam")


@teszt("a veszelyes esetek")
def _():
    import szinkron
    esetek = [
        # (mennyiseg, csomag_ertek, csomag_egyseg, bulk) -> vart darab
        (({"kind": "piece", "value": 30}, 10, "db", False), 3,
         "30 tojas 10-es dobozbol = 3 doboz, NEM 30"),
        (({"kind": "weight", "value": 500}, 1, "kg", True), 1,
         "kimert aru: 1 egyseg, NEM 500"),
        (({"kind": "volume", "value": 2000, "unit": "ml"}, 1, "l", False), 2,
         "ket liter tej"),
        (({"kind": "weight", "value": 300, "unit": "g"}, 400, "g", False), 1,
         "30 deka 400g-os kiszerelesbol"),
        (({"kind": "package", "value": 2}, 1, "l", False), 2, "ket doboz"),
        (({"kind": "unspecified", "value": None}, 1, "l", False), 1, "csak tej"),
        (({"kind": "weight", "value": 250, "unit": "g"}, None, None, False), 1,
         "ismeretlen kiszereles -> 1, nem hibas szam"),
        (({"kind": "piece", "value": 3}, 1, "db", False), 3, "harom citrom"),
    ]
    for (m, cv, cu, bulk), vart, cimke in esetek:
        db, _, _ = szinkron.darabszam(m, cv, cu, bulk)
        assert db == vart, f"{cimke}: {db} lett {vart} helyett"


@teszt("kimert arunal figyelmeztet")
def _():
    import szinkron
    _, _, mj = szinkron.darabszam(
        {"kind": "weight", "value": 500, "unit": "g"}, 1, "kg", True)
    assert mj and "kimert" in mj


# ─────────────────────────────────────────────────────── eszkozok

fejezet("Eszkozok")


@teszt("minden deklaralt eszkoznek van implementacioja")
def _():
    import asszisztens as asz
    a = uj_asszisztens()
    for e in asz.ESZKOZOK:
        assert hasattr(a, e["name"]), f"hianyzik: {e['name']}"
        for kulcs in ("name", "description", "parameters"):
            assert kulcs in e, f"{e.get('name')}: hianyzo {kulcs}"


@teszt("hivas() sosem dob kivetelt")
def _():
    a = uj_asszisztens()
    esetek = [
        ("nincs_ilyen_eszkoz", {}),
        ("termek_keres", {"rossz_parameter": 1}),
        ("termek_keres", {}),
        ("kosarba_tesz", {"kifli_id": "nem szam", "termek": "x"}),
        ("kosarbol_kivesz", {"termek": ""}),
        ("_kosar_ertelmez", {"nyers": "x"}),     # privat metodus nem hivhato
        ("etkezes_javaslat", {"etkezes": None}),
    ]
    for nev, args in esetek:
        r = a.hivas(nev, args)
        assert isinstance(r, dict), f"{nev}: {type(r)} jott vissza"
        json.dumps(r, ensure_ascii=False)   # kuldheto-e a modellnek


@teszt("MCP hiba hibauzenetkent jon vissza, nem kivetelkent")
def _():
    mcp = HamisMCP()
    mcp.hibas_toolok.add("search_products")
    a = uj_asszisztens(mcp)
    r = a.hivas("termek_keres", {"termek": "tej"})
    assert "hiba" in r, r


@teszt("a kiszereles NEM lesz darabszam (16 tekercses vecepapir)")
def _():
    # Ez volt a valodi hiba: a "16 tekercses vecepapir" nevbol a program
    # 16 CSOMAGOT tett be, pedig a 16 a kiszereles.
    kosar = KOSAR.replace('• Házi vekni (Rádi)',
                          '• Magyar Tej ESL Tej 2,8% (Magyar)')
    mcp = HamisMCP(kosar=kosar)
    a = uj_asszisztens(mcp)
    a.termek_keres("tej")
    mcp.naplo.clear()
    a.kosarba_tesz(16321, "16 tekercses vécépapír", darab=1)
    hivas = next(h for h in mcp.naplo if h[0] == "add_to_cart")
    db = hivas[1]["products"][0]["quantity"]
    assert db == 1, f"{db} csomag ment be 1 helyett"


@teszt("darabszam nelkul 1-et tesz be es szol")
def _():
    # A kosar tartalmazza a terméket, kulonben a betetel-ellenorzes
    # (helyesen) hibat jelezne
    kosar = KOSAR.replace('• Házi vekni (Rádi)',
                          '• Magyar Tej ESL Tej 2,8% (Magyar)')
    a = uj_asszisztens(HamisMCP(kosar=kosar))
    a.termek_keres("tej")
    r = a.kosarba_tesz(16321, "tej")
    assert "hiba" not in r, r
    assert r.get("darab") == 1
    assert "megjegyzes" in r, "nem szolt, hogy nem tudta a darabszamot"


@teszt("az LLM altal adott darabszam ervenyesul")
def _():
    kosar = KOSAR.replace('• Házi vekni (Rádi)',
                          '• Magyar Tej ESL Tej 2,8% (Magyar)')
    mcp = HamisMCP(kosar=kosar)
    a = uj_asszisztens(mcp)
    a.termek_keres("tej")
    mcp.naplo.clear()
    a.kosarba_tesz(16321, "tej", darab=3)
    hivas = next(h for h in mcp.naplo if h[0] == "add_to_cart")
    assert hivas[1]["products"][0]["quantity"] == 3


@teszt("ertelmetlen darabszam nem szall el")
def _():
    a = uj_asszisztens()
    a.termek_keres("tej")
    for rossz in ("sok", None, -5, 0, 2.7):
        r = a.kosarba_tesz(16321, "tej", darab=rossz)
        assert isinstance(r, dict)
        if "hiba" not in r and "darab" in r:
            assert r["darab"] >= 1, f"{rossz} -> {r['darab']}"


@teszt("mennyiseget_modosit: levesz es ujra betesz")
def _():
    mcp = HamisMCP()
    a = uj_asszisztens(mcp)
    a.termek_keres("tej")
    # A kosarban a "Házi vekni" van; keressuk meg elobb, hogy ismerjuk
    a.utolso_talalatok.append(
        {"id": 5611, "nev": "Házi vekni", "ar": 599,
         "mennyiseg": 500, "egyseg": "g"})
    mcp.naplo.clear()
    r = a.mennyiseget_modosit("vekni", 3)
    nevek = [h[0] for h in mcp.naplo]
    assert "remove_from_cart" in nevek and "add_to_cart" in nevek, nevek
    hozzaad = next(h for h in mcp.naplo if h[0] == "add_to_cart")
    assert hozzaad[1]["products"][0]["quantity"] == 3


@teszt("mennyiseget_modosit ismeretlen tetelre nem talalgat")
def _():
    a = uj_asszisztens()
    r = a.mennyiseget_modosit("nincs ilyen termek", 2)
    assert "hiba" in r


@teszt("kosarba_tesz ismeretlen ID-t visszautasit")
def _():
    a = uj_asszisztens()
    r = a.kosarba_tesz(999999, "tej")
    assert "hiba" in r


@teszt("kosarba_tesz ellenorzi, hogy tenyleg bement-e")
def _():
    # A kosar ures marad -> a program szoljon, ne higgye, hogy sikerult
    mcp = HamisMCP(kosar="Cart Summary:\n• Total items: 0\n\nProducts in cart:")
    a = uj_asszisztens(mcp)
    a.termek_keres("tej")
    r = a.kosarba_tesz(16321, "tej")
    assert "hiba" in r and "NEM kerult be" in r["hiba"], r


@teszt("kosarbol_kivesz a Cart ID-t hasznalja")
def _():
    mcp = HamisMCP()
    a = uj_asszisztens(mcp)
    mcp.naplo.clear()
    r = a.kosarbol_kivesz("vekni")
    assert r.get("levettem"), r
    assert ("remove_from_cart", {"order_field_id": "123456615"}) in mcp.naplo


@teszt("tobb talalatra visszakerdez, nem talalgat")
def _():
    a = uj_asszisztens()
    r = a.kosarbol_kivesz("i")      # tobb tetelre is illik
    assert "tobb_talalat" in r, r


@teszt("szaraz mod nem ir a kosarba")
def _():
    mcp = HamisMCP()
    a = uj_asszisztens(mcp, szaraz=True)
    a.termek_keres("tej")
    mcp.naplo.clear()
    r = a.kosarba_tesz(16321, "tej")
    assert r.get("szaraz_futas")
    assert not any(n == "add_to_cart" for n, _ in mcp.naplo), mcp.naplo
    assert "figyelmeztetes" in r, "az LLM-nek tudnia kell, hogy proba volt"


@teszt("akcio_kategoriak: kiolvassa a szekciokat (pl. Ments meg)")
def _():
    a = uj_asszisztens()
    r = a.akcio_kategoriak()
    nevek = [k["nev"] for k in r["kategoriak"]]
    assert "Ments meg!" in nevek, nevek
    ments = next(k for k in r["kategoriak"] if k["nev"] == "Ments meg!")
    assert ments["id"] == 300118


@teszt("akciok_most: tipus es kategoria atmegy a Kiflihez")
def _():
    mcp = HamisMCP()
    a = uj_asszisztens(mcp)
    mcp.naplo.clear()
    a.akciok_most(tipus="week-sales", kategoria_id=300118, darab=5)
    hivas = next(h for h in mcp.naplo if h[0] == "get_discounted_items")
    assert hivas[1]["sale_type"] == "week-sales", hivas
    assert hivas[1]["category_id"] == 300118, hivas


@teszt("ures akcios szekcional nem talal ki terméket")
def _():
    class Ures(HamisMCP):
        def hiv(self, nev, args=None):
            if nev == "get_discounted_items" and not (args or {}).get(
                    "list_categories"):
                return "No discounted items found."
            return super().hiv(nev, args)

    a = uj_asszisztens(Ures())
    r = a.akciok_most(tipus="bundles")
    assert r["termekek"] == []
    assert "NE talalj ki" in r.get("megjegyzes", "")


@teszt("elofizetes: kiolvassa az allapotot es a kedvezmenyeket")
def _():
    a = uj_asszisztens()
    r = a.elofizetesem()
    assert r.get("aktiv") is True, r
    assert r.get("tipus") == "MONTHLY", r


@teszt("szallitasi cim kiolvasasa")
def _():
    a = uj_asszisztens()
    r = a.szallitasi_cimem()
    assert "Példa utca" in (r.get("cim") or ""), r
    assert "Kifli appban" in r.get("megjegyzes", ""), "hianyzik a korlat"


@teszt("idosav: nem allitja, hogy lefoglalta")
def _():
    a = uj_asszisztens()
    r = a.szallitasi_idosavok()
    szoveg = json.dumps(r, ensure_ascii=False).lower()
    # Allito mult ideju kijelentesek tiltva - a tagadas ("nem lehet
    # lefoglalni") viszont pont hogy kell
    for tiltott in ("lefoglaltam", "lefoglalva", "kivalasztottam",
                    "beallitottam", "sikeresen"):
        assert tiltott not in szoveg, f"felrevezeto allitas: {tiltott}"
    assert "nem lehet lefoglalni" in r["megjegyzes"].lower()
    assert r["legkorabbi"]["ido"].startswith("12:45")
    assert any(x["premium"] for x in r["idosavok"])


@teszt("nem talalgatunk a 'Can order' jelzesbol")
def _():
    # A Kifli addig 'No'-t ad, amig nincs idosav valasztva - ez szinte
    # mindig igy van, ezert nem szabad belole kovetkeztetni semmire.
    a = uj_asszisztens()
    r = a.kosar_megmutat()
    szoveg = json.dumps(r, ensure_ascii=False).lower()
    for tiltott in ("minimalis", "minimális", "nem rendelhet"):
        assert tiltott not in szoveg, f"felrevezeto allitas: {tiltott}"
    r2 = a.kosar_lezar()
    szoveg2 = json.dumps(r2, ensure_ascii=False).lower()
    for tiltott in ("minimalis", "minimális", "nem rendelhet"):
        assert tiltott not in szoveg2, f"felrevezeto allitas a lezarasban"

    for f in ("webui/index.html", "webui/mobil.html"):
        html = Path(f).read_text(encoding="utf-8").lower()
        assert "minimális rendelési" not in html, f


@teszt("kosar_lezar nem allitja, hogy leadta a rendelest")
def _():
    a = uj_asszisztens()
    r = a.kosar_lezar()
    assert "MEG NINCS LEADVA" in r["fontos"]
    assert a.lezarva


@teszt("a visszaigazolas a valodi adatokat tartalmazza")
def _():
    a = uj_asszisztens()
    a.termek_keres("tej")
    t = next(x for x in a.utolso_talalatok if x["id"] == 97506)
    sz = a._visszaigazolas(t, 2)
    assert "413" in sz, f"hianyzik az ar: {sz}"
    assert "2 darab" in sz, f"hianyzik a darabszam: {sz}"
    assert "10 szazalek" in sz, f"hianyzik a kedvezmeny: {sz}"


@teszt("a talalatlista nem no korlatlanul")
def _():
    import asszisztens as asz
    a = uj_asszisztens()
    for i in range(200):
        a._talalatokat_megjegyez([{"id": 100000 + i, "nev": f"T{i}", "ar": 1}])
    assert len(a.utolso_talalatok) <= a.TALALAT_KERET, len(a.utolso_talalatok)


# ───────────────────────────────────────────────────────── tarolas

fejezet("Kep")


@teszt("kepformatum felismerese")
def _():
    import kep
    esetek = [(b"\xff\xd8\xff\xe0" + b"\x00" * 20, "image/jpeg"),
              (b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png"),
              (b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 10, "image/webp"),
              (b"GIF89a" + b"\x00" * 20, "image/gif"),
              (b"nem kep" + b"\x00" * 20, None)]
    for adat, vart in esetek:
        assert kep._kep_tipus(adat) == vart, adat[:8]


@teszt("hibas kep ertheto uzenetet ad")
def _():
    import kep
    for adat, jel in ((b"", "res"), (b"nem kep" * 5, "format"),
                      (b"\xff\xd8\xff" + b"\x00" * (21 * 1024 * 1024), "nagy")):
        try:
            kep.listat_kiolvas(adat)
            raise AssertionError(f"{jel}: atment")
        except kep.KepHiba as e:
            assert jel.lower() in str(e).lower(), f"{jel}: {e}"


@teszt("a felismeres valaszat rendesen dolgozza fel")
def _():
    import kep

    def v(tartalom):
        return {"choices": [{"message": {"content": tartalom}}]}

    r = kep._feldolgoz(v(json.dumps({
        "tetelek": [
            {"szoveg": "2 l tej", "megbizhatosag": 0.95},
            {"szoveg": "trap. 30 dkg", "megbizhatosag": 0.6,
             "bizonytalan_resz": "30 vagy 50"},
            {"szoveg": "  ", "megbizhatosag": 0.9}],
        "iras_tipusa": "keziras"})))
    assert len(r["tetelek"]) == 2, "az ures tétel bent maradt"
    assert r["iras_tipusa"] == "keziras"

    # markdown kodblokk, szoveges tétel, ertelmetlen megbizhatosag
    assert kep._feldolgoz(v('```json\n{"tetelek":[{"szoveg":"tej"}]}\n```')
                          )["tetelek"][0]["megbizhatosag"] == 0.5
    assert len(kep._feldolgoz(v('{"tetelek":["a","b"]}'))["tetelek"]) == 2
    r = kep._feldolgoz(v('{"tetelek":[{"szoveg":"x","megbizhatosag":"sok"},'
                         '{"szoveg":"y","megbizhatosag":5}]}'))
    assert [t["megbizhatosag"] for t in r["tetelek"]] == [0.5, 1.0]


@teszt("a bizonytalan tételeket kulon adja at a modellnek")
def _():
    a = uj_asszisztens()
    a.kep_tetelek = {"tetelek": [
        {"szoveg": "2 l tej", "megbizhatosag": 0.95,
         "bizonytalan_resz": None},
        {"szoveg": "trap. 30 dkg", "megbizhatosag": 0.55,
         "bizonytalan_resz": "30 vagy 50"}],
        "iras_tipusa": "keziras"}

    r = a.feltoltott_lista()
    assert r["biztosan_olvashato"] == ["2 l tej"], r
    assert len(r["bizonytalan"]) == 1
    assert r["bizonytalan"][0]["mi_nem_egyertelmu"] == "30 vagy 50"
    assert "OLVASD FEL" in r["megjegyzes"]
    # csak egyszer hasznalhato fel
    assert a.feltoltott_lista()["tetelek"] == []


@teszt("kep nelkul nem talal ki listat")
def _():
    a = uj_asszisztens()
    r = a.feltoltott_lista()
    assert r["tetelek"] == []
    assert "uzenet" in r


@teszt("mindket felulet tud kepet kuldeni")
def _():
    for f in ("webui/index.html", "webui/mobil.html"):
        sz = Path(f).read_text(encoding="utf-8")
        assert "kepetKuld" in sz, f
        assert "kep_allapot" in sz, f
        assert 'accept="image/*"' in sz, f
    # a mobilon a kamera is elerheto legyen
    mobil = Path("webui/mobil.html").read_text(encoding="utf-8")
    assert 'capture="environment"' in mobil, "nincs kozvetlen fotozas"


fejezet("Tanulas")


@teszt("ment es visszaolvas")
def _():
    import adat
    t = adat.Tarolo(":memory:")
    t.ment("tejföl", 28042, "Magyar Tejföl 20%", 330, "g")
    r = t.keres("TEJFÖL")        # kis-nagybetu nem szamit
    assert r and r["kifli_id"] == 28042 and r["amount_value"] == 330


@teszt("ismetelt mentes szamol, nem duplikal")
def _():
    import adat
    t = adat.Tarolo(":memory:")
    for _ in range(3):
        t.ment("tej", 1, "Tej", 1, "l")
    assert len(t.osszes()) == 1
    assert t.keres("tej")["hit_count"] == 3


@teszt("irasvedett adatbazisnal ertheto hibat ad")
def _():
    import sqlite3
    import adat
    t = adat.Tarolo(":memory:")

    class Irasvedett:
        def execute(self, *a, **k):
            raise sqlite3.OperationalError(
                "attempt to write a readonly database")
        def commit(self): pass

    t.db = Irasvedett()
    try:
        t._irhato_e()
        raise AssertionError("nem jelzett irasvedettseget")
    except adat.TaroloHiba as e:
        assert "chown" in str(e), "nincs benne a javitas modja"


@teszt("torles")
def _():
    import adat
    t = adat.Tarolo(":memory:")
    t.ment("tej", 1, "Tej")
    t.torol("tej")
    assert t.keres("tej") is None


@teszt("szalbiztos: parhuzamos iras kulon szalakrol")
def _():
    import concurrent.futures
    import adat
    ut = Path(tempfile.gettempdir()) / "teszt_szal.db"
    ut.unlink(missing_ok=True)
    t = adat.Tarolo(ut)

    def ir(i):
        t.ment(f"t{i}", i, f"T{i}", 1, "db")
        t.naploz("x", "y", "z")
        return t.keres(f"t{i}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        sorok = list(ex.map(ir, range(40)))
    assert all(sorok) and len(t.osszes()) == 40
    t.close()
    ut.unlink(missing_ok=True)


# ───────────────────────────────────────────── ratakorlat-kezeles

fejezet("Ratakorlat")


@teszt("429 utan var es ujraprobal")
def _():
    import mcp_kliens as mk
    HAMIS = '''
import json, sys
n = 0
for sor in sys.stdin:
    sor = sor.strip()
    if not sor: continue
    u = json.loads(sor)
    if u.get("method") == "initialize":
        ki = {"jsonrpc":"2.0","id":u["id"],"result":{
              "protocolVersion":"2024-11-05","capabilities":{},
              "serverInfo":{"name":"f","version":"0"}}}
    elif u.get("method") == "tools/call":
        n += 1
        if n < 3:
            ki = {"jsonrpc":"2.0","id":u["id"],"result":{"content":[
                  {"type":"text","text":"HTTP 429: Too Many Requests"}],
                  "isError":True}}
        else:
            ki = {"jsonrpc":"2.0","id":u["id"],"result":{"content":[
                  {"type":"text","text":"Found 0 products:"}]}}
    else:
        continue
    sys.stdout.write(json.dumps(ki) + "\\n"); sys.stdout.flush()
'''
    p = Path(tempfile.gettempdir()) / "hamis_rata_t.py"
    p.write_text(HAMIS)
    regi_var, regi_szunet = mk.UJRA_VARAKOZAS, mk.MIN_SZUNET
    mk.UJRA_VARAKOZAS, mk.MIN_SZUNET = (0.02, 0.02, 0.02), 0.01
    try:
        with mk.MCPKliens(parancs=["python3", str(p)]) as m:
            r = m.hiv("search_products", {"product_name": "tej"})
            assert "Found" in r, r
    finally:
        mk.UJRA_VARAKOZAS, mk.MIN_SZUNET = regi_var, regi_szunet
        p.unlink(missing_ok=True)


# ────────────────────────────────────────────────── kliens oldal

fejezet("Felulet")


@teszt("mindket felulet kezeli a visszhangot")
def _():
    for f in ("webui/index.html", "webui/mobil.html"):
        sz = Path(f).read_text(encoding="utf-8")
        assert "echoCancellation:true" in sz or "echoCancellation: true" in sz
        assert "audioSession" in sz, f"{f}: hianyzik az iOS audioSession"
        assert "beszel_e()" in sz, f"{f}: hianyzik a nemitas beszed kozben"


@teszt("a WebSocket cim mindharom uzemmodot kezeli")
def _():
    for f in ("webui/index.html", "webui/mobil.html"):
        sz = Path(f).read_text(encoding="utf-8")
        assert "ws_kulso_port" in sz, f"{f}: kulon port (Synology)"
        assert "ws_utvonal" in sz, f"{f}: utvonal (Tailscale)"
        assert "beallitas.json" in sz, f"{f}: helyi mod"


@teszt("a felhasznaloi szoveg escapelve kerul a DOM-ba")
def _():
    for f in ("webui/index.html", "webui/mobil.html"):
        sz = Path(f).read_text(encoding="utf-8")
        assert "function esc(" in sz
        # a terméknevek mindig esc()-en at mennek
        assert "esc(t.nev)" in sz, f"{f}: a terméknev nincs escapelve"


@teszt("a szerver haromfele beallitast ad vissza")
def _():
    import os
    import gui
    port, ws_port = gui.szabad_port(9700), gui.szabad_port(9750)
    k = gui.statikus_szerver(port, ws_port)
    import time
    import urllib.request
    time.sleep(0.3)
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/beallitas.json", timeout=5) as v:
            b = json.load(v)
        assert b["ws_port"] == ws_port
        # a mobil felulet iPhone user-agentre
        k2 = urllib.request.Request(f"http://127.0.0.1:{port}/",
                                    headers={"User-Agent": "iPhone Safari"})
        with urllib.request.urlopen(k2, timeout=5) as v:
            assert "Koppints" in v.read().decode()
    finally:
        k.shutdown()


@teszt("az utvonal-bejaras vedve van")
def _():
    import time
    import urllib.error
    import urllib.request
    import gui
    port = gui.szabad_port(9800)
    k = gui.statikus_szerver(port, port + 1)
    time.sleep(0.3)
    try:
        for gonosz in ("/../gui.py", "/../../etc/passwd", "/../.env"):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{gonosz}",
                                       timeout=5)
                raise AssertionError(f"{gonosz} elerheto!")
            except urllib.error.HTTPError as e:
                assert e.code == 404
    finally:
        k.shutdown()


fejezet("Dokumentacio")


@teszt("a README minden Python fajlt emlit")
def _():
    import re
    olvas = Path("README.md").read_text(encoding="utf-8")
    emlitett = set(re.findall(r"`([a-z_]+\.py)`", olvas))
    osszes = {f.name for f in Path(".").glob("*.py")}
    hianyzo = osszes - emlitett
    assert not hianyzo, f"nincs a README-ben: {sorted(hianyzo)}"


@teszt("a README hivatkozasai leteznek")
def _():
    import re
    olvas = Path("README.md").read_text(encoding="utf-8")
    utak = (re.findall(r'src="([^"h][^"]*)"', olvas)
            + re.findall(r"\]\((docs/[^)]+)\)", olvas)
            + re.findall(r"`(webui/[^`]+)`", olvas))
    for ut in set(utak):
        assert Path(ut).exists(), f"hianyzo hivatkozas: {ut}"


@teszt("a README eszkozszama egyezik a kodeval")
def _():
    import asszisztens as asz
    olvas = Path("README.md").read_text(encoding="utf-8")
    szamok = {13: "tizenhárom", 14: "tizennégy", 15: "tizenöt",
              16: "tizenhat", 17: "tizenhét", 18: "tizennyolc",
              19: "tizenkilenc", 20: "húsz"}
    szo = szamok.get(len(asz.ESZKOZOK))
    assert szo, f"{len(asz.ESZKOZOK)} eszkoz - bovitsd a szamnev-tablat"
    assert szo in olvas, (
        f"{len(asz.ESZKOZOK)} eszkoz van, de a README nem mondja "
        f"'{szo}'-nak")


@teszt("a dokumentacioban nincs szemelyes adat")
def _():
    import re
    minta = re.compile(
        r"@gmail|@freemail|\+36\s*\d|sk-[A-Za-z0-9_-]{20,}"
        r"|\b\d{4}\s+Budapest\b", re.I)
    for f in list(Path(".").glob("*.md")) + list(Path("docs").glob("*.md")):
        szoveg = f.read_text(encoding="utf-8")
        for sor in szoveg.splitlines():
            # a pelda-ertekek rendben vannak
            if "pelda.hu" in sor or "példa" in sor.lower():
                continue
            t = minta.search(sor)
            assert not t, f"{f.name}: {t.group(0)}"


# ────────────────────────────────────────────────────── osszegzes

hibas = [e for e in eredmenyek if not e[0]]
print(f"\n{'─' * 58}")
if hibas:
    print(f"{PI}{len(hibas)} teszt elbukott{ALAP} "
          f"({len(eredmenyek) - len(hibas)} rendben)")
    sys.exit(1)
print(f"{Z}Mind a {len(eredmenyek)} teszt rendben.{ALAP}")
