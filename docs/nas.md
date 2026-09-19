# Synology NAS-on (vagy bármilyen szerveren)

A NAS mindig fut, nem alszik el, és nem kell a gépedre várni. A hangot
továbbra is a **böngésződ** veszi — a NAS csak a logikát futtatja, nem
kell hozzá hangkártya.

Ugyanaz a kód, csak Dockerben csomagolva.

---

## Amire szükség van

| | Miért |
|:--|:--|
| x86_64 NAS | `uname -m` mondja meg |
| Docker / Container Manager | a DSM Csomagkezelőjéből |
| ~300 MB szabad memória | a konténer 150-250 MB-ot használ |
| HTTPS elérés | a mikrofonhoz a böngésző megköveteli |

A DS216+II és felette minden Intel-alapú modell megfelel.

---

## 1. Másold fel a projektet

SSH-zz be a NAS-ra, és tedd a fájlokat egy megosztott mappába:

```bash
ssh admin@<nas-ip>
cd /volume1/docker
git clone https://github.com/babszon/Kifli_Assistant.git
cd Kifli_Assistant
```

Ha nincs `git` a NAS-on, a DSM File Stationjével is felmásolhatod.

---

## 2. Állítsd be

A telepítő varázsló a NAS-on is lefut, de egyszerűbb a `.env`-et kézzel
megírni — a gépeden úgyis megvan:

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Legalább ezek kellenek:

```
OPENAI_API_KEY=sk-...
ROHLIK_BASE_URL=https://www.kifli.hu
ROHLIK_USERNAME=email@pelda.hu
ROHLIK_PASSWORD=jelszo
OPENAI_REALTIME_VOICE=marin
```

<details>
<summary><b>Vidd át a megtanult termékeket a gépedről</b></summary>

<br>

Ha már használtad a gépen, a tanulás átvihető:

```bash
mkdir -p adat
scp ~/Kifli_Assistant/kifli.db admin@<nas-ip>:/volume1/docker/Kifli_Assistant/adat/
```

Így nem kell elölről kezdenie.

</details>

---

## 3. Jogosultságok

A konténer a saját felhasználódként fut, hogy írni tudjon az `adat/`
mappába. Derítsd ki az azonosítódat:

```bash
id -u && id -g
```

Synologyn tipikusan `1026` és `100`. Ha más, tedd a `.env`-be:

```
KIFLI_UID=1026
KIFLI_GID=100
```

Aztán add meg a mappa tulajdonosát:

```bash
mkdir -p adat
sudo chown -R $(id -u):$(id -g) adat
```

> Ha ez kimarad, a felület működik, de a tanulás nem: az adatbázis
> írásvédett lesz, és `attempt to write a readonly database` hibát kapsz.

## 4. Indítsd el

```bash
sudo docker compose up -d --build
```

Az első építés 3-5 perc. Utána:

```bash
sudo docker compose logs -f
```

Ki kell írnia:

```
  Kifli asszisztens
  0.0.0.0:8420 (minden interfeszen)
  Figyelem: a mikrofon csak HTTPS-en vagy localhoston mukodik.
```

Próbáld ki a böngészőből: `http://<nas-ip>:8420`

A felület be fog jönni, **de a mikrofon nem fog működni** — ahhoz HTTPS
kell. Ez a következő lépés.

---

## 5. HTTPS — kétféleképpen

### A) Synology fordított proxyval (ha van DDNS-ed)

Ha már van `valami.synology.me` címed érvényes tanúsítvánnyal, ez a
legegyszerűbb.

**Vezérlőpult → Bejelentkezési portál → Fordított proxy → Létrehozás**

Két szabály kell.

**Első — a felület:**

| Mező | Érték |
|:--|:--|
| Leírás | `Kifli` |
| Forrás protokoll | HTTPS |
| Forrás gazdanév | `kifli.valami.synology.me` |
| Forrás port | 443 |
| Cél protokoll | HTTP |
| Cél gazdanév | `localhost` |
| Cél port | 8420 |

**Második — a hangkapcsolat:**

A DSM egy gazdanév + port párosra csak **egy** szabályt enged, ezért a
hangkapcsolat másik portra kerül:

| Mező | Érték |
|:--|:--|
| Leírás | `Kifli hang` |
| Forrás gazdanév | `kifli.valami.synology.me` |
| Forrás port | **`9080`** (vagy bármelyik szabad) |
| Cél port | `8421` |

Az **Egyéni fejléc** fülön itt is kapcsold be a **WebSocket**
előbeállítást.

> A WebSocket fejlécek nélkül a lap betöltődik, de a hang nem indul el.
> Ez a leggyakoribb hiba.

Végül mondd meg a programnak, melyik ez a port. A `.env`-be:

```
WS_KULSO_PORT=9080
```

Aztán `docker compose restart`.

<details>
<summary><b>Szabad port keresése</b></summary>

<br>

```bash
sudo netstat -tlnp | grep -E ":(9080|9443|8450)"
```

Ami nem jön vissza, az szabad. A 8443-at a DSM használja.

</details>

### B) Tailscale-lel

Ha nem akarsz a DSM-mel bajlódni, vagy nincs DDNS-ed:

```bash
sudo tailscale serve --bg 8420
sudo tailscale serve --bg --set-path=/ws 8421
```

Ilyenkor a `.env`-be ez kerül:

```
WS_UTVONAL=/ws
```

A Tailscale a Synology Csomagkezelőjéből telepíthető.

---

## 6. Tedd a telefonodra

A kapott HTTPS címet nyisd meg Safariban, engedélyezd a mikrofont, és
**Megosztás → Hozzáadás a Főképernyőhöz**.

A részletek a [telefonos útmutatóban](telefon.md).

---

## Karbantartás

```bash
# Naplók
sudo docker compose logs -f --tail 50

# Újraindítás
sudo docker compose restart

# Frissítés a GitHubról
git pull && sudo docker compose up -d --build

# Mennyi memóriát használ
sudo docker stats kifli --no-stream
```

A `.env` és a megtanult termékek az `adat/` mappában vannak, kívül a
konténeren — újraépítésnél megmaradnak.

---

## Ha valami nem megy

| Tünet | Mit nézz meg |
|:--|:--|
| A konténer újraindulgat | `docker compose logs` — általában hiányzó `.env` |
| „Nincs jogosultság" a naplóban | Rossz OpenAI kulcs vagy Kifli jelszó |
| A lap nem jön be | Nyitva van-e a 8420-as port a NAS tűzfalán |
| Betölt, de nem hall | Hiányzik a második proxy-szabály, vagy a `WS_KULSO_PORT` a `.env`-ből |
| „A mikrofon nem indult el" | HTTP-n vagy. HTTPS kell |
| Kevés a memória | `mem_limit` emelése a `docker-compose.yml`-ben |
| `readonly database` | `sudo chown -R $(id -u):$(id -g) adat`, majd restart |
| Nem tanul semmit | Ugyanaz: az `adat/` mappa jogosultsága |

<details>
<summary><b>A rohlik-mcp első indítása lassú</b></summary>

<br>

A konténer előre telepíti, de az első Kifli-bejelentkezés így is
eltarthat egy percig. A naplóban látszik:

```
Rohlik MCP server running on stdio
```

Ha ez megjelenik, a kapcsolat él.

</details>

---

## Amit a NAS nem tud

A **terminálos hangvezérlés** (`kifli.py --terminal`) nem fut a NAS-on,
mert nincs hangkártyája. Nincs is rá szükség: a grafikus felület a te
böngésződben veszi a mikrofont.

A **telefonos API** (`api.py`) viszont fut — ha azt is akarod, vedd fel
a `docker-compose.yml`-be második szolgáltatásként.
