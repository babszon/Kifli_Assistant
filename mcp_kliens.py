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
import queue


class MCPHiba(Exception):
    pass


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

    def _var(self, azonosito, timeout=120):
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

    def hiv(self, nev, argumentumok=None):
        """Meghiv egy MCP toolt, es a szoveges valaszt adja vissza."""
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
            raise MCPHiba(f"{nev}: {szoveg}")
        return szoveg


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
