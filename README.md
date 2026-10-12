# ✈️ Atlas'ın Uçak Gözlem Kulesi · v0.3.3

Eindhoven Havalimanı (EHEH) kuzey koridorunu ve Blixembosch bahçesinin üzerinden geçen uçakları
canlı gösteren, koyu temalı Streamlit panosu.

## Sayfalar
| Sayfa | Ne gösterir |
|---|---|
| 🛰️ **Radar** | Harita + seçili uçağın detay paneli + kart şeridi. **Rotası bilinmeyen uçaklar gizlenir** (⚙️ menüsünden açılabilir; gizlenen sayı 🙈 çipinde). |
| 🛫 **Terminal** | Eindhoven Airport bilgi ekranı: **Varış** ve **Kalkış** ayrı panellerde, her yönde en az 20 uçuş, **Durum** ve **Gecikme** ayrı sütun, arama, "Daha fazla göster". |
| 📒 **Gözlem Defteri** | Bahçeden görülen uçaklar otomatik kaydedilir: bugün / hafta / toplam, son 7 gün grafiği, son görülenler. |

Üstte **Demo modu** (gece uçak yokken / anahtarsız deneme) ve **Çıkış** vardır.

## Kurulum
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # doldurun
streamlit run Radar.py
```

## Şifre
Uygulama açılışta şifre sorar. Şifre koda yazılmaz; secrets içindeki `APP_PASSWORD` değeridir.
`APP_PASSWORD` tanımlı değilse uygulama **kilitli** kalır. 3 yanlıştan sonra kısa bekleme uygulanır.
Giriş yapılmadan hiçbir veri çağrısı yapılmaz.

## Terminal ekranı için AeroDataBox (ücretsiz)
1. RapidAPI'de **AeroDataBox**'a abone olun (Basic/ücretsiz plan, ayda ~600 birim).
2. Anahtarı secrets içine `AERODATABOX_KEY` olarak yazın.

Ücretsiz kota az olduğu için tarife **veritabanında önbelleklenir**; ekran hep veritabanından okunur ve
API yalnızca gerektiğinde çağrılır (kalan bütçeye göre ~2–12 saatte bir; en az 1 saat arayla). Çağrılar
tüm oturumlar arasında tekilleştirilir, kota sayacı veritabanında tutulur ve %10'u güvenlik payı olarak
ayrılır. Terminal sayfasında "bu ay X/Y birim" bilgisi görünür. Anahtar yoksa sayfa açıklama gösterir.

## Veritabanı (SQLite) ve `data` dalı
Şema: [`db/schema.sql`](db/schema.sql) — `meta`, `fids_flights` (tarife), `sightings` (gözlem defteri),
`api_usage` (kota), `fetch_log`.

Streamlit Cloud'da dosya sistemi kalıcı değildir; bu yüzden `db/radar.db` dosyası GitHub deposunun
**`data` dalında** saklanır:
* Açılışta `data` dalından çekilir; dal yoksa ilk yedekte **otomatik oluşturulur** (ana koddan bağımsız dal,
  içinde `db/radar.db` ve `db/schema.sql`).
* Değişiklik varsa en çok 20 dakikada bir arka planda yedeklenir (Gözlem Defteri'nde **☁️ Şimdi yedekle**).
* `data` dalına yazmak uygulamayı yeniden dağıtmaz (uygulama `main` dalını izler).
* **Güvenlik:** çekme başarılı olmadan uzaktaki veritabanının üzerine asla yazılmaz; çekme başarısız olursa
  yerel veri korunur, sonra birleştirilir.
* `GITHUB_TOKEN` yoksa yalnızca yerel dosya kullanılır (Cloud yeniden başlayınca silinir).

GitHub token: Settings → Developer settings → **Fine-grained token** → yalnızca bu depo → *Contents: Read and write*.

## Ayarlar
`Radar.py` başındaki sabitler (ör. görüş yarıçapı, yenileme süreleri) ve secrets:

| Secret | Anlamı |
|---|---|
| `APP_PASSWORD` | Açılış şifresi (zorunlu) |
| `AERODATABOX_KEY`, `AERODATABOX_HOST`, `ADB_MONTHLY_UNITS` | Terminal tarifesi ve kota |
| `GITHUB_TOKEN`, `GITHUB_REPO`, `DATA_BRANCH`, `DB_PUSH_MIN` | Veritabanı yedeği |
| `opensky_client_id`, `opensky_client_secret` | OpenSky hesabı (önerilir) |
| `TRAFFIC_SOURCE` | `auto` (varsayılan: OpenSky, ulaşılamazsa adsb.lol), `opensky` ya da `adsblol` |
| `HOME_LAT`, `HOME_LON` | Ev konumu (depo herkese açıksa kodda bırakmayın) |

> Depo **public** ise kodda yazan yaklaşık ev koordinatı herkese görünür. Depoyu *private* yapın ya da
> koordinatı `HOME_LAT`/`HOME_LON` secrets'ına taşıyıp koddakini genel bir noktayla değiştirin.

## Test
```bash
bash tests/run_all.sh
```
Streamlit, GitHub, AeroDataBox ve OpenSky sahtelerle çalışır (internet gerekmez): şifre kapısı, rota filtresi,
radar akışı, terminal (≥20 satır, arama, kota), veritabanı + `data` dalı eşitleme.

## Veri kaynakları
[OpenSky Network](https://opensky-network.org) ve [adsb.lol](https://adsb.lol) (canlı konum; OpenSky bulut sunucularına bazen zaman aşımı verir, uygulama otomatik adsb.lol'a geçer) · [adsbdb](https://www.adsbdb.com) (rota, uçak) ·
[AeroDataBox](https://aerodatabox.com) (tarife) · [planespotters.net](https://www.planespotters.net) (fotoğraf) ·
[Open-Meteo](https://open-meteo.com) (hava) · Harita: © OpenStreetMap katkıcıları, © CARTO

> Rota, model ve koltuk bilgisi bazı uçaklarda eksik olabilir. Koltuk sayıları tipik düzene göre yaklaşıktır.
