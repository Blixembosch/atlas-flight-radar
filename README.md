# 🛫 Atlas'ın Uçak Gözlem Kulesi (Atlas Flight Radar)

[![Atlas Flight Test Suite](https://github.com/Blixembosch/atlas-flight-radar/actions/workflows/tests.yml/badge.svg)](https://github.com/Blixembosch/atlas-flight-radar/actions/workflows/tests.yml)
[![FIDS Sync](https://github.com/Blixembosch/atlas-flight-radar/actions/workflows/sync_data.yml/badge.svg)](https://github.com/Blixembosch/atlas-flight-radar/actions/workflows/sync_data.yml)
[![Sürüm](https://img.shields.io/badge/s%C3%BCr%C3%BCm-v0.5.0-38bdf8.svg)](Radar.py)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](requirements.txt)
[![Streamlit](https://img.shields.io/badge/streamlit-1.32+-ff4b4b.svg)](https://streamlit.io)

> **Atlas'ın Uçak Gözlem Kulesi**, Eindhoven Havalimanı (**EHEH / EIN**) yaklaşma koridorunda bulunan Blixembosch bahçesinden geçen uçakları gerçek zamanlı izlemek, gökyüzünde başımızı nereye kaldıracağımızı bilmek ve geçen uçakları baba-oğul (Anıl & Atlas) oyunlaştırılmış bir **Anı Defteri**'nde biriktirmek için tasarlanmış **%100 ücretsiz** avionik uçuş takip ve terminal sistemidir.

---

## 📑 İçindekiler
1. [Proje Hikayesi ve Temel İlkeler](#1-proje-hikayesi-ve-temel-ilkeler)
2. [Sayfa ve Ekran Mimarisi](#2-sayfa-ve-ekran-mimarisi)
   - [🛫 1. Terminal Ekranı](#-1-terminal-ekranı)
   - [📒 2. Gözlem Defteri ve Anı Defteri](#-2-gözlem-defteri-ve-anı-defteri)
   - [🛰️ 3. Canlı Radar Ekranı](#-3-canlı-radar-ekranı)
3. [Çekirdek Modüller ve Mimari](#3-çekirdek-modüller-ve-mimari)
4. [Kalıcı SQL Veritabanı ve `data` Dalı Ayrımı](#4-kalıcı-sql-veritabanı-ve-data-dalı-ayrımı)
5. [Yönetim ve Otomasyon Araçları (`scripts/`)](#5-yönetim-ve-otomasyon-araçları-scripts)
6. [GitHub Actions İş Akışları (Workflows)](#6-github-actions-iş-akışları-workflows)
7. [Bekçi Sistemleri (Guards)](#7-bekçi-sistemleri-guards)
   - [🛡️ Kapsam Bekçisi](#️-kapsam-bekçisi)
   - [🛡️ Doküman Bekçisi](#️-doküman-bekçisi)
8. [Sıfır Bloklamalı Performans ve Önbellek Mimarisi](#8-sıfır-bloklamalı-performans-ve-önbellek-mimarisi)
9. [Test Altyapısı ve Kalite Standartları](#9-test-altyapısı-ve-kalite-standartları)
10. [Kurulum, Yapılandırma ve Dağıtım](#10-kurulum-yapılandırma-ve-dağıtım)

---

## 1. Proje Hikayesi ve Temel İlkeler

* **Kullanım Senaryosu:** Eindhoven Havalimanı (`EHEH` / `EIN`) kuzey yaklaşma/kalkış koridoru (pist `03/21`, `30°/210°`) üzerindeki bahçemizden (`51.4950, 5.4750`) gökyüzüne baktığımızda geçen uçakları canlı harita üzerinde görmek, kerteriz ve bakış açısını (**Gökyüzü Pusulası**) anında okumak, bahçe üstüne yeni uçak girdiğinde kokpit anons çanı duymak ve uçakları koleksiyon rozetleri kazandıran bir **Anı Defteri**'ne kaydetmektir.
* **Sıfır Maliyet Kuralı:** Sistem yalnızca ücretsiz veya cömert ücretsiz katmanlara sahip servislerle çalışır:
  - **Sunucu:** Streamlit Community Cloud (ücretsiz, geçici/ephemeral dosya sistemi).
  - **Kalıcı Depolama:** GitHub REST API üzerinden ana kod dalından (`main`) bağımsız `data` dalında (`orphan branch`) tutulan düz metin ANSI SQL dökümü (`db/radar.sql`) ve SQLite ikili dosyası (`db/radar.db`).
  - **Canlı Konum:** OpenSky Network (birincil) + `adsb.lol` (otomatik yedek, anahtarsız).
  - **Uçuş & Rota Zenginleştirme:** `adsbdb.com` + yerel FIDS tarifesi füzyonu + `planespotters.net` (fotoğraf).
  - **Terminal Tarifesi (FIDS):** AeroDataBox (RapidAPI Basic ücretsiz plan, aylık kota bütçeleyicili).
  - **Hava Durumu:** Open-Meteo (ücretsiz, anahtarsız).

---

## 2. Sayfa ve Ekran Mimarisi

Uygulama 3 temel sayfadan oluşur. Açılış doğrudan en hafif ve hızlı sayfa olan Terminal ile gerçekleşir:

```
PAGES = ["🛫 Terminal", "📒 Gözlem Defteri", "🛰️ Radar"]
```

### 🛫 1. Terminal Ekranı
* **Eindhoven Airport (EIN · EHEH) FIDS Panosu:** Varış (`🛬 Varış`) ve Kalkış (`🛫 Kalkış`) uçuşları bağımsız iki panelde, varsayılan 20 (60'a kadar genişletilebilir) uçuş olarak listelenir.
* **Görünümler:**
  - **Şimdi:** Son 60 dakika içinde inen/kalkan + aktif uçuşlar + önümüzdeki 30 dakikalık seferler.
  - **Tüm Gün:** Günün ilk seferinden son seferine kadar tüm tarife.
* **Avionik Detaylar:** Havayolu logoları, ülke bayrakları, hedef/kalkış şehri, kapı (`Gate`) numarası, durum (`Expected`, `Landed`, `Departed`) ve rötar dakikaları.
* **Sıfır Bloklamalı Açılış:** GitHub veya harici AeroDataBox servisini beklemeden 0.01 sn içinde anında render edilir.

### 📒 2. Gözlem Defteri ve Anı Defteri
* **Otomatik & Manuel Kayıt:** Bahçe görüş alanına (`dist_home ≤ 4.0 km` ve `alt_ft ≤ 5.000 ft`) giren tüm uçaklar otomatik olarak SQLite veritabanına ve GitHub `data` dalına kaydedilir. İstenirse Radar detay kartındaki **📖 Gözlem Defterine Kaydet** düğmesiyle manuel de eklenebilir.
* **🏅 Uçak Avcısı Rütbe Sistemi:** Yakalanan uçak sayısına göre 5 farklı rütbe seviyesi verilir:
  1. 🐣 *Meraklı Gözlemci* (1–4 uçak)
  2. 🔭 *Bahçe Gözcüsü* (5–14 uçak)
  3. 🛩️ *Hava Trafik Uzmanı* (15–29 uçak)
  4. 👨‍✈️ *Baş Pilot* (30–49 uçak)
  5. 🏆 *Gökyüzü Efsanesi* (50+ uçak)
* **🎖️ 8 Rozetlik Avcı Koleksiyonu:**
  - **İlk Av:** İlk uçağını deftere kaydettin!
  - **Keskin Göz:** 10 farklı uçak yakaladın.
  - **Dünya Turu:** 5 farklı ülkeden gelen uçuş gördün.
  - **Filo Uzmanı:** 3 farklı uçak modeli tanıdın.
  - **Alçak Uçuş:** 2.000 ft altına inen uçağı yakaladın.
  - **Tam Tepemizde:** Bahçeye 2 km'den yakın geçen uçuş.
  - **Sadık Gözcü:** 3 farklı günde gözlem yaptın.
  - **Kule Efsanesi:** 50 uçakla gökyüzü efsanesi oldun!
* **Anı Defteri Görsel Paneli:** Bugün / Son 7 Gün / Toplam uçak KPI sayaçları, son 7 günün çubuk grafiği ve son gözlemler tablosu (Terminal ile tam uyumlu elektrik gök mavisi `#38bdf8` kokpit teması).

### 🛰️ 3. Canlı Radar Ekranı
* **Canlı Harita & 500 ms Kayma Animasyonu:** Sunucudan yeni veri gelmesini beklemeden hız ve kerteriz vektörlerine göre uçakların akıcı süzüldüğü Leaflet / Pydeck (WebGL) harita motoru (`MOTION_JS`).
* **Bahçe Önceliği:** Bahçe görüş alanındaki uçaklar asla gizlenmez. Rotası bilinmeyen uçaklar bile (askeri nakliye, Lifeliner hava ambulansı, polis helikopteri) ekranda tutulur.
* **🧭 Gökyüzü Pusulası & Bakış Açısı:** Uçağın bahçemize göre hangi yönde (*Kuzeydoğu ↗* vb.) ve ufuktan kaç derece yukarıda olduğunu hesaplar:
  - `≥ 45°`: *"🦅 Tam tepemizde! Başını yukarı kaldır"*
  - `20°–44°`: *"👀 Gökyüzünde orta yükseklikte"*
  - `8°–19°`: *"🌲 Ağaçların / çatıların üstünde"*
  - `< 8°`: *"🌅 Ufuk çizgisine yakın"*
* **🧒 Çocuk Dostu Kıyaslamalar:** 50+ uçak tipi için eğlenceli bilgiler ve uçağın o anki hız ve irtifasını Formula 1 aracı, çita, Eyfel Kulesi ve Burj Khalifa ile kıyaslayan canlı kutu.
* **🔔 Bahçe Sesli Uyarısı:** Bahçe üstüne yeni bir uçak girdiğinde tarayıcının Web Audio API sentezleyicisi ile çift tonlu kokpit anons çanı (*587 Hz → 440 Hz*) çalar.
* **🔗 Terminal + Radar Füzyonu:** `adsbdb`'de yer almayan Avrupa charter ve düşük maliyetli uçuşların şehir, saat, rötar ve kapı bilgisi yerel Terminal (`fids_flights`) veritabanından tamamlanır.

---

## 3. Çekirdek Modüller ve Mimari

| Modül | Görev ve Sorumluluk |
|---|---|
| [`Radar.py`](Radar.py) | Ana Streamlit uygulaması, sayfa render döngüsü, oturum durumu (`session_state`), canlı radar veri entegrasyonu (`fetch_states`, `build_flights`), WebGL harita ve 3 sayfa kontrolü. |
| [`radar_db.py`](radar_db.py) | SQLite (`RadarDB`) veri erişim katmanı, düz metin ANSI SQL dökümü (`dump_sql`, `restore_sql`), bellek içi TTL önbelleği (`_stats_cache`, `_recent_cache`), GitHub `data` dalı çift formatlı senkronizasyonu (`GitStore`). |
| [`radar_fids.py`](radar_fids.py) | Eindhoven FIDS tarifesi motoru: AeroDataBox API istemcisi, kota bütçeleyicisi (`budget_state`), JSON ayrıştırıcı (`parse_adb`), "Şimdi" ve "Tüm gün" filtreleri. |
| [`radar_config.py`](radar_config.py) | Havalimanı ve bahçe koordinatları, yaklaşma koridoru açıları, çocuk kıyaslama metinleri, uçak tipleri, koltuk kapasiteleri ve hava durumu sabitleri. |
| [`radar_styles.py`](radar_styles.py) | Koyu havacılık teması, cam morfizm kartlar, yüksek kontrastlı tipografi (WCAG AA), responsive grid ve dinamik havayolu CSS sınıfları (`fids_logo_css`). |
| [`radar_auth.py`](radar_auth.py) | Güvenlik kapısı (`gate`), sabit zamanlı şifre karşılaştırması (`hmac.compare_digest`), 3 yanlışta 5 sn kilit, mobil ana ekran için URL token (`?k=`) desteği. |
| [`radar_motion.py`](radar_motion.py) | Leaflet Motion animasyon motoru ve Pydeck WebGL radar katmanı yapılandırmaları. |

---

## 4. Kalıcı SQL Veritabanı ve `data` Dalı Ayrımı

Streamlit Community Cloud geçici kapsayıcılarda (*ephemeral containers*) çalıştığı için her dağıtımda yerel disk sıfırlanır. Veri kaybını önlemek ve ana kod tabanını veri dosyalarından tamamen bağımsız tutmak için:

```
[GitHub Repo]
  ├── main (Yalnızca kaynak kod, testler ve şema DDL; sıfır veri kirliliği)
  └── data (Orphan Branch: Kalıcı Veritabanı ve Döküm)
        ├── db/radar.sql  -> İnsan tarafından okunabilir ANSI SQL dökümü (iterdump)
        ├── db/radar.db   -> SQLite ikili veritabanı (anında açılış için)
        └── db/schema.sql -> Tablo DDL tanımları
```

* **`.gitignore` Koruması:** `*.db`, `*.db-journal`, `db/radar.sql` ana dala asla girmez.
* **Tutarlı SQL Dökümü (`dump_sql`):** Canlı yazmalarla çakışmayı önlemek için önce bellek içine (`con.backup`) anlık kopya alınır ve `iterdump()` ile standart SQL dökümü üretilir.
* **Güvenli Geri Yükleme (`restore_sql`):** SQL dökümünü geçici dosyada kurup `PRAGMA integrity_check` doğrulaması yaptıktan sonra atomik olarak yerine koyar.
* **Çift Formatlı Eşitleme:** Otomatik senkronizasyon çalıştığında hem `db/radar.sql` hem de `db/radar.db` `data` dalına yazılır.

---

## 5. Yönetim ve Otomasyon Araçları (`scripts/`)

### Veritabanı Yönetimi ([`scripts/manage_db.py`](scripts/manage_db.py))
```bash
# 1. Yerel DB, SQL dökümü ve GitHub data dalı durumunu incele
python3 scripts/manage_db.py status

# 2. Yerel veritabanından db/radar.sql dökümü oluştur
python3 scripts/manage_db.py dump

# 3. db/radar.sql dökümünden SQLite veritabanını yeniden kur
python3 scripts/manage_db.py restore

# 4. GitHub data dalındaki son DB ve SQL dökümünü çek
python3 scripts/manage_db.py pull

# 5. Yerel DB ve SQL dökümünü GitHub data dalına anında yükle
python3 scripts/manage_db.py push
```

### Arka Plan Tarife Eşitlemesi ([`scripts/sync_fids.py`](scripts/sync_fids.py))
Eindhoven Havalimanı tarifesini çeker, kota bütçesini kontrol eder ve `data` dalındaki veritabanını günceller.

### Dokümantasyon Otomasyonu ([`scripts/sync_docs.py`](scripts/sync_docs.py))
Projedeki tüm modülleri inceler, Doküman Bekçisi standartlarına göre `README.md` dosyasının eksiksizliğini doğrular ve `CLAUDE.md` ile `README.md` dosyalarını otomatik senkronize tutar.

---

## 6. GitHub Actions İş Akışları (Workflows)

1. **`Atlas Flight Test Suite` ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)):**
   - Her `push` ve `pull_request` anında çalışır.
   - 18 farklı birim, fonksiyonel, performans ve bekçi testini internetsiz deterministik ortamda çalıştırır.
2. **`Arka Plan Tarife Senkronizasyonu` ([`.github/workflows/sync_data.yml`](.github/workflows/sync_data.yml)):
   - Eindhoven Havalimanı aktif saatlerinde her 3 saatte bir (`cron: "15 5,8,11,14,17,20 * * *"`) çalışır.
   - `python3 scripts/sync_fids.py` çalıştırarak `data` dalındaki `db/radar.sql` ve `db/radar.db` dosyalarını günceller.

---

## 7. Bekçi Sistemleri (Guards)

Sistem kalitesini korumak için projeye iki temel otomatik bekçi dahil edilmiştir:

### 🛡️ Kapsam Bekçisi ([`tests/test_kapsam_bekcisi.py`](tests/test_kapsam_bekcisi.py))
> **Kural:** *"Her fonksiyon en az bir testte çalışmalı; yeni fonksiyon testsiz eklenince kırmızıya döner."*
- Python `ast` (Abstract Syntax Tree) modülü ile projedeki tüm fonksiyonları tarar.
- `tests/test_*.py` altındaki testlerde referansı bulunmayan fonksiyon tespit edildiğinde testi fail eder ve eksik fonksiyonları listeler.

### 🛡️ Doküman Bekçisi ([`tests/test_dokuman_bekcisi.py`](tests/test_dokuman_bekcisi.py))
> **Kural:** *"Bu README.md her sayfayı, çekirdek modülü, aracı, workflow'u ve Anı Defteri modülünü/sekmesini kapsamalı."*
- `README.md` dosyasını tarayarak tüm zorunlu sayfaların, modüllerin, yönetim araçlarının, iş akışlarının ve Anı Defteri bileşenlerinin dokümanda tam olarak yer aldığını denetler.

---

## 8. Sıfır Bloklamalı Performans ve Önbellek Mimarisi

* **Kalıcı HTTP Havuzu:** Tüm dış istekler `_session()` ile kalıcı TCP/TLS havuzunda tutulur; el sıkışma gecikmeleri önlenir.
* **SQLite Bellek İçi TTL Önbellek:** `radar_db.py` içindeki `_stats_cache` (30 sn) ve `_recent_cache` (15 sn) sayesinde Gözlem Defteri her tıklandığında diske gitmez, sayfalar arası geçiş **0.1 ms – 1.8 ms** seviyesindedir.
* **Asenkron Hava Durumu ve Görseller:** Open-Meteo, havayolu logoları ve uçak fotoğrafları arka planda indirilir; ana sayfa çizimi sıfır milisaniye gecikmeyle açılır.

---

## 9. Test Altyapısı ve Kalite Standartları

Tüm testler sahte (`mock`) Streamlit, Folium, Requests ve GitHub katmanlarıyla internetsiz çalışır:

```bash
bash tests/run_all.sh
```

* [`tests/harness3.py`](tests/harness3.py): Streamlit'in yaşam döngüsünü taklit eder (yeniden çizimlerde kaybolmaması gereken anahtarlar `keep()` ile korunur).
* [`tests/test_page_flow_perf.py`](tests/test_page_flow_perf.py): Sayfa geçiş sürelerini ölçer (hedef: < 200 ms, ortalama < 50 ms).
* [`tests/test_sql_db_sync.py`](tests/test_sql_db_sync.py): SQL dökümü ve `data` dalı senkronizasyonunu test eder.
* [`tests/test_kapsam_bekcisi.py`](tests/test_kapsam_bekcisi.py): Fonksiyon kapsamını doğrular.
* [`tests/test_dokuman_bekcisi.py`](tests/test_dokuman_bekcisi.py): Dokümantasyon bütünlüğünü doğrular.

---

## 10. Kurulum, Yapılandırma ve Dağıtım

### Yerel Çalıştırma
```bash
# 1. Depoyu klonlayın
git clone https://github.com/Blixembosch/atlas-flight-radar.git
cd atlas-flight-radar

# 2. Sanal ortamı kurun ve etkinleştirin
python3 -m venv .venv
source .venv/bin/activate

# 3. Bağımlılıkları yükleyin
pip install -r requirements.txt

# 4. secrets.toml dosyasını oluşturun
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 5. Uygulamayı başlatın
streamlit run Radar.py
```

### Secrets Parametreleri (`secrets.toml`)

| Secret | Zorunlu mu? | Açıklama |
|---|---|---|
| `APP_PASSWORD` | **Evet** | Uygulama açılış şifresi |
| `AERODATABOX_KEY` | Önerilir | Eindhoven FIDS tarifesi için RapidAPI anahtarı |
| `GITHUB_TOKEN` | Önerilir | Veritabanını `data` dalına yedeklemek için Fine-Grained Token (*Contents: Read & Write*) |
| `GITHUB_REPO` | Önerilir | Depo adı (`Blixembosch/atlasradar`) |
| `DATA_BRANCH` | İsteğe bağlı | Veritabanı dalı (Varsayılan: `data`) |
| `DATA_SQL_PATH` | İsteğe bağlı | SQL döküm yolu (Varsayılan: `db/radar.sql`) |
| `DATA_DB_PATH` | İsteğe bağlı | SQLite yolu (Varsayılan: `db/radar.db`) |
| `TRAFFIC_SOURCE` | İsteğe bağlı | `auto` (OpenSky → `adsb.lol`), `opensky` veya `adsblol` |
| `HOME_LAT`, `HOME_LON` | İsteğe bağlı | Bahçe koordinatları (Varsayılan: `51.4950`, `5.4750`) |

---

## 11. Sürüm Yol Haritası ve Değişiklik Günlüğü (`ROADMAP.md`)

Projenin başlangıcından bu yana gerçekleşen tüm sürümler, detaylı mimari dönüşümler ve gelecek planları [`ROADMAP.md`](ROADMAP.md) dosyasında tutulur:
* **Her Push ve Sürümde Güncelleme Kuralı**: Projeye yeni bir özellik, mimari iyileştirme veya hata düzeltmesi eklendiğinde `ROADMAP.md` güncellenir.
* **Otomasyon & Bekçi Denetimi**: [`tests/test_dokuman_bekcisi.py`](tests/test_dokuman_bekcisi.py) ve [`scripts/sync_docs.py`](scripts/sync_docs.py) her test ve push işleminde `ROADMAP.md`'nin güncel, eksiksiz ve master dokümanla uyumlu olduğunu otomatik olarak denetler.
* **Gelecek Vizyonu**: Gelecek sürümler için planlanan push bildirimleri, 3D irtifa koridorları, sesli ATC simülasyonu ve Turso Edge libSQL entegrasyon hedefleri `ROADMAP.md` içinde listelenmiştir.
