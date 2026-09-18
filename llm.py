#!/usr/bin/env python3
"""
LLM reteg: normalizalas es termekvalasztas.

Ket kulonbozo feladat, ket kulon prompttal. A normalizalo prompt
fajlbol jon (normalizalo_prompt.md), a termekvalaszto itt van.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PROMPT_FILE = HERE / "normalizalo_prompt.md"
MODELL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

VALASZTO_PROMPT = """Bevasarlolista-tetelhez valasztasz terméket egy magyar
webshop talalatai kozul.

Kapsz egy normalizalt keresest es a talalatok listajat. Valaszd ki azt,
amelyik a leginkabb megfelel egy atlagos haztartas szamara.

SZABALYOK
1. A legegyszerubb, legaltalanosabb valtozatot valaszd. Ha "tej"-et
   kernek, a sima teljes vagy 2,8%-os tej a jo valasz, nem a prémium
   A2 vagy a laktozmentes.
2. Ha a keresesben jelzo szerepel (bio, laktozmentes, teljes kiorlesu),
   azt KOTELEZO figyelembe venni. Ha nincs ilyen talalat, confidence < 0.5.
3. A MENNYISEG NEM A TE DOLGOD. Ne valassz kiszereles alapjan, ne
   szamolj darabszamot, es SOHA ne kerdezz mennyisegrol vagy
   kiszerelesrol. Azt a hivo program szamolja ki. Te csak azt dontsd
   el, MELYIK TERMEK a helyes.
4. Ha egyik talalat sem felel meg egyertelmuen, confidence < 0.5.
5. Az olcsobb nem automatikusan jobb. A megszokott, bevett termek jobb.

A "kerdes" mezo szabalyai (csak ha confidence < 0.5):
- Egyetlen rovid magyar mondat, legfeljebb 12 szo.
- A felhasznalo egy SZAMOZOTT LISTAT lat, es sorszammal valaszol.
  Ezert a kerdes csak arra kerdezzen ra, MELYIK TERMEK kell.
- JO:   "Melyik sajtot kerjem?"
- JO:   "Egyik sem trappista. Melyiket tegyem?"
- ROSSZ: "Ket darab 125 grammosat vagy egy 500 grammosat szeretnel?"
- ROSSZ: barmi, ami mennyiseget, kiszerelest vagy arat kerdez.

Valaszolj CSAK ezzel a JSON objektummal:
{
  "kifli_id": a valasztott termek ID-ja vagy null,
  "indok": "egy rovid mondat magyarul, miert ezt",
  "kerdes": "ha confidence < 0.5, a rovid magyar kerdes, kulonben null",
  "confidence": 0.0-1.0
}"""


class LLMHiba(Exception):
    pass


def _hiv(system, user, model=None, json_mod=True):
    kulcs = os.environ.get("GEMINI_API_KEY")
    if not kulcs:
        raise LLMHiba("Hianyzik a GEMINI_API_KEY.")

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model or MODELL}:generateContent?key={kulcs}")
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0},
    }
    if json_mod:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    keres = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(keres, timeout=120) as v:
            valasz = json.loads(v.read().decode())
    except urllib.error.HTTPError as h:
        raise LLMHiba(f"HTTP {h.code}: {h.read().decode()[:400]}")
    except urllib.error.URLError as h:
        raise LLMHiba(f"Halozati hiba: {h}")

    try:
        return valasz["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise LLMHiba("Varatlan valasz: " + json.dumps(valasz)[:400])


def _json_kinyer(nyers):
    szoveg = nyers.strip()
    if szoveg.startswith("```"):
        szoveg = szoveg.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(szoveg)
    except json.JSONDecodeError:
        for nyito, zaro in (("[", "]"), ("{", "}")):
            e, v = szoveg.find(nyito), szoveg.rfind(zaro)
            if e != -1 and v != -1:
                try:
                    return json.loads(szoveg[e:v + 1])
                except json.JSONDecodeError:
                    continue
        raise LLMHiba("Nem sikerult JSON-t kinyerni: " + nyers[:300])


def rendszerprompt():
    szoveg = PROMPT_FILE.read_text(encoding="utf-8")
    return szoveg.split("---", 1)[1].strip() if "---" in szoveg else szoveg.strip()


def normalizal(nyers_tetelek):
    """Nyers magyar tetelek -> strukturalt lista. Egy hivas az egeszre."""
    if not nyers_tetelek:
        return []
    user = json.dumps(nyers_tetelek, ensure_ascii=False, indent=2)
    adat = _json_kinyer(_hiv(rendszerprompt(), user))
    if isinstance(adat, dict):
        for kulcs in ("tetelek", "items", "results"):
            if isinstance(adat.get(kulcs), list):
                return adat[kulcs]
        return [adat]
    return adat


def termeket_valaszt(normalizalt, talalatok):
    """Egy tetelhez valaszt terméket a talalatok kozul."""
    if not talalatok:
        return {"kifli_id": None, "indok": "Nincs talalat.",
                "kerdes": f"A(z) '{normalizalt.get('product')}' termekre nincs "
                          f"talalat. Mit keressek helyette?", "confidence": 0.0}

    user = json.dumps({
        "kereses": normalizalt,
        "talalatok": [{
            "id": t["id"], "nev": t["nev"], "marka": t.get("marka"),
            "ar": t.get("ar"), "kedvezmeny": t.get("kedvezmeny"),
            "mennyiseg": t.get("mennyiseg"), "egyseg": t.get("egyseg"),
        } for t in talalatok],
    }, ensure_ascii=False, indent=2)

    return _json_kinyer(_hiv(VALASZTO_PROMPT, user))


if __name__ == "__main__":
    print("--- normalizalas ---")
    for t in normalizal(["a tejet", "harminc deka trappistát", "30 darab tojás"]):
        print(" ", json.dumps(t, ensure_ascii=False))

    print("\n--- termekvalasztas ---")
    print(json.dumps(termeket_valaszt(
        {"product": "tej", "quantity": {"kind": "volume", "value": 2000, "unit": "ml"}},
        [{"id": 16321, "nev": "Magyar Tej ESL Tej 2,8%", "marka": "Magyar",
          "ar": 397.0, "kedvezmeny": None, "mennyiseg": 1.0, "egyseg": "l"},
         {"id": 122982, "nev": "Jersey Tej A2 5%", "marka": None,
          "ar": 764.23, "kedvezmeny": -23, "mennyiseg": 1.0, "egyseg": "l"}],
    ), ensure_ascii=False, indent=2))
