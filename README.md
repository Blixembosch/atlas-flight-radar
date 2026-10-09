# ✈️ Atlas'ın Uçak Gözlem Kulesi

Eindhoven Havalimanı (EHEH) kuzey koridorunu ve Blixembosch bahçesinin üzerinden geçen uçakları
canlı gösteren, koyu temalı Streamlit panosu.

## Özellikler
- Tek ekran: harita + seçili uçağın detay paneli + alt kart şeridi
- Uçak ikonları gidiş yönüne döner, hız ve yöne göre harita üzerinde kayar
- Seçili uçak sarı renkle vurgulanır (haritadan ya da "İncele" ile seçilir)
- Havayolu logosu, rota (bayraklı), uçak modeli, tescil, fotoğraf, yükseklik, hız, koltuk sayısı
- Aktif pist (03 / 21) tahmini, bahçeden görünürlük ve "kaç dk sonra bahçede" bilgisi
- İsteğe bağlı "Üstümüzden geçenler" modu ve ayarlanabilir kapsama alanı
- Arama: çağrı kodu, uçuş numarası (HV6710), havayolu, şehir, havalimanı kodu, model, tescil
- Demo modu (gece uçak yokken arayüzü denemek için)

## Kurulum
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run Radar.py
```

## Ayarlar
`Radar.py` dosyasının başındaki sabitler:

| Sabit | Anlamı |
|---|---|
| `HOME_LAT`, `HOME_LON` | Mavi nokta (ev) konumu |
| `VISIBLE_KM`, `VISIBLE_ALT_FT` | "Bahçeden görünür" mesafe ve irtifa |
| `OVERFLIGHT_KM` | "Üstümüzden geçenler" mesafesi |
| `REFRESH_ACTIVE`, `REFRESH_IDLE` | Veri yenileme aralıkları (sn) |
| `MAP_HEIGHT` | Harita yüksekliği |

### OpenSky hesabı (önerilir)
Hesapsız kullanımda günlük kota düşüktür. Ücretsiz hesap açıp
`.streamlit/secrets.toml.example` dosyasını `.streamlit/secrets.toml` olarak kopyalayın ve doldurun.
Bu dosya `.gitignore` içindedir, GitHub'a gitmez.

### Logolar
Logo internetten otomatik alınır. İsterseniz `assets/logos/TRA.png`, `RYR.png`, `WZZ.png`,
`TUI.png` gibi dosyalar koyarak kendi logolarınızı kullanabilirsiniz (öncelikli olur).

## Veri kaynakları
[OpenSky Network](https://opensky-network.org) (canlı konum) ·
[adsbdb](https://www.adsbdb.com) (rota, uçak kaydı) ·
[planespotters.net](https://www.planespotters.net) (fotoğraf) ·
[Open-Meteo](https://open-meteo.com) (hava durumu) ·
Harita: © OpenStreetMap katkıcıları, © CARTO

> Rota, model ve koltuk bilgisi bazı uçaklarda eksik olabilir. Koltuk sayıları tipik düzene göre yaklaşıktır.
