#!/usr/bin/env python3
"""
Kepfelismeres: bevasarlolista fotorol vagy kepernyokeprol.

A kepet az OpenAI modellnek kuldjuk, ami kiolvassa a tételeket. A
kimenet ugyanolyan nyers magyar szoveg, mint amit diktalnal - onnantol
ugyanaz a lanc fut (normalizalas, kereses, tanult termekek).

A KEZIRAS a nehez eset. Ezert minden tetel kap egy megbizhatosagot, es
ami bizonytalan, azt az asszisztens NEM teszi be csendben, hanem
felolvassa es rakerdez.
"""

import base64
import json
import os
import urllib.error
import urllib.request

# A kepfelismereshez erosebb modell kell, mint a szoveghez. A kezzel
# irt magyar cetli a hatarterulet - olcsobb modellek itt talalgatnak.
MODELL = os.environ.get("OPENAI_VISION_MODEL", "gpt-5.6-terra")

MAX_MERET = 20 * 1024 * 1024        # az OpenAI korlatja
TAMOGATOTT = {"image/jpeg", "image/png", "image/webp", "image/gif"}

PROMPT = """Bevasarlolistat olvasol ki egy kepbol. A kep lehet kezzel
irt cetli, telefonos jegyzet, kepernyokep vagy nyomtatott lista.

FELADAT
Olvasd ki a tételeket UGY, AHOGY LE VANNAK IRVA. Ne ertelmezd, ne
normalizald, ne egeszitsd ki - a nyers szoveget add vissza, mert azt
egy kesobbi lepes dolgozza fel.

SZABALYOK
1. Minden tétel kulon sor. Ha egy soron tobb dolog van vesszovel
   elvalasztva, bontsd szet oket.
2. A mennyiseget HAGYD BENNE a szovegben: "2 l tej", "30 dkg trappista",
   "tojas 10 db". Ne szamold at, ne valtoztasd meg.
3. A roviditeseket NE oldd fel. A "trap." maradjon "trap.", a "dkg"
   maradjon "dkg". A kovetkezo lepes ismeri oket.
4. Amit athuztak, kipipaltak vagy kihuztak, azt HAGYD KI.
5. A cim, a datum, a "bevasarlolista" felirat es az osszeadott vegosszeg
   NEM tétel - ne vedd fel.

MEGBIZHATOSAG - EZ A LEGFONTOSABB
Minden tételnel mondd meg, mennyire vagy biztos abban, amit olvasol:
- 0.9 folott: tisztan olvashato, nyomtatott vagy egyertelmu keziras
- 0.5 - 0.9: olvashato, de lehet felreolvasas (elmosodott, kusza iras)
- 0.5 alatt: tippelsz

SOHA ne talalj ki tételt, ami nincs a kepen. Ha egy sort nem tudsz
elolvasni, vedd fel alacsony megbizhatosaggal, es a 'bizonytalan_resz'
mezoben mondd meg, mi az, amit nem tudsz kiolvasni. Inkabb legyen egy
tétel bizonytalan, mint hogy rosszat talalj ki.

Ha a kepen NEM bevasarlolista van, add vissza: {"tetelek": [],
"uzenet": "roviden mi van a kepen"}.

VALASZ - csak ez a JSON, semmi mas:
{
  "tetelek": [
    {"szoveg": "a tétel ugy, ahogy irva van",
     "megbizhatosag": 0.0-1.0,
     "bizonytalan_resz": "mi nem olvashato, vagy null"}
  ],
  "iras_tipusa": "keziras" | "nyomtatott" | "kepernyokep",
  "uzenet": "egy rovid mondat magyarul, ha van barmi emlitesre melto"
}"""


class KepHiba(Exception):
    pass


def _kep_tipus(adat):
    """A fajl elso bajtjaibol allapitja meg a tipust."""
    if adat[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if adat[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if adat[:4] == b"RIFF" and adat[8:12] == b"WEBP":
        return "image/webp"
    if adat[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def listat_kiolvas(kep_adat, model=None):
    """
    Kep -> nyers bevasarlolista-tételek.

    Visszaad:
      {"tetelek": [{"szoveg", "megbizhatosag", "bizonytalan_resz"}],
       "iras_tipusa", "uzenet"}
    """
    # Eloszor a kepet ellenorizzuk, csak utana a kulcsot: igy ertheto
    # hibat kap az is, akinek nincs beallitva a kulcs
    if not kep_adat:
        raise KepHiba("Ures kep.")
    if len(kep_adat) > MAX_MERET:
        raise KepHiba(f"A kep tul nagy ({len(kep_adat) // 1024 // 1024} MB). "
                      f"A hatar 20 MB.")

    tipus = _kep_tipus(kep_adat)
    if tipus not in TAMOGATOTT:
        raise KepHiba("Nem tamogatott kepformatum. JPEG, PNG, WebP vagy GIF "
                      "kell.")

    kulcs = os.environ.get("OPENAI_API_KEY")
    if not kulcs:
        raise KepHiba("Hianyzik az OPENAI_API_KEY.")

    adat_url = (f"data:{tipus};base64,"
                f"{base64.b64encode(kep_adat).decode()}")

    payload = {
        "model": model or MODELL,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": [
                {"type": "text",
                 "text": "Olvasd ki a bevasarlolistat errol a keprol."},
                {"type": "image_url",
                 "image_url": {"url": adat_url, "detail": "high"}},
            ]},
        ],
        "response_format": {"type": "json_object"},
    }
    # A temperature-t szandekosan NEM allitjuk: az ujabb modellek csak
    # az alapertelmezett erteket fogadjak el, a kepfelismeresnel pedig
    # ugysem szamit.

    keres = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {kulcs}"},
        method="POST")
    try:
        with urllib.request.urlopen(keres, timeout=180) as v:
            valasz = json.loads(v.read().decode("utf-8"))
    except urllib.error.HTTPError as h:
        test = h.read().decode("utf-8", errors="replace")
        # Modellenkent eltero korlatok: ha valamelyik mezot nem fogadja
        # el, kivesszuk es ujraprobaljuk - egyszer.
        ujra = _kihagyando_mezok(test)
        if ujra:
            for mezo in ujra:
                payload.pop(mezo, None)
            if "reasoning" in test.lower():
                payload["reasoning_effort"] = "none"
            return _ujra(keres.full_url, payload, kulcs)
        raise KepHiba(f"HTTP {h.code}: {test[:300]}")
    except urllib.error.URLError as h:
        raise KepHiba(f"Halozati hiba: {h}")

    return _feldolgoz(valasz)


def _kihagyando_mezok(hibaszoveg):
    """Melyik mezot nem fogadta el a modell?"""
    szoveg = hibaszoveg.lower()
    mezok = []
    for mezo in ("temperature", "response_format", "reasoning_effort",
                 "top_p", "detail"):
        if mezo in szoveg:
            mezok.append(mezo)
    return mezok


def _ujra(url, payload, kulcs):
    keres = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {kulcs}"}, method="POST")
    try:
        with urllib.request.urlopen(keres, timeout=180) as v:
            return _feldolgoz(json.loads(v.read().decode("utf-8")))
    except urllib.error.HTTPError as h:
        raise KepHiba(f"HTTP {h.code}: {h.read().decode()[:300]}")


def _feldolgoz(valasz):
    try:
        szoveg = valasz["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError):
        raise KepHiba("Varatlan valasz: " + json.dumps(valasz)[:300])

    szoveg = szoveg.strip()
    if szoveg.startswith("```"):
        szoveg = szoveg.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        adat = json.loads(szoveg)
    except json.JSONDecodeError:
        eleje, vege = szoveg.find("{"), szoveg.rfind("}")
        if eleje == -1 or vege == -1:
            raise KepHiba("Nem sikerult ertelmezni a valaszt.")
        adat = json.loads(szoveg[eleje:vege + 1])

    tetelek = []
    for t in adat.get("tetelek", []):
        if isinstance(t, str):
            t = {"szoveg": t, "megbizhatosag": 0.5}
        szov = (t.get("szoveg") or "").strip()
        if not szov:
            continue
        try:
            biztos = float(t.get("megbizhatosag", 0.5))
        except (TypeError, ValueError):
            biztos = 0.5
        tetelek.append({
            "szoveg": szov,
            "megbizhatosag": max(0.0, min(1.0, biztos)),
            "bizonytalan_resz": t.get("bizonytalan_resz") or None,
        })

    return {"tetelek": tetelek,
            "iras_tipusa": adat.get("iras_tipusa"),
            "uzenet": adat.get("uzenet")}
