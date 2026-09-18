#!/usr/bin/env python3
"""
Tarolo (SQLite) es Home Assistant kliens.

A tarolo harom tablat kezel:
  termek_map     - amit biztosan tudunk, mert megmondtad
  helyettesites  - amit felajanlhat, de sosem alkalmaz magatol
  naplo          - mit kerdezett es mit valaszoltal, hogy visszakovetheto legyen
"""

import json
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SEMA = """
CREATE TABLE IF NOT EXISTS termek_map (
    product      TEXT PRIMARY KEY,
    kifli_id     INTEGER NOT NULL,
    kifli_nev    TEXT,
    amount_value REAL,
    amount_unit  TEXT,
    bulk         INTEGER DEFAULT 0,
    hit_count    INTEGER DEFAULT 0,
    last_used    TEXT
);

CREATE TABLE IF NOT EXISTS helyettesites (
    eredeti_id    INTEGER NOT NULL,
    alternativ_id INTEGER NOT NULL,
    dontes        TEXT NOT NULL,
    datum         TEXT,
    PRIMARY KEY (eredeti_id, alternativ_id)
);

CREATE TABLE IF NOT EXISTS naplo (
    datum  TEXT,
    raw    TEXT,
    kerdes TEXT,
    valasz TEXT
);
"""


def _most():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Tarolo:
    def __init__(self, utvonal="kifli.db"):
        self.utvonal = Path(utvonal)
        # check_same_thread=False: a realtime asszisztens kulon szalon
        # hivja az eszkozoket. A zar gondoskodik arrol, hogy egyszerre
        # csak egy szal irjon.
        self.db = sqlite3.connect(self.utvonal, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._zar = threading.Lock()
        with self._zar:
            self.db.executescript(SEMA)
            self.db.commit()

    def close(self):
        with self._zar:
            self.db.close()

    # ------------------------------------------------------------ termek_map

    def keres(self, product):
        with self._zar:
            sor = self.db.execute(
                "SELECT * FROM termek_map WHERE product = ?",
                (product.lower(),)).fetchone()
        return dict(sor) if sor else None

    def ment(self, product, kifli_id, kifli_nev=None,
             amount_value=None, amount_unit=None, bulk=False):
        with self._zar:
            self.db.execute("""
                INSERT INTO termek_map
                    (product, kifli_id, kifli_nev, amount_value, amount_unit,
                     bulk, hit_count, last_used)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(product) DO UPDATE SET
                    kifli_id     = excluded.kifli_id,
                    kifli_nev    = excluded.kifli_nev,
                    amount_value = excluded.amount_value,
                    amount_unit  = excluded.amount_unit,
                    bulk         = excluded.bulk,
                    hit_count    = termek_map.hit_count + 1,
                    last_used    = excluded.last_used
            """, (product.lower(), kifli_id, kifli_nev, amount_value,
                  amount_unit, int(bulk), _most()))
            self.db.commit()

    def hasznalat(self, product):
        with self._zar:
            self.db.execute(
                "UPDATE termek_map SET hit_count = hit_count + 1, "
                "last_used = ? WHERE product = ?",
                (_most(), product.lower()))
            self.db.commit()

    def osszes(self):
        with self._zar:
            return [dict(s) for s in self.db.execute(
                "SELECT * FROM termek_map ORDER BY hit_count DESC")]

    def torol(self, product):
        with self._zar:
            self.db.execute("DELETE FROM termek_map WHERE product = ?",
                            (product.lower(),))
            self.db.commit()

    # --------------------------------------------------------- helyettesites

    def helyettesites_dontes(self, eredeti_id, alternativ_id):
        """'elfogadva' | 'elutasitva' | None"""
        with self._zar:
            sor = self.db.execute(
                "SELECT dontes FROM helyettesites WHERE eredeti_id = ? "
                "AND alternativ_id = ?",
                (eredeti_id, alternativ_id)).fetchone()
        return sor["dontes"] if sor else None

    def helyettesites_ment(self, eredeti_id, alternativ_id, dontes):
        if dontes not in ("elfogadva", "elutasitva"):
            raise ValueError("dontes: 'elfogadva' vagy 'elutasitva'")
        with self._zar:
            self.db.execute("""
                INSERT INTO helyettesites
                    (eredeti_id, alternativ_id, dontes, datum)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(eredeti_id, alternativ_id) DO UPDATE SET
                    dontes = excluded.dontes, datum = excluded.datum
            """, (eredeti_id, alternativ_id, dontes, _most()))
            self.db.commit()

    # ---------------------------------------------------------------- naplo

    def naploz(self, raw, kerdes, valasz):
        with self._zar:
            self.db.execute(
                "INSERT INTO naplo (datum, raw, kerdes, valasz) "
                "VALUES (?, ?, ?, ?)", (_most(), raw, kerdes, valasz))
            self.db.commit()


class HAHiba(Exception):
    pass


class HAKliens:
    """Home Assistant REST API - todo lista olvasasa es modositasa."""

    def __init__(self, url=None, token=None, entitas=None):
        self.url = (url or os.environ.get("HA_URL", "")).rstrip("/")
        self.token = token or os.environ.get("HA_TOKEN", "")
        self.entitas = entitas or os.environ.get("HA_TODO", "todo.bevasarlolista")
        if not self.url or not self.token:
            raise HAHiba("HA_URL vagy HA_TOKEN hianyzik.")

    def _keres(self, ut, adat=None, metodus="GET"):
        keres = urllib.request.Request(
            f"{self.url}{ut}",
            data=json.dumps(adat).encode() if adat is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=metodus,
        )
        try:
            with urllib.request.urlopen(keres, timeout=30) as v:
                test = v.read().decode()
                return json.loads(test) if test.strip() else None
        except urllib.error.HTTPError as h:
            raise HAHiba(f"HTTP {h.code}: {h.read().decode()[:300]}")
        except urllib.error.URLError as h:
            raise HAHiba(f"Halozati hiba: {h}")

    def tetelek(self):
        """A lista nyitott tetelei, nyers szovegkent."""
        valasz = self._keres(
            "/api/services/todo/get_items?return_response=true",
            {"entity_id": self.entitas, "status": "needs_action"},
            "POST",
        )
        szolgaltatas = (valasz or {}).get("service_response", {})
        adatok = szolgaltatas.get(self.entitas, {})
        return [t["summary"] for t in adatok.get("items", [])]

    def kesz(self, osszefoglalo):
        """Egy tetelt keszre allit."""
        self._keres("/api/services/todo/update_item",
                    {"entity_id": self.entitas,
                     "item": osszefoglalo, "status": "completed"}, "POST")


if __name__ == "__main__":
    t = Tarolo(":memory:")
    t.ment("tej", 16321, "Magyar Tej ESL 2,8%", 1.0, "l")
    t.ment("tej", 16321, "Magyar Tej ESL 2,8%", 1.0, "l")
    print("termek_map:", t.keres("Tej"))
    t.helyettesites_ment(68938, 90143, "elutasitva")
    print("helyettesites:", t.helyettesites_dontes(68938, 90143))
    print("ismeretlen:", t.helyettesites_dontes(1, 2))
    t.naploz("harminc deka trappista", "Melyik sajt?", "gouda")
    print("tarolo OK")

    try:
        ha = HAKliens()
        print("HA lista:", ha.tetelek())
    except HAHiba as e:
        print("HA kihagyva:", e)
