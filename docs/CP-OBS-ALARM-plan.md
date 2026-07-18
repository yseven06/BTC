# CP-OBS-ALARM — Liveness/Heartbeat Alarm Planı

**Tarih:** 2026-07-18 · **Statü:** plan + B-parçası (read-only checker) uygulandı
**Gerekçe:** `docs/CP-OBS-HEARTBEAT-report.md` — 26 günde 5 kesinti (4'ü çoklu-saat 4.5–7.8s + 96dk lock), hiçbiri fark edilmemiş; **canlı liveness sinyali yok.** Bu seri o boşluğu kapatır — sinyal davranışına dokunmadan.

## Ölçüm ilkesi
- **Birincil nabız:** `signal_status_history.created_at` (tracker her ~2dk pass'te yazar; HEARTBEAT: normal cadence median 0.75dk / p99 10dk; gerçek kesintiler ≥96dk → temiz ayrışma).
- **Bütün-sistem bayatlığı = üç akışın EN TAZESİNİN bayatlığı** (`min` staleness): `status_history` · `signals.generated_at` · `signal_snapshots.created_at`. **Bir akış bile taze ise sistem OK** — tek-akış-quiet (kripto 7/24, sessiz pass) yanlış-pozitif yapmasın; ancak ÜÇÜ birden susarsa = scheduler down.
- Duplicate/overlap: şu an 0 (single-flight sağlam) → ucuz yan-kontrol.

## Eşikler (kripto 7/24 → piyasa-saati gating GEREKMEZ)
- **OK: ≤ 20 dk** · **WARNING: > 20 dk** · **CRITICAL: > 45 dk** (5 gerçek kesintinin hepsi ≥96dk → 45dk beşini de yakalar, ~sıfır false-positive; normal p99 10dk).

## Ayrı-proses ilkesi (kritik)
Checker izlediği şeyden **AYRI-PROSES** olmalı — app'in APScheduler'ına job olarak KONMAZ (scheduler ölürse in-app check de ölür). Doğru yer = OS-seviyesi zamanlayıcı (Windows Task / cron), app scheduler'ına dokunmadan. **Bu (B) parçası hiçbir zamanlayıcı KURMAZ** — durumsuz script, elle veya (C'de) OS-task ile koşar.

## Checkpoint yapısı
- **A · plan/doc** (bu dosya).
- **B · read-only checker** (`backend/scripts/cp_obs_alarm_check.py`): durumsuz, 3-akış bayatlığı → OK/WARNING/CRITICAL + exit-code (0/1/2) + tek parse-edilebilir satır. **Push/OS-task/dış-servis YOK.** ← *uygulanan parça*.
- **C · minimal push + OS-schedule** (ayrı onay): CRITICAL'te bağımsız Telegram/webhook POST (env-kredensiyel) + Windows Task/cron kaydı. Bu CP'de YAPILMAZ.

## Kesin kırmızı çizgiler (B)
Read-only (SELECT + rollback, yazma yok) · scheduler/signal-generation/model/gate/scoring/frontend/migration/runtime davranışına dokunma · app scheduler'ına job yok · OS-task/cron/supervisor yok · Telegram/webhook/email/dış-servis yok · yeni tablo/migration yok · yeni dependency yok · private staging yok. Yalnız sessiz-durmayı GÖRÜNÜR kılar; sinyal kararını etkilemez.

---

## CP-OBS-ALARM-C — dead-man's-switch ping (UYGULANDI, script içine)

**Tasarım:** `scripts/cp_obs_alarm_check.py` verdict **OK** olduğunda `CP_OBS_ALARM_PING_URL`'e (env'den) **stdlib `urllib` GET pingi** atar. WARNING/CRITICAL/ERROR → **ping atmaz.** Ping DURUNCA (app-down · **makine-kapalı** · checker hiç koşmuyor) dış cron-monitor **grace penceresi sonrası alarm verir** → HEARTBEAT'te kanıtlanan makine-kapalı/gece kesinti modunu, yerel push'un asla yakalayamayacağı bu modu, **kapatır.**

**Sözleşme:**
- **Secret yalnız env** (`CP_OBS_ALARM_PING_URL`); kodda URL yok; loglarda **maskeli** (`scheme://host/xxxx***`).
- **PING_URL yoksa:** crash YOK → console-only, verdict üretmeye devam, `ping=disabled_no_env` basar.
- **Ping başarısızsa:** DB/verdict bozulmaz; `ping=failed(<Reason>)` basar; **liveness exit-code DEĞİŞMEZ** (başarısız ping = kaçan ping = monitor zaten alarm verir). Timeout kısa (5 sn).
- **Yeni dependency yok** (stdlib); yeni tablo/migration yok; app/scheduler/signal'e sıfır dokunuş; outbound-only (açık port yok).
- **Exit-code:** OK=0 · WARNING=1 · CRITICAL=2 · ERROR=3 (B'den korunur).

**OS-level scheduling (yalnız MANUEL kurulum — bu repo KURMAZ):**
Bu repo yalnız checker + ping desteği sağlar; OS-seviyesi zamanlama **kullanıcı/ops tarafından** ayrıca kurulur. Önerilen aralık **15 dk**. Cron-monitor **grace > 15 dk** (ör. 30-45 dk) olmalı ki tek kaçan ping/kısa WARNING false-alarm yapmasın.

- **Windows Task Scheduler (yerel), tek seferlik:**
  ```
  schtasks /Create /SC MINUTE /MO 15 /TN "CP-OBS-ALARM" /TR ^
    "C:\Users\Wolrider\Desktop\BTC\backend\venv\Scripts\python.exe C:\Users\Wolrider\Desktop\BTC\backend\scripts\cp_obs_alarm_check.py" ^
    /ST 00:00
  ```
  (Task'ın "Start in" / çalışma dizini `...\BTC\backend` olmalı — PYTHONPATH ve `.env` için.)
- **cron (gelecekteki private staging), tek seferlik:**
  ```
  */15 * * * * cd /path/BTC/backend && ./venv/bin/python scripts/cp_obs_alarm_check.py
  ```

**Notlar:**
- App down olsa bile OS-task çalışıyorsa ping devam eder → dış servis sessiz kalır (sistem OK). Makine kapanırsa ping kesilir → dead-man's-switch alarm verir.
- Dış servis seçimi (healthchecks.io / cronitor / betterstack) ve PING_URL **env üzerinden**; repo bağımsızdır.
- **Private staging** gelince aynı checker cron ile taşınır (değişiklik yok).
- **C'de YAPILMAYAN (bilinçli):** Telegram/webhook/email kodu · OS-task otomatik kurulumu · frontend/panel · WARNING-bildirimi (yalnız OK-ping / not-OK-sessizlik).
