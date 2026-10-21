# CLAUDE.md — Atlas'ın Uçak Gözlem Kulesi (Mimari ve Geliştirici Rehberi)

Bu belge, **Atlas'ın Uçak Gözlem Kulesi (`v0.4.0`)** projesinin tüm iş mantığını, veri akışını, performans kurallarını, veritabanı mimarisini ve test altyapısını açıklar. Kod tabanında değişiklik yaparken burada belirtilen mimari ilkelere ve kısıtlara uyulmalıdır.

---

## 1. Proje Amacı ve Bağlamı

* **Kullanım Senaryosu:** Eindhoven Havalimanı (`EHEH` / `EIN`) kuzey yaklaşma/kalkış koridoru (pist `03/21`, `30°/210°`) üzerinde bulunan **Blixembosch bahçesinden (`51.4950, 5.4750`)** geçen uçakları baba-oğul (Anıl & Atlas) birlikte gerçek zamanlı takip etmek, gökyüzünde hangi yöne bakılacağını görmek ve yakalanan uçakları oyunlaştırılmış bir gözlem defterinde biriktirmek.
* **Barındırma ve Maliyet Kısıtı:** Uygulama **%100 ücretsiz** servisler üzerinde çalışacak şekilde tasarlanmıştır:
  * **Sunucu:** Streamlit Community Cloud (ücretsiz, geçici/ephemeral dosya sistemi).
  * **Kalıcı Depolama:** SQLite (`db/radar.db`) + GitHub REST API üzerinden ana koddan bağımsız `data` dalına (`orphan branch`) otomatik yedekleme ve açılışta geri yükleme.
  * **Canlı Trafik:** OpenSky Network (birincil) + `adsb.lol` (ücretsiz, anahtarsız, otomatik yedek).
  * **Uçuş & Gövde Zenginleştirme:** `adsbdb.com` (ücretsiz) + yerel FIDS veritabanı birleştirmesi + `planespotters.net` (ücretsiz fotoğraf).
  * **Havalimanı Tarifesi (FIDS):** AeroDataBox (RapidAPI Basic ücretsiz plan — ayda ~600 birim kota bütçeleyicili).
  * **Hava Durumu:** Open-Meteo (ücretsiz, anahtarsız).

---

## 2. Dosya ve Modül Yapısı

| Dosya | Sorumluluk |
|---|---|
| `Radar.py` | Ana Streamlit uygulaması, koyu tema CSS sistemi, canlı radar veri katmanı (`fetch_states`, `build_flights`, `enrich_geometry`), Folium/Leaflet harita + 500 ms istemci tarafı hareket motoru (`MOTION_JS`), Web Audio API sesli uyarı (`chime_script_html`) ve 3 sayfa (`page_radar`, `page_terminal`, `page_diary`). |
| `radar_db.py` | SQLite (`RadarDB`) veri erişim katmanı, bellek içi `meta` ve `fids_lookup_map` önbellekleri, gözlem defteri (`sightings`) istatistikleri, kota (`api_usage`) kayıtları ve GitHub `data` dalı (`BranchSync`) senkronizasyonu. |
| `radar_fids.py` | Eindhoven Terminal (FIDS) motoru: AeroDataBox API istemcisi, aylık kota bütçe hesaplayıcısı (`budget_state`, `due_for_refresh`), esnek JSON ayrıştırıcı (`parse_fids_payload`), "Şimdi" (`-60/+30 dk`) ve "Tüm gün" görünüm seçicisi (`select_board`). |
| `radar_auth.py` | Şifre kapısı (`require_login`), sabit zamanlı karşılaştırma (`hmac.compare_digest`), yanlış şifre hız sınırlaması (3 hatada 5 sn kilit) ve mobil/tablet yer imleri için URL token (`?k=<hmac_token>`) doğrulaması (`make_token`). |
| `db/schema.sql` | SQLite veritabanı şeması (`meta`, `fids_flights`, `sightings`, `api_usage`, `fetch_log`). |
| `tests/` | İnternetsiz çalışan deterministik test paketi (`harness3.py`, `run_all.sh`, `test_perf.py`, `test_app.py`, `test_radar_flow.py`, `test_fids.py`, `test_db_auth.py`, `test_default_page.py` vb.). |

---

## 3. Uçtan Uca Çalışma Mantığı

### 3.1. Giriş ve Kimlik Doğrulama (`radar_auth.py`)
1. `secrets.toml` içinde `APP_PASSWORD` tanımlı değilse uygulama güvenlik nedeniyle **kilitli** kalır ve hiçbir dış API çağrısı yapmaz.
2. Kullanıcı doğru şifreyi girdiğinde `st.session_state["auth_ok"] = True` olur ve `st.query_params["k"] = make_token(APP_PASSWORD)` (SHA-256 tabanlı 16 karakterlik HMAC özeti) URL'ye yazılır.
3. Kullanıcı bu URL'yi telefon/tablet ana ekranına eklediğinde sonraki açılışlarda `?k=...` parametresi doğrulanarak şifre ekranı otomatik geçilir.

### 3.2. Sıfır Bloklamalı (Non-Blocking) Performans Mimarisi
Streamlit her kullanıcı etkileşiminde betiği baştan sona yeniden çalıştırır. Arayüzün asla donmaması için şu kurallar uygulanır:
1. **Kalıcı HTTP Havuzu (`_HTTP_SESSION`):** Tüm dış istekler `_http_get` ve `_http_post` üzerinden `requests.Session()` ile yapılır; TCP ve TLS el sıkışmaları yeniden kullanılır (testlerde `requests.get` monkeypatch edildiğinde otomatik algılanıp sahte fonksiyona yönlendirilir).
2. **İki Aşamalı Arka Plan Trafik Çekme (`fetch_states` & `_traffic_job`):**
   * İlk açılışta (`COLD_NONBLOCK = True`, `block = False`) veri henüz yoksa ekran **beklemez**: boş harita ve *"Canlı hava trafiği yükleniyor…"* mesajı `0.01 sn` içinde çizilir, yenileme süresi geçici olarak `2 sn` yapılır.
   * Arka plan iş parçacığı (`_traffic_job`), OpenSky veya `adsb.lol`'dan ham konumları alır almaz (rota ve logo indirmelerini beklemeden!) `_TCACHE[key]` önbelleğini günceller; ardından `build_flights` ve `attach_logos` ile önbelleği ısıtır.
   * Sonraki tüm çizimlerde `allow_stale=True` kullanılır: önbellekteki veri `FETCH_TTL` (8 sn) süresini aşmış ama `STALE_OK_S` (180 sn) içindeyse mevcut veri **anında** döndürülür ve tazeleme arka planda başlatılır.
3. **Beklemesiz Yan Kaynaklar (`fetch_weather`, `peek_logo`, `peek_photo`):**
   * Hava durumu (Open-Meteo), havayolu logoları ve uçak fotoğrafları (`planespotters.net`) ana çizim iş parçacığını **asla bloklamaz**. Önbellekte yoksa arka plan iş parçacığı başlatılır ve mevcut çizim hemen tamamlanır.
4. **SQLite ve Bellek Önbelleği (`radar_db.py`):**
   * `PRAGMA journal_mode=DELETE` yalnızca `init_schema()` içinde bir kez çalışır; her okuma bağlantısında tekrarlanmaz.
   * `meta_get` çağrıları `_meta_cache` sözlüğünden sıfır disk G/Ç ile okunur.
   * `fids_lookup_map` sonucu veritabanı yazma sayacına (`_write_seq`) bağlı olarak bellekte tutulur; `fids_flights` tablosu değişmedikçe yeniden sorgulanmaz.

### 3.3. Canlı Trafik Kaynakları ve Otomatik Yedekleme (`_fetch_states_live`)
* Varsayılan mod (`TRAFFIC_SOURCE = "auto"`):
  1. Önce **OpenSky Network** (`OPENSKY_TIMEOUT = 3.5 sn`) denenir.
  2. Bulut sunucularında OpenSky IP engeli/zaman aşımı yaşanması durumunda `_SRC["os_down_until"] = now + 900` (15 dakika) işaretlenir ve anında ücretsiz **`adsb.lol`** (`api.adsb.lol/v2/point/{lat}/{lon}/{nm}`) servisine geçilir.
  3. `adsblol_to_states()` fonksiyonu `readsb` JSON çıktısını OpenSky `state vector` dizisine dönüştürür (knot → m/s, ft/dk → m/s dikey hız, yerde/telsiz kulesi filtreleri).

### 3.4. Uçak Seçimi ve 3 Kaynaklı Veri Birleştirme (`_candidates` & `build_flights`)
1. **Aday Filtresi (`_candidates`):**
   * `near`: Eindhoven'a `≤ 50 km` ve `≤ 10.000 ft` irtifa.
   * `inbound`: `50 km < mesafe ≤ kapsama (50/100/200 km)`, `≤ 22.000 ft`, alçalan (`vrate ≤ -1.0 m/s`) ve burnu havalimanına dönük (`angle_diff ≤ 30°`).
   * `transit`: "Üstümüzden geçenler" (`f_over`) açıkken bahçeye `≤ 30 km` mesafedeki yüksek irtifa uçuşları.
2. **3 Kaynaklı Zenginleştirme:**
   * **Kaynak 1 — `adsbdb`:** Çağrı kodundan rota (`/v0/callsign/{cs}`) ve ICAO24 hex kodundan gövde/tescil (`/v0/aircraft/{hex}`) bilgileri `ThreadPoolExecutor(12)` ile paralel çekilir ve `store` içinde önbelleklenir (başarılı rota 1 saat, uçak 24 saat, geçici ağ hatası `_state: "err"` 20 sn).
   * **Kaynak 2 — Terminal (FIDS) Füzyonu (`_match_fids`):** `adsbdb` birçok Avrupa charter/düşük maliyetli uçuşunu bilmez. `build_flights`, yerel SQLite veritabanındaki `fids_flights` tablosunu çağrı kodu (`TRA6672`), ICAO→IATA dönüşümü (`TRA6672 → HV6672`) ve kuyruk tescili (`PH-HXA`) ile tarar. Eşleşme bulunduğunda:
     * Kalkış/varış havalimanı, şehir ve ülke bayrağı tamamlanır (`route_known = True`).
     * Uçağın planlanan/tahmini saati, rötar durumu ve kapı (`gate`) bilgisi `f["fids"]` alanına eklenerek Radar detay kartında gösterilir.
   * **Kaynak 3 — Askeri / Hava Ambulansı / Polis Koruması (`SPECIAL_PREFIXES`, `SPECIAL_TYPES`):** Eindhoven hem sivil havalimanı hem de askeri hava üssüdür. `NAF` (Hollanda Hava Kuvvetleri), `MMF` (NATO MRTT), `LIF`/`ANW` (Lifeliner Hava Ambulansı), `ZXP` (Polis Helikopteri) çağrı kodları ve `C130`, `A400`, `F35`, `EC35` gibi özel tipler `adsbdb`'de rotası olmasa bile gizlenmez.

### 3.5. Baba-Oğul Etkileşim Özellikleri
* **🧭 Gökyüzü Pusulası (`enrich_geometry`):**
  * Evin koordinatından uçağın koordinatına kerteriz açısı (`from_home`) hesaplanır ve 8 yönden birine (`Kuzey ⬆️`, `Kuzeydoğu ↗️` vb.) çevrilir.
  * Uçağın irtifası (metre) ve yatay uzaklığından (`dist_home`) dikey bakış açısı $\text{elev} = \arctan(\text{alt\_m} / \text{dist\_m})$ derece cinsinden hesaplanır:
    * `≥ 45°`: *"🦅 Tam tepemizde! Başını yukarı kaldır"*
    * `20°–44°`: *"👀 Gökyüzünde orta yükseklikte"*
    * `8°–19°`: *"🌲 Ağaçların / çatıların üstünde"*
    * `< 8°`: *"🌅 Ufuk çizgisine yakın"*
* **🧒 Çocuk Dostu Kıyaslamalar (`kid_comparison` & `AIRCRAFT_TYPES`):**
  * 50+ uçak tipi için çocuk dilinde ilginç bilgiler ve uçağın o anki hız/irtifasını Formula 1 aracı, çita, Eyfel Kulesi veya Burj Khalifa ile kıyaslayan dinamik kutu.
* **🔔 Sesli Bahçe Uyarısı (`chime_script_html`):**
  * Harici ses dosyasına ihtiyaç duymadan tarayıcının `AudioContext` (Web Audio API) sentezleyicisi ile `587.33 Hz (D5) → 440 Hz (A4)` çift tonlu kokpit anons çanı üretir. Aynı uçak için tekrar tekrar çalmaması adına `st.session_state["_last_chime_id"]` ile tekilleştirilir.
* **🏅 Gözlem Defteri ve Rozet Sistemi (`page_diary` & `badges_html`):**
  * Bahçe görüş küresine (`dist_home ≤ 4.0 km` ve `alt_ft ≤ 5.000 ft`) giren uçaklar otomatik olarak `sightings` tablosuna kaydedilir; ayrıca Radar detay kartındaki **"📖 Gözlem Defterine Kaydet"** düğmesiyle manuel kayıt yapılabilir.
  * Toplam yakalanan uçak sayısına göre 5 rütbe (*🐣 Meraklı Gözlemci → 🔭 Bahçe Gözcüsü → 🛩️ Hava Trafik Uzmanı → 👨‍✈️ Baş Pilot → 🏆 Gökyüzü Efsanesi*) ve 8 rozet (*İlk Av, Keskin Göz, Dünya Turu, Filo Uzmanı, Alçak Uçuş, Tam Tepemizde, Sadık Gözcü, Kule Efsanesi*) hesaplanır.

### 3.6. Terminal (FIDS) ve Kota Bütçeleyicisi (`radar_fids.py`)
* AeroDataBox çağrısı başına 2 kota birimi harcar (`withLeg=true` ile tek çağrıda hem varış hem kalkış, 12 saatlik pencere).
* `budget_state(db, now, monthly_units=600)`: Aylık kotanın `%10`'unu güvenlik payı olarak ayırır (`cap = 540`). Ayın kalan saatine ve kalan kotaya göre yenileme aralığını `1 saat` ile `12 saat` arasında dinamik hesaplar.
* Gece `00:00–05:00` (Hollanda saati) arasında Eindhoven'da tarifeli uçuş olmadığı için otomatik API çağrısı yapılmaz.

### 3.7. Veritabanı ve GitHub `data` Dalı Eşitleme (`radar_db.py`)
* `BranchSync`:
  * Açılışta `pull_if_empty()` arka plan iş parçacığında çalışır (`background=True`); yerel veritabanı boşsa GitHub `data` dalındaki `db/radar.db` indirilir.
  * İndirme sırasında kullanıcı yerel veritabanına yeni kayıt yazmışsa ezilmez; `merge_from()` ile uzak ve yerel tablolar (`fids_flights`, `sightings`, `api_usage`) güvenli şekilde birleştirilir (`MIN(min_km)`, `MAX(units)`).
  * **Güvenlik Kuralı:** `pull_ok` bayrağı `True` olmadan `push()` asla uzaktaki `data` dalının üzerine yazmaz (ağ hatası durumunda uzaktaki yedeğin sıfırlanmasını önler).

---

## 4. Test Altyapısı ve Geliştirme Kuralları

Tüm testler internet bağlantısı olmadan, sahte (`mock`) Streamlit, Folium, Requests ve GitHub katmanlarıyla çalışır:

```bash
bash tests/run_all.sh
```

* **`tests/harness3.py`:** Gerçek Streamlit'in katı kurallarını taklit eder:
  * Bir bileşen çizildikten sonra aynı çalıştırmada `session_state[key]` değiştirilirse `StreamlitAPIException` fırlatır.
  * O çalıştırmada çizilmeyen sekme bileşenlerinin anahtarlarını `session_state`'ten siler (bu yüzden sayfa geçişlerinde korunması gereken değerler `keep()` ve `remember()` ile `_saved` sözlüğünde saklanır).
* **`tests/test_perf.py`:** Ağ gecikmelerini (OpenSky zaman aşımı, GitHub indirme süresi, yavaş hava durumu/logo servisleri) simüle ederek her ekran çiziminin milisaniyeler içinde tamamlandığını doğrular.
* **Önemli Kural:** Yeni bir dış HTTP çağrısı eklerken doğrudan `requests.get` yerine `Radar.py` içindeki `_http_get` / `_http_post` yardımcılarını kullanın; böylece hem üretimde `requests.Session()` bağlantı havuzu kullanılır hem de `harness3.py` test yakalayıcısı bozulmaz.
