# CP-OBS-HEARTBEAT — Scheduler / Telemetry Reliability Diagnostic (read-only)

**Tarih:** 2026-07-18 · **Statü:** salt-okuma teşhis (davranış/scheduler değişikliği YOK)
**Script:** `backend/scripts/cp_obs_heartbeat.py` (read-only; DB'ye yazmaz; analiz deterministik — tek `[LIVE PROBE]` satırı hariç byte-identical)
**Amaç:** SQF sonrası ana strateji = veri-birikimi. Bu birikim güvenilir akıyor mu, yoksa kaçan fire / telemetri-boşluğu / sessiz-durma var mı — ölç.

---

## Executive conclusion

Sistem **şu an canlı akıyor** (status_history en son ~1 dk önce; ~103 sinyal/gün stabil) ve **duplicate/overlap YOK** (single-flight sağlam: 0/0/0). **AMA sessiz-durma riski POST-HOC KANITLANDI:** ~26 günlük gözlem penceresinde **5 kesinti** var — **4'ü kesin çoklu-saat** (06-30·07-01·07-14·07-15, **4.5-7.8 saat**) + 1'i **96 dk** (07-16, memory'deki `--reload` lock) — scheduler hiç ateşlememiş, hem generation hem tracking durmuş, **hiçbir alarm tetiklenmemiş.** En büyüğü **7.8 saat** (07-14). Toplam kanıtlanmış kesinti ≈ **27 saat** (>1h bloklar). Biri (07-16, 96 dk) memory'de kayıtlı `--reload` kilit olayıyla birebir eşleşiyor → telemetri güvenilir bir downtime-detektörü; diğer 4 kesinti **belgelenmemiş** (bilinmeyen duruşlar).

**KARAR (kullanıcının karar-mantığına göre):** Fire-kaçırma + sessiz-durma **kanıtlandı** → sonraki checkpoint meşru. **Öneri: (1) minimal liveness/heartbeat alarmı** (ucuz interim — şu an downtime'ı CANLI göremiyorsun, yalnız post-hoc); **(2) Private Staging = yapısal fix** (yerel dev-makine 24/7 çok-haftalık birikim için kanıtlanmış-güvenilmez). Bu CP yalnız teşhistir; canlı davranış eklenmedi.

---

## Bulgular

### [A] Canlı tazelik `[LIVE PROBE]`
status_history ~1 dk · generation ~6 dk · resolution ~6 dk bayat → **sistem şu an çalışıyor.**

### [B] Günlük yoğunluk (deterministik)
Tam-gün generation: min 14 / max 159 / **ort 91.5** (ilk/son kısmi gün hariç); resolved≈gen (birikim dengeli). status_history telemetrisi **06-22'den başlıyor** (ilk 2 gün lifecycle-telemetrisi yok). Düşük günler: 06-27/28 (~49-50), 06-30 (50), 07-08 (66).

### [C] Nabız boşluk analizi — `signal_status_history` (deterministik)
- Normal cadence sağlıklı: **median 0.75 dk · p90 4.0 dk · p99 10 dk** (her ~2-dk pass'te birden çok status olayı).
- Boşluklar: **>15dk: 82 · >30dk: 11 · >60dk: 5 · MAX: 468 dk.**
- **5 çoklu-saat kesinti (gerçek downtime adayları):**

| Tarih | Pencere | Süre |
|---|---|---|
| 2026-07-14 | 01:36 → 09:24 | **468 dk (7.8 sa)** |
| 2026-07-01 | 13:04 → 20:39 | **456 dk (7.6 sa)** |
| 2026-07-15 | 02:28 → 07:50 | **322 dk (5.4 sa)** |
| 2026-06-30 | 11:46 → 16:14 | **268 dk (4.5 sa)** |
| 2026-07-16 | 00:24 → 02:00 | **96 dk** (= memory'deki `--reload` lock) |

### [D] Birleşik-zaman-çizelgesi sessizliği (tüm akışlar)
Yukarıdaki 5 kesinti burada da görünür (hem generation hem tracking aynı anda susmuş → gerçek downtime, "sessiz piyasa" değil). Kripto 7/24 olduğundan bu boşluklar piyasa-saati artefaktı olamaz. İlk 2 gün (06-17→06-22) kurulum-dönemi aralıklı.

### [E] 2-dk slot kapsaması
18.363 slot'un %38.2'si boş — ama boş-slot = o pass'te status DEĞİŞMEDİ (sessiz), kaçan-fire kanıtı DEĞİL. Gerçek downtime yalnız uzun ardışık boşluklarda ([C]/[D] max-gap). Median 0.75 dk cadence normal işleyişi doğruluyor.

### [F] Duplicate / overlap
**0 / 0 / 0** — 0 sinyal >1 trade_path, 0 duplicate status satırı, 0 sinyal >1 performance. **Single-flight koruması sağlam; çakışan/çift-run YOK.**

---

## Net verdict (8 soru)

1. **Scheduler güvenilir çalışıyor mu?** — **ÇOĞUNLUKLA evet, ama tam değil.** Cadence sağlıklı + şu an canlı + duplicate yok; ancak 26 günde **5 çoklu-saat kesinti** (≈27 sa toplam).
2. **Son N günde fire kaçırma var mı?** — **EVET, kanıtlandı.** 4-8 saatlik pencerelerde yüzlerce 2-dk pass hiç ateşlemedi (07-14 7.8 sa; 07-15 5.4 sa en yeni örnekler).
3. **Telemetry boşluğu var mı?** — **EVET** (yukarıdaki kesintiler + ilk 2 gün lifecycle-telemetrisi yok).
4. **Sessiz durma riski var mı?** — **EVET, KANITLANDI.** Sistem birden çok kez saatlerce sessizce durdu; **canlı alarm olmadığı için fark edilmedi** (yalnız bu post-hoc analizle görünür oldu). Korkulan riskin tam kendisi.
5. **Duplicate/overlap var mı?** — **HAYIR (0/0/0).** Single-flight güvenilir.
6. **Yerel env yeterli mi?** — **HAYIR / güvenilmez.** 26 günde 5 çoklu-saat kesinti (gündüz duruşları = restart/crash/lock; gece duruşları = makine uykusu) 24/7 çok-haftalık birikim için yerel dev-makinenin uygun olmadığını gösteriyor.
7. **Private Staging'e şimdi geçmek gerekiyor mu?** — **Güçlü aday (yapısal fix), ama zorunlu-acil değil.** Birikim yine de akıyor (kesintiler ~%5 downtime, aralıklı). Karar kullanıcının (maliyet/çaba); teknik gerekçe kanıtlandı.
8. **Minimal heartbeat gerekli mi, yoksa mevcut telemetry yeterli mi?** — **Minimal heartbeat/alarm GEREKLİ.** Mevcut telemetri downtime'ı yalnız **post-hoc** gösteriyor; **canlı liveness sinyali yok** → sistem saatlerce durabiliyor ve kimse bilmiyor. Gerçek gözlem-eksiği bu.

## Karar mantığı sonucu

Kullanıcı kuralına göre: *"fire kaçırma veya sessiz durma riski kanıtlanırsa → sonraki checkpoint Private Staging veya minimal heartbeat olabilir."* Kanıtlandı. **Önerilen sıra (over-build değil, ikisi de ayrı onaylı CP; bu CP'de EKLENMEDİ):**
1. **CP-OBS-ALARM (minimal, ucuz interim):** additive liveness/heartbeat — son fire üzerinden X dk geçtiyse görünür uyarı (Telegram/log). Sinyal davranışına dokunmaz; yalnız "durdu mu" görünürlüğü. Silent-stop'u anında görünür kılar.
2. **CP-STAGING (yapısal fix, değerlendir):** birikimi always-on private host'a taşı (public/ödeme yok → beta legal kapılarına takılmaz). Yerel-makine kesintilerini yapısal çözer + beta altyapı provası.

**Not:** İki kesinti (07-16 lock, 07-14/07-15 gece) dev-makine-gözlem fazında beklenen türden — ki bu tam olarak "always-on host gerekir" tezini doğruluyor. Duplicate/overlap yokluğu single-flight'ın sağlam olduğunu; asıl açık = **liveness-görünürlüğü + 24/7 host güvenilirliği.**

---

## Ek — bağımsız doğrulama (adversarial SQL, ≥2 yöntem)

Script'e güvenmeden her manşet ≥2 bağımsız SQL yöntemiyle (lag-gap DEĞİL; saatlik-bucket + cross-stream) yeniden-türetildi. Hepsi **CONFIRM**:

| İddia | Yöntem 1 (saatlik sıfır-run) | Yöntem 2 (cross-stream / distinct) | Verdict |
|---|---|---|---|
| 5 çoklu-saat kesinti | 5 ardışık sıfır-saat run'ı birebir: 06-30 (4sa), 07-01 (6sa), 07-14 (7sa, en büyük), 07-15 (4sa), 07-16 (1sa); geri kalan 17-gün hiç sıfır değil | 5 pencerenin hepsinde generation=**0** + interior saatler sıfır; süreler 268/455/468/322/96 dk eşleşti | **CONFIRM** |
| duplicate/overlap yok | HAVING count>1 = **0/0/0** (trade_path·status·perf) | count(*)=distinct: trade_path **2010=2010**, perf **2598=2598**, status **23255=23255** | **CONFIRM** |
| birikim aksi halde sağlıklı + canlı | 28 tam-gün ort **91.54** (min14/max159), resolved≈gen | tazelik **2.06 dk** (canlı); son-7g 719 gen / 717 resolved (~102.7/gün) | **CONFIRM** |

**Verifier nüansları (rapora işlendi):** (a) 07-16 kesintisi ~96 dk / 1 tam sıfır-saat → "çoklu-saat" için sınırda; **kesin multi-hour olan 4'ü** (06-30·07-01·07-14·07-15, 4.5-7.8 sa). (b) "~90-120/gün" bandı gevşek — sağlıklı günler **~90-160** aralığında; ort 91.5, kesinti-etkilenen günlerin "tam gün" sayılmasıyla aşağı çekiliyor. İkisi de merkez bulguyu (sessiz-durma kanıtı) değiştirmiyor.

## Ek — çalıştırma

`cd backend && PYTHONPATH=. venv/Scripts/python.exe scripts/cp_obs_heartbeat.py`
Read-only · DB'ye yazmaz · scheduler/davranış değiştirmez · cron/worker/supervisor eklemez · analiz deterministik (tek `[LIVE PROBE]` satırı canlılık okuması olduğundan koşudan koşuya değişir — tasarım gereği).
