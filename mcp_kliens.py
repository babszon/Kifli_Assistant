#!/usr/bin/env python3
"""
Minimalis MCP stdio kliens a rohlik-mcp szerverhez.

A szervert egyetlen hosszu eletu alfolyamatkent inditja, es JSON-RPC
uzeneteket kuld neki a stdin/stdout parjan keresztul. Igy egy session
alatt egyszer tortenik a Kifli login, nem hivasonkent.

Hasznalat:
    with MCPKliens() as mcp:
        talalatok = mcp.hiv("search_products", {"product_name": "tej", "limit": 5})
"""

import json
import os
import subprocess
import sys
import threading
import time
import queue

# A Kifli ratakorlatot szab. Ha egy mondatban sok terméket sorolsz fel,
# a program mindegyikre kulon keresest indit - ezek tul gyorsan mennenek
# ki, es 429-et kapnank. Ezert hivasok kozott minimalis szunetet tartunk,
# es 429 utan varunk, majd ujraprobalunk.
MIN_SZUNET = 0.7          # masodperc ket hivas kozott
UJRA_VARAKOZAS = (2, 6, 15)   # 429 utan ennyit varunk, sorban

# Ha egyszer 429-et kaptunk, egy ideig lassabban kuldunk - igy nem
# esunk ujra bele rogton.
BUNTETO_SZUNET = 3.0
BUNTETES_HOSSZA = 90.0    # masodperc

# Ha a varakozasok utan is 429 jon, a Kifli tartosan korlatoz. Ilyenkor
# a KOVETKEZO hivasok AZONNAL hibat adnak, nem varnak ujra - kulonben
# minden egyes tétel ujabb fel percet allna, es a beszelgetes befagyna.
ZARLAT_HOSSZA = 60.0      # masodperc


class MCPHiba(Exception):
    pass


class MCPRataHiba(MCPHiba):
    """Ratakorlat - erdemes varni es ujraprobalni."""


class MCPKliens:
    def __init__(self, parancs=None, kornyezet=None, csendes=True):
        self.parancs = parancs or ["npx", "-y", "@tomaspavlin/rohlik-mcp"]
        self.kornyezet = {**os.environ, **(kornyezet or {})}
        self.csendes = csendes
        self.proc = None
        self._id = 0
        self._valaszok = {}
        self._sor = queue.Queue()
        self._olvaso = None
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

    # ------------------------------------------------------------ publikus

    def eszkozok(self):
        azon = self._kov_id()
        self._kuld({"jsonrpc": "2.0", "id": azon, "method": "tools/list"})
        return self._var(azon)["result"]["tools"]

    def _hiv_egyszer(self, nev, argumentumok):
        """Egyetlen hivas, ujraprobalkozas nelkul."""
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

        Ket hivas kozott minimalis szunetet tart, es ratakorlat (429)
        eseten var, majd ujraprobal - de a varakozas alatt NEM fogja a
        zarat, tehat mas hivasok kozben is mehetnek.
        """
        # Zarlat alatt azonnal visszaszolunk: ha egyszer mar vegigvartuk
        # a teljes sorozatot, nincs ertelme minden tételnel ujra.
        hatra = self._zarlat_vege - time.monotonic()
        if hatra > 0:
            raise MCPRataHiba(
                f"A Kifli most tul sok kerest kap. Meg korulbelul "
                f"{int(hatra)} masodpercig nem probalkozom ujra.")

        for probalkozas in range(len(UJRA_VARAKOZAS) + 1):
            self._utemez()
            try:
                return self._hiv_egyszer(nev, argumentumok)
            except MCPRataHiba:
                # Innentol lassabban kuldunk, hogy ne essunk ujra bele
                self._buntetes_vege = time.monotonic() + BUNTETES_HOSSZA
                if probalkozas >= len(UJRA_VARAKOZAS):
                    break
                var = UJRA_VARAKOZAS[probalkozas]
                print(f"\033[90m  (a Kifli lassit, {var} mp varakozas"
                      f"...)\033[0m", flush=True)
                time.sleep(var)
            except MCPHiba:
                raise

        # Vegleges kudarc: zarlatot hirdetunk, hogy a tobbi tétel ne
        # fusson vegig ugyanezen a sorozaton
        self._zarlat_vege = time.monotonic() + ZARLAT_HOSSZA
        raise MCPRataHiba(
            f"A Kifli most tul sok kerest kap, es {sum(UJRA_VARAKOZAS)} "
            f"masodperc varakozas utan sem valaszolt. Par perc mulva "
            f"ujra lehet probalni.")


if __name__ == "__main__":
    # Onteszt: listazza az eszkozoket es keres egy terméket.
    hianyzo = [k for k in ("ROHLIK_BASE_URL", "ROHLIK_USERNAME", "ROHLIK_PASSWORD")
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
