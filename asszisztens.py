#!/usr/bin/env python3
"""
Kifli asszisztens - az LLM vezeti a beszelgetest, eszkozoket hiv.

    python3 asszisztens.py
    python3 asszisztens.py --szaraz      # nem ir a valodi kosarba

A kulonbseg a beszelgetes.py-hoz kepest: ott a program vezetett es
kulcsszavakat illesztett ("igen", "nem"). Itt minden megszolalasod az
LLM-hez megy, es O donti el, mit jelent. Ezert erti azt is, hogy
"bocsanat, igen jo lesz" vagy "melyik a legolcsobb markas?".

Ami NEM az LLM-e:
  - a darabszam-szamitas (30 tojas -> 3 doboz), mert abban hibazna
  - a vegso jovahagyas a kosar elott
"""

import argparse
import time
import sys

import adat
import arak
import parser as p
import szinkron
import motor as motor_modul
from mcp_kliens import MCPKliens, MCPHiba


Z, PI, S, SZ, HA, ALAP = ("\033[92m", "\033[91m", "\033[93m",
                          "\033[96m", "\033[90m", "\033[0m")

# A kosarellenorzeshez: a Kifli kosarnevei gyakran csonkak, de a
# "tej" nem egyezhet a "tejfol"-lel.
_NEV_MIN_ELOTAG = 12


def _nevek_egyeznek(a, b):
    """Pontos egyezes, vagy csonka elotag (min. 12 karakter)."""
    a = (a or "").lower().strip()
    b = (b or "").lower().strip()
    if not a or not b:
        return False
    if a == b:
        return True
    rovidebb, hosszabb = (a, b) if len(a) <= len(b) else (b, a)
    return (len(rovidebb) >= _NEV_MIN_ELOTAG
            and hosszabb.startswith(rovidebb))

RENDSZERPROMPT = """Egy magyar haztartas bevasarlo-asszisztense vagy a
Kifli.hu webshopban. A felhasznalo beszel hozzad, te eszkozoket hivsz.

STILUS - EZ A LEGFONTOSABB
A valaszod HANGON fog elhangzani, es a felhasznalo sokszor NEM nezi a
kepernyot. Ugy beszelj, ahogy egy kedves, gyakorlott asszisztens
beszelne a konyhaban allva - nem ugy, mint egy lista vagy egy gep.

- Osszefuggo MONDATOKBAN beszelj, ne felsorolasban. Rossz: "Betettem.
  Kitchin Extra szuz olivaolaj, 0.75 l, 4166 forint." Jo: "Bement a
  Kitchin extra szuz olivaolaj, het es fel deci, negyezer-szazhatvanhat
  forint - most akcios."
- Legyen emberi ritmusa. Hasznalj kotoszot, atvezetest: "akkor", "meg",
  "es mar csak", "kesz is". Ne minden mondat ugyanugy induljon.
- Legyen kedves, de ne nyalas. Egy-egy termeszetes reakcio belefer
  ("jo valasztas", "ez most olcso"), de ne dicserj minden lepesnel.
- Ket-harom mondat a szokasos hossz. Ha sok mindent csinaltal
  egyszerre, lehet negy is - de akkor is mondatokban.
- A hosszu termekneveket ROVIDITSD beszedben, ha egyertelmu. A
  "Kitchin Extra szuz olivaolaj" lehet "a Kitchin olivaolaj". Az
  ar es a kiszereles viszont MINDIG hangozzon el pontosan.
- SOHA ne olvass fel hosszu talalati listat. Ha a felhasznalo
  valasztani szeretne, ket-harom lehetoseget mondj, nem tobbet.

MUNKAMENET - HALADJ MAGADTOL
A felhasznalonak NE kelljen minden tetelnel biztatnia. Ha felsorol ot
dolgot, menj vegig mind az oton anelkul, hogy kozben kerdezgetned,
hogy "folytassam?". Csak ott allj meg, ahol tenyleg dontenie kell.

1. Ha a felhasznalo terméket emlit, hivd a termek_keres eszkozt.
   Tobb terméket emlithet egy mondatban - keress rajuk egyesevel,
   EGYMAS UTAN, ugyanabban a korben.
2. Amit MAGABIZTOSAN el tudsz donteni, azt TEDD BE KERDEZES NELKUL:
   - a kereses jelzi, hogy korabban mar vette ("korabban_vett")
   - vagy egyertelmu, melyik termek kell (egy markat nevezett meg,
     vagy csak egy ertelmes talalat van)
   Ezeknel ne kerdezz, csak tedd be, es a vegen mondd el, mi ment be.
3. CSAK AKKOR kerdezz, ha tenyleg dontes kell:
   - tobb ertelmes valtozat van (izesites, kiszereles, minoseg)
   - a talalat nem egyertelmuen az, amit kertek
   - draga termek, es van sokkal olcsobb odaillo alternativa
   Ilyenkor egy kerdest tegyel fel, ket-harom lehetoseggel.
4. A vegen OSSZEFOGLALVA mondd el, mi ment be, es ha valami kimaradt
   vagy kerdeses, azt is. Peldaul: "Bement a tej, a kenyer meg a
   tojas, osszesen ezernyolcszaz forint. A sajtbol viszont tobbfele
   van - trappistat vagy goudat kerjek?"
5. Ha nemet mond egy javaslatra, javasolj MASIKAT ugyanabbol a
   talalati listabol. Ne keress ujra, hacsak nem kifejezetten mast ker.
6. SOHA ne kerdezd, hogy "folytassam?" vagy "mehetunk tovabb?".
   Menj tovabb magadtol. Akkor allj meg, ha elfogytak a tetelek.
7. Ha kerdez (mi a legolcsobb, mik vannak meg, mennyibe kerul),
   VALASZOLJ a mar meglevo talalatokbol. Ne hivj ujra eszkozt.
8. Ha lezarna (kesz, mehet, ennyi lesz), hivd a kosar_lezar eszkozt.
9. Ha a felhasznalo MASIK markat vagy valtozatot ker (pl. "inkabb
   Finish-t"), es az nincs a mar meglevo talalatok kozott, KERESS RA
   kulon. Csak akkor valassz a meglevo listabol, ha tenyleg ott van.
10. TOBB TETEL EGYSZERRE. Ha a felhasznalo egy mondatban tobb terméket
   sorol fel, mindet fel kell dolgoznod. Menj VEGIG rajtuk egyesevel:
   javasolj, kerdezz, tedd be, majd LEPJ A KOVETKEZORE magadtol.
   A vegen mondd meg, ha valamelyik kimaradt.
   SOHA ne hagyj ki tetelt csendben.
11. MENNYISEGEK - EZ FONTOS.
   Add at a mennyiseg_szoveg-et UGY, AHOGY A FELHASZNALO MONDTA:
   'harminc deka', '20 tojas', 'ket liter'. A PROGRAM szamolja ki
   belole a csomagszamot - NE SZAMOLJ TE. A 'darab' parametert CSAK
   akkor add meg, ha a felhasznalo explicit CSOMAGSZAMOT mondott
   ('ket doboz', 'tegyel be harom csomagot').

   - "egy 16 tekercses csomag vecepapir"  -> mennyiseg_szoveg = 'egy csomag'
   - "harom doboz tojas"                  -> mennyiseg_szoveg = 'harom doboz'
   - "ket liter tej"                      -> mennyiseg_szoveg = 'ket liter'
   - "harminc deka sajt"                  -> mennyiseg_szoveg = 'harminc deka'
   - "20 tojas"                           -> mennyiseg_szoveg = '20 tojas'
   - ha nem mondott mennyiseget           -> hagyd ki a parametert

   A kiszereles (16 tekercs, 10 db, 1 liter) a termek TULAJDONSAGA,
   sosem a darabszam. Ha a felhasznalo azt mondja, hogy "csak egy
   kell", az darab = 1, akkor is, ha a csomagban 16 tekercs van.

   Ha mar a kosarban van valami rossz mennyiseggel, a
   mennyiseget_modosit eszkozt hasznald - NE vedd ki es tedd be ujra.

HIBAK KEZELESE
Ha egy eszkoz valaszaban 'hiba' mezo van, az a termek NEM kerult be a
kosarba. Ilyenkor:
- SOHA ne mondd, hogy bement, hogy betetted, vagy hogy megvan.
- Mondd meg roviden, mi tortent, es lepj tovabb a kovetkezo tetelre.
- A program magatol var es ujraprobal, ha a Kifli lassit - neked nem
  kell ujra hivnod ugyanazt az eszkozt. Ha megis hibat kapsz, az mar a
  vegleges allapot.
- Ha a hiba azt mondja, hogy a Kifli "tul sok kerest kap", akkor a
  webshop lassit, nem a te hibad es nem is a felhasznaloe. Ilyenkor:
  ALLJ MEG AZONNAL. Ne probald vegigfuttatni a tobbi tételt, mert
  mindegyik ugyanugy elbukna. Mondd meg roviden, hogy a Kifli most
  terhelt, es sorold fel, mi maradt ki - hogy kesobb ne kelljen ujra
  elmondania. Kerdezd meg, varjatok-e par percet.
- Ha a hiba megmondja, hany masodpercig nem probalkozol ujra, azt
  mondd el a felhasznalonak, hogy tudja, mennyit kell varnia.
- A vegen foglald ossze, mi maradt ki. Peldaul: "A tej, a kenyer es a
  tojas bement. A mosoport most nem talalta a rendszer, azt majd
  probaljuk ujra."
- Ha bizonytalan vagy abban, mi van a kosarban, hivd a kosar_megmutat
  eszkozt, es abbol beszelj - ne emlekezetbol.

TILTASOK - EZEKET SOHA NE TEDD
0. AZ ADATOK PONTOSSAGA. Ha az eszkoz valaszaban van 'adatok' mezo,
   az abban szereplo TERMEKNEVET, ARAT es KISZERELEST pontosan kell
   kozolnod - de SAJAT, TERMESZETES MONDATBAN, nem felsorolasként.
   A felhasznalo sokszor nem nezi a kepernyot, ezert ez az egyetlen
   modja, hogy ellenorizze, mi kerult a kosarba.

   Az ARAT es a MENNYISEGET soha ne valtoztasd meg es ne hagyd el.
   A terméknevet roviditheted, ha egyertelmu marad.

   Jo:   "Bement a Kitchin olivaolaj, het es fel deci, negyezer-
          szazhatvanhat forintert."
   Jo:   "Megvan a ket Old Spice dezodor, darabja ketezer-kilencven-
          kilenc, osszesen negyezer-szazkilencvennyolc forint."
   Rossz: "Betettem. Kitchin Extra szuz olivaolaj, 0.75 l, 4166 forint."
          (ez felsorolas, nem mondat)
   Rossz: "Bement az olivaolaj." (hianyzik az ar)

   Ha tobb terméket tettel be egyszerre, egy mondatban is osszefoglal-
   hatod oket, de MINDEGYIK ara hangozzon el, vagy mondd meg a vegosszeget.
1. SOHA ne allitsd, hogy a rendeles leadva, lezarva vagy elkuldve.
   A termekeket a Kifli kosarba teszed, de a RENDELEST a felhasznalo
   adja le a Kifli appban: ott valaszt idosavot es fizet.
   A helyes valasz a vegen: "Kesz, minden a kosaradban van. A Kifli
   appban tudod befejezni." NEM: "Lezartam a rendelest", NEM
   "Koszonom a vasarlast".
2. SOHA ne emlits olyan terméket, arat vagy kiszerelest, ami nem
   szerepel a termek_keres eredmenyeben. Ha nem talalod a listaban,
   mondd meg, hogy nincs ilyen talalat. Inkabb legy hasznalhatatlan,
   mint kitalalos.
3. SOHA ne mondj vegosszeget fejbol. Hivd a kosar_osszeg eszkozt.
4. SOHA ne keress ujra olyan termekre, aminek a talalatai mar
   megvannak az elozmenyben. Ha a felhasznalo valaszt a mar kiirt
   listabol, csak hivd a kosarba_tesz eszkozt a megfelelo ID-vel.

DONTESI ELVEK
- Az egysegar (Ft/kg, Ft/l) alapjan a legolcsobb NEM mindig a jo valasz.
  Egy baba-mosogel olcsobb lehet, de nem altalanos mososzer.
  Eloszor azt nezd, hogy a talalat TENYLEG az-e, amit kertek.
- A megszokott, bevett markak jobbak, mint az ismeretlen olcso.
- Ha akcios egy jo termek, emlitsd meg egy fel mondatban.
- Ha a felhasznalo kifejezetten olcsot ker, akkor a legolcsobb
  ODAILLO terméket javasold.
- Ha azt kerdezi, mit szokott venni vagy akcios-e a szokasos, hivd a
  szokasos_termekek eszkozt.
- Ha ALTALANOSSAGBAN kerdez az akciokrol, az akciok_most eszkozt hivd.
- Ha egy KONKRET AKCIOS SZEKCIOT emlit nev szerint - peldaul "Ments
  meg" (kozeli lejaratu termekek), "a het akcioi", "tobbet olcsobban" -,
  eloszor hivd az akcio_kategoriak eszkozt, keresd meg a nevhez tartozo
  azonositot, es azzal hivd az akciok_most eszkozt. SOHA ne mondd, hogy
  nem tudsz ranezni egy szekciora, amig ezt meg nem probaltad.
  A 'tipus' parameter kulon szekciokat is elerhetove tesz:
  week-sales, multipack, bundles, premium-sales, favorite-sales.
- Ha azt kerdezi, mit rendelt korabban, a korabbi_rendelesek eszkozzel
  kezdd. A tetelekhez utana a rendeles_reszletei kell.
- "Ugyanazt kerem, mint legutobb" eseten: korabbi_rendelesek, majd a
  legutobbi rendelesre rendeles_reszletei, es a tetelekre egyesevel
  termek_keres + kosarba_tesz. Ne talald ki a tetellistat.
- Mielott nagyobb rendelest zarnal le, erdemes a beutemezett_rendelesek
  eszkozzel ellenorizni, hogy nincs-e mar folyamatban rendeles.

FELTOLTOTT KEP
Ha a felhasznalo kepet tolt fel a listajarol, hivd a feltoltott_lista
eszkozt. HAROM csoportot kapsz vissza, es mindegyikkel MAS a teendo.

1. 'biztosan_olvashato' - ugy jarj el, mintha diktalta volna: keress ra,
   es tedd be.

2. 'rank_bizta' - olvashato, de a felhasznalo szandekosan nyitva hagyta:
   "kenyer valami jobb fele", "valami dinnye", "tojas jobb fele".
   NE KERDEZZ VISSZA. Keress ra, es valaszd a LEGJOBB AR-ERTEK ARANYUT -
   nem a legolcsobbat, hanem azt, ami a penzeert a legtobbet adja.
   A "jobb fele" azt jelenti, hogy a minoseg szamit, nem csak az ar.
   A visszaigazolasban mondd meg, mit valasztottal es miert roviden:
   "A kenyerbol a teljes kiorlesu Rozsavolgyit tettem be, mert az
   olcsobb kilonkent, mint a tobbi teljes kiorlesu."

3. 'bizonytalan' - ezeket nem tudtuk elolvasni. EGYSZERRE olvasd fel
   oket, egy mondatban, ne egyesevel. Peldaul: "Harom sort nem tudok
   biztosan kiolvasni: a hatodikban paprika van valami athuzva, a
   WC papirnal lelog a sor vege, es van egy sor, ami lehet harminc vagy
   otven deka." Csak a valasza utan tedd be oket.

A vegen foglald ossze, mit tettel be, es kerdezd meg, maradt-e ki
valami. SOHA ne talalj ki tételt, ami nem szerepelt a listan.

HELYETTESITES - OLCSOBB ALTERNATIVAK
- Ha a felhasznalo azt kerdezi, lehetne-e olcsobban, vagy ha a lezaras
  elott sok minden van a kosarban, hivhatod a helyettesitest_javasol
  eszkozt.
- A javaslatokat EGYESEVEL mutasd be, roviden. Mondd meg a nevet es
  azt, hany szazalekkal olcsobb. Peldaul: "A Miil gouda helyett az
  Ammerlander tilsiter most 30 szazalekkal olcsobb kilonkent - erdekel?"
- FONTOS: a ket termek NEM ugyanaz. Soha ne mondd, hogy "ugyanaz csak
  olcsobb". Mondd meg mindket nevet, hogy a felhasznalo tudja, mit
  cserelne.
- A valasza utan MINDIG hivd a helyettesitest_dontesz eszkozt. Ha
  elfogadta, az elvegzi a cseret is - neked nem kell kivenni es
  betenni.
- Egy beszelgetesben legfeljebb KET-HAROM cseret ajanlj fel. Tobb mar
  zavaro, es a felhasznalo nem azert jott, hogy alkudozzon.
- SOHA ne csereld le magatol, amit a felhasznalo kert. A csere mindig
  az o dontese.

SZALLITAS, ELOFIZETES, CIM
- Ha a szallitas idejerol kerdez, hivd a szallitasi_idosavok eszkozt, es
  mondd meg a LEGKORABBI lehetoseget az araval. Legfeljebb ket-harom
  idopontot sorolj fel, tobbet soha.
- Az idosavot INNEN NEM LEHET LEFOGLALNI. A felhasznalo a Kifli appban
  valasztja ki, a fizetessel egyutt. Soha ne allitsd, hogy lefoglaltad,
  beallitottad vagy kivalasztottad.
- Ha a szallitas araról vagy az elofizetesrol kerdez, hivd az
  elofizetesem eszkozt. Ha van aktiv Premium, azt erdemes megemliteni -
  peldaul hogy ingyenes a szallitas, vagy hany expressz maradt.
- Az arak amugy is a felhasznalo sajat fiokjabol jonnek, tehat amit a
  keresesben latsz, az mar a ra vonatkozo ar. Ne szamolj hozza vagy
  vonj le belole semmit.
- Ha a cimrol kerdez, hivd a szallitasi_cimem eszkozt. A cim
  MEGVALTOZTATASA sem lehetseges innen - azt is a Kifli appban teszi.

AR-ERTEK ARANY
Ha a felhasznalo azt kerdezi, mi a legjobb ar-ertek arany, NE csak az
egysegarat nezd. A termeknev maga sok minosegi informaciot hordoz, es
ezt kell osszevetned az arral. Magyar termekneveken pl:

- Olivaolaj: "extra szuz" (hidegsajtolt, legjobb) > "szuz" >
  "pomace" vagy "sansa" (olivapogacsabol, vegyi uton, gyenge minoseg).
  A pomace olcsobb, de NEM ugyanaz a termek.
- Felvagott, virsli, sonka: a "% hustartalom" a kulcs. 94% >> 55%.
- Tojas: "szabadtartasu" es "mélyalmos" > ketreces.
- Kenyer, liszt, teszta: "teljes kiorlesu" mas kategoria, mint a feher.
- Tejtermek: a zsirtartalom (%) nem minoseg, hanem valtozat - ne
  keverd ossze. A "sajtszeru keszitmeny" viszont NEM sajt.
- Gyumolcsle: "100%" vagy "rostos" > "nektar" > "udito".
- Altalanos: "bio", "E-mentes", "hozzaadott cukor nelkul",
  "adalekanyag-mentes" felarat jelent, de valodi kulonbseget is.

A valaszod EKKOR IS rovid legyen, legfeljebb harom mondat: mondd meg,
melyiket ajanlod, es EGY okot ra. Peldaul: "A Kitchin extra szuz a jo
valasztas, 5555 forint literenkent. A ket olcsobb pomace olaj, az
gyengebb minoseg." Ne sorold fel az osszes talalatot.

Ha a nevekbol nem derul ki a minosegi kulonbseg, mondd meg oszinten,
hogy csak az ar es a kiszereles alapjan tudsz donteni.

BIZONYTALANSAG
- Ha nem erted, mit mondott, kerdezz vissza egy rovid mondattal.
- Ures uzenetre vagy ertelmetlen bemenetre NE talalj ki semmit,
  csak kerdezz vissza: "Bocsanat, ezt nem ertettem."
- Soha ne tedd kosarba azt, amire nem mondott igent."""

ESZKOZOK = [
        {
            "name": "termek_keres",
            "description": ("Rakeres egy termekre a Kifli.hu-n. A talalatokat "
                            "egysegarral egyutt adja vissza, es jelzi, ha a "
                            "felhasznalo korabban mar vett ilyet."),
            "parameters": {
                "type": "object",
                "properties": {
                    "termek": {"type": "string",
                               "description": "A keresendo termek neve, "
                                              "alanyesetben, egyes szamban"},
                    "mennyiseg_szoveg": {
                        "type": "string",
                        "description": "A felhasznalo altal mondott mennyiseg "
                                       "nyersen, pl. 'harminc deka' vagy "
                                       "'ket liter'. Ures, ha nem mondott."},
                },
                "required": ["termek"],
            },
        },
        {
            "name": "kosarba_tesz",
            "description": ("Egy kivalasztott termeket AZONNAL a valodi "
                            "Kifli kosarba tesz."),
            "parameters": {
                "type": "object",
                "properties": {
                    "kifli_id": {"type": "integer"},
                    "termek": {"type": "string",
                               "description": "A normalizalt termeknev, ahogy "
                                              "a felhasznalo hivja (pl. 'ketchup')"},
                    "darab": {
                        "type": "integer",
                        "description":
                            "Hany CSOMAGOT tegyunk a kosarba. CSAK akkor "
                            "add meg, ha a felhasznalo explicit csomagszamot "
                            "mondott ('ket doboz', 'harom csomag'). Ha "
                            "mennyiseget mondott ('20 tojas', 'ket liter', "
                            "'harminc deka'), add at mennyiseg_szoveg-kent, "
                            "es HAGYD KI ezt a parametert - a program "
                            "szamolja ki a csomagszamot."},
                    "mennyiseg_szoveg": {
                        "type": "string",
                        "description":
                            "A felhasznalo altal mondott mennyiseg nyersen, "
                            "pl. 'harminc deka', '20 tojas', 'ket liter'. "
                            "A program ebbol szamolja a csomagszamot."},
                },
                "required": ["kifli_id", "termek"],
            },
        },
        {
            "name": "mennyiseget_modosit",
            "description": ("Egy mar kosarban levo tetel darabszamanak "
                            "modositasa. Ezt hasznald, ha a felhasznalo "
                            "keveselli vagy sokallja a mennyiseget - ne "
                            "vedd ki es tedd be ujra."),
            "parameters": {
                "type": "object",
                "properties": {
                    "termek": {"type": "string",
                               "description": "a termek neve vagy egy resze"},
                    "darab": {"type": "integer",
                              "description": "az uj darabszam (legalabb 1)"},
                },
                "required": ["termek", "darab"],
            },
        },
        {
            "name": "feltoltott_lista",
            "description": (
                "A felhasznalo altal feltoltott KEPROL kiolvasott "
                "bevasarlolista. Akkor hivd, ha a felhasznalo azt mondja, "
                "hogy kepet toltott fel, fotot csinalt a listarol, vagy "
                "ha ertesitest kapsz arrol, hogy kep erkezett. Minden "
                "tételhez megbizhatosagot is kapsz - ami bizonytalan, azt "
                "NE tedd be csendben, hanem olvasd fel es kerdezz ra."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "helyettesitest_javasol",
            "description": (
                "Megnezi, van-e a kosarban olyan termek, amire most van "
                "olcsobb vagy akcios alternativa. Akkor hivd, ha a "
                "felhasznalo azt kerdezi, lehet-e olcsobban, vagy a "
                "lezaras elott egyszer, ha sok minden van a kosarban. "
                "Amit korabban elutasitott, azt nem ajanlja ujra."),
            "parameters": {
                "type": "object",
                "properties": {
                    "termek": {
                        "type": "string",
                        "description": ("egy konkret termek neve, ha csak "
                                        "arra vagy kivancsi; kihagyhato")},
                },
            },
        },
        {
            "name": "helyettesitest_dontesz",
            "description": (
                "Rogziti, hogy a felhasznalo elfogadta vagy elutasitotta "
                "egy helyettesitesi javaslatot. MINDIG hivd, miutan "
                "valaszolt - igy legkozelebb nem kerdezed ujra ugyanazt. "
                "Elfogadas eseten a csere is megtortenik."),
            "parameters": {
                "type": "object",
                "properties": {
                    "eredeti_id": {"type": "integer",
                                   "description": "a kosarban levo termek"},
                    "alternativ_id": {"type": "integer",
                                      "description": "a javasolt termek"},
                    "elfogadta": {"type": "boolean"},
                },
                "required": ["eredeti_id", "alternativ_id", "elfogadta"],
            },
        },
        {
            "name": "kosar_megmutat",
            "description": ("Megmutatja a VALODI Kifli kosar tartalmat "
                            "arakkal es vegosszeggel."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "kosarbol_kivesz",
            "description": ("Levesz egy tetelt a VALODI Kifli kosarbol. "
                            "A termek nevenek egy reszlete eleg."),
            "parameters": {
                "type": "object",
                "properties": {"termek": {"type": "string"}},
                "required": ["termek"],
            },
        },
        {
            "name": "kosar_osszeg",
            "description": ("A VALODI Kifli kosar vegosszege es tetelei. "
                            "MINDIG ezt hivd, ha arrol kerdeznek, "
                            "soha ne szamolj fejbol."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "szokasos_termekek",
            "description": ("A felhasznalo korabbi rendeleseibol a "
                            "leggyakrabban vett termekek, es hogy melyik "
                            "akcios most. Akkor hivd, ha azt kerdezi, mit "
                            "szokott venni, vagy hogy akcios-e a szokasos."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "etkezes_javaslat",
            "description": ("Javaslatok egy adott etkezeshez a felhasznalo "
                            "vasarlasi elozmenyeibol. Akkor hivd, ha azt "
                            "kerdezi, mi kell a reggelihez, vacsorahoz, "
                            "sutéshez, vagy hasonlo."),
            "parameters": {
                "type": "object",
                "properties": {
                    "etkezes": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack",
                                 "baking", "drinks", "healthy"],
                        "description": "reggeli=breakfast, ebed=lunch, "
                                       "vacsora=dinner, nassolnivalo=snack, "
                                       "sutes=baking, italok=drinks, "
                                       "egeszseges=healthy"},
                    "darab": {"type": "integer",
                              "description": "hany terméket javasoljon (3-30)"},
                },
                "required": ["etkezes"],
            },
        },
        {
            "name": "korabbi_rendelesek",
            "description": ("A felhasznalo korabbi, mar kiszallitott "
                            "rendeleseinek listaja datummal. Akkor hivd, ha "
                            "azt kerdezi, mit rendelt korabban vagy mikor."),
            "parameters": {
                "type": "object",
                "properties": {
                    "darab": {"type": "integer",
                              "description": "hany rendelest (1-20)"},
                },
            },
        },
        {
            "name": "rendeles_reszletei",
            "description": ("Egy konkret korabbi rendeles teljes tetellistaja. "
                            "Eloszor hivd a korabbi_rendelesek eszkozt, hogy "
                            "megtudd a rendeles azonositojat."),
            "parameters": {
                "type": "object",
                "properties": {"rendeles_id": {"type": "string"}},
                "required": ["rendeles_id"],
            },
        },
        {
            "name": "beutemezett_rendelesek",
            "description": ("A mar leadott, meg ki nem szallitott rendelesek. "
                            "Akkor hivd, ha a felhasznalo azt kerdezi, van-e "
                            "mar folyamatban rendelese, vagy ha ketszer "
                            "rendelne ugyanazt."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "akciok_most",
            "description": (
                "A jelenleg akcios termekek. Akkor hivd, ha a felhasznalo "
                "altalanossagban kerdez az akciokrol, vagy egy adott "
                "akciotipusra kivancsi. Ha azt kerdezi, hogy a SZOKASOS "
                "termekei akciosak-e, a szokasos_termekek eszkozt hivd."),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipus": {
                        "type": "string",
                        "enum": ["sales", "week-sales", "multipack",
                                 "bundles", "premium-sales",
                                 "favorite-sales"],
                        "description":
                            "sales = minden akcio (alap); week-sales = a "
                            "het akcioi; multipack = tobbet olcsobban; "
                            "bundles = termekcsomagok; premium-sales = csak "
                            "Xtra elofizetoknek; favorite-sales = nepszeru "
                            "akciok"},
                    "kategoria_id": {
                        "type": "integer",
                        "description":
                            "Egy kategoriara szukites. Az azonositokat az "
                            "akcio_kategoriak eszkoz adja meg. Ha a "
                            "felhasznalo egy szekciot emlit nev szerint "
                            "(peldaul 'Ments meg'), eloszor azt hivd."},
                    "darab": {"type": "integer",
                              "description": "hany terméket (1-50)"},
                },
            },
        },
        {
            "name": "akcio_kategoriak",
            "description": (
                "A Kifli akcios szekcioinak listaja nevvel es azonositoval. "
                "Akkor hivd, ha a felhasznalo egy konkret szekciot emlit "
                "nev szerint - peldaul 'Ments meg' (kozeli lejaratu "
                "termekek) -, es meg kell talalnod hozza az azonositot. "
                "Ne talalgasd az azonositot, mindig ebbol dolgozz."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "elofizetesem",
            "description": ("A felhasznalo Kifli Premium / Xtra "
                            "elofizetesenek allapota: aktiv-e, mennyi "
                            "ingyenes szallitas es expressz maradt. Akkor "
                            "hivd, ha a szallitas araról, az elofizetesrol "
                            "vagy a kedvezmenyekrol kerdez."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "szallitasi_cimem",
            "description": ("A jelenleg kivalasztott szallitasi cim es a "
                            "kovetkezo szallitas adatai. Akkor hivd, ha a "
                            "felhasznalo azt kerdezi, hova megy a rendeles, "
                            "vagy melyik cimre szallitanak."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "szallitasi_idosavok",
            "description": ("A szabad szallitasi idosavok a felhasznalo "
                            "cimere. Akkor hivd, ha arrol kerdez, mikor "
                            "erkezhet a rendeles, vagy mikor a legkorabbi "
                            "szallitas."),
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "kosar_lezar",
            "description": ("Jelzi, hogy a felhasznalo keszen van, es "
                            "megmutatja a Kifli kosar vegleges tartalmat. "
                            "NEM adja le a rendelest - azt a felhasznalo "
                            "fejezi be a Kifli appban."),
            "parameters": {"type": "object", "properties": {}},
        },
]


_ESZKOZ_NEVEK = {e["name"] for e in ESZKOZOK}


class Asszisztens:
    def __init__(self, mcp, tarolo, szaraz=False):
        self.mcp = mcp
        self.tarolo = tarolo
        self.szaraz = szaraz
        self.utolso_talalatok = []
        self.arak_szerint = {}        # kifli_id -> ar, a vegosszeghez
        self._akcio_gyorstar = None
        self.kep_tetelek = None        # a feltoltott keprol kiolvasva
        # Amire mar kerestunk ebben a beszelgetesben - nem kerdezunk ujra
        self._kereses_gyorstar = {}
        self._mennyiseg_gyorstar = {}  # termek -> a felhasznalo mennyisege
        self._kosar_gyorstar = None    # (idopont, nyers valasz)
        self.lezarva = False

    # ------------------------------------------------------------- eszkozok

    def termek_keres(self, termek, mennyiseg_szoveg="", frissen_keress=False):
        """
        Termekkereses a Kiflin.

        A Kifli ratakorlatot szab, ezert KET helyen sporolunk kerest:
        1. Amit mar megtanultunk, arra nem keresunk ujra - az ID megvan.
        2. Amire mar kerestunk ebben a beszelgetesben, azt a
           gyorstarbol adjuk vissza.
        Egy 15 tételes listanal ez a keresesek ketharmadat megsporolja.
        """
        termek = (termek or "").strip().lower()
        if not termek:
            return {"hiba": "Ures keresés."}
        if mennyiseg_szoveg:
            self._mennyiseg_gyorstar[termek] = str(mennyiseg_szoveg).strip()

        ismert = self.tarolo.keres(termek)

        # 1. Tanult termek - nincs szukseg keresesre
        if ismert and not frissen_keress:
            talalat = {
                "id": ismert["kifli_id"], "nev": ismert["kifli_nev"],
                "ar": self.arak_szerint.get(ismert["kifli_id"]),
                "mennyiseg": ismert["amount_value"],
                "egyseg": ismert["amount_unit"],
                "bulk": bool(ismert["bulk"]),
            }
            self._talalatokat_megjegyez([talalat])
            print(f"\n{HA}  '{termek}' - ismert, nem kerestem ujra{ALAP}")
            return {
                "kereses": termek,
                "mennyiseg_szoveg": mennyiseg_szoveg or None,
                "talalatok": [{
                    "id": talalat["id"], "nev": talalat["nev"],
                    "ar": talalat["ar"],
                    "kiszereles": (f"{talalat['mennyiseg']:g} "
                                   f"{talalat['egyseg']}"
                                   if talalat.get("mennyiseg") else None),
                }],
                "ismert_termek": True,
                "hanyszor_vette": ismert["hit_count"],
                "megjegyzes": (
                    "Ezt a felhasznalo korabban mar valasztotta, ezert nem "
                    "kerestem ujra - igy gyorsabb, es kevesebbet terheljuk "
                    "a Kiflit. Tedd be kerdes nelkul. Ha a felhasznalo "
                    "MASIKAT szeretne, hivd ujra ezt az eszkozt a "
                    "frissen_keress=true kapcsoloval."),
            }

        # 2. Ebben a beszelgetesben mar kerestunk ra
        if not frissen_keress and termek in self._kereses_gyorstar:
            talalatok = self._kereses_gyorstar[termek]
            print(f"\n{HA}  '{termek}' - mar kerestem, a korabbi "
                  f"talalatok{ALAP}")
        else:
            try:
                nyers = self.mcp.hiv("search_products",
                                     {"product_name": termek, "limit": 25})
            except MCPHiba as e:
                return {"hiba": str(e)}

            talalatok = arak.rangsorol(p.termekek_ertelmez(nyers))
            if not talalatok:
                return {"talalatok": [],
                        "uzenet": f"Nincs talalat erre: {termek}",
                        "megjegyzes": ("Mondd meg oszinten, hogy nincs "
                                       "talalat. NE talalj ki terméket.")}
            self._kereses_gyorstar[termek] = talalatok
            self._talalatok_kiir(termek, talalatok)

        # A korabbi talalatok is elerhetok maradnak, hogy a felhasznalo
        # visszahivatkozhasson rajuk ("akkor megis az elso legyen")
        self._talalatokat_megjegyez(talalatok)

        eredmeny = {
            "kereses": termek,
            "mennyiseg_szoveg": mennyiseg_szoveg or None,
            "talalatok": [{
                "id": t["id"], "nev": t["nev"], "marka": t.get("marka"),
                "ar": t.get("ar"),
                "kiszereles": (f"{t['mennyiseg']:g} {t['egyseg']}"
                               if t.get("mennyiseg") else None),
                "egysegar": arak.egysegar_szoveg(t) or None,
                "kedvezmeny": t.get("kedvezmeny"),
                "legolcsobb": t.get("legolcsobb"),
            } for t in talalatok],
        }
        if ismert:
            eredmeny["korabban_vett"] = {
                "id": ismert["kifli_id"], "nev": ismert["kifli_nev"],
                "hanyszor": ismert["hit_count"],
            }
        return eredmeny

    # A kosar tartalma ennyi ideig ervenyes. Egymas utan betett
    # tételeknel igy nem kerjuk le minden alkalommal - a Kifli
    # ratakorlatja miatt ez sokat szamit.
    KOSAR_ERVENYES = 4.0     # masodperc

    def _kosar_nyers(self, frissen=False):
        """A kosar nyers tartalma, rovid ideig gyorstarazva."""
        most = time.monotonic()
        if (not frissen and self._kosar_gyorstar
                and most - self._kosar_gyorstar[0] < self.KOSAR_ERVENYES):
            return self._kosar_gyorstar[1]
        nyers = self.mcp.hiv("get_cart_content")
        self._kosar_gyorstar = (most, nyers)
        return nyers

    def _kosar_ervenytelenit(self):
        """A kosar valtozott - a kovetkezo lekeres legyen friss."""
        self._kosar_gyorstar = None

    def _kivesz_es_betesz(self, cart_item_id, uj_id, darab,
                          vissza_id=None, vissza_darab=None):
        """
        Levesz egy tetelt, majd betesz egy masikat (vagy ugyanazt
        mas darabszammal). Ha a betetel elhasal, a regit visszarakja,
        hogy a tétel ne tunjon el.
        """
        try:
            self.mcp.hiv("remove_from_cart",
                         {"order_field_id": str(cart_item_id)})
        except MCPHiba as e:
            self._kosar_ervenytelenit()
            return False, f"Nem sikerult levenni: {e}"
        try:
            self.mcp.hiv("add_to_cart", {"products": [
                {"product_id": uj_id, "quantity": darab}]})
            self._kosar_ervenytelenit()
            return True, None
        except MCPHiba as e:
            vissza_hiba = None
            if vissza_id is not None:
                try:
                    self.mcp.hiv("add_to_cart", {"products": [
                        {"product_id": vissza_id,
                         "quantity": vissza_darab or 1}]})
                except MCPHiba as vissza:
                    vissza_hiba = str(vissza)
            self._kosar_ervenytelenit()
            if vissza_hiba:
                return False, (f"{e}; a visszarakas sem sikerult: "
                               f"{vissza_hiba}")
            return False, str(e)

    def _kosarban_van(self, kifli_id, nev):
        """
        Ellenorzi, hogy a termek tenyleg bekerult-e a kosarba.
        Visszaad: (bent_van, kosarban_szereplo_ar)

        bent_van: True / False / None (None = a kosarat nem sikerult
        lekerni, ne allitsuk sem azt, hogy bement, sem azt, hogy nem).

        Nev alapjan keres, mert a get_cart_content a Cart ID-t adja,
        nem a termek ID-jat. A hasonlo, rovid nevek (tej / tejfol)
        nem keverednek: csak pontos vagy csonka-elotag egyezes szamit.
        """
        try:
            nyers = self._kosar_nyers(frissen=True)
        except MCPHiba:
            return None, None

        tetelek = self._kosar_ertelmez(nyers)["tetelek"]
        for t in tetelek:
            if _nevek_egyeznek(nev, t.get("nev")):
                return True, t.get("ar")
        return False, None

    def _visszaigazolas(self, talalat, db):
        """
        A tenyleges listaadatokbol osszerakott mondat.

        Ez NEM az LLM megfogalmazasa, hanem a kereses eredmenyebol epult
        szoveg. Ezert nem tud teves arat vagy kiszerelest mondani. Ez az
        egyetlen ellenorzesi pont, ha a felhasznalo nem nezi a kepernyot.
        """
        reszek = [talalat["nev"]]
        if db > 1:
            reszek.append(f"{db} darab")
        if talalat.get("mennyiseg") and talalat.get("egyseg"):
            reszek.append(f"{talalat['mennyiseg']:g} {talalat['egyseg']}")
        if talalat.get("ar"):
            ossz = talalat["ar"] * db
            if db > 1:
                reszek.append(f"{talalat['ar']:.0f} forint darabja, "
                              f"osszesen {ossz:.0f} forint")
            else:
                reszek.append(f"{talalat['ar']:.0f} forint")
        if talalat.get("kedvezmeny"):
            reszek.append(f"{abs(talalat['kedvezmeny'])} szazalek kedvezmennyel")
        return ", ".join(reszek) + "."

    # Egy hosszu beszelgetesben sok kereses fut le; a talalatokat
    # megtartjuk, hogy a felhasznalo visszahivatkozhasson rajuk, de nem
    # korlatlanul - kulonben a memoria es a keresesi ido no.
    TALALAT_KERET = 300

    def _talalatokat_megjegyez(self, talalatok):
        megvan = {t["id"] for t in self.utolso_talalatok}
        self.utolso_talalatok.extend(t for t in talalatok
                                     if t["id"] not in megvan)
        if len(self.utolso_talalatok) > self.TALALAT_KERET:
            del self.utolso_talalatok[:-self.TALALAT_KERET]
        for t in talalatok:
            if t.get("ar"):
                self.arak_szerint[t["id"]] = t["ar"]

    def kosarba_tesz(self, kifli_id, termek, darab=None, mennyiseg_szoveg=None):
        talalat = next((t for t in self.utolso_talalatok
                        if t["id"] == kifli_id), None)
        if talalat is None:
            return {"hiba": "Ez az ID nincs a legutobbi talalatok kozott. "
                            "Keress ra eloszor a termek_keres eszkozzel."}

        termek = (termek or talalat["nev"]).strip().lower()

        # A darabszamot A PROGRAM szamolja a kimondott mennyisegbol es
        # a kiszerelesbol. Az LLM 'darab' parametere csak akkor ervenyes,
        # ha nincs ertelmezheto mennyiseg_szoveg - kulonben a "30 tojas"
        # 30 csomag lenne egy 10-es dobozbol.
        szoveg = (mennyiseg_szoveg or "").strip() or (
            self._mennyiseg_gyorstar.get(termek) or "")
        ertelmezett = szinkron.mennyiseg_szovegbol(szoveg) if szoveg else None
        van_mennyiseg = (ertelmezett
                         and ertelmezett.get("kind") not in (None, "unspecified")
                         and ertelmezett.get("value") is not None)

        megjegyzes = tobblet = None
        if van_mennyiseg:
            db, tobblet, megjegyzes = szinkron.darabszam(
                ertelmezett, talalat.get("mennyiseg"), talalat.get("egyseg"),
                p.kimert_e(talalat))
        elif darab is not None:
            try:
                db = max(1, int(darab))
            except (TypeError, ValueError):
                return {"hiba": f"A darabszam nem szam: {darab!r}"}
        else:
            db = 1
            megjegyzes = ("Nem mondtad meg a darabszamot, ezert 1-et tettem "
                          "be. Ha tobb kell, mondd meg hanyat.")

        if self.szaraz:
            print(f"  {HA}[szaraz] + {db}x {talalat['nev']}{ALAP}")
            return {"szaraz_futas": True,
                    "mit_tennek_be": talalat["nev"], "darab": db,
                    "figyelmeztetes": ("SZARAZ FUTAS: a termek NEM kerult be a "
                                       "kosarba. A kosar_megmutat ezt nem fogja "
                                       "mutatni. Mondd meg a felhasznalonak, "
                                       "hogy ez csak proba volt.")}

        try:
            self.mcp.hiv("add_to_cart", {"products": [
                {"product_id": kifli_id, "quantity": db}]})
            self._kosar_ervenytelenit()
        except MCPHiba as e:
            self._kosar_ervenytelenit()
            return {"hiba": f"Nem sikerult a kosarba tenni: {e}"}

        # Ellenorizzuk, hogy tenyleg bement. Az add_to_cart nem mindig
        # jelez hibat, ha a Kifli elutasitja a terméket - ilyenkor a
        # felhasznalo azt hinne, hogy megrendelte.
        bent, kosar_ar = self._kosarban_van(kifli_id, talalat["nev"])
        if bent is False:
            print(f"  {PI}! NEM kerult be: {talalat['nev']}{ALAP}")
            return {"hiba": f"A(z) '{talalat['nev']}' NEM kerult be a kosarba. "
                            f"A Kifli elutasitotta, vagy elfogyott. "
                            f"Szolj a felhasznalonak, es javasolj masikat."}

        self.tarolo.ment(termek, kifli_id, talalat["nev"],
                         talalat.get("mennyiseg"), talalat.get("egyseg"),
                         p.kimert_e(talalat))
        self.tarolo.naploz(termek, "termekvalasztas", talalat["nev"])

        ar = self.arak_szerint.get(kifli_id)
        ar_szoveg = f"  {HA}{ar * db:,.0f} Ft{ALAP}".replace(",", " ") if ar else ""
        print(f"  {Z}+ {db}x {talalat['nev']}{ALAP}{ar_szoveg}")

        # Ha a kosarban mas az ar, mint a talalatban, a KOSAR az igaz
        if kosar_ar and ar and abs(kosar_ar - ar * db) > 1:
            print(f"  {S}  (a kosarban {kosar_ar:,.0f} Ft){ALAP}".replace(",", " "))
            talalat = {**talalat, "ar": kosar_ar / max(db, 1)}

        valasz = {
            "betettem": talalat["nev"], "darab": db,
            "ar": kosar_ar or (ar * db if ar else None),
            "adatok": self._visszaigazolas(talalat, db),
        }
        if tobblet and tobblet > 0.5:
            valasz["figyelmeztetes"] = (
                f"{tobblet * 100:.0f}%-kal tobb, mint amennyit kert")
        if megjegyzes:
            valasz["megjegyzes"] = megjegyzes
        if bent is None:
            valasz["figyelmeztetes"] = (
                "A kosarat most nem tudtam ellenorizni. Ne allitsd "
                "biztosra, hogy bement - mondd meg, hogy a Kifli "
                "most nem valaszolt, es a felhasznalo nezze meg.")
        return valasz

    def mennyiseget_modosit(self, termek, darab):
        """
        Egy mar kosarban levo tetel darabszamanak modositasa.

        A Kifli API-ban nincs kozvetlen 'mennyiseget allits' muvelet,
        ezert levesszuk es ujra betesszuk a kivant darabszammal. Ez
        biztonsagosabb, mint ha az LLM probalna ugyanezt ket lepesben -
        ugy konnyen felezodik vagy duplazodik a mennyiseg.
        """
        try:
            uj_darab = max(1, int(darab))
        except (TypeError, ValueError):
            return {"hiba": f"A darabszam nem szam: {darab!r}"}

        try:
            nyers = self._kosar_nyers()
        except MCPHiba as e:
            return {"hiba": str(e)}

        tetelek = self._kosar_ertelmez(nyers)["tetelek"]
        mit = (termek or "").lower().strip()
        if not mit:
            return {"hiba": "Nem mondtad meg, melyik tetelt."}

        jeloltek = [t for t in tetelek if mit in t["nev"].lower()]
        if not jeloltek:
            return {"hiba": f"Nem talaltam a kosarban: {termek}",
                    "kosarban": [t["nev"] for t in tetelek]}
        if len(jeloltek) > 1:
            return {"tobb_talalat": [t["nev"] for t in jeloltek],
                    "kerdes": "Tobb tetelre is illik. Melyikre gondoltal?"}

        tetel = jeloltek[0]
        if tetel.get("darab") == uj_darab:
            return {"valtozatlan": tetel["nev"], "darab": uj_darab,
                    "uzenet": "Mar ennyi van belole."}

        # A kosarban levo tetel Cart ID-ja alapjan keressuk meg a
        # termek ID-jat a korabbi talalatok kozott
        talalat = next((t for t in self.utolso_talalatok
                        if t["nev"].lower() == tetel["nev"].lower()), None)
        if talalat is None:
            return {"hiba": f"Nem tudom, melyik termek ez a Kiflin. "
                            f"Keress ra eloszor: {tetel['nev']}"}

        if self.szaraz:
            print(f"  {HA}[szaraz] {tetel['nev']}: "
                  f"{tetel.get('darab')} -> {uj_darab}{ALAP}")
            return {"szaraz_futas": True, "termek": tetel["nev"],
                    "uj_darab": uj_darab}

        ok, hiba = self._kivesz_es_betesz(
            tetel["cart_item_id"], talalat["id"], uj_darab,
            vissza_id=talalat["id"], vissza_darab=tetel.get("darab") or 1)
        if not ok:
            return {"hiba": f"Nem sikerult a modositas: {hiba}"}

        bent, kosar_ar = self._kosarban_van(talalat["id"], tetel["nev"])
        if bent is False:
            return {"hiba": f"A modositas utan a(z) '{tetel['nev']}' NEM "
                            f"maradt a kosarban. Nezd meg a kosarat."}

        print(f"  {Z}~ {tetel['nev']}: "
              f"{tetel.get('darab')} -> {uj_darab}{ALAP}")
        return {"modositva": tetel["nev"],
                "regi_darab": tetel.get("darab"), "uj_darab": uj_darab,
                "ar": kosar_ar,
                "adatok": f"{tetel['nev']}, most {uj_darab} darab"
                          + (f", {kosar_ar:.0f} forint." if kosar_ar else ".")}

    def feltoltott_lista(self):
        """
        A legutobb feltoltott keprol kiolvasott tételek.

        A kepet a gui.py dolgozza fel, amint megerkezik - ez az eszkoz
        csak atadja az eredmenyt a modellnek. Igy a felismeres mar kesz
        van, mire a beszelgetes odaer.
        """
        if not self.kep_tetelek:
            return {"tetelek": [],
                    "uzenet": "Nem erkezett kep, vagy mar feldolgoztuk.",
                    "megjegyzes": ("Kerd meg a felhasznalot, hogy toltse "
                                   "fel a kepet a kapocs ikonnal.")}

        adatok = self.kep_tetelek
        self.kep_tetelek = None        # egyszer hasznaljuk fel

        # Harom kulon kategoria, mert MAS a teendo mindegyikkel:
        #  - biztos:      keresd meg es tedd be
        #  - nyitott:     olvashato, de rank bizta a valasztast
        #  - bizonytalan: nem tudtuk elolvasni, kerdezni kell
        biztos, nyitott, kerdeses = [], [], []
        for t in adatok["tetelek"]:
            if t["megbizhatosag"] < 0.8:
                kerdeses.append(t)
            elif t.get("nyitott"):
                nyitott.append(t)
            else:
                biztos.append(t)

        return {
            "tetelek": adatok["tetelek"],
            "biztosan_olvashato": [t["szoveg"] for t in biztos],
            "rank_bizta": [t["szoveg"] for t in nyitott],
            "bizonytalan": [
                {"szoveg": t["szoveg"],
                 "mi_nem_egyertelmu": t.get("bizonytalan_resz")}
                for t in kerdeses],
            "iras_tipusa": adatok.get("iras_tipusa"),
            "megjegyzes": (
                "HAROM csoport, mindegyikkel MAS a teendo.\n"
                "1. 'biztosan_olvashato': keresd meg es tedd be a szokasos "
                "modon.\n"
                "2. 'rank_bizta': a felhasznalo szandekosan nem hatarozta "
                "meg (peldaul 'valami jobb fele kenyer'). NE kerdezz "
                "vissza - keress ra, es tedd be a LEGJOBB AR-ERTEK "
                "ARANYU valasztast. A visszaigazolasban mondd meg, mit "
                "valasztottal es miert.\n"
                "3. 'bizonytalan': ezeket nem tudtuk elolvasni. Ezeket "
                "EGYSZERRE olvasd fel, egy mondatban - ne egyesevel "
                "kerdezz ra mindegyikre, az faraszto. Csak a valasza utan "
                "tedd be oket."),
        }

    def helyettesitest_javasol(self, termek=None):
        """
        Olcsobb vagy akcios alternativak keresese a kosarban levokre.

        Csak javasol - a csere SOHA nem tortenik meg magatol. Amit a
        felhasznalo korabban elutasitott, azt nem ajanljuk ujra.
        """
        try:
            nyers = self._kosar_nyers()
        except MCPHiba as e:
            return {"hiba": str(e)}

        tetelek = self._kosar_ertelmez(nyers)["tetelek"]
        if not tetelek:
            return {"javaslatok": [], "uzenet": "A kosar ures."}

        if termek:
            mit = termek.lower().strip()
            tetelek = [t for t in tetelek if mit in t["nev"].lower()]
            if not tetelek:
                return {"hiba": f"Nem talaltam a kosarban: {termek}"}

        akciok = self._akciok()
        javaslatok = []

        for tetel in tetelek[:8]:      # nem futtatjuk vegig 30 tételen
            eredeti = next((t for t in self.utolso_talalatok
                            if t["nev"].lower() == tetel["nev"].lower()),
                           None)
            if eredeti is None:
                continue
            eredeti_egysegar, egyseg = arak.egysegar(eredeti)
            if not eredeti_egysegar:
                continue

            jelolt = self._legjobb_alternativa(
                eredeti, eredeti_egysegar, egyseg, akciok)
            if jelolt:
                javaslatok.append(jelolt)

        if not javaslatok:
            return {"javaslatok": [],
                    "uzenet": "Nem talaltam jobb alternativat a kosarban "
                              "levokre.",
                    "megjegyzes": ("Mondd meg roviden, hogy most nincs jobb "
                                   "ajanlat. NE talalj ki alternativat.")}

        print(f"\n{SZ}  {len(javaslatok)} lehetseges csere:{ALAP}")
        for j in javaslatok:
            print(f"  {HA}{j['eredeti']['nev'][:34]:36}"
                  f" -> {j['ajanlott']['nev'][:34]}{ALAP}")
            print(f"  {HA}{'':36}    {j['megtakaritas_szazalek']}% olcsobb "
                  f"kilonkent{ALAP}")

        return {
            "javaslatok": javaslatok,
            "megjegyzes": (
                "Ezek CSAK JAVASLATOK - egyik sem tortent meg. Mutasd be "
                "oket EGYESEVEL, roviden, es mondd meg, mennyivel olcsobb. "
                "Fontos: a ket termek NEM ugyanaz, ezert mondd meg a "
                "nevet is. A valasz utan MINDIG hivd a "
                "helyettesitest_dontesz eszkozt - elfogadas eseten az "
                "vegzi el a cseret is."),
        }

    def _legjobb_alternativa(self, eredeti, eredeti_egysegar, egyseg, akciok):
        """
        A legjobb csere-jelolt egy kosarban levo termekre.

        Ket feltetel: legalabb 15%-kal olcsobb egysegaron, es a
        felhasznalo korabban nem utasitotta el ezt a parost.
        """
        legjobb = None
        for jelolt in self.utolso_talalatok:
            if jelolt["id"] == eredeti["id"]:
                continue
            if self.tarolo.helyettesites_dontes(
                    eredeti["id"], jelolt["id"]) == "elutasitva":
                continue

            j_egysegar, j_egyseg = arak.egysegar(jelolt)
            if not j_egysegar or j_egyseg != egyseg:
                continue      # kilot nem hasonlitunk literhez
            if j_egysegar >= eredeti_egysegar * 0.85:
                continue      # nem eleg nagy a kulonbseg

            akcios = akciok.get(jelolt["id"])
            pontszam = eredeti_egysegar / j_egysegar
            if akcios:
                pontszam *= 1.2      # az akcios jelolt elonyt kap
            if legjobb is None or pontszam > legjobb["_pontszam"]:
                legjobb = {
                    "_pontszam": pontszam,
                    "eredeti": {"id": eredeti["id"], "nev": eredeti["nev"],
                                "egysegar": arak.egysegar_szoveg(eredeti)},
                    "ajanlott": {
                        "id": jelolt["id"], "nev": jelolt["nev"],
                        "ar": jelolt.get("ar"),
                        "egysegar": arak.egysegar_szoveg(jelolt),
                        "kedvezmeny": jelolt.get("kedvezmeny")},
                    "megtakaritas_szazalek": round(
                        (1 - j_egysegar / eredeti_egysegar) * 100),
                    "akcios": bool(akcios),
                }

        if legjobb:
            legjobb.pop("_pontszam", None)
        return legjobb

    def helyettesitest_dontesz(self, eredeti_id, alternativ_id, elfogadta):
        """
        A dontes rogzitese, es elfogadas eseten a csere elvegzese.

        Az elutasitas VEGLEGES: ezt a parost tobbe nem ajanljuk. Az
        elfogadas viszont csak erre az alkalomra szol - legkozelebb
        ujra megkerdezzuk, mert lehet, hogy most csak azert fogadtad
        el, mert epp elfogyott a szokasos.
        """
        try:
            eredeti_id = int(eredeti_id)
            alternativ_id = int(alternativ_id)
        except (TypeError, ValueError):
            return {"hiba": "Az azonositok nem szamok."}

        dontes = "elfogadva" if elfogadta else "elutasitva"
        self.tarolo.helyettesites_ment(eredeti_id, alternativ_id, dontes)

        if not elfogadta:
            print(f"  {HA}~ elutasitott csere megjegyezve{ALAP}")
            return {"megjegyeztem": "elutasitva",
                    "uzenet": "Rendben, ezt tobbe nem ajanlom."}

        eredeti = next((t for t in self.utolso_talalatok
                        if t["id"] == eredeti_id), None)
        uj = next((t for t in self.utolso_talalatok
                   if t["id"] == alternativ_id), None)
        if eredeti is None or uj is None:
            return {"hiba": "Az egyik termek nincs a legutobbi talalatok "
                            "kozott, ezert nem tudom elvegezni a cseret."}

        if self.szaraz:
            print(f"  {HA}[szaraz] csere: {eredeti['nev']} -> "
                  f"{uj['nev']}{ALAP}")
            return {"szaraz_futas": True, "csere": uj["nev"]}

        # A regi darabszamot atvesszuk
        try:
            nyers = self._kosar_nyers()
        except MCPHiba as e:
            return {"hiba": str(e)}
        kosarban = next(
            (t for t in self._kosar_ertelmez(nyers)["tetelek"]
             if t["nev"].lower() == eredeti["nev"].lower()), None)
        if kosarban is None:
            return {"hiba": f"A(z) '{eredeti['nev']}' mar nincs a kosarban."}

        darab = kosarban.get("darab") or 1
        ok, hiba = self._kivesz_es_betesz(
            kosarban["cart_item_id"], alternativ_id, darab,
            vissza_id=eredeti_id, vissza_darab=darab)
        if not ok:
            return {"hiba": f"A csere nem sikerult: {hiba}"}

        bent, kosar_ar = self._kosarban_van(alternativ_id, uj["nev"])
        if bent is False:
            return {"hiba": f"A csere utan a(z) '{uj['nev']}' NEM kerult a "
                            f"kosarba. Nezd meg a kosarat."}

        self.tarolo.naploz(eredeti["nev"], "helyettesites", uj["nev"])
        print(f"  {Z}~ {eredeti['nev']} -> {uj['nev']}{ALAP}")
        return {"lecsereltem": {"regi": eredeti["nev"], "uj": uj["nev"],
                                "darab": darab, "ar": kosar_ar},
                "adatok": f"{uj['nev']}, {darab} darab"
                          + (f", {kosar_ar:.0f} forint." if kosar_ar else ".")}

    def kosar_megmutat(self):
        """A VALODI Kifli kosar tartalma, nem a memoria."""
        try:
            nyers = self._kosar_nyers()
        except MCPHiba as e:
            return {"hiba": str(e)}

        adat_kosar = self._kosar_ertelmez(nyers)
        tetelek = adat_kosar["tetelek"]
        if not tetelek:
            print(f"\n{HA}  A Kifli kosar ures.{ALAP}")
            return {"kosar": [], "uzenet": "A kosar ures."}

        print(f"\n{Z}  Kifli kosar ({len(tetelek)}){ALAP}")
        szamitott = 0.0
        for t in tetelek:
            ar = f"{t['ar']:,.0f} Ft".replace(",", " ") if t.get("ar") else "?"
            if t.get("ar"):
                szamitott += t["ar"]
            print(f"    {t['darab']}x {t['nev'][:44]:46} {ar:>10}")

        osszeg = adat_kosar["osszesen"] or szamitott
        print(f"  {Z}  Osszesen: {osszeg:,.0f} Ft{ALAP}".replace(",", " "))

        # A 'Can order' jelzest NEM ertelmezzuk: a Kifli addig 'No'-t ad,
        # amig nincs kivalasztva szallitasi idosav, amit a felhasznalo a
        # penztarnal tesz meg. Vagyis ez szinte mindig 'No', es semmit nem
        # mond a kosarrol. Korabban ebbol lett egy felrevezeto uzenet.
        return {"kosar": tetelek, "osszeg_ft": round(osszeg) or None}

    def kosarbol_kivesz(self, termek):
        """A VALODI Kifli kosarbol vesz le tetelt."""
        try:
            nyers = self._kosar_nyers()
        except MCPHiba as e:
            return {"hiba": str(e)}

        tetelek = self._kosar_ertelmez(nyers)["tetelek"]
        mit = (termek or "").lower().strip()
        if not mit:
            return {"hiba": "Nem mondtad meg, mit vegyek le."}

        jeloltek = [t for t in tetelek if mit in t["nev"].lower()]
        if not jeloltek:
            return {"hiba": f"Nem talaltam a kosarban: {termek}",
                    "kosarban": [t["nev"] for t in tetelek]}
        if len(jeloltek) > 1:
            return {"tobb_talalat": [t["nev"] for t in jeloltek],
                    "kerdes": "Tobb tetelre is illik. Melyiket vegyem le?"}

        tetel = jeloltek[0]
        if not tetel.get("cart_item_id"):
            return {"hiba": "Nem talaltam a tetel azonositojat a kosarban."}

        if self.szaraz:
            print(f"  {HA}[szaraz] - {tetel['nev']}{ALAP}")
            return {"szaraz_futas": True, "mit_vennek_le": tetel["nev"]}

        try:
            self.mcp.hiv("remove_from_cart",
                         {"order_field_id": str(tetel["cart_item_id"])})
            self._kosar_ervenytelenit()
        except MCPHiba as e:
            self._kosar_ervenytelenit()
            return {"hiba": f"Nem sikerult levenni: {e}"}

        print(f"  {PI}- {tetel['nev']}{ALAP}")
        return {"levettem": tetel["nev"]}

    _kosar_ertelmez = staticmethod(p.kosar_ertelmez)

    def kosar_osszeg(self):
        """A VALODI Kifli kosar vegosszege."""
        eredmeny = self.kosar_megmutat()
        if "hiba" in eredmeny:
            return eredmeny
        return {"osszeg_ft": eredmeny.get("osszeg_ft"),
                "tetelek": eredmeny.get("kosar", []),
                "megjegyzes": ("Ez a termekek ara. A szallitas es a kimert "
                               "aruk elterese nincs benne.")}

    def szokasos_termekek(self):
        try:
            nyers = self.mcp.hiv("get_frequent_items",
                                 {"orders_to_analyze": 20, "top_items": 25,
                                  "show_categories": False})
        except MCPHiba as e:
            return {"hiba": str(e)}

        gyakori = p.gyakori_ertelmez(nyers)
        if not gyakori:
            return {"termekek": [], "uzenet": "Nincs eleg rendelestortenet."}

        akciok = self._akciok()
        eredmeny = []
        for g in gyakori:
            sor = {"id": g["id"], "nev": g["nev"],
                   "hany_rendelesben": g.get("rendelesek")}
            akcio = akciok.get(g["id"])
            if akcio:
                sor["akcios_most"] = True
                sor["kedvezmeny"] = akcio.get("kedvezmeny")
                sor["ar"] = akcio.get("ar")
                self._talalatokat_megjegyez([akcio])
            eredmeny.append(sor)

        akciosok = [s for s in eredmeny if s.get("akcios_most")]
        print(f"\n{HA}  {len(eredmeny)} szokasos termek, "
              f"{len(akciosok)} akcios{ALAP}")
        for s in akciosok[:8]:
            print(f"  {HA}{s['nev'][:48]:50}{ALAP} {PI}{s['kedvezmeny']}%{ALAP}")

        return {"termekek": eredmeny}

    def _akciok(self):
        """Akcios termekek ID -> termek. Egyszer kerjuk le sessiononkent."""
        if self._akcio_gyorstar is not None:
            return self._akcio_gyorstar
        terkep = {}
        for tipus in ("sales", "premium-sales"):
            try:
                szoveg = self.mcp.hiv("get_discounted_items",
                                      {"sale_type": tipus, "limit": 50})
                for t in p.termekek_ertelmez(szoveg):
                    if t.get("kedvezmeny"):
                        terkep[t["id"]] = t
            except MCPHiba:
                continue
        self._akcio_gyorstar = terkep
        return terkep

    def etkezes_javaslat(self, etkezes, darab=10):
        try:
            nyers = self.mcp.hiv("get_meal_suggestions",
                                 {"meal_type": etkezes,
                                  "items_count": max(3, min(30, darab))})
        except MCPHiba as e:
            return {"hiba": str(e)}
        self._nyers_kiir(f"javaslatok ({etkezes})", nyers)
        return {"javaslatok": nyers[:3000]}

    def korabbi_rendelesek(self, darab=10):
        try:
            nyers = self.mcp.hiv("get_order_history",
                                 {"limit": max(1, min(20, darab))})
        except MCPHiba as e:
            return {"hiba": str(e)}
        self._nyers_kiir("korabbi rendelesek", nyers)
        return {"rendelesek": nyers[:3000]}

    def rendeles_reszletei(self, rendeles_id):
        try:
            nyers = self.mcp.hiv("get_order_detail",
                                 {"orderId": str(rendeles_id)})
        except MCPHiba as e:
            return {"hiba": str(e)}
        self._nyers_kiir(f"rendeles {rendeles_id}", nyers)
        return {"reszletek": nyers[:4000]}

    def beutemezett_rendelesek(self):
        try:
            nyers = self.mcp.hiv("get_upcoming_orders")
        except MCPHiba as e:
            return {"hiba": str(e)}
        self._nyers_kiir("beutemezett rendelesek", nyers)
        return {"rendelesek": nyers[:2000]}

    def akcio_kategoriak(self):
        """
        A Kifli akcios szekcioinak listaja.

        Ez azert kell, mert a szekciok nevei boltonkent es idoben is
        valtoznak (pl. 'Ments meg' a kozeli lejaratu termekekre). Az
        azonositokat sosem talaljuk ki - mindig innen vesszuk.
        """
        try:
            nyers = self.mcp.hiv("get_discounted_items",
                                 {"list_categories": True})
        except MCPHiba as e:
            return {"hiba": str(e)}

        kategoriak = p.akcio_kategoriak_ertelmez(nyers)

        if not kategoriak:
            return {"kategoriak": [],
                    "uzenet": "Nem sikerult kiolvasni a szekciokat.",
                    "nyers_reszlet": (nyers or "")[:800]}

        print(f"\n{HA}  {len(kategoriak)} akcios szekcio:{ALAP}")
        for k in kategoriak[:15]:
            print(f"  {HA}{k['nev'][:46]:48} (ID {k['id']}){ALAP}")

        return {"kategoriak": kategoriak,
                "megjegyzes": ("Az azonositot add at az akciok_most eszkoz "
                               "'kategoria_id' parametereben.")}

    def akciok_most(self, tipus="sales", kategoria_id=None, darab=20):
        try:
            darab = max(1, min(50, int(darab)))
        except (TypeError, ValueError):
            darab = 20

        # Alapesetben a gyorstarazott 'sales' + 'premium-sales' halmaz;
        # konkret tipusnal vagy kategorianal frissen kerjuk le
        if tipus == "sales" and kategoria_id is None:
            akciok = self._akciok()
            termekek = sorted(akciok.values(),
                              key=lambda t: t.get("kedvezmeny") or 0)[:darab]
        else:
            keres = {"sale_type": tipus, "limit": darab}
            if kategoria_id is not None:
                keres["category_id"] = int(kategoria_id)
            try:
                nyers = self.mcp.hiv("get_discounted_items", keres)
            except MCPHiba as e:
                return {"hiba": str(e)}
            termekek = arak.rangsorol(p.termekek_ertelmez(nyers))
            termekek.sort(key=lambda t: t.get("kedvezmeny") or 0)

        if not termekek:
            return {"termekek": [],
                    "uzenet": f"Ebben a szekcioban ({tipus}"
                              + (f", kategoria {kategoria_id}"
                                 if kategoria_id else "")
                              + ") most nincs termek.",
                    "megjegyzes": ("Mondd meg oszinten, hogy nem talaltal "
                                   "semmit. NE talalj ki terméket.")}

        self._talalatokat_megjegyez(termekek)

        print(f"\n{HA}  {len(termekek)} akcios termek ({tipus}){ALAP}")
        for t in termekek[:10]:
            ar = f"{t['ar']:,.0f} Ft".replace(",", " ") if t.get("ar") else "?"
            kedv = f"{PI}{t['kedvezmeny']}%{ALAP}" if t.get("kedvezmeny") else ""
            print(f"  {HA}{t['nev'][:44]:46} {ar:>10}{ALAP} {kedv}")

        return {"tipus": tipus, "kategoria_id": kategoria_id,
                "termekek": [{
                    "id": t["id"], "nev": t["nev"], "ar": t.get("ar"),
                    "kedvezmeny": t.get("kedvezmeny"),
                    "egysegar": arak.egysegar_szoveg(t) or None,
                    "kiszereles": (f"{t['mennyiseg']:g} {t['egyseg']}"
                                   if t.get("mennyiseg") else None),
                } for t in termekek]}

    @staticmethod
    def _nyers_kiir(cimke, nyers, sorok=12):
        print(f"\n{HA}  {cimke}:{ALAP}")
        for sor in nyers.splitlines()[:sorok]:
            if sor.strip():
                print(f"  {HA}{sor[:76]}{ALAP}")

    def elofizetesem(self):
        """
        A Premium / Xtra elofizetes allapota.

        Az arak amugy is a bejelentkezett munkamenetbol jonnek, tehat az
        Xtra-arakat mar most is latjuk. Ez arra kell, hogy az asszisztens
        TUDJON rola, es megemlithesse - peldaul hogy ingyenes a szallitas.
        """
        try:
            nyers = self.mcp.hiv("get_premium_info")
        except MCPHiba as e:
            return {"hiba": str(e)}

        adatok = self._elofizetes_ertelmez(nyers)
        if adatok.get("aktiv"):
            reszek = ["Premium elofizetes aktiv"]
            if adatok.get("ingyenes_szallitas") is not None:
                reszek.append(f"{adatok['ingyenes_szallitas']} ingyenes "
                              f"szallitas maradt")
            if adatok.get("expressz") is not None:
                reszek.append(f"{adatok['expressz']} expressz maradt")
            print(f"\n{HA}  {', '.join(reszek)}{ALAP}")
        else:
            print(f"\n{HA}  Nincs aktiv Premium elofizetes.{ALAP}")

        adatok["nyers_reszlet"] = nyers[:1500]
        return adatok

    _elofizetes_ertelmez = staticmethod(p.elofizetes_ertelmez)

    def szallitasi_cimem(self):
        """A jelenlegi szallitasi cim es a kovetkezo szallitas."""
        try:
            nyers = self.mcp.hiv("get_account_data")
        except MCPHiba as e:
            return {"hiba": str(e)}

        adatok = self._cim_ertelmez(nyers)
        if adatok.get("cim"):
            print(f"\n{HA}  Szallitasi cim: {adatok['cim']}{ALAP}")
        else:
            print(f"\n{HA}  A cimet nem sikerult kiolvasni.{ALAP}")

        adatok["megjegyzes"] = (
            "A cim megvaltoztatasa nem lehetseges innen - azt a Kifli "
            "appban tudja atallitani a felhasznalo.")
        return adatok

    _cim_ertelmez = staticmethod(p.cim_ertelmez)

    def szallitasi_idosavok(self):
        try:
            nyers = self.mcp.hiv("get_delivery_slots")
        except MCPHiba as e:
            return {"hiba": str(e)}

        savok = self._idosavok_ertelmez(nyers)
        if not savok:
            return {"idosavok": [],
                    "uzenet": ("Most nincs szabad idosav - vagy minden "
                               "betelt, vagy a Kifli nem adott vissza "
                               "hasznalhato adatot."),
                    "megjegyzes": ("Mondd meg a felhasznalonak, hogy most "
                                   "nem latsz szabad idopontot, es hogy a "
                                   "Kifli appban erdemes megneznie. NE "
                                   "talalj ki idopontot."),
                    "nyers_reszlet": nyers[:800]}

        print(f"\n{HA}  Legkozelebbi szabad idosavok:{ALAP}")
        for s in savok[:6]:
            ar = "ingyenes" if s["ar"] == 0 else f"{s['ar']:.0f} Ft"
            jelek = "".join(j for j, v in (("P", s.get("premium")),
                                           ("E", s.get("eco"))) if v)
            cimke = f"  {s['cimke']}" if s.get("cimke") else ""
            print(f"  {HA}{s['nap']} {s['ido']}  -  {ar}"
                  f"{'  ' + jelek if jelek else ''}{cimke}{ALAP}")

        ingyenesek = [s for s in savok if s["ar"] == 0]
        cimkezett = [s for s in savok if s.get("cimke")]
        return {
            "idosavok": savok[:12],
            "legkorabbi": savok[0] if savok else None,
            "kiemelt": cimkezett[:3],
            "ingyenes_savok_szama": len(ingyenesek),
            "megjegyzes": (
                "A lista idorendben van, az elso a legkorabbi. Az idosavot "
                "a felhasznalo a Kifli appban valasztja ki a fizetessel "
                "egyutt - innen nem lehet lefoglalni. Mondd meg neki a "
                "legkorabbi lehetoseget es az arat, de ne allitsd, hogy "
                "lefoglaltad."),
        }

    _idosavok_ertelmez = staticmethod(p.idosavok_ertelmez)

    def kosar_lezar(self):
        self.lezarva = True
        eredmeny = self.kosar_megmutat()
        tetelek = eredmeny.get("kosar", [])
        osszeg = eredmeny.get("osszeg_ft")

        # Felolvashato osszefoglalo a VALODI kosarbol. Ez az utolso
        # pillanat, amikor a felhasznalo javithat, ezert minden tetel
        # elhangzik, nem csak a darabszam.
        sorok = []
        for t in tetelek:
            reszek = []
            if (t.get("darab") or 1) > 1:
                reszek.append(f"{t['darab']} darab")
            reszek.append(t["nev"])
            if t.get("ar"):
                reszek.append(f"{t['ar']:.0f} forint")
            sorok.append(" ".join(reszek))

        if sorok:
            felolvasando = ("A kosaradban: " + "; ".join(sorok) + ". "
                            + (f"Osszesen {osszeg} forint." if osszeg else ""))
        else:
            felolvasando = "A kosarad ures."

        return {"kosar": tetelek, "osszeg_ft": osszeg,
                "adatok": felolvasando,
                "fontos": ("A termekek mar a Kifli kosaraban vannak, de a "
                           "RENDELES MEG NINCS LEADVA. Mondd el sajat "
                           "szavaiddal, mi van a kosarban - MINDEN tetelt "
                           "es a vegosszeget -, majd hogy a Kifli appban "
                           "tudja befejezni. SOHA ne allitsd, hogy leadtad "
                           "a rendelest.")}

    # --------------------------------------------------------------- belsok

    def _talalatok_kiir(self, termek, talalatok):
        """A reszletes, kepernyos alak. Ez SOHA nem hangzik el."""
        print(f"\n{HA}  '{termek}' - {len(talalatok)} talalat{ALAP}")
        for i, t in enumerate(talalatok[:8], 1):
            ar = f"{t['ar']:,.0f} Ft".replace(",", " ") if t.get("ar") else "?"
            egys = arak.egysegar_szoveg(t)
            kedv = f" {PI}{t['kedvezmeny']}%{ALAP}" if t.get("kedvezmeny") else ""
            jel = f" {Z}<-olcso{ALAP}" if t.get("legolcsobb") else ""
            print(f"  {HA}{i}. {t['nev'][:42]:44} {ar:>10} {egys:>12}{ALAP}"
                  f"{kedv}{jel}")

    def hivas(self, nev, argumentumok):
        """
        Egy eszkoz meghivasa. SOHA nem dob kivetelt.

        Ez kritikus: a realtime modell addig var, amig meg nem kapja a
        valaszt az eszkozhivasra. Ha itt kivetel szallna fel, a hivo nem
        kuldene vissza semmit, es a beszelgetes megallna. Ezert minden
        hibat elkapunk, es hibauzenetkent adunk vissza - abbol a modell
        tud mit mondani a felhasznalonak.
        """
        fuggveny = getattr(self, nev, None)
        if nev not in _ESZKOZ_NEVEK or fuggveny is None:
            return {"hiba": f"Ismeretlen eszkoz: {nev}"}
        try:
            eredmeny = fuggveny(**(argumentumok or {}))
        except TypeError as e:
            return {"hiba": f"Rossz parameterek ({nev}): {e}"}
        except MCPHiba as e:
            return {"hiba": str(e)}
        except Exception as e:
            print(f"  {PI}! {nev} hiba: {type(e).__name__}: {e}{ALAP}")
            return {"hiba": f"Vartalan hiba a(z) {nev} kozben: {e}"}

        # A megszolalas elott biztosan JSON-kent kuldheto legyen
        if eredmeny is None:
            return {"ok": True}
        return eredmeny


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--szaraz", action="store_true",
                   help="ne irjon a valodi Kifli kosarba")
    a.add_argument("--szolgaltato", choices=["openai", "gemini"],
                   help="melyik AI szolgaltato (alap: LLM_PROVIDER)")
    a.add_argument("--model", help="modellnev (alap: LLM_MODEL)")
    a.add_argument("--db", default="kifli.db")
    args = a.parse_args()

    tarolo = adat.Tarolo(args.db)

    try:
        motor = motor_modul.motor_valaszt(
            RENDSZERPROMPT, ESZKOZOK,
            szolgaltato=args.szolgaltato, model=args.model)
    except motor_modul.MotorHiba as e:
        sys.exit(str(e))

    print(f"{SZ}Mondd, mire van szukseg. Ugy beszelj, ahogy termeszetes.{ALAP}")
    print(f"{HA}Motor: {motor.nev} / {motor.model}   Kilepes: Ctrl+C{ALAP}")

    with MCPKliens() as mcp:
        asszisztens = Asszisztens(mcp, tarolo, args.szaraz)

        while not asszisztens.lezarva:
            try:
                bemenet = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nKilepek.")
                return

            if not bemenet:
                print(f"{SZ}Bocsanat, ezt nem ertettem. Mit keressek?{ALAP}")
                continue

            try:
                valasz = motor.beszelget(bemenet, asszisztens)
            except motor_modul.MotorHiba as e:
                print(f"\n{PI}Nem sikerult a hivas: {e}{ALAP}")
                print(f"{HA}Probald ujra, az elozmeny megmaradt.{ALAP}")
                continue
            print(f"\n{SZ}{valasz}{ALAP}")

        print(f"\n{Z}Kesz. A termekek a Kifli kosaradban vannak.{ALAP}")
        print(f"{HA}Az idosav valasztasa es a fizetes a Kifli appban "
              f"tortenik.{ALAP}")
        if args.szaraz:
            print(f"{HA}(Szaraz futas volt - a kosar nem valtozott.){ALAP}")

    tarolo.close()


if __name__ == "__main__":
    main()
