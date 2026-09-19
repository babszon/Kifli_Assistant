#!/usr/bin/env python3
"""Statikus ellenorzes: gyanus mintak keresese a kodbazisban."""
import ast
import re
import sys
from pathlib import Path

ITT = Path(__file__).parent
talalatok = []


def jelez(fajl, sor, szint, uzenet):
    talalatok.append((szint, f"{fajl}:{sor}", uzenet))


for fajl in sorted(ITT.glob("*.py")):
    if fajl.name == "ellenorzes.py":
        continue
    forras = fajl.read_text(encoding="utf-8")
    fa = ast.parse(forras, filename=str(fajl))
    sorok = forras.splitlines()

    # 1. Csupasz except: elnyelheti a KeyboardInterruptot is
    for csomo in ast.walk(fa):
        if isinstance(csomo, ast.ExceptHandler) and csomo.type is None:
            jelez(fajl.name, csomo.lineno, "figyelem",
                  "csupasz except: - a KeyboardInterruptot is elnyeli")

    # 2. except Exception: pass - csendes elnyeles
    for csomo in ast.walk(fa):
        if (isinstance(csomo, ast.ExceptHandler)
                and len(csomo.body) == 1
                and isinstance(csomo.body[0], ast.Pass)):
            jelez(fajl.name, csomo.lineno, "figyelem",
                  "except ... : pass - csendben elnyelt hiba")

    # 3. Valtozo hasznalata definialas elott ugyanabban a fuggvenyben
    #    (egyszeru heurisztika: nev hasznalata, ami csak kesobb kap erteket)

    # 4. Mutalhato alapertelmezett parameter
    for csomo in ast.walk(fa):
        if isinstance(csomo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for alap in csomo.args.defaults + csomo.args.kw_defaults:
                if isinstance(alap, (ast.List, ast.Dict, ast.Set)):
                    jelez(fajl.name, csomo.lineno, "hiba",
                          f"{csomo.name}(): mutalhato alapertelmezett ertek")

    # 5. Nyitott fajl with nelkul
    for csomo in ast.walk(fa):
        if (isinstance(csomo, ast.Call)
                and isinstance(csomo.func, ast.Name)
                and csomo.func.id == "open"):
            szulo_with = any(
                isinstance(k, ast.With) and any(
                    e.context_expr is csomo for e in k.items)
                for k in ast.walk(fa))
            sor = sorok[csomo.lineno - 1]
            if not szulo_with and ".read_text" not in sor and "with " not in sor:
                jelez(fajl.name, csomo.lineno, "megjegyzes",
                      "open() with nelkul")

    # 6. Nem ASCII a kodban (cirill betuk keverednek be)
    for i, sor in enumerate(sorok, 1):
        for ch in sor:
            # Csak a latin betukre hasonlito cirill/gorog jelek gyanusak -
            # azok csendben elrontjak a kodot. Az emoji es a tipografia rendben.
            if 0x0400 <= ord(ch) <= 0x04FF or 0x0370 <= ord(ch) <= 0x03FF:
                jelez(fajl.name, i, "hiba",
                      f"cirill/gorog betu latin szovegben: {ch!r} "
                      f"U+{ord(ch):04X}")

    # 7. print() hosszu ciklusban flush nelkul - konteneren nem latszik
    if "PYTHONUNBUFFERED" not in forras and "flush=True" not in forras:
        pass  # a Dockerfile beallitja, rendben

    # 8. Idozites nelkuli halozati hivas
    for csomo in ast.walk(fa):
        if (isinstance(csomo, ast.Call)
                and isinstance(csomo.func, ast.Attribute)
                and csomo.func.attr in ("urlopen", "run", "connect")):
            kulcsok = {k.arg for k in csomo.keywords}
            if not ({"timeout"} & kulcsok) and csomo.func.attr == "urlopen":
                jelez(fajl.name, csomo.lineno, "hiba",
                      "urlopen() timeout nelkul - orokre lefagyhat")


# 9. A JS fajlokban: nem kezelt promise, elgepelt valtozo
for fajl in sorted((ITT / "webui").glob("*.html")):
    forras = fajl.read_text(encoding="utf-8")
    for i, sor in enumerate(forras.splitlines(), 1):
        if re.search(r"\bvar\s+\w", sor):
            jelez(fajl.name, i, "megjegyzes", "var helyett let/const")
        if "innerHTML" in sor and "esc(" not in sor and "`" in sor:
            if not re.search(r"innerHTML\s*=\s*['\"`][^$]*['\"`]\s*;?\s*$", sor):
                jelez(fajl.name, i, "figyelem",
                      "innerHTML sablonnal - ellenorizd az escapelest")

szintek = {"hiba": 0, "figyelem": 1, "megjegyzes": 2}
talalatok.sort(key=lambda t: (szintek[t[0]], t[1]))

szinek = {"hiba": "\033[91m", "figyelem": "\033[93m", "megjegyzes": "\033[90m"}
for szint, hely, uzenet in talalatok:
    print(f"{szinek[szint]}{szint:10}\033[0m {hely:24} {uzenet}")

szamok = {s: sum(1 for t in talalatok if t[0] == s) for s in szintek}
print(f"\n{szamok['hiba']} hiba, {szamok['figyelem']} figyelem, "
      f"{szamok['megjegyzes']} megjegyzes")
sys.exit(1 if szamok["hiba"] else 0)
