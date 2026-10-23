# 🗺️ Atlas Flight Radar - Sürüm Yol Haritası ve Değişiklik Günlüğü (Changelog & Roadmap)

Bu doküman, **Atlas'ın Uçak Radarı & FIDS (Eindhoven Airport)** projesinin başlangıcından bugüne kadar olan tüm sürüm geçmişini, mimari evrimini ve gelecekte planlanan yenilikleri kronolojik olarak kayıt altında tutar.

---

## 📌 Sürüm Özeti

| Sürüm | Tarih | Odak Noktası | Durum |
| :--- | :--- | :--- | :--- |
| **v0.5.2** | 2026-10-23 | ROADMAP.md Sürüm Yol Haritası, Doküman Bekçisi ROADMAP Denetimi, Push Senkronizasyon Otomasyonu | 🚀 Canlıda |
| **v0.5.1** | 2026-10-23 | Tek Master README & CLAUDE Senkronizasyonu, Kapsam Bekçisi, Doküman Bekçisi, `sync_docs.py` | ✅ Tamamlandı |
| **v0.5.0** | 2026-10-23 | SQL Veritabanı ve `data` Dalı Ayrımı (`db/radar.db`, `db/radar.sql`, `scripts/manage_db.py`, `iterdump`) | ✅ Tamamlandı |
| **v0.4.9** | 2026-10-23 | Sayfa Sıralaması (Terminal → Gözlem Defteri → Radar), Sarı Renksiz Kokpit Teması, Geçiş Benchmarkları | ✅ Tamamlandı |
| **v0.4.8** | 2026-10-23 | Garanti Tıklama Navigasyonu (`st.session_state["nav_target"]`), Sıfır Bloklamalı Geçiş, Durum Çubuğu | ✅ Tamamlandı |
| **v0.4.5 - v0.4.7** | 2026-10-23 | Pydeck WebGL Radar Görselleştirmesi, CartoDB Altlığı, İkon Rotasyonu, Transit Kapsaması, Render Hızı | ✅ Tamamlandı |
| **v0.4.4** | 2026-10-22 | Modüler Mimari Refactoring (`radar_db.py`, `radar_fids.py`, `radar_config.py`, vb.), Fonksiyonel Testler | ✅ Tamamlandı |
| **v0.4.2 - v0.4.3** | 2026-10-22 | Özel Hava Taşıtları (LIFELINER ambulans helikopteri), Yüksek Kontrastlı UI, Tarayıcı User-Agent Desteği | ✅ Tamamlandı |
| **v0.4.0 - v0.4.1** | 2026-10-22 | Anı Defteri (Gözlem Defteri), 8 Koleksiyon Rozeti, Rütbeler, Gökyüzü Pusulası, Çocuk Kıyasları, Bahçe Çanı | ✅ Tamamlandı |
| **v0.3.5 - v0.3.14** | 2026-10-13 | FIDS Şimdi Görünümü, Açılış Hızlandırma, Radar Ön Isıtma (Warmup), Tolerant Parser, Dinamik Kapsama | ✅ Tamamlandı |
| **v0.3.0 - v0.3.4** | 2026-10-13 | Eindhoven Airport (EIN/EHEH) Terminal Ekranı, AeroDataBox Entegrasyonu, Şifreli Giriş, SQL Data Dalı | ✅ Tamamlandı |
| **v0.2.0** | 2026-10-10 | OpenSky Network Canlı Uçuş Trafiği, Ev ve Havalimanı Koordinatları, İrtifa ve Mesafe Filtreleri | ✅ Tamamlandı |
| **v0.1.0** | 2026-10-10 | İlk Kurulum, Temel Uçak Radarı Prototipi ve Harita Çizimi | ✅ Tamamlandı |
| **v0.6.0+** | Gelecek | Push Bildirimleri, 3D İrtifa Katmanları, Kokpit Sesli Asistanı, Turso Edge libSQL | 📋 Planlandı |

---

## 🚀 Sürüm Detayları

### [v0.5.2] - 2026-10-23 (Sürüm Yol Haritası ve Push Senkronizasyon Otomasyonu)
- **🗺️ ROADMAP.md Yol Haritası ve Değişiklik Günlüğü:**
  - Projenin kuruluşundan günümüze kadar olan tüm mimari evrimi kronolojik olarak kayıt altına alındı.
  - Sürüm özeti tablosu ve gelecek planları eklendi.
- **🛡️ Doküman Bekçisi ROADMAP Entegrasyonu (`tests/test_dokuman_bekcisi.py`):**
  - Doküman Bekçisi artık her test koşumunda ve push işleminde `ROADMAP.md`'nin varlığını, yapısını ve son sürümleri eksiksiz kapsadığını doğrular.
- **⚙️ Otomasyon Genişletmesi (`scripts/sync_docs.py`):**
  - `sync_docs.py` betiğine `ROADMAP.md` bütünlük denetimi kazandırıldı. Dokümantasyon senkronizasyonunda `README.md`, `CLAUDE.md` ve `ROADMAP.md` tam uyumlu tutulur.
- **📌 Uygulama Sürüm Güncellemesi (`Radar.py`):**
  - Arayüz durum popover'larında ve sistem izleme çubuğunda sürüm `v0.5.2` olarak güncellendi.

---

### [v0.5.1] - 2026-10-23 (Master Dokümantasyon ve Kalite Bekçileri)
- **📚 Tek Master README ve CLAUDE Senkronizasyonu:**
  - `README.md` tek ve kapsamlı master doküman haline getirildi (tüm sayfalar, çekirdek modüller, araçlar, workflow'lar, SQL veri mimarisi ve Anı Defteri modülü).
  - `CLAUDE.md` otomasyon başlığıyla `README.md` üzerinden otomatik üretilir hale getirildi.
- **🛡️ Kapsam Bekçisi (`tests/test_kapsam_bekcisi.py`):**
  - AST tabanlı kod analiziyle tüm modüllerdeki fonksiyonlar tespit edilir. Her fonksiyonun en az bir testte çalıştırılması şart koşulur; testsiz yeni fonksiyon eklendiğinde CI kırmızıya döner.
- **🛡️ Doküman Bekçisi (`tests/test_dokuman_bekcisi.py`):**
  - Master dokümanın tüm kritik bileşenleri (sayfalar, modüller, araçlar, kalıcı veritabanı, Anı Defteri, bekçiler) kapsadığını garanti eden bekçi testi eklendi.
- **🔄 Doküman Senkronizasyon Betiği (`scripts/sync_docs.py`):**
  - Tek komutla master dokümanı denetleyen ve `CLAUDE.md` dosyasını senkronize eden CLI aracı yazıldı.

---

### [v0.5.0] - 2026-10-23 (Düz Metin SQL Veritabanı ve data Dalı Ayrımı)
- **💾 SQL Veritabanı Mimari Ayrımı:**
  - Veritabanı ikili dosya (`radar.db`) yerine insan tarafından okunabilir, diff alınabilir düz metin SQL dökümü (`db/radar.sql`, `sqlite3 iterdump`) olarak yönetilmeye başlandı.
  - Şema tanımı `db/schema.sql` içerisine çıkarıldı (FIDS tablosu, sightings tablosu, kota sayaçları tablosu ve indeksler).
- **☁️ GitHub `data` Dalı Otomatik Senkronizasyonu:**
  - Uygulama ayağa kalkarken GitHub `data` dalından hem ikili `radar.db` hem de metin `radar.sql` dosyasını çeker. İkili dosya bozuk veya yoksa düz metin SQL'den veritabanını sıfırdan ayağa kaldırır.
  - Yeni gözlem kaydında GitHub `data` dalına anında SQL dökümü commit edilir.
- **🛠️ Veritabanı Yönetim Aracı (`scripts/manage_db.py`):**
  - Yerel ve CI ortamında `status`, `dump`, `restore`, `sync-data` komutlarıyla veritabanı denetimi sağlayan CLI betiği eklendi.
- **🧪 SQL ve data Dalı Test Paketi (`tests/test_sql_db_sync.py`):**
  - Döküm üretimi, SQL'den geri yükleme, bozuk SQL koruması ve GitHub `data` dalı senkronizasyonunu sınayan kapsamlı testler eklendi.

---

### [v0.4.9] - 2026-10-23 (Yeni Sayfa Sıralaması, Sarı Renksiz Kokpit Teması ve Benchmarklar)
- **📐 Kullanıcı Odaklı Sayfa Sıralaması:**
  - Sayfa gezinme sırası kullanıcının en çok ihtiyaç duyduğu akışa göre düzenlendi:
    1. **🛫 Eindhoven Havalimanı (Terminal FIDS)**
    2. **📖 Gözlem Defteri (Atlas'ın Anı Defteri & Rozetler)**
    3. **📡 Canlı Uçak Radarı (Pydeck WebGL & CartoDB)**
- **🎨 Sarı Renksiz Şık Kokpit Teması:**
  - Gözlem Defteri'ndeki göze batan sarı renk tonları (`#fde047`, `rgb(250, 204, 21)`) tamamen kaldırıldı.
  - Havacılık standartlarına uygun gök mavisi (`#38bdf8`), lacivert (`#0f172a`), zümrüt yeşili (`#34d399`) ve kehribar (`#f59e0b`) kokpit renk paletine geçildi.
- **⚡ Ultra Hızlı Sayfa Geçiş Benchmarkları (`tests/test_page_flow_perf.py`):**
  - Sayfalar arası geçiş süresi 24 ardışık simülasyonla test edildi.
  - Ortalama geçiş süresi **0.4 ms** (< 50 ms bütçe), en yavaş geçiş **0.9 ms** (< 150 ms bütçe) olarak rekor performansa ulaştı.

---

### [v0.4.8] - 2026-10-23 (Garanti Tıklama Navigasyonu ve Modern Durum Çubuğu)
- **🎯 Tıklama Yakalama ve Sıfır Bloklama:**
  - Streamlit radio butonlarının CSS katmanları nedeniyle tıklamaları kaçırmasını engelleyen `st.session_state["nav_target"]` garanti yönlendirme mekanizması geliştirildi.
  - Sayfa tıklamalarında 5 saniyeyi aşan donmalar ve asılı kalmalar sıfıra indirildi.
- **📟 Avionik Alt Durum Çubuğu:**
  - Her 3 sayfanın altına ortak tasarıma sahip modern `status-info` durum çubuğu eklendi.
  - Canlı saat, aktif veri kaynağı, radar kapsama alanı, sürüm bilgisi ve GitHub senkron durumu tek bir satırda gösterildi.

---

### [v0.4.5 - v0.4.7] - 2026-10-23 (Pydeck WebGL Radar Görselleştirmesi)
- **🚀 WebGL Donanım Hızlandırmalı Harita:**
  - Yavaş Folium/Leaflet harita katmanı yerine GPU hızlandırmalı `pydeck.Deck` kütüphanesine geçildi.
  - **CartoDB Dark Matter** altlık haritası entegre edildi.
- **✈️ SVG Uçak Sembolleri ve Yön Rotasyonu:**
  - Uçakların anlık rota açısına (`track`) göre dönen SVG uçak ikonu katmanı (`IconLayer`) oluşturuldu.
- **🌐 Dinamik Transit Uçuş Kapsaması:**
  - Seçilen kapsama alanı (50 / 100 / 200 km) değiştiğinde transit uçuşların haritada doğru ölçeklenmesi sağlandı.
- **⚡ Warmed Radar Render Optimizasyonu:**
  - Radar sayfasının önceden ısıtılmış bellekle 0.01 saniyede çizilmesi sağlandı; CI süre bütçesi optimize edildi.

---

### [v0.4.4] - 2026-10-22 (Modüler Mimari Refactoring)
- **🧱 Modüler Ayrıştırma:**
  - Dev monolitik yapıdan modüler alt sistem mimarisine geçildi:
    - `radar_db.py`: Veritabanı ve GitHub senkronizasyonu
    - `radar_fids.py`: Terminal uçuş tarifesi, durum hesaplama ve AeroDataBox işleme
    - `radar_config.py`: Sabitler, havalimanı ve ev koordinatları, çocuk karşılaştırma mantığı
    - `radar_styles.py`: Tek merkezden yönetilen CSS kokpit teması
    - `radar_auth.py`: Şifreli giriş ve URL token güvenliği
    - `radar_motion.py`: İnterpolasyon ve hareket simülasyonu
- **🧪 Modüler Fonksiyonel Test Paketi (`tests/test_functional_modular.py`):**
  - Alt sistemlerin bağımsız çalışmasını denetleyen birim ve fonksiyonel testler eklendi.

---

### [v0.4.0 - v0.4.3] - 2026-10-22 (Anı Defteri ve Çocuk Odaklı Özellikler)
- **📖 Gözlem Defteri (Atlas'ın Anı Defteri):**
  - Atlas'ın yakaladığı uçakları kaydedebileceği, geçmiş gözlemleri filtreleyebileceği ve detayları inceleyebileceği kayıt defteri geliştirildi.
- **🏅 Rütbe ve Rozet Koleksiyonu:**
  - 5 kademeli rütbe sistemi: *🐣 Meraklı Gözlemci → 🔭 Bahçe Gözcüsü → 🛩️ Hava Trafik Uzmanı → 👨‍✈️ Baş Pilot → 🏆 Gökyüzü Efsanesi*.
  - 8 kilit açılabilir rozet: *🎯 İlk Av, 🔥 Keskin Göz, 🌍 Dünya Turu, ✈️ Filo Uzmanı, 🦅 Alçak Uçuş, 🏠 Tam Tepemizde, 📅 Sadık Gözcü, 👑 Kule Efsanesi*.
- **🧭 Gökyüzü Pusulası & Çocuk Karşılaştırmaları:**
  - Evin bahçesinden bakan bir çocuğun uçağı görebileceği yön ve açı göstergesi.
  - Uçak hızı ve irtifasını çita, yarış arabası, hızlı tren ve Everest Dağı ile kıyaslayan eğlenceli çocuk kartları.
- **🔔 Bahçe Sesli Uyarısı:**
  - Evin 3 km yakınına 3.000 ft altında bir uçak girdiğinde Web Audio API ile iki tonlu kokpit çanı çalan bildirim sistemi.
- **🚁 Özel Çağrı Kodları:**
  - Hollanda ambulans helikopteri (`LIFELINER`), polis helikopteri (`POLICE`) ve askeri uçuşlar için özel tanıma sistemi.

---

### [v0.3.x] - 2026-10-13 (Terminal FIDS ve Performans İyileştirmeleri)
- **🛫 Eindhoven Airport (EIN/EHEH) Terminal Ekranı:**
  - Havalimanı varış ve kalkış tablosu (FIDS), AeroDataBox API entegrasyonu, uçuş durumu, gecikme ve kapı bilgisi.
- **⚡ Sıfır Bloklamalı Açılış ve Isıtma:**
  - Uygulama ilk açıldığında Terminal ekranının 0.01 sn içinde ekrana gelmesi sağlandı.
  - Ağ istekleri arka plana devredildi; arka plan cron işi (`sync-fids.yml`) ile FIDS verisi önceden hazırlandı.

---

### [v0.1.0 - v0.2.0] - 2026-10-10 (İlk Kurulum ve Canlı Trafik)
- **📡 Canlı Trafik:** OpenSky Network anonim API entegrasyonu, Eindhoven ve Blixembosch koordinatları etrafında uçuş takibi.
- **🔐 Giriş Güvenliği:** Streamlit secrets ve URL token tabanlı şifreli giriş.
- **🗺️ Harita:** Temel Streamlit harita prototipi.

---

## 🔮 Gelecek Yol Haritası (Planned & Upcoming)

### 📌 v0.6.0 - Bildirimler, Yakınlık Alarmları ve Zenginleştirilmiş Veri
- [ ] **Bahçe Yaklaşma Push Bildirimi:** Tarayıcı kapalıyken veya arka plandayken evin üzerinden geçen uçak için Web Push bildirimi.
- [ ] **3D İrtifa Katmanları:** Pydeck üzerinde uçakların irtifasına göre 3 boyutlu yükselen irtifa kolonları ve gökyüzü koridorları.
- [ ] **Gelişmiş Uçak Fotoğraf Galerisi:** JetPhotos ve Planespotters API'lerinden uçağın yüksek çözünürlüklü fotoğraflarını getiren önbellekli görselleştirme.

### 📌 v0.7.0 - Sesli Kokpit Asistanı ve Telsiz Efektleri
- [ ] **Sesli Kokpit Telsizi (ATC Simülasyonu):** Yeni bir uçak bahçe alanına girdiğinde kule anonsu tonunda sesli seslendirme ("*Transavia 5101, Eindhoven 21 pistine yaklaşıyor*").
- [ ] **Çocuklar İçin Sesli Havacılık Masalları:** Atlas'ın yakaladığı uçağın tipine göre ("Boeing 737", "Airbus A320") eğlenceli sesli kısa bilgiler.

### 📌 v1.0.0 - Turso Edge libSQL ve Gerçek Zamanlı Çoklu Cihaz Senkronizasyonu
- [ ] **Turso (libSQL) Edge SQLite Desteği:** GitHub'a SQL dökümü göndermek yerine doğrudan bulutta barındırılan ultra hızlı, sıfır gecikmeli libSQL SQLite veritabanı.
- [ ] **Progressive Web App (PWA) & Mobil Çevrimdışı Mod:** Atlas'ın iPad ve telefonundan tam ekran uygulama deneyimi ve çevrimdışı rozet görüntüleme.
