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
  Cart ID: 376224796

• Kitchin Extra szűz olívaolaj (Kitchin)
  Quantity: 1
  Price: 4629 HUF
  Category: Tartós élelmiszer
  Cart ID: 376224110

• Házi vekni (Rádi)
  Quantity: 1
  Price: 599 HUF
  Category: Pékség és cukrászat
  Cart ID: 376224615"""

GYAKORI = """🛒 MOST FREQUENTLY PURCHASED ITEMS

1. Coca-Cola colaízű szénsavas üdítőital multipack (2x1,75l) • Uncategorized
   📊 9× orders • 9 units
   🆔 1417

2. Jacobs Classico Lungo (6) - Nespresso kávékapszula • Uncategorized
   📊 8× orders • 8 units
   🆔 60476"""

IDOSAVOK = json.dumps({"slots": [{"days": [{"slots": [
    {"slotId": 1, "since": "2026-09-19 08:00", "till": "2026-09-19 10:00",
     "capacity": "GREEN", "price": 490, "timeWindow": "08:00 – 10:00",
     "timeSlotCapacityDTO": {"capacityMessage": "Szabad"}},
    {"slotId": 2, "since": "2026-09-19 10:00", "till": "2026-09-19 12:00",
     "capacity": "RED", "price": 0, "timeWindow": "10:00 – 12:00",
     "timeSlotCapacityDTO": {"capacityMessage": "Megtelt"}},
]}]}]})


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
    assert r["tetelek"][0]["cart_item_id"] == "376224796", "NEM a termek ID"
    assert r["tetelek"][0]["darab"] == 2


@teszt("gyakori tetelek")
def _():
    import parser as p
    g = p.gyakori_ertelmez(GYAKORI)
    assert len(g) == 2 and g[0]["id"] == 1417
    assert g[0]["rendelesek"] == 9


@teszt("idosavok: a megtelt kimarad")
def _():
    import asszisztens as asz
    s = asz.Asszisztens._idosavok_ertelmez(IDOSAVOK)
    assert len(s) == 1, f"{len(s)} sav, 1 kellene (a RED kimarad)"
    assert s[0]["ar"] == 490


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
    assert ("remove_from_cart", {"order_field_id": "376224615"}) in mcp.naplo


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


# ────────────────────────────────────────────────────── osszegzes

hibas = [e for e in eredmenyek if not e[0]]
print(f"\n{'─' * 58}")
if hibas:
    print(f"{PI}{len(hibas)} teszt elbukott{ALAP} "
          f"({len(eredmenyek) - len(hibas)} rendben)")
    sys.exit(1)
print(f"{Z}Mind a {len(eredmenyek)} teszt rendben.{ALAP}")
