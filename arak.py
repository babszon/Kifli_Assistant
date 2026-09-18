#!/usr/bin/env python3
"""
Egysegar-szamitas es a talalatok rangsorolasa.

Az ar-ertek arany SZAMITAS, nem itelet: a program szamolja ki, nem az
LLM. Az LLM dolga csak az, hogy eldontse, melyik talalat tartozik
egyaltalan a kereshez (krumpli != edesburgonya != chips).
"""

# Kozos alapegysegre: minden suly kg-ra, minden terfogat literre,
# a darabos termekek darabra. Igy az egysegarak osszehasonlithatok.
SULY = {"g": 0.001, "dkg": 0.01, "kg": 1.0}
TERFOGAT = {"ml": 0.001, "cl": 0.01, "dl": 0.1, "l": 1.0}
DARAB = {"db": 1.0, "darab": 1.0, "pcs": 1.0}


def alapegyseg(mennyiseg, egyseg):
    """
    Visszaad: (ertek_alapegysegben, alapegyseg_neve) vagy (None, None).
    Pl. (400, 'g') -> (0.4, 'kg');  (330, 'ml') -> (0.33, 'l')
    """
    if mennyiseg is None or not egyseg:
        return None, None
    e = egyseg.lower().strip()
    for tabla, nev in ((SULY, "kg"), (TERFOGAT, "l"), (DARAB, "db")):
        if e in tabla:
            return mennyiseg * tabla[e], nev
    return None, None


def egysegar(termek):
    """
    Visszaad: (ar_alapegysegenkent, alapegyseg) vagy (None, None).

    Eloszor a Kifli sajat 'Unit price' mezojet hasznalja, mert az
    a pontos. Ha nincs, az arbol es a kiszerelesbol szamol.
    """
    # 1. A Kifli sajat egysegara
    if termek.get("egysegar") and termek.get("egysegar_egyseg"):
        e = termek["egysegar_egyseg"].lower().strip()
        for tabla, nev in ((SULY, "kg"), (TERFOGAT, "l"), (DARAB, "db")):
            if e in tabla:
                # A Kifli 'HUF/l' formaban adja, tehat mar egysegre vonatkozik
                return termek["egysegar"] / tabla[e] if tabla[e] else None, nev

    # 2. Szamitas arbol es kiszerelesbol
    ar = termek.get("ar")
    ertek, nev = alapegyseg(termek.get("mennyiseg"), termek.get("egyseg"))
    if ar and ertek:
        return ar / ertek, nev
    return None, None


def rangsorol(termekek):
    """
    Kiegesziti a termekeket egysegarral, es rendezi: eloszor az
    osszehasonlithatok egysegar szerint, utana a tobbi.

    Minden termek kap egy 'egysegar_szamitott' es 'alapegyseg' mezot,
    valamint egy 'legolcsobb' jelzot.
    """
    bovitett = []
    for t in termekek:
        ar, egys = egysegar(t)
        bovitett.append({**t, "egysegar_szamitott": ar, "alapegyseg": egys,
                         "legolcsobb": False})

    # Csak az azonos alapegysegueket lehet osszehasonlitani
    egysegek = {}
    for t in bovitett:
        if t["egysegar_szamitott"] and t["alapegyseg"]:
            egysegek.setdefault(t["alapegyseg"], []).append(t)

    # A leggyakoribb alapegyseg csoportjaban jeloljuk a legolcsobbat
    if egysegek:
        fo_csoport = max(egysegek.values(), key=len)
        legolcsobb = min(fo_csoport, key=lambda t: t["egysegar_szamitott"])
        legolcsobb["legolcsobb"] = True

    def kulcs(t):
        return (t["egysegar_szamitott"] is None,
                t["egysegar_szamitott"] or float("inf"))

    return sorted(bovitett, key=kulcs)


def megtakaritas(valasztott, termekek):
    """
    Hany szazalekkal dragabb a valasztott a legolcsobbnal?
    None, ha nem osszehasonlithato.
    """
    va = valasztott.get("egysegar_szamitott")
    if not va:
        return None
    azonosak = [t for t in termekek
                if t.get("egysegar_szamitott")
                and t.get("alapegyseg") == valasztott.get("alapegyseg")]
    if not azonosak:
        return None
    legolcsobb = min(t["egysegar_szamitott"] for t in azonosak)
    if legolcsobb <= 0:
        return None
    return (va - legolcsobb) / legolcsobb


def egysegar_szoveg(termek):
    """'713 Ft/kg' vagy ures string."""
    ar, egys = termek.get("egysegar_szamitott"), termek.get("alapegyseg")
    return f"{ar:,.0f} Ft/{egys}".replace(",", " ") if ar and egys else ""


if __name__ == "__main__":
    minta = [
        {"nev": "Újburgonya csomagolt", "ar": 356.3, "mennyiseg": 500,
         "egyseg": "g", "egysegar": 712.6, "egysegar_egyseg": "kg", "id": 1},
        {"nev": "Sárga burgonya lédig", "ar": 549, "mennyiseg": 1,
         "egyseg": "kg", "egysegar": None, "egysegar_egyseg": None, "id": 2},
        {"nev": "Bio burgonya", "ar": 1199, "mennyiseg": 1,
         "egyseg": "kg", "egysegar": None, "egysegar_egyseg": None, "id": 3},
        {"nev": "Magyar burgonya 2 kg", "ar": 1498, "mennyiseg": 2,
         "egyseg": "kg", "egysegar": None, "egysegar_egyseg": None, "id": 4},
    ]
    for t in rangsorol(minta):
        jel = " <- legolcsobb" if t["legolcsobb"] else ""
        print(f"  {t['nev']:26} {egysegar_szoveg(t):>12}{jel}")

    print()
    rangsorolt = rangsorol(minta)
    bio = next(t for t in rangsorolt if t["id"] == 3)
    print(f"  A bio burgonya {megtakaritas(bio, rangsorolt) * 100:.0f}%-kal dragabb.")
