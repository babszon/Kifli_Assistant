#!/usr/bin/env python3
"""
MCP kliens a Kiflihez.

Alapbol a hivatalos szervert hasznalja (https://mcp.kifli.hu/mcp),
HTTP-n, a fiók email/jelszo fejleceivel. A regi, nem hivatalos
rohlik-mcp stdio-n akkor megy, ha KIFLI_MCP=stdio, vagy a hivo
explicit parancsot ad (tesztek).

Hasznalat:
    with MCPKliens() as mcp:
        talalatok = mcp.hiv("search_products", {"product_name": "tej"})
"""

import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
import queue
import urllib.error
import urllib.request

# A Kifli ratakorlatot szab. Ha egy mondatban sok terméket sorolsz fel,
# a program mindegyikre kulon keresest indit - ezek tul gyorsan mennenek
# ki, es 429-et kapnank. Ezert hivasok kozott minimalis szunetet tartunk.
# 429-nel NEM varunk es NEM probalkozunk ujra: a varakozas alatt a
# korlat csak szigorodik, es a beszelgetes befagyna. Helyette zarlat:
# a tobbi hivas azonnal hibaval ter vissza.
MIN_SZUNET = 0.7          # masodperc ket hivas kozott

# Ha egyszer 429-et kaptunk, egy ideig lassabban kuldunk - igy nem
# esunk ujra bele rogton, amint a zarlat lejar.
BUNTETO_SZUNET = 3.0
BUNTETES_HOSSZA = 90.0    # masodperc

# 429 utan a kovetkezo hivasok AZONNAL hibaval ternek vissza.
ZARLAT_HOSSZA = 60.0      # masodperc

HIVATALOS_URL = "https://mcp.kifli.hu/mcp"

# A Cloudflare a Python urllib alapertelmezett User-Agentjet tiltja
# (HTTP 1010). A hivatalos kliensek bongeszo-alairast kuldnek.
_BOGESSZO_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


class MCPHiba(Exception):
    pass


class MCPRataHiba(MCPHiba):
    """Ratakorlat - erdemes varni es ujraprobalni."""


def hivatalos_lekepez(nev, argumentumok=None):
    """
    A regi (rohlik-mcp) eszkozneveket a hivatalos Kifli MCP-re kepzi.

    Visszaad: (hivatalos_nev, argumentumok). A context mezot a Kifli
    analyticshez keri - soha nem megy bele szemelyes adat.
    """
    args = dict(argumentumok or {})

    def ctx(mondat):
        return mondat

    if nev == "search_products":
        return "batch_search_products", {
            "queries": [{"keyword": args.get("product_name")
                         or args.get("query") or ""}],
            "context": ctx("Termekkereses a kosar osszeallitasahoz."),
        }
    if nev == "get_cart_content":
        return "get_cart", {
            "context": ctx("A kosar aktualis tartalmanak megtekintese."),
        }
    if nev == "add_to_cart":
        tetelek = []
        for t in args.get("products") or args.get("items") or []:
            pid = t.get("productId", t.get("product_id"))
            tetelek.append({
                "productId": int(pid),
                "quantity": int(t.get("quantity") or 1),
            })
        return "add_items_to_cart", {
            "items": tetelek,
            "context": ctx("Termekek kosarba tetele."),
        }
    if nev == "remove_from_cart":
        pid = args.get("product_id", args.get("order_field_id"))
        return "remove_cart_item", {
            "product_id": int(pid),
            "context": ctx("Egy tetel levetel a kosarbol."),
        }
    if nev == "clear_cart":
        return "clear_cart", {
            "context": ctx("A kosar teljes uritese a felhasznalo keresere."),
        }
    if nev == "get_frequent_items":
        return "get_typical_order", {
            "add_to_cart": False,
            "context": ctx("A szokasos vasarolt termekek lekerese."),
        }
    if nev in ("get_premium_info", "get_account_data"):
        return "get_user_info", {
            "context": ctx("A fiok es az elofizetes allapotanak lekerese."),
        }
    if nev == "get_order_history":
        return "fetch_orders", {
            "limit": int(args.get("limit") or 10),
            "context": ctx("Korabbi rendelesek lekerese."),
        }
    if nev == "get_order_detail":
        kimeno = {"context": ctx("Egy rendeles reszleteinek lekerese.")}
        if args.get("order_id") is not None:
            kimeno["order_id"] = args["order_id"]
        return "fetch_orders", kimeno
    if nev == "get_upcoming_orders":
        return "fetch_orders", {
            "context": ctx("Kozelgo rendelesek lekerese."),
        }
    if nev == "get_meal_suggestions":
        etkezes = args.get("meal_type") or "ebed"
        return "search_recipes_by_vector_similarity", {
            "query": str(etkezes),
            "limit": max(1, min(10, int(args.get("items_count") or 10))),
            "context": ctx("Etkezesi otletek keresese."),
        }
    if nev == "get_delivery_slots":
        return "get_timeslots_checkout", {
            "timeslots_day": str(args.get("timeslots_day") or "0"),
            "context": ctx("Szallitasi idosavok lekerese."),
        }
    if nev == "get_discounted_items":
        kimeno = {"context": ctx("Aktualis akciok lekerese.")}
        for k in ("sale_type", "category_id", "limit", "page", "sort",
                  "list_categories"):
            if args.get(k) is not None:
                kimeno[k] = args[k]
        return "get_discounted_items", kimeno

    if "context" not in args:
        args["context"] = ctx("Bevasarlo asszisztens hivasa.")
    return nev, args


def _sse_json(nyers):
    """Egy SSE vagy sima JSON valaszbol a JSON-RPC objektum."""
    if not nyers or not str(nyers).strip():
        return None
    darabok = []
    for m in re.finditer(r"^data:\s*(.+)$", nyers, re.M):
        s = m.group(1).strip()
        if s and s != "[DONE]":
            try:
                darabok.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    if darabok:
        return darabok[-1]
    try:
        return json.loads(nyers)
    except json.JSONDecodeError:
        return None


def _stdio_e(parancs, kornyezet=None):
    """True, ha a regi stdio szervert kell inditani."""
    if parancs:
        return True
    env = kornyezet if kornyezet is not None else os.environ
    mod = str(env.get("KIFLI_MCP") or "").strip().lower()
    return mod in ("stdio", "unofficial", "rohlik")


class MCPKliens:
    def __init__(self, parancs=None, kornyezet=None, csendes=True):
        self.kornyezet = {**os.environ, **(kornyezet or {})}
        self.csendes = csendes
        self.stdio_e = _stdio_e(parancs, self.kornyezet)
        self.tud_clear_cart = not self.stdio_e
        # A ROHLIK_MCP_PARANCS a stdio-visszaeseshöz kell (tesztek, javitas).
        sajat = self.kornyezet.get("ROHLIK_MCP_PARANCS") or os.environ.get(
            "ROHLIK_MCP_PARANCS")
        if parancs:
            self.parancs = parancs
        elif sajat:
            self.parancs = sajat.split()
        else:
            self.parancs = ["npx", "-y", "@tomaspavlin/rohlik-mcp"]
        self.proc = None
        self._id = 0
        self._valaszok = {}
        self._sor = queue.Queue()
        self._olvaso = None
        self._session = None
        self._ssl = ssl.create_default_context()
        # Egyszerre csak egy hivas mehet ki, es kozottuk szunet van
        self._utemezo = threading.Lock()
        self._utolso_hivas = 0.0
        self._buntetes_vege = 0.0
        self._zarlat_vege = 0.0

    # ------------------------------------------------------------ eletciklus

    def __enter__(self):
        self.indit()
        return self

    def __exit__(self, *_):
        self.leallit()
        return False

    def indit(self):
        if self.stdio_e:
            self._stdio_indit()
        else:
            self._http_indit()

    def leallit(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._session = None

    def _stdio_indit(self):
        self.proc = subprocess.Popen(
            self.parancs,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if self.csendes else None,
            env=self.kornyezet,
            text=True,
            bufsize=1,
        )
        self._olvaso = threading.Thread(target=self._olvas, daemon=True)
        self._olvaso.start()

        self._kuld({
            "jsonrpc": "2.0", "id": self._kov_id(), "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kifli-asszisztens", "version": "1"},
            },
        })
        self._var(self._id)
        self._kuld({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _http_indit(self):
        valasz = self._http_rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "kifli-asszisztens", "version": "1"},
        })
        if not valasz or "error" in (valasz or {}):
            hiba = (valasz or {}).get("error") or "nincs valasz"
            raise MCPHiba(f"A hivatalos Kifli MCP nem indul: {hiba}")
        self._http_rpc("notifications/initialized", None, ertesites=True)

    # --------------------------------------------------------------- belsok

    def _kov_id(self):
        self._id += 1
        return self._id

    def _olvas(self):
        for sor in self.proc.stdout:
            sor = sor.strip()
            if not sor or not sor.startswith("{"):
                continue
            try:
                self._sor.put(json.loads(sor))
            except json.JSONDecodeError:
                continue

    def _kuld(self, uzenet):
        self.proc.stdin.write(json.dumps(uzenet) + "\n")
        self.proc.stdin.flush()

    def _var(self, azonosito, timeout=180):
        if azonosito in self._valaszok:
            return self._valaszok.pop(azonosito)
        while True:
            try:
                uzenet = self._sor.get(timeout=timeout)
            except queue.Empty:
                raise MCPHiba(f"Idotullepes a(z) {azonosito} valaszara.")
            if uzenet.get("id") == azonosito:
                return uzenet
            if "id" in uzenet:
                self._valaszok[uzenet["id"]] = uzenet

    def _http_fejlecek(self):
        email = self.kornyezet.get("ROHLIK_USERNAME") or ""
        jelszo = self.kornyezet.get("ROHLIK_PASSWORD") or ""
        fej = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": _BOGESSZO_UA,
            "rhl-email": email,
            "rhl-pass": jelszo,
        }
        if self._session:
            fej["mcp-session-id"] = self._session
        return fej

    def _http_rpc(self, method, params, ertesites=False):
        body = {"jsonrpc": "2.0", "method": method}
        if not ertesites:
            body["id"] = self._kov_id()
        if params is not None:
            body["params"] = params
        url = self.kornyezet.get("KIFLI_MCP_URL") or HIVATALOS_URL
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers=self._http_fejlecek(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60, context=self._ssl) as v:
                session = v.headers.get("mcp-session-id")
                if session:
                    self._session = session
                nyers = v.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            nyers = e.read().decode("utf-8", "replace")
            if e.code == 429:
                raise MCPRataHiba(nyers[:300] or "HTTP 429")
            if e.code == 401:
                raise MCPHiba("A Kifli belépés sikertelen. Ellenőrizd az "
                              "emailt és a jelszót.")
            if e.code == 403 and "1010" in nyers:
                raise MCPHiba(
                    "A Kifli MCP a kliens alairasa miatt elutasitott "
                    "(Cloudflare 1010).")
            raise MCPHiba(f"A Kifli MCP HTTP {e.code}: {nyers[:200]}")
        except urllib.error.URLError as e:
            raise MCPHiba(f"A hivatalos Kifli MCP nem erheto el: {e.reason}")

        if ertesites:
            return None
        valasz = _sse_json(nyers)
        if valasz is None:
            raise MCPHiba(f"{method}: ertelmezhetetlen valasz.")
        return valasz

    def _http_tool(self, nev, argumentumok):
        valasz = self._http_rpc("tools/call", {
            "name": nev, "arguments": argumentumok or {},
        })
        if "error" in valasz:
            uzenet = valasz["error"].get("message", valasz["error"])
            raise MCPHiba(f"{nev}: {uzenet}")

        eredmeny = valasz.get("result") or {}
        if eredmeny.get("structuredContent") is not None:
            tartalom = eredmeny["structuredContent"]
            szoveg = json.dumps(tartalom, ensure_ascii=False)
        else:
            darabok = [
                d.get("text", "") for d in eredmeny.get("content") or []
                if d.get("type") == "text"
            ]
            szoveg = "\n".join(darabok)
            tartalom = None

        if eredmeny.get("isError"):
            if "429" in szoveg or "Too Many Requests" in szoveg:
                raise MCPRataHiba(szoveg)
            raise MCPHiba(f"{nev}: {szoveg}")
        return szoveg if tartalom is None else json.dumps(
            tartalom, ensure_ascii=False)

    # ------------------------------------------------------------ publikus

    def eszkozok(self):
        if self.stdio_e:
            azon = self._kov_id()
            self._kuld({"jsonrpc": "2.0", "id": azon, "method": "tools/list"})
            return self._var(azon)["result"]["tools"]
        valasz = self._http_rpc("tools/list", {})
        return ((valasz or {}).get("result") or {}).get("tools") or []

    def _hiv_egyszer(self, nev, argumentumok):
        """Egyetlen hivas, ujraprobalkozas nelkul."""
        if not self.stdio_e:
            return self._hiv_hivatalos(nev, argumentumok)

        azon = self._kov_id()
        self._kuld({
            "jsonrpc": "2.0", "id": azon, "method": "tools/call",
            "params": {"name": nev, "arguments": argumentumok or {}},
        })
        valasz = self._var(azon)

        if "error" in valasz:
            raise MCPHiba(f"{nev}: {valasz['error'].get('message', valasz['error'])}")

        eredmeny = valasz.get("result", {})
        darabok = [
            d.get("text", "") for d in eredmeny.get("content", [])
            if d.get("type") == "text"
        ]
        szoveg = "\n".join(darabok)

        if eredmeny.get("isError"):
            if "429" in szoveg or "Too Many Requests" in szoveg:
                raise MCPRataHiba(szoveg)
            raise MCPHiba(f"{nev}: {szoveg}")
        return szoveg

    def _hiv_hivatalos(self, nev, argumentumok):
        if nev == "get_delivery_slots":
            osszes = []
            for nap in ("0", "1"):
                hiv_nev, args = hivatalos_lekepez(
                    "get_delivery_slots", {"timeslots_day": nap})
                if osszes:
                    time.sleep(MIN_SZUNET)
                osszes.append(json.loads(self._http_tool(hiv_nev, args)))
            return json.dumps(osszes, ensure_ascii=False)

        hiv_nev, args = hivatalos_lekepez(nev, argumentumok)
        return self._http_tool(hiv_nev, args)

    def _utemez(self):
        """
        Megvarja a sorat.

        A zarat CSAK a szamolas idejere fogja, az alvast mar nelkule
        vegzi. Ez fontos: korabban a zar a teljes varakozas alatt fogva
        volt, igy egy percig varakozo hivas minden mast is blokkolt - az
        asszisztens emiatt tunt nemanak.
        """
        with self._utemezo:
            most = time.monotonic()
            szunet = (BUNTETO_SZUNET if most < self._buntetes_vege
                      else MIN_SZUNET)
            indulhat = max(self._utolso_hivas + szunet, most)
            self._utolso_hivas = indulhat     # a kovetkezo ehhez igazodik
        varakozas = indulhat - time.monotonic()
        if varakozas > 0:
            time.sleep(varakozas)

    def hiv(self, nev, argumentumok=None):
        """
        Meghiv egy MCP toolt, es a szoveges valaszt adja vissza.

        Ket hivas kozott minimalis szunetet tart. Ratakorlatnal
        azonnal zarlatot hirdet - nem var 2-6-15 masodpercet, mert
        az a korlat alatt tovabb terhelne a Kiflit.
        """
        hatra = self._zarlat_vege - time.monotonic()
        if hatra > 0:
            raise MCPRataHiba(
                f"A Kifli most tul sok kerest kap. Meg korulbelul "
                f"{max(1, int(hatra))} masodpercig nem probalkozom ujra.")

        self._utemez()
        try:
            return self._hiv_egyszer(nev, argumentumok)
        except MCPRataHiba:
            self._buntetes_vege = time.monotonic() + BUNTETES_HOSSZA
            self._zarlat_vege = time.monotonic() + ZARLAT_HOSSZA
            raise MCPRataHiba(
                f"A Kifli most tul sok kerest kap. Par perc mulva "
                "ujra lehet probalni.")
        except MCPHiba:
            raise


if __name__ == "__main__":
    hianyzo = [k for k in ("ROHLIK_USERNAME", "ROHLIK_PASSWORD")
               if not os.environ.get(k)]
    if hianyzo:
        sys.exit("Hianyzo kornyezeti valtozok: " + ", ".join(hianyzo))

    with MCPKliens() as mcp:
        eszkozok = mcp.eszkozok()
        print(f"{len(eszkozok)} eszkoz elerheto:")
        for e in eszkozok:
            print(f"  - {e['name']}")
        print("\nProbakereses ('tej'):\n")
        print(mcp.hiv("search_products", {"product_name": "tej", "limit": 3}))
