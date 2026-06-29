# KEY1-c Analiz Raporu — Backtest'i D2/D3 ile canlı geometriye hizalama

**Statü:** ANALİZ — uygulanmadı. Onay bekleniyor. Bu faz **backtest davranışını** (rapor
sayılarını) bilinçli değiştirir; **canlı sistem değişmez**.

## 0. Bağlam
KEY1-b1→b3 ile backtest + canlı tracker **tek `resolution_core.step_bar`** çözüm
geometrisini paylaşıyor (byte-identical kanıtlandı). Ancak ikisi hâlâ **giriş** ve
**süre-dolumu** semantiğinde ayrışıyor — bu, backtest'in canlı sistemi doğrulama (BP2
gate) yeteneğini geçersiz kılıyor. KEY1-c bunu giderir.

## 1. Mevcut davranış → Yeni davranış

| Boyut | CANLI (kanonik) | BACKTEST (mevcut) | KEY1-c sonrası BACKTEST |
|---|---|---|---|
| **Giriş (D2)** | Giriş-bölgesi ortası `(entry_zone_low+high)/2` | Sonraki bar **OPEN** (`next_open`) | Giriş-bölgesi ortası (= canlı) |
| **Seviyeler** | `signal.stop_loss/tp1/2/3` (kaydırılmamış) | `next_open` offset'iyle kaydırılmış (`+next_open−signal_close`) | Kaydırılmamış (= canlı) |
| **Süre dolumu (D3)** | Duvar-saati **48h SABİT** (`generated_at+48h`, tf-bağımsız) | `age ≥ max_age` **bar** (default 48 bar) | `max_age` = duvar-saati saat → bar: `round(48h / tf_saat)` |

**D3 sayısal:** 48h sabit → 1h: **48 bar (DEĞİŞMEZ)** · 4h: 48→**12 bar** · 15m: 48→**192 bar** · 1d: 48→**2 bar**. Yani **1h backtest'lerde D3 etkisizdir**; asıl etki diğer timeframe'lerde.

**Önemli not:** Backtest çözüm-geometrisi (SL/TP/scale-out/BE/intrabar) **DEĞİŞMEZ** —
o zaten step_bar (byte-identical). KEY1-c yalnız **hangi giriş/seviye/expiry-penceresi**
beslendiğini değiştirir.

## 2. Backtest metriklerinde beklenen değişimler

**D2 (next_open → bölge-ortası, kaydırılmamış seviyeler):**
- Backtest artık canlının **varsaydığı** girişi ölçer: fiyat bölge-ortasına çekilip
  limit-dolum olur varsayımı (canlı tracker da bunu varsayar — fiyatın bölgeye değip
  değmediğini doğrulamaz). Eski `next_open` = market-dolum varsayımı.
- R:R + TP-hit oranı **canlı değerlere** yaklaşır. (Canlı analitik: planlanan R:R TP1
  medyanı **0.60**, TP1-hit ~**%59** — backtest bu profile kayar.)
- Yön: long için bölge-ortası genelde `current_price`'ın hafif ALTINDA (≈ −0.25·ATR);
  `next_open`'a göre giriş/getiri/win-rate **değişir** (tek-yön garantisi yok, sembole bağlı).

**D3 (bar-sayısı → duvar-saati-ölçekli):**
- 1h: değişmez. 4h+: trade'ler **daha erken expire** → daha çok EXPIRED, daha az TP2/TP3,
  muhtemelen daha düşük win-rate. <1h: daha geç expire → daha çok TP-hit.
- Backtest endpoint default `timeframe="1h"` olduğundan **çoğu mevcut backtest 1h'de D3'ten
  etkilenmez**; çok-timeframe analizlerde etkilenir.

**Etkilenen rapor alanları:** win_rate, loss_rate, profit_factor, average_return, average_rr,
expectancy, sharpe/sortino, max_drawdown, total_trades, expired, equity_curve, trades_log
(entry_price/return_pct). **Bu bir regresyon DEĞİL, metodoloji düzeltmesidir** — yeni sayılar
canlının gerçek aynasıdır.

## 3. Kazanımlar ve riskler

**Kazanımlar:**
- **BP2 gate GEÇERLİ olur:** backtest artık canlı sistemi ölçtüğü için gelecekteki geometri
  değişiklikleri (BUG-2 min-TP1-floor vb.) tarihsel veride **doğrulanabilir**.
- CM v2 / Similarity / Adaptive / TP-SL kalibrasyonu için **sadık shadow-simülatör** (canlı
  geometriyi değiştirmeden "ne olurdu" testi).
- Tek, dürüst backtest sayısı (canlıyı yansıtan).

**Riskler:**
- **Backtest UI sayıları değişir** (Performans sayfası) — kullanıcıya "metodoloji düzeltmesi,
  regresyon değil" diye iletilmeli; eski ekran görüntüleriyle kıyas kafa karıştırabilir.
- **Bölge-ortası limit-dolum varsayımı iyimser** (fiyat bölgeye gerçekten değdi mi kontrol
  edilmez). Ama bu varsayımı **canlı da paylaşıyor** → gate amacı için doğru (canlının
  yaptığını ölçer). "Dolum gerçekçiliği" ayrı bir gelecek iyileştirme (hem canlı hem backtest'i
  etkiler, KEY1-c kapsamı dışı).
- Frontend kırılması yok; yalnız değerler farklı.

## 4. CM / Similarity / Lifecycle / Adaptive üzerindeki etki

- **DOĞRUDAN ETKİ: YOK.** Bu öğrenme katmanları **CANLI telemetriyi** (`SignalTradePath`,
  live tracker) tüketir; D2/D3 **backtest-only** (canlı dokunulmaz). Hiçbir veri/davranış
  değişmez.
- **DOLAYLI (olumlu):** backtest canlıyı yansıtınca, bu katmanlardaki gelecekteki
  değişiklikler için **geçerli doğrulama/shadow aracı** olur.

## 5. Rollback planı
- D2/D3 = yalnız `run_backtest` içinde **kod değişikliği** (giriş hesabı + max_age ölçekleme).
  **DB/veri/migration YOK, canlı dokunulmaz.** Backtest stateless (talep üzerine hesaplanır;
  saklanan backtest sonucu yok).
- **Rollback = ilgili KEY1-c commit'ini `git revert`** → anında, risksiz. Veri geri-alma yok.
- Opsiyon: eski `next_open`+bar-count davranışı **etiketli sensitivity-modu** olarak
  korunabilir (flag); kanonik default canlı-eşleşen olur. (Karar bekleniyor.)

## 6. Before/After doğrulama planı
1. **Aynı** backtest'i ESKİ vs YENİ ile koş — deterministik synthetic df + (mümkünse) gerçek
   sembol/endpoint, **çoklu timeframe**: 1h (D2'yi izole eder, D3=no-op) + 4h (D2+D3 birlikte).
2. **Before/After tablosu:** win_rate, loss_rate, profit_factor, max_drawdown, avg_return,
   expectancy, sharpe, sortino, total_trades, expired, avg_rr + trade-bazında entry/return diff.
3. **Canlı değişmedi kanıtı:** golden 8/8 + differential 8000/8000 + mapping 3000/3000 yeniden
   PASS (bunlar canlı yolu test eder; D2/D3 dokunmaz).
4. Before/After raporu sunulur → **onay alınmadan merge edilmez.** Beklenmeyen/açıklanamayan
   bir fark çıkarsa: oto-fix yok, neden+kapsam+etki + alternatifler raporlanır.

## 7. Uygulama notları (onay sonrası)
- D2: `run_backtest` aç-kodunda `next_open` + offset bloğu kaldırılır; `entry = (decision
  entry_zone_high + entry_zone_low)/2`, seviyeler kaydırılmamış. Lookahead-bias notu güncellenir
  (giriş artık sinyal-anı bölge-ortası, canlıyla aynı varsayım).
- D3: `max_age` param **duvar-saati saat** olarak yorumlanır (default 48h); `max_age_bars =
  round(max_age_saat / tf_saat)`. **API/Frontend kontrolü:** backtest UI `max_age` gönderiyorsa
  semantik "bar"→"saat" değişir (geriye-uyum kontrol edilecek).
- KEY1-c tek/küçük commit + before/after raporu; equivalence/golden testleri yeniden PASS.

## 8. UYGULAMA SONUCU (KEY1-c uygulandı + doğrulandı)
**Canlı regresyonsuz:** golden 8/8 + differential 8000/8000 + mapping 3000/3000 +
backtest-equivalence 9000/9000 (per-trade resolution DEĞİŞMEDİ) PASS.

**Before/After (synthetic 140-bar df, git-stash ile ESKİ b3b-2b vs YENİ KEY1-c):**

| Metrik | 1h ESKİ | 1h YENİ | 4h ESKİ | 4h YENİ |
|---|---|---|---|---|
| trades | 5 | 5 | 3 | **4** |
| expired | 0 | 0 | 0 | **2** |
| win_rate | 20.0 | **40.0** | 0.0 | **25.0** |
| pf | 0.08 | 0.21 | 0.0 | 0.38 |
| avg_ret | -1.04 | -0.81 | -2.0 | **-0.11** |
| max_dd | 1.65 | 1.54 | 1.65 | **0.34** |

- **1h = D2 izole** (D3 no-op): giriş orta-noktaya kaydı (115.81→115.23, 105.15→104.65 vb.) →
  hafif daha iyi girişler → win_rate/pf/avg_ret iyileşti; trade sayısı aynı (5). Bu, canlının
  varsaydığı orta-nokta limit-dolumudur.
- **4h = D2+D3:** D3 erken-expire (48 bar→12) → büyük kayıp kısaldı (−6.61→**−1.34**, age 19→12),
  0→**2 expired**; tek-pozisyon yuvası erken boşaldığı için trade seti **3→4** (overlap
  etkileşimi — analizde §2'de öngörüldü).
- **Tüm değişimler D2/D3 ile açıklanır; beklenmeyen anomali yok.** Sayılar bu sentetik örnekte
  iyileşti (veri-özel); asıl kazanım backtest'in artık canlıyı yansıtması.
