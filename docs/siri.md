# Siri és a telefon

Bárhonnan, bármikor: szólsz Sirinek, bemondod, mi kell, és bekerül a
Kifli kosaradba. Nem kell előkapni a telefont, nem kell appot nyitni.

```
Te:   Hé Siri, kifli
Siri: Mi kell?
Te:   Két liter tej meg egy kenyér
Siri: Bement 2 Magyar Tej ESL és Házi vekni, összesen 1594 forint.
```

---

## Mire való, és mire nem

Ez a **gyorsfelvétel**: eszedbe jut valami az utcán, bemondod, kész. Egy
kör, nincs beszélgetés.

Amit ismer az előzményeidből, azt beteszi. Amiről dönteni kellene
(„sajt” — de melyik?), azt **nem teszi be**, csak szól, hogy majd
otthon. Így nem kapsz meglepetést a szállításnál.

A válogatós bevásárlás, az ár-érték összehasonlítás és a kosár
rendezése marad a beszélgetős felületen.

---

## 1. Indítsd el az API-t

A szervernek futnia kell valahol, ami mindig elérhető. Otthon a Mac,
vagy — ha megjön — a mini PC.

```bash
cd Kifli_Assistant
source .venv/bin/activate
python3 api.py
```

Első indításkor generál egy tokent, és beleírja a `.env` fájlba. Ezt
írja ki a képernyőre is:

```
  Kifli API
  http://0.0.0.0:8477
  Token: xK3n...  ← ez kell a Parancsok alkalmazásba
```

<details>
<summary><b>Indítsa magától, ne kelljen terminált nyitni (macOS)</b></summary>

<br>

Hozz létre egy `~/Library/LaunchAgents/hu.kifli.api.plist` fájlt:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>hu.kifli.api</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/FELHASZNALO/Kifli_Assistant/.venv/bin/python3</string>
    <string>/Users/FELHASZNALO/Kifli_Assistant/api.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/FELHASZNALO/Kifli_Assistant</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/kifli-api.log</string>
  <key>StandardErrorPath</key><string>/tmp/kifli-api.log</string>
</dict>
</plist>
```

A `FELHASZNALO` helyére a saját neved. Aztán:

```bash
launchctl load ~/Library/LaunchAgents/hu.kifli.api.plist
```

Innentől bejelentkezés után magától elindul. Egy dolog marad: **a gépnek
ébren kell lennie**. `System Settings → Lock Screen → Prevent automatic
sleeping when the display is off`.

</details>

---

## 2. Érd el kívülről — Tailscale

Ne nyiss portot a routeren. A **Tailscale** egy privát hálózatot csinál
a gépeid közé, titkosítva, és ingyenes magánhasználatra.

```bash
brew install --cask tailscale
```

Indítsd el, jelentkezz be. Utána telepítsd a Tailscale appot a
telefonodra is, ugyanazzal a fiókkal.

A gép Tailscale-címét így kapod meg:

```bash
tailscale ip -4
```

Valami ilyet ad: `100.94.12.7`. **Ez a cím a telefonodról is működni fog,
bárhonnan** — mobilneten, idegen wifin, külföldről.

A teljes cím, ami a Parancsok alkalmazásba kell:

```
http://100.94.12.7:8477/api/hozzaad
```

<details>
<summary><b>Miért nem port forwarding</b></summary>

<br>

A porttovábbítás az egész internetnek megnyitja a szolgáltatást. Még
tokennel is: a Kifli fiókod jelszavát kezelő szerver lenne nyilvánosan
elérhető.

A Tailscale titkosított, csak a saját eszközeid látják, és nem kell
hozzá a tűzfalhoz nyúlni. Ha van FortiGate-ed, ott is ez az egyszerűbb
út.

</details>

---

## 3. A Parancs a telefonon

Nyisd meg a **Parancsok** (Shortcuts) alkalmazást, és hozz létre egy új
parancsot ezekkel a lépésekkel:

| # | Művelet | Beállítás |
|:--|:--|:--|
| 1 | **Szöveg kérése** | Kérdés: `Mi kell?` |
| 2 | **Szótár** | kulcs: `szoveg`, érték: az 1. lépés eredménye |
| 3 | **Tartalom lekérése URL-ből** | lásd lent |
| 4 | **Érték lekérése a szótárból** | kulcs: `mondat` |
| 5 | **Szöveg felolvasása** | a 4. lépés eredménye |

A 3. lépés beállításai (nyisd ki a nyíllal):

- **URL:** `http://100.94.12.7:8477/api/hozzaad`
- **Módszer:** `POST`
- **Fejlécek:** `Authorization` → `Bearer a-te-tokened`
- **Kérelem törzse:** `JSON`, és tedd bele a 2. lépés szótárát

Végül fent a beállításoknál (ⓘ ikon):

- **Név:** `Kifli`
- **Hozzáadás Sirihez** → a kimondandó szöveg legyen `kifli`

Innentől: **„Hé Siri, kifli”**.

<details>
<summary><b>Második parancs: mi van a kosaramban</b></summary>

<br>

Ugyanígy, de egyszerűbben:

| # | Művelet | Beállítás |
|:--|:--|:--|
| 1 | **Tartalom lekérése URL-ből** | `http://100.94.12.7:8477/api/kosar`, `GET`, ugyanaz a fejléc |
| 2 | **Érték lekérése a szótárból** | kulcs: `mondat` |
| 3 | **Szöveg felolvasása** | a 2. lépés eredménye |

Siri-szöveg: `kifli kosár`.

</details>

<details>
<summary><b>Androidon</b></summary>

<br>

A **HTTP Shortcuts** (ingyenes, nyílt forrású) alkalmazás ugyanezt
tudja: POST kérés, Bearer fejléc, JSON törzs, és a válasz felolvasása.
Google Assistant-tal is összeköthető, vagy kirakható a kezdőképernyőre.

</details>

---

## 4. Próbáld ki előbb parancssorból

Mielőtt a telefonnal bajlódnál, ellenőrizd, hogy a szerver válaszol:

```bash
# Életjel, token nélkül
curl http://100.94.12.7:8477/api/egeszseg

# Valódi hozzáadás
curl -X POST http://100.94.12.7:8477/api/hozzaad \
  -H "Authorization: Bearer a-te-tokened" \
  -H "Content-Type: application/json" \
  -d '{"szoveg":"két liter tej meg egy kenyér"}'
```

A válasz:

```json
{
  "ok": true,
  "mondat": "Bement 2 Magyar Tej ESL és Házi vekni, összesen 1594 forint.",
  "betett": [...],
  "kerdeses": []
}
```

Ha ez megy, a Parancs is menni fog.

---

## Ha valami nem működik

| Tünet | Mit nézz meg |
|:--|:--|
| Siri semmit nem mond | A Parancsban az 5. lépés (Szöveg felolvasása) megvan-e |
| „Nincs jogosultság” | A token elgépelve, vagy hiányzik a `Bearer ` előtag |
| Nem éri el a szervert | Fut-e az `api.py`; be van-e kapcsolva a Tailscale a telefonon |
| Mindent „nem egyértelműnek” mond | Még üres a tanult terméklista — futtasd a `telepites.py`-t, és töltsd be az előzményeket |
| Otthon megy, kint nem | A Tailscale nincs bekapcsolva a telefonon, vagy a gép alszik |

---

## Biztonság

A token az egyetlen védelem, és a Tailscale-hálózaton belül elég. Kezeld
jelszóként: ne oszd meg, és ha kiszivárog, töröld a `.env`-ből az
`API_TOKEN` sort — a következő indításkor újat generál.

Az API **nem tud rendelést leadni és nem tud fizetni**, ugyanúgy, mint a
többi felület. A legrosszabb, ami történhet, hogy valaki beletesz
valamit a kosaradba.
