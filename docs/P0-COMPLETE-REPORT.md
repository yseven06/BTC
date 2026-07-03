# P0 Sprint — Complete Report

**Tarih:** 2026-07-03 · **Statü:** P0-1 → P0-6 **TAMAMLANDI** (kod tarafı) · **Branch:** main
**Standart:** [Design Bible v1.1](design/DESIGN-BIBLE-v1.1.md) + [Visual Language v1.1](design/VISUAL-LANGUAGE-v1.1.md) (LOCKED)
**Disiplin:** her madde analiz → kapsam → uygulama → before/after → canlı doğrulama → regresyon (tsc 0 hata) → izole commit.

> Amaç: davet-usulü beta öncesi **dürüstlük + profesyonellik + hukuki hijyen** boşluklarını kapatmak. AI motoruna (BP2) dokunulmadı; değişiklikler UI/copy/legal/flag düzeyinde.

---

## 1 · P0-1 → P0-6 Özetleri

### P0-1 — Dashboard sahte verilerini kaldır · `f30a786`
Sabit piyasa delta'ları (`-6.12% / +0.35% / -0.42%`) + `Math.random`+sinüs ile tek noktadan uydurulmuş sentetik market-cap grafiği (`buildMarketCapChart`/`MarketCapPoint`) kaldırıldı. Gerçek market-cap %, hacim, dominance ve altındaki gerçek TradingView grafiği korundu.

### P0-2 — Dev/debug mesajlarını kullanıcı diline çevir · `7bc199e`
Kullanıcıya gösterilen 3 dev talimatı temizlendi: signals + performance "Backend çalışmıyor. **BAŞLAT.bat**…" → "Sunucuya şu an ulaşılamıyor. Lütfen birazdan tekrar deneyin."; macro "**FRED_API_KEY** ortam değişkenini ayarla…" → "ABD makro verileri şu an kullanılamıyor."

### P0-3 — Beta'da ödeme hunisini kapat · `f1a1a1e`
Tek-kaynak `PAYMENTS_ENABLED` flag'i (default `false`). pricing: beta banner + plan CTA "Yakında"/disabled + `subscribe()` no-op (checkout + waiver-consent hiç çalışmaz) + "ödeme USD" dipnotu gizli. Yükselt CTA'ları gizlendi: dashboard, signals, Sidebar (free), LockedOverlay. Planlar bilgilendirici olarak görünür kalır.

### P0-4/A — Beta legal temizliği · `b825a73`
"…taslaktır; nihai hukuki inceleme…" ibaresi **8 belgeden** kaldırıldı. MERSİS → "Uygulanmaz — bireysel işletici (tüzel kişi değil)". Mesafeli-satış + tüketici-satış kanalı beta-pasifleştirme notuyla işaretlendi ("ödeme etkinleştiğinde uygulanır"). `npm run legal:gen` ile generated yeniden üretildi. **B-grubu** (ad/adres/vergi/e-posta/KEP kimlik alanları) `[doldurulacak]` olarak korundu — açılışta gerçek veriyle doldurulacak.

### P0-5 — Dashboard sekme/error-state/disclaimer · `af62e84`
İşlevsiz "Genel/Kripto/Hisse/Forex" sekmeleri + `marketTab` state kaldırıldı. `dataError` error-state: signals+perf birlikte reddedilince yanıltıcı sıfır yerine "Veriler yüklenemiyor + Tekrar dene" kartı. `InvestmentDisclaimer` dashboard üstüne eklendi.

### P0-6 — Beta kimliği + over-claim temizliği · `22d4824`
"BETA" rozeti: Sidebar (app-geneli) + landing + register. Register beta notu ("Erken erişim beta sürümü…"). Landing STEPS "97 Varlığı" (fabrike) → "Kripto & BIST'i Canlı İzle". Over-claim: H1 "kanıtlanmış"→"doğrulanabilir"; "Institutional/Kurumsal" 4 yerde (layout OG, ShareCard, performance rozeti, signals altyazı) temizlendi.

---

## 2 · Etkilenen Dosyalar

| P0 | Dosyalar |
|---|---|
| P0-1 | `dashboard/page.tsx` · `lib/api.ts` |
| P0-2 | `signals/page.tsx` · `performance/page.tsx` · `macro/page.tsx` |
| P0-3 | **`lib/config.ts` (yeni)** · `pricing/page.tsx` · `dashboard/page.tsx` · `signals/page.tsx` · `layout/Sidebar.tsx` · `ui/LockedOverlay.tsx` |
| P0-4/A | `content/legal/tr/*.md` (8) · `lib/legal/generated/{meta,bodies}.ts` |
| P0-5 | `dashboard/page.tsx` |
| P0-6 | `page.tsx` · `layout.tsx` · `ui/ShareCardModal.tsx` · `performance/page.tsx` · `signals/page.tsx` · `register/page.tsx` · `layout/Sidebar.tsx` |

**Toplam benzersiz dosya:** ~19 (frontend UI/legal/config). **Backend: 0 dosya** (AI engine dokunulmadı).

---

## 3 · Commit Listesi (main, kronolojik)

```
22d4824  feat(ui):      P0-6  beta kimligi + kayit notu + birim + over-claim temizligi
af62e84  fix(dashboard): P0-5  islevsiz sekmeleri kaldir + error-state + risk disclaimer
b825a73  docs(legal):    P0-4/A beta legal temizligi (taslak/uygulanmaz/satis pasif)
f1a1a1e  feat(billing):  P0-3  beta'da odeme hunisini kapat (PAYMENTS_ENABLED)
7bc199e  fix(ui):        P0-2  dev/debug mesajlarini kullanici diline cevir
f30a786  fix(ui):        P0-1  dashboard sahte verileri kaldir
```

---

## 4 · Öncesi / Sonrası

| Alan | Öncesi | Sonrası |
|---|---|---|
| Piyasa delta'ları | Sabit `-6.12%` vb. canlıymış gibi | Kaldırıldı; yalnız gerçek değerler |
| Market-cap grafiği | Sentetik (Math.random) | Kaldırıldı; gerçek TradingView grafiği kaldı |
| Backend-down mesajı | "BAŞLAT.bat çift tıkla" | "Sunucuya şu an ulaşılamıyor…" |
| FRED uyarısı | "FRED_API_KEY ayarla…" | "ABD makro verileri şu an kullanılamıyor" |
| Ödeme hunisi | ~8 Yükselt CTA + canlı checkout + consent | Flag ile kapalı; pricing "Yakında"; consent toplanmıyor |
| Legal metinler | "taslaktır" + MERSİS placeholder | Taslak yok; MERSİS "uygulanmaz"; satış beta-pasif |
| Dashboard sekmeleri | İşlevsiz Genel/Kripto/Hisse/Forex | Kaldırıldı |
| Backend hatası (dashboard) | Yanıltıcı "0 sinyal / %0" | "Veriler yüklenemiyor + Tekrar dene" |
| Risk disclaimer (dashboard) | Yok | Üstte görünür |
| Beta kimliği | Yok | "BETA" rozeti (Sidebar+landing+register) |
| Landing H1 | "kanıtlanmış sinyaller" | "doğrulanabilir sinyaller" |
| "Institutional/Kurumsal" | 4 yerde over-claim | Temizlendi |

**Regresyon:** her adımda `tsc --noEmit` **0 hata**; canlı tarayıcı doğrulaması **konsol 0 hata**; happy-path'ler sağlam.

---

## 5 · Açık Kalan Maddeler

**Bu sprint kapsamında bilinçli ertelenenler:**
- **P0-4/B — gerçek işletici bilgileri** (ad · adres · destek e-postası · vergi statüsü · yurt-dışı aktarım) → açılıştan hemen önce gerçek veriyle **tek seferde** doldurulacak (`lib/contact.ts` + künye `[doldurulacak]`). *Kullanıcı kararı: geçici placeholder üretilmedi.*
- **Error-state canlı tetikleme** — backend çalışır durumda olduğundan `dataError` dalı (P0-5) ve BAŞLAT.bat error branch'i (P0-2) canlı tetiklenemedi; statik (tsc+kod) doğrulandı.

**P1'e devredilenler (Design Bible'da zaten P1):**
- "Son Kazanan Sinyaller" win-wall (cherry-pick) → hero/landing redesign (kart-restyle gerekir).
- signals `'Tarama başlatılamadı: ' + msg` ham exception → hata-hijyeni.
- ScoreRing etiketi, kart/badge birleştirme, mobil tablo→kart, a11y fonksiyonel bug'lar, tasarım-sistemi tek-kaynak (token/tailwind-merge/next-font).

**Beta yayını için dış bağımlılıklar (kod-dışı, P0 kapsamı değil):**
- B1 gerçek işletici bilgisi (yukarıdaki P0-4/B) · B2 Stripe anahtarları (ödeme açılınca) · B3 Turnstile + prod-env + deploy.

---

## 6 · P1'e Hazır mıyız?

**Evet — P1 *geliştirmesi* için hazır.**
- P0'ın beta-dürüstlük/hijyen temeli **kod tarafında tamam**; AI motoru (BP2) hiç değişmedi → Phase-2 sinyal-kalitesi çalışmaları güvenle başlayabilir.
- Design Standards v1.1 kilitli; P1 işleri bu standarda göre ilerleyecek.

**Ancak — herkese açık *yayın* için hazır değiliz:** P0-4/B (gerçek işletici legal bilgisi) + dış bağımlılıklar (Turnstile/prod-env/deploy; ödeme açılırsa Stripe) tamamlanmadan public launch yapılmaz. Bunlar **P1 geliştirmesini bloke etmez** (davet-usulü beta ve iç geliştirme sürebilir).

**Öneri:** P1'e Design Bible §07 P1 sırasıyla (tasarım-sistemi tek-kaynak → hero premium → mobil/a11y) veya Phase-2 roadmap önceliğiyle (sinyal kalitesi) başlanabilir; hangisini önce istersen onunla ilerleriz.
