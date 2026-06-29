# Trade-Path Telemetry (SignalTradePath)

**Amaç:** Her çözülen sinyal için, geriye dönük analiz + Coin Memory + Similarity +
Adaptive Learning'in kullanacağı **zengin, immutable, policy-bağımsız** bir kayıt.
Tümü çözülmüş bir işlemin **gözlemlenmiş gerçekleri**dir — outcome/seviye/çözümü
ASLA değiştirmez (saf observability). Yazım fail-open'dır: telemetri hatası işlem
çözümünü bloklayamaz.

Tek-kaynak: tüm satırlar `app/backtesting/trade_path.py :: compute_trade_path` ile
üretilir (canlı tracker + ileride backtest/shadow aynı fonksiyonu çağırır).

## Versiyonlama
- **`schema_version`** (kolon): satır METRİK TANIMI çağı. Bir kolonun ANLAMI değişince
  artar (eski satırlar karışmaz). Şu an `1`.
- **`extra.telemetry_version`**: `extra` JSON sözleşme sürümü. Yalnız mevcut bir
  key'in ANLAMI değişince artar; yeni key eklemek artırmaz (tüketici eksik key'i
  `None` saymalı). Şu an `1`.
- **`source`**: `live` | `backtest` | `shadow` — satırın nereden üretildiği.

## Kolonlar (özet)
**🟢 Policy-bağımsız path (geometri değişse de geçerli):** `mfe_pct`, `mae_pct`,
`mfe_r`, `mae_r` (risk-R birimi), `mfe_atr`, `mae_atr` (ATR birimi), `bars_total`,
`mfe_bar_idx`, `mae_bar_idx`, `sl_dist_pct`, `atr_pct_at_signal`.
**🟢 Bağlam (koşullu-edge analizi):** `gen_utc_hour`, `weekday`, `volatility_ratio`,
`session`, `volatility_bucket`, `regime`.
**Kendine-yeten fiyatlar:** `entry_price`, `sl_price`, `tp1/2/3_price`.
**🟡 Policy-koşullu (mevcut geometriye bağlı — değişince yeniden türet):**
`cur_reached_tp1/2/3`, `cur_bars_to_tp1`, `cur_post_tp1_mae_r`, `cur_post_tp1_mfe_r`,
`cur_gave_back_after_tp1`, `cur_realized_return`.
**🔶 Belirsizlik/güven:** `intrabar_ambiguous`, `sl_before_tp` (null=bilinmiyor),
`still_forming_resolution`.

## `extra` JSON anahtarları (zengin telemetri — bu commit)
Hepsi mevcut primitiflerden TÜRETİLİR (yeni veri toplamaz) veya çözüm anında
ucuza gözlenir. Tüketici: **CM**=Coin Memory, **SIM**=Similarity, **ADP**=Adaptive.

| Key | Anlam | Kullanım |
|---|---|---|
| `telemetry_version` | extra sözleşme sürümü | hepsi |
| `planned_rr_tp1/2/3` | planlanan ödül:risk (her TP) = (tp−entry)/(entry−sl) | R:R kalite denetimi, BUG-2 floor kalibrasyonu (KEY2) |
| `tp1/2/3_dist_pct` | her TP'nin entry'ye uzaklığı (% ) | CM, SIM |
| `tp1/2/3_dist_atr`, `sl_dist_atr` | aynı uzaklıklar ATR biriminde (normalize) | SIM (ANN feature), ADP |
| `entry_zone_width_pct` | giriş bölgesi genişliği (% entry) | SIM, slippage analizi |
| `mfe_to_tp1` | mfe_pct / tp1_dist_pct (≥1 → fiyat TP1 mesafesine ulaştı) | "TP1 çok uzak/yakın mı" |
| `mae_to_sl` | mae_pct / sl_dist_pct (≥1 → fiyat SL mesafesine ulaştı) | "SL çok dar mı" |
| `captured_tp1_potential` | MFE, TP1 mesafesini yakaladı mı (bool) | CM, ADP |
| `final_return_pct` | gerçekleşen getiri (realized_return aynası) | hepsi |
| `gave_back_pct` | tepe-MFE'nin kapanışta geri verilen kısmı = max(0, mfe−realized) | "kâr geri verme" |
| `time_to_mfe_bars` / `time_to_mae_bars` | MFE/MAE bar indeksi | zamanlama analizi |
| `bars_to_tp1` | TP1'e kaç bar | TP-erişim süresi (task #15) |
| `resolution_source` | `bar_walk` \| `live_sl` \| `expiry` | güven ağırlığı, BUG-9/11 izleme |
| `sl_before_tp` | SL herhangi bir TP'den ÖNCE mi vuruldu (null=belirsiz) | doğru kazanç atfı |
| `tp_touched_but_sl_won` | aynı-bar belirsizliğinde TP değdi ama SL kazandı (konservatif) | BUG-10 sıklık ölçümü |
| `gave_back_after_tp1` | TP1 sonrası TP2 ıskalandı mı | scale-out kalitesi |

### Rezerve gelecek slotları (extensible — şema değişmeden doldurulacak)
- **`extra.birth`** (şu an `None`): doğum-anı geometri provenansı — `atr_used`,
  `atr_fallback_used` (BUG-1 izleme), `sr_override_tp1/sl` (BUG-2 popülasyonu),
  `nearest_support/resistance`. (Sonraki telemetri dalgası; `SignalSnapshot` zengin
  bağlamı zaten saklıyor — engine_scores/regime_data/mtf_trends/vol/sentiment.)
- **`extra.shadow`** (şu an `None`): alternatif-geometri **shadow-policy** sonuçları
  (Adaptive Learning v2 — canlı geometriyi değiştirmeden "ne olurdu" karşılaştırması).

## Tasarım değişmezleri
1. Saf gözlem — outcome/seviye/çözüm değişmez.
2. Fail-open — telemetri hatası çözümü bloklamaz (tracker try/except sarar).
3. Extensible — bilinmeyen `None`; yeni key şema değişmeden eklenir; `birth`/`shadow`
   sonraki dalgaları önceden ayırır → **gelecekte büyük refactor yok**.
4. Performans — ek I/O yok; her şey tracker'ın çözüm anında zaten elindeki
   primitiflerden hesaplanır.
