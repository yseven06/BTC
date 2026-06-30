# P1.2 — Lifecycle Aksiyon Katmanı + Proaktif Bildirim — HAZIRLIK ANALİZİ (kod YOK)

**Tarih:** 2026-06-30 · **Statü:** ANALİZ (yalnız analiz; kod yazılmadı) · **veri-bağımsız** (hemen değer).
**Kaynak:** 4-ajan paralel kod-haritalama (Lifecycle v2 + bildirim sistemi + tracker dikişi + alarm/anti-spam) + sentez.

## 0. Özet & boşluk
Lifecycle v2 **olgun ama gözlem-only**: bir sinyal WEAKENING/INVALIDATING/APPROACHING_TP'ye geçince
yalnız DB state + history satırı yazılıyor, **kullanıcıya proaktif bildirim YOK**. (Doğrulandı:
`tracker.py`'de sıfır notify importu; `notify_signal` yalnız `scheduler.py:429` yeni-sinyal yolunda.)
**P1.2 = bu teslimat boşluğunu doldurur** — tespit mantığına dokunmadan, tamamlanan P0.2 per-user
bildirim altyapısı üzerine. **Veri-bağımsız** (tespit zaten doğru çalışıyor; eşik kalibrasyonu ayrı P2 işi).

## 1. Mevcut mimari (haritalardan)
- **Lifecycle durumları** (`lifecycle.py:29-39`): ACTIVE, APPROACHING_TP, WEAKENING, INVALIDATING.
  Severity merdiveni `{active:0, weakening:1, invalidating:2}`. STRENGTHENING yok; 'closed' terminal
  (resolution, live_status değil). TR etiketler `status_tr()`; `lc.reason` hazır TR açıklama taşır.
- **P1.2 DİKİŞİ (tek nokta):** `tracker.py:707-721` — `if prev_status != lc.status or live_status_since
  is None:` bloğu. Gerçek transition'ın tek tespit+persist+log (make_event) yeri. **Anti-spam BURADA
  zaten yerleşik:** hysteresis + min-state-süresi + transition-gate → **once-per-transition bedava**;
  `lc.suppressed` flip-flop'lar satır yazmaz → bildirim de almaz.
- **Bildirim (P0.2):** `notify_signal` (`service.py:49-108`) — per-user fan-out (NotificationSettings⋈User
  WHERE telegram_enabled+token+chat_id), per-user **tier gate** (`_user_can_use_telegram`, Pro+/admin),
  mesajı bir kez kur, `send_telegram_message`. **Per-user izole.** Kanal: yalnız Telegram.
- **Dağıtım zamanlaması:** `notify_signal` DB session DIŞINDA, commit SONRASI çağrılır (`scheduler.py:429`).
  Tracker döngü sonunda tek commit (`tracker.py:724`).
- **MUTLAK YOK:** dedup/cooldown/last-notified kolonu hiçbir yerde **yok**. (Yeni proaktif yol kendi
  anti-spam'ını once-per-transition'dan ALIR.)

## 2. Mevcut sisteme etki (additive, fail-open)
| Bileşen | Etki |
|---|---|
| Lifecycle DETECTION (`evaluate_lifecycle`/`_classify_raw`/`_apply_hysteresis`/eşikler) | **DEĞİŞMEZ (FROZEN)** — P2 kalibrasyonu. |
| tracker resolution / trade-path / coin-memory yazımları | **DEĞİŞMEZ.** |
| `make_event` / live_status / history | **DEĞİŞMEZ** — P1.2 yalnız transition'ın YANINA notify ekler. |
| notify sistemi | **notify_lifecycle()** (notify_signal'i aynalar) + **format_lifecycle_message** (yeni formatter). |
| NotificationSettings | **opt-in kolon** (`notify_lifecycle`) → additive migration. |

→ Bildirim **fire-and-forget + fail-open** (notify_signal'ın try/except-swallow + tracker'ın fail-open
deseni gibi): bir Telegram hatası **asla** tracking pass'ini, commit'i veya status persist'i bloklamaz.

## 3. Kritik kararlar (kullanıcı onayı gerekiyor)
1. **HEDEFLEME — sinyaller GLOBAL (user_id yok).** İki model:
   - **(A) Global fan-out** (notify_signal gibi): telegram-açık her Pro+ kullanıcı, her sinyalin
     transition'ını alır. Basit + tutarlı; **ama hacim yüksek**.
   - **(B) Opt-in per-asset** (`AlertType.SIGNAL` — tanımlı ama **uygulanmamış**, scheduler.py:496):
     kullanıcı bir varlığa abone olur, yalnız sahipler alır. Düşük-spam ama opt-in UX + uygulama ister.
   - **Önerim: (A) + yeni `notify_lifecycle` opt-in kolonu (default False)** → kullanıcı bilinçli açar
     (sürpriz spam yok), global fan-out'un basitliği korunur. (B) zengin bir gelecek iyileştirmesi.
2. **TETİK SETİ (muhafazakâr):** yalnız **`{invalidating, approaching_tp}`** transition'larında bildir
   (yüksek-sinyal, düşük-gürültü). **WEAKENING'i başta ATLA** (en gürültülü; v2.2 persistence filtresi
   onu zaten damp'liyor). `kind='birth'` ve de-eskalasyon (recovery) → bildirme; yalnız eskalasyon
   (`_SEVERITY` testi). Eşik **eklemeyiz** (detection frozen).
3. **TIER GATE:** lifecycle bildirimleri de Pro+ gate'ine uymalı (ücretli özellik sızıntısını önler).
   `min_confidence`/`notify_hold` yeni-sinyal kavramları → lifecycle'a uygulanmaz.

## 4. Riskler / edge-case'ler
- **Spam (en önemli):** global fan-out × N aktif sinyal × Pro+ kullanıcı = yüksek hacim. Azaltıcılar:
  once-per-transition (bedava) + `{invalidating, approaching_tp}` seti + WEAKENING hariç + opt-in kolon.
- **Re-arm:** sinyal weakening↔active salınabilir → her biri gerçek transition. WEAKENING'i setten
  çıkarmak bunu çözer; invalidating terminale yakın (düşük re-arm).
- **Dağıtım izolasyonu:** notify'ı **commit SONRASI** yap (döngüde transition tuple'larını topla →
  `db.commit()` sonrası fan-out); tracker DB session'ına I/O karıştırma.
- **Fail-open:** Telegram hatası resolution/tracking'i bloklamamalı (envelope zorunlu).
- **MUTLAK dokunma:** detection, resolution, AI/trade kararı, Similarity/Adaptive, TP/SL.

## 5. Migration / telemetry ihtiyaçları
- **Migration (1 additive kolon):** `notification_settings.notify_lifecycle BOOL DEFAULT false`
  (tracked migration + model alanı). (B) seçilirse `AlertType.SIGNAL` uygulaması + opsiyonel kolonlar.
- **Telemetry (ops.):** `/lifecycle/metrics` zaten transition'ları aggregate ediyor (read-only) →
  `lifecycle_alerts_sent` sayacı buraya additive eklenebilir (bildirim kalitesi takibi).
- Yeni tablo gerekmez (history zaten dedup ledger'ı).

## 6. Uygulama sırası & milestone planı (küçük commit'ler — onay sonrası)
- **P12-1:** migration — `notify_lifecycle` kolonu (default False) + NotificationSettings model alanı +
  schema/test. (Davranış değişmez; opt-in kapalı.)
- **P12-2:** `format_lifecycle_message` (telegram.py) + `notify_lifecycle()` service fn (notify_signal
  fan-out'unu aynalar: per-user SELECT + Pro+ gate + opt-in kolon + send; fail-open/never-raise) + birim test.
- **P12-3:** tracker hook — transition'ları döngüde topla, `db.commit()` SONRASI fire-and-forget fan-out;
  yalnız `{invalidating, approaching_tp}` + birth/suppressed/de-eskalasyon hariç. **Doğrulama:** detection
  byte-identical (regresyon/parity) + canlı smoke (transition'da bildirim 1:1, suppressed'da yok).
- **P12-4 (ops.):** frontend `notify_lifecycle` toggle + `/lifecycle/metrics` `lifecycle_alerts_sent` sayacı.

## 7. Öneri
P1.2 **veri-bağımsız + yüksek değer** (erken-uyarı = güven + ayrışma) ve tamamlanan P0.2 üzerine kurulur.
Detection FROZEN; P1.2 yalnız **fire-and-forget notify side-effect** ekler. **Önerilen ilk yapı:** (A)
global fan-out + `notify_lifecycle` opt-in kolonu + tetik seti `{invalidating, approaching_tp}` + Pro+
gate + once-per-transition + fail-open. İlk adım: **P12-1 (migration + model)**. Hedefleme (A vs B) ve
tetik setini onaylaman yeterli; ardından küçük commit'lerle başlarız.
