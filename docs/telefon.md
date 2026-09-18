# A telefonon

Ugyanaz a beszélgetés, mint a gépen — a saját hangján, a saját
modelljével. Nem a Siri érti meg, csak elindítja.

```
Te:      Hé Siri, Kifli
         (megnyílik, és már hallgat)
Te:      Elfogyott a mosópor
Kifli:   A Persil Color mosókapszula, hatvanhétszáz-kilencvenkilenc
         forint. Betegyem?
Te:      Inkább olcsóbbat
Kifli:   A Tomi Power Caps, ötezer-száz­kilencvenkilenc. Ez jó?
Te:      Igen
Kifli:   Bement. Kell még valami?
```

---

## Amit előre tudni érdemes

**A Siri nem tud magyarul.** Soha nem tudott, és a 2026-os Siri AI is
csak angollal indult. Ezért a Siri szerepe egyetlen dolog: felismeri a
„Kifli" szót, és elindítja a parancsot. A megértés és a válasz teljesen
a mi szerverünkön készül.

**Az iOS egy koppintást kérhet.** A Safari a mikrofonhoz felhasználói
érintést vár. Ez az első alkalommal biztosan így lesz — utána, ha a
kezdőképernyőről nyitod, sokszor magától elindul. Ahol mégsem, ott az
**egész képernyő a gomb**: bárhova bökhetsz, nem kell célozni.

**A Művelet gomb jobb, mint a Siri.** iPhone 15 Pro-tól felfelé a
Művelet gomb közvetlenül indíthatja a parancsot — nincs hívószó, nincs
nyelvi korlát, egy nyomás.

---

## 1. HTTPS a Tailscale-lel

A mikrofonhoz a böngésző **biztonságos kapcsolatot** követel. Sima
`http://` címen a Safari nem engedi. A Tailscale ezt ingyen megoldja.

```bash
# Egyszer, a gépen ahol a szerver fut
brew install --cask tailscale
tailscale up
```

Indítsd el a szervert:

```bash
cd Kifli_Assistant
source .venv/bin/activate
python3 gui.py --nyitas-nelkul
```

Jegyezd fel, melyik portot írja ki (például `8420`). Aztán egy másik
ablakban:

```bash
tailscale serve --bg 8420
```

Ez ad egy HTTPS címet, valami ilyet:

```
https://macbook-air.farkas-tail1234.ts.net/
```

**Ez a cím a telefonodról bárhonnan működik** — mobilneten, idegen
wifin, külföldön —, és HTTPS, tehát a mikrofon is megy.

A telefonra telepítsd a Tailscale appot, jelentkezz be ugyanazzal a
fiókkal, és kapcsold be.

<details>
<summary><b>Miért nem port forwarding</b></summary>

<br>

A porttovábbítás az egész internetnek megnyitja a szolgáltatást, és a
HTTPS-t külön kellene megoldani. A Tailscale titkosít, csak a saját
eszközeid látják, és a tanúsítványt is intézi.

</details>

---

## 2. Tedd a kezdőképernyőre

Ez a lépés a legfontosabb, ezen múlik, hogy koppintás nélkül induljon.

1. Nyisd meg a **Safariban** a Tailscale-címet
2. Engedélyezd a mikrofont, amikor kéri
3. **Megosztás** gomb → **Hozzáadás a Főképernyőhöz**
4. Név: `Kifli`

Innentől a kezdőképernyős ikonról indítva teljes képernyőn nyílik,
Safari-sáv nélkül, és a mikrofonengedély megmarad.

---

## 3. A Parancs és a hívószó

A **Parancsok** alkalmazásban új parancs, egyetlen művelettel:

| # | Művelet | Beállítás |
|:--|:--|:--|
| 1 | **URL megnyitása** | `https://...ts.net/mobil.html` |

A beállításoknál (ⓘ):

- **Név:** `Kifli`
- **Hozzáadás Sirihez** → kimondandó szöveg: `Kifli`

Ennyi. `Hé Siri, Kifli`.

<details>
<summary><b>Művelet gombra (iPhone 15 Pro és újabb)</b></summary>

<br>

`Beállítások → Művelet gomb` → lapozz a **Parancs** lehetőségig →
válaszd a `Kifli` parancsot.

Innentől egy gombnyomás, nincs hívószó, nincs Siri.

</details>

<details>
<summary><b>Vezérlőközpontba vagy zárképernyőre</b></summary>

<br>

**Vezérlőközpont:** `Beállítások → Vezérlőközpont` → `Parancs`
hozzáadása.

**Zárképernyő:** tartsd nyomva a zárképernyőt → `Testreszabás` →
widget hely → `Parancsok`.

**Hátsó koppintás:** `Beállítások → Kezelhetőség → Érintés → Hátsó
koppintás` → dupla koppintás → `Kifli`.

</details>

---

## 4. Használat

Az ikonra koppintva megnyílik, és ha az engedély már megvan, **azonnal
hallgat**. A képernyő ébren marad, amíg beszélgettek.

- A **piros pötty** azt jelenti, hogy hall
- Az **arany** azt, hogy keres
- A **zöld** azt, hogy beszél vagy kész
- A kosár alul, összecsukva — koppints rá, ha látni akarod
- A **Kész** gomb lezárja a beszélgetést

A fizetés és az időpontválasztás a Kifli appban marad, ahogy mindenhol
máshol is.

---

## Ha valami nem működik

| Tünet | Mit nézz meg |
|:--|:--|
| „A mikrofon nem indult el" | HTTPS-en vagy-e? `http://`-n a Safari nem engedi |
| Mindig koppintani kell | Tedd a kezdőképernyőre, és onnan indítsd |
| Nem éri el a szervert | Fut-e a `gui.py`; be van-e kapcsolva a Tailscale a telefonon |
| Elalszik a képernyő | Az ébrentartás csak akkor él, ha a lap előtérben van |
| Siri nem ismeri fel | Adj a parancsnak rövid, egyszerű nevet — a `Kifli` jó |
| Visszhangzik | Fejhallgatóval biztosan nem; hangszóróval a böngésző
  visszhangtörlése dolgozik, de zajos helyen segít a fejhallgató |

---

## Ami itt nem megoldható

Az iOS **nem enged harmadik féltől hívószó-figyelést**. A „Hé Siri"
azért működik, mert az Apple saját hardvere figyeli a mikrofont — ehhez
más alkalmazás nem fér hozzá, és a háttérben folyamatosan hallgató app
nem engedélyezett.

Vagyis egy gombnyomás vagy egy Siri-hívás mindig kelleni fog az
indításhoz. Onnantól viszont minden hangon megy.

Ha tényleg mindig figyelő asszisztenst akarsz, az **otthon**
megvalósítható, Home Assistant hangszatelittel — ott nincs ilyen
korlát.
