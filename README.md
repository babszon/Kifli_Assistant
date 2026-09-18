# Kifli asszisztens

Hangvezérelt bevásárló asszisztens a [Kifli.hu](https://www.kifli.hu)-hoz.
Elmondod, mire van szükséged, ő megkeresi, kosárba teszi, és megjegyzi,
hogy legközelebb ne kelljen újra magyaráznod.

```
Te:  Elfogyott itthon a ketchup, kellene 20 tojás meg 4 liter kóla.
     Mosogatógép tabletta is kell, márkás legyen.

AI:  Bement a Heinz ketchup, 570 gramm, 2249 forintért. A tojásból
     két doboz Farm Prémium, összesen 1678 forint. A kóla most akciós,
     a három és feles multipack 999 forint. A tablettából a Finish
     Power All in 1 nyolcvan darabos csomagja 7039 forint — mehet?
```

**Nem adja le a rendelést.** A kosarat összeállítja, a fizetést és az
időpontválasztást te végzed a Kifli appban.

---

## Mit tud

- **Beszélsz vele, nem parancsolsz neki.** „Elfogyott a tejföl", „inkább
  a Finish-t", „mi a legolcsóbb márkás" — mind érti.
- **Magyarul, ahogy tényleg beszélsz.** A „harminc deka trappistát" 300
  grammot jelent, a „kenyeret" kenyeret. A tárgyeset és a dekagramm
  nem okoz gondot.
- **Megtanulja a szokásaidat.** Ha egyszer megmondtad, hogy a „tejföl"
  nálad a Magyar Tejföl 20%, onnantól kérdés nélkül azt teszi be.
- **Kiszámolja a mennyiséget.** 20 tojás → 2 doboz (tízesével árulják).
  Fél kiló darált hús → kimért áru, jelzi, hogy a végösszeg eltérhet.
- **Figyeli az akciókat.** Megmondja, ha a szokásos terméked épp
  kedvezményes.
- **Ár-érték arányt elemez.** Tudja, hogy a pomace olívaolaj olcsóbb,
  de nem ugyanaz, mint az extra szűz.
- **Mindig visszamondja, mi került be**, névvel, kiszereléssel, árral —
  hogy képernyő nélkül is ellenőrizhesd.

## Mit nem tud

- **Nem fizet és nem ad le rendelést.** Szándékosan. A kosarat
  előkészíti, a többi a tiéd.
- **Nem lát termékleírást.** A Kifli keresője nem adja vissza, így a
  minőségi különbségeket a termék nevéből olvassa ki.
- **Autóban visszhangozhat.** A grafikus felület a böngésző
  visszhangtörlését használja, ami a legtöbb helyzetet megoldja. Az
  autóban viszont erős a hangszóró és a mikrofon közti csatolás — ott
  fejhallgató vagy telefonos használat a járható út.

---

## Telepítés

Kell hozzá **Python 3.9+**, **Node.js** és egy **OpenAI API kulcs**.

```bash
git clone https://github.com/babszon/Kifli_Assistant.git
cd Kifli_Assistant

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python3 telepites.py
```

A telepítő végigvezet mindenen: ellenőrzi a rendszert, bekéri az OpenAI
kulcsot és a Kifli belépési adataidat, teszteli a kapcsolatokat, és
felajánlja, hogy betölti a korábbi rendeléseidből, mit szoktál venni.

A grafikus felülethez ennyi elég. A **terminálos** változathoz kell még:

```bash
# macOS
brew install portaudio

# Linux
sudo apt install portaudio19-dev ffmpeg
```

---

## Használat

```bash
source .venv/bin/activate
python3 kifli.py
```

Megnyílik a böngészőben. Kattints a **Mehet** gombra, engedélyezd a
mikrofont, és beszélj — nem kell gombot nyomni. Ha nincs mikrofon vagy
nem engedélyezed, a felület gépelve ugyanúgy működik.

| Parancs | Mit csinál |
|---|---|
| `python3 kifli.py` | grafikus felület a böngészőben |
| `python3 kifli.py --terminal` | hangvezérelt, terminálban |
| `python3 kifli.py --gepelt` | gépelt beszélgetés, terminálban |
| `python3 kifli.py --proba` | mindent megcsinál, de nem ír a kosárba |
| `python3 kifli.py --tanultak` | mit tanult meg eddig |
| `python3 kifli.py --felejts tej` | egy rossz tanulás törlése |
| `python3 kifli.py --telepites` | beállítások újra |

### Két változat

**Grafikus** (alapértelmezés) — böngészőben nyílik meg, látod a kosarat
épülni, a találatokat és az árakat. A mikrofont a böngésző kezeli, ami
**hardveres visszhangtörlést** ad: hangszóróval is használható, nem kell
fejhallgató. Ehhez csak a `websockets` csomag kell.

**Terminálos** (`--terminal`) — ugyanaz a beszélgetés, felület nélkül.
Szerveren, Home Assistant mellett, vagy ha nem akarsz böngészőt. Ehhez
kell a `sounddevice` és a PortAudio is, és fejhallgató ajánlott, mert a
visszhangtörlés csak szoftveres.

### Ha kapkod a felismerés

Hangosabb környezetben érdemes kevésbé érzékenyre állítani:

```bash
python3 kifli.py --erzekenyseg 0.85 --csend 1400
```

---

## Hogyan működik

```
  böngésző                 Python                  OpenAI
  ────────                 ──────                  ──────
  mikrofon  ──── hang ───►  híd  ──── hang ────►  realtime
  (visszhang-               │                        │
   törléssel)               │      ◄── eszköz ───────┘
                            ▼        hívások
  felület   ◄── esemény ── Kifli.hu · tanulás · egységár
```

Az API kulcs a Python oldalon marad, nem kerül ki a böngészőbe.

Az asszisztens **tizenhárom eszközt** kap: keresés, kosárkezelés,
akciók, korábbi rendelések, szállítási idősávok. Az LLM dönti el, mit
mikor hív — de a mennyiségszámítás, az egységár és a visszaigazoló
mondatok a programban készülnek, nem a modellben. Ez szándékos: ezekben
a modellek hibáznak.

### Fájlok

| Fájl | Mire való |
|---|---|
| `kifli.py` | indító |
| `telepites.py` | telepítő varázsló |
| `gui.py` | grafikus felület szervere |
| `webui/index.html` | maga a felület |
| `realtime.py` | hangvezérelt beszélgetés terminálban |
| `asszisztens.py` | az eszközök és a rendszerprompt |
| `motor.py` | OpenAI / Gemini szöveges tool calling |
| `mcp_kliens.py` | kapcsolat a Kifli szerverhez |
| `parser.py` | a Kifli válaszainak feldolgozása |
| `arak.py` | egységár-számítás |
| `adat.py` | tanulás (SQLite) és Home Assistant |
| `llm.py` | a magyar szöveg normalizálása |
| `szinkron.py` | listából kosár, beszélgetés nélkül |

### Home Assistant

Ha van Home Assistanted, a bevásárlólistát onnan is olvashatja.
Tedd a `.env`-be:

```
HA_URL=http://192.168.1.10
HA_TOKEN=<hosszú élettartamú token>
HA_TODO=todo.bevasarlolista
```

Utána:

```bash
python3 szinkron.py
```

---

## Biztonság és adatvédelem

- A **Kifli jelszavad** a `.env` fájlban van, a gépeden, `600`
  jogosultsággal. Nem megy sehova rajtad és a Kiflin kívül.
- A `.env` és az adatbázis a `.gitignore`-ban van — nem kerülnek a
  repóba.
- A **beszéd** az OpenAI-hoz megy fel feldolgozásra.
- A projekt a [`rohlik-mcp`](https://github.com/tomaspavlin/rohlik-mcp)
  szervert használja, ami a Kifli **nem hivatalos** API-ját szólítja
  meg. Ez az ÁSZF-be ütközhet, és egy alkalmazásfrissítés bármikor
  elronthatja.

**Ne használd ugyanazt a jelszót máshol.**

---

## Ismert korlátok

- A rendelés leadása mindig kézi — ez nem hiba, hanem szándék.
- A Kifli időnként más árat számol, mint ami a keresőben látszik
  (akciók, kimért áruk). Ilyenkor a kosár ára az igaz, és az asszisztens
  azt mondja.
- Kimért árunál (hús, zöldség) a végösszeg eltérhet.
- A hangfelismerés ritka márkaneveket félrehallhat. A gyakoriakat
  (Old Spice, Hellmann's, Heinz) megtanítottuk neki.

## Közreműködés

Hibajelentést és javaslatot szívesen fogadok. Ha új funkciót írnál,
érdemes előbb egy issue-ban megbeszélni.

## Licenc

MIT — lásd a [LICENSE](LICENSE) fájlt.

Ez egy független hobbiprojekt. Semmilyen kapcsolatban nem áll a
Kifli.hu-val vagy a Rohlik Grouppal.
