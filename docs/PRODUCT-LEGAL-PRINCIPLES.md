# Ürün / Legal / Security Prensipleri (BAĞLAYICI)

Bu belge **kalıcı ve bağlayıcı** ürün konumlandırma, hukuki ve güvenlik prensiplerini
tanımlar. Tüm yeni özellik, sayfa, metin ve pazarlama içeriği bu prensiplere uymak
zorundadır. Yaklaşım: **global / regülasyon odaklı, en savunmacı.** Ürün hiçbir koşulda
"yatırım danışmanlığı / kişiye özel tavsiye / otomatik işlem / portföy yönetimi" olarak
konumlanmaz.

İlgili: [LEGAL-PACKAGE-PLAN.md](./LEGAL-PACKAGE-PLAN.md), [SECURITY.md](./SECURITY.md),
[SMOKE-TEST.md](./SMOKE-TEST.md). Tek-kaynak disclaimer: `frontend/src/lib/legal/disclaimer.ts`.

> Kabul tarihi: 2026-06-29. Avukat onayı public yayından önce alınacak (şimdilik beklemede);
> bu prensipler o ana kadar da bağlayıcıdır.

---

## Prensipler

1. **Konumlandırma.** Platform yalnızca "**AI destekli genel analiz ve karar destek aracı**"
   olarak konumlanır. Pazarlama, UI metni, hukuki metin ve dış iletişimde bu çerçeve korunur.

2. **Yapılmayanlar (kesin sınır).** Kişiye özel yatırım danışmanlığı YOK · uygunluk/yerindelik
   analizi YOK · emir iletimi YOK · otomatik işlem (auto-trade) YOK · portföy yönetimi YOK.
   (Gelecekteki Auto Trade yalnızca ayrı sözleşme + ayrı risk onayıyla; o zamana dek "yakında"
   çerçevesi dışında sunuluyormuş gibi konumlandırılmaz.)

3. **Sorumluluk.** Tüm karar ve sorumluluk kullanıcıya aittir.

4. **Üçlü mesaj (her kritik yüzeyde BİRLİKTE).** "Yatırım tavsiyesi değildir" TEK BAŞINA
   yeterli sayılmaz. Her kritik karar/analiz yüzeyinde şu üç mesaj birlikte bulunur:
   - (a) Genel bilgilendirme/analiz amaçlıdır,
   - (b) Nihai karar **ve risk** kullanıcıya aittir,
   - (c) Platform kullanıcı adına işlem yapmaz, emir iletmez, portföy yönetmez.

   Uygulama: tek kaynak `disclaimer.ts` (`DISCLAIMER_SHORT`/`DISCLAIMER_FULL` üçünü de taşır)
   → `InvestmentDisclaimer` bileşeni. Kritik yüzeyler (signal detail, signals, signal-history,
   symbol-analysis, pricing, backtest, performance, strategy-lab, landing karar bölümleri,
   gelecekteki Auto Trade) gövde-içi (inline/backtest/warning) disclaimer taşır; footer tek
   başına yeterli sayılmaz.

5. **Şirket bilgileri.** Public yayına kadar placeholder. Yayından önce gerçek **unvan,
   MERSİS, vergi no, adres, KEP, resmi iletişim** ile doldurulur.

6. **Hukuki metin sürümü.** Metinler **v0.9** kalır; public yayın öncesi avukat onayı +
   şirket bilgileri ile **v1.0**'a yükseltilir.

7. **KVKK ayrımı.** Aydınlatma Metni, Açık Rıza ve Çerez onayları **ayrı** tutulur
   (`aydinlatma-metni`, `acik-riza`, `cerez-politikasi`).

8. **Ön-işaretli onay yok.** Açık rıza / çerez / pazarlama onayları **ön-işaretli olmaz**
   (default kapalı; analitik çerez varsayılan kapalı). Zorunlu legal kutular da ön-işaretsizdir;
   kullanıcı işaretlemeden ilerleyemez.

9. **Otomatik yenileme.** Yalnızca **checkout ekranında açıkça gösterilip** ayrı ve
   ön-işaretsiz bir onay kutusuyla **ayrıca kabul edilirse** geçerlidir. Periyot, sonraki
   tahsilat tarihi, ücret, iptal/cayma tek bakışta görünür; kritik bilgi tooltip/küçük
   punto/gizli olmaz.

10. **Yanıltıcı içerik yok.** Sahte kullanıcı yorumu, sahte kullanıcı sayısı, sahte/garanti
    başarı oranı, "kesin kazanç" veya garanti algısı yaratan dil **kullanılmaz**. Tüm metrikler
    doğrulanabilir ve yalnızca gerçek, kapanmış sinyallerden hesaplanır.

---

## Uyum durumu (denetim: 2026-06-29)

Kod tabanı 10 prensibe karşı 7-boyutlu adversarial workflow denetiminden geçti.

| Boyut | Durum |
|---|---|
| Tek-kaynak disclaimer üçlü mesaj (4) | ✅ uygun (`disclaimer.ts`) |
| Disclaimer yerleşimi her kritik yüzeyde (4) | ✅ **düzeltildi** — signal-history/signals/symbol-analysis'e inline eklendi ([`d226a18`](https://github.com/yseven06/BTC/commit/d226a18)) |
| Ön-işaretli onay yok (8) | ✅ uygun (kayıt/çerez/re-consent/checkout default kapalı) |
| Otomatik yenileme açık + ayrı onay (9) | ✅ uygun (checkout 2 ayrı ön-işaretsiz kutu) |
| Yanıltıcı pazarlama yok (10) | ✅ uygun (metrikler gerçek-veri-gated) |
| Konumlandırma dili (1,2,3) | ✅ uygun ("karar destek"; "TP seviyesi") |
| Hukuki metin / KVKK (5,6,7) | ✅ uygun (placeholder, v0.9.0, KVKK ayrı belgeler) |

**Public yayın kapısı (gate):** (a) şirket placeholder'ları → gerçek bilgi; (b) avukat onayı;
(c) hukuki metinler v0.9 → v1.0; (d) [SMOKE-TEST.md](./SMOKE-TEST.md) deploy-sonrası checklist.

## Yeni iş geliştirirken (uyum kuralları)
- Her yeni karar/analiz yüzeyine **tek-kaynak `InvestmentDisclaimer`** koy (uygun variant);
  disclaimer metnini asla sayfada hard-code etme.
- Disclaimer metnini değiştirmek gerekirse **yalnızca `disclaimer.ts`**'de değiştir (her yere yayılır)
  ve Risk Bildirimi (`/yasal/risk-bildirimi`) ile hizalı tut.
- Hiçbir consent/çerez/pazarlama kutusunu ön-işaretli yapma.
- Otomatik yenileme/abonelik akışında kritik bilgiyi açıkça göster + ayrı onay al.
- Pazarlama/UI metninde garanti/kesin kazanç/sahte sosyal kanıt kullanma; yalnızca doğrulanabilir ifade.
- Konumlandırmada "danışmanlık/tavsiye/senin yerine işlem/portföy yönetimi" çağrışımı yapma.
