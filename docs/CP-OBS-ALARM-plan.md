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
