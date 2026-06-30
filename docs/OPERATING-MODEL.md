# İşletim Modeli — Gerçek Kişi / Bireysel İşletici (Kanonik Karar)

**Tarih:** 2026-06-30 · **Statü:** BAĞLAYICI PROJE KARARI. Diğer tüm dokümanlar buna hizalanır.

## 0. Karar
Proje, **bir şirket (tüzel kişilik) kurulacağı varsayımına DAYANMAZ.** Hizmet sağlayıcı, **gerçek
kişi / bireysel işletici** modeliyle çalışır. "Şirket kurulunca doldurulacak / şirket bilgileri
bekleniyor" gibi varsayımlar **geçersizdir** ve dokümantasyondan kaldırılmıştır.

> ⚖️ **Hukuki sınır:** Bu doküman hukuki tavsiye DEĞİLDİR ve hangi yasal yükümlülüğün uygulanacağını
> KESİNLEŞTİRMEZ. Ticari faaliyet yürüten gerçek kişinin **vergi mükellefiyeti / kayıt türü** (serbest
> meslek, şahıs işletmesi/esnaf vb.) ve buna bağlı yükümlülükler (MERSİS, KEP, VERBİS) **işleticinin
> hukuki kararına** bağlıdır → ilgili maddeler "**hukuki karar gerektirir**" olarak işaretlenmiştir.

## 1. Şirket-bağımlı maddelerin sınıflandırması
Her madde: **(M)** gerçekten zorunlu mu · **(Ş-suz)** şirket olmadan yapılabilir mi · **(GK)** gerçek
kişi modelinde nasıl · **(Aksiyon)** kaldır / yeniden-yaz / hukuki-karar.

| # | Madde | M? | Ş-suz? | Gerçek kişi (GK) modeli | Aksiyon |
|---|---|---|---|---|---|
| 1 | **Hizmet sağlayıcı kimliği** (ETK 6563 künye) | Evet (ticari faaliyet) | Evet | İşleticinin **ad/işletme adı** + iletişim | **YENİDEN-YAZ** → gerçek kişi (yapıldı) |
| 2 | **Ticaret unvanı** | Koşullu | Evet | Gerçek kişi adı **veya** kayıtlı şahıs-işletmesi adı | **YENİDEN-YAZ** (unvan→ad/işletme adı) |
| 3 | **MERSİS** | Hayır (genel) | Evet | Yalnız **ticaret siciline kayıtlı** işletici için; çoğu gerçek kişide **uygulanmaz** | **HUKUKİ KARAR** ("varsa / uygulanmaz") |
| 4 | **KEP adresi** | Hayır (genel) | Evet | Tüzel kişilere zorunlu; gerçek kişide genelde **opsiyonel** | **HUKUKİ KARAR** ("varsa") |
| 5 | **Vergi dairesi / vergi no** | Evet (ticari gelir) | Evet | İşleticinin **vergi kimlik bilgileri** (T.C./vergi no, mükellefiyete göre) | **YENİDEN-YAZ** → vergi kimlik bilgileri |
| 6 | **Açık adres** | Evet | Evet | İşleticinin **resmî/iletişim adresi** | **YENİDEN-YAZ** (gerçek kişi adresi) |
| 7 | **Resmî iletişim** (destek/KVKK/tüketici e-posta) | Evet | Evet | İşleticinin **gerçek e-posta/telefon** kanalları (tek-kaynak `lib/contact.ts`) | **YENİDEN-YAZ** (yapıldı, A2a) |
| 8 | **VERBİS kaydı** | Koşullu | Evet | İşleticinin KVKK statüsüne göre; küçük işleticiler için **istisna olabilir** | **HUKUKİ KARAR** |
| 9 | **Yurt-dışı aktarım mekanizması** (KVKK m.9) | Evet (PII varsa) | Evet | İşletici, sözleşme/güvence ile veya açık rıza ile | **HUKUKİ KARAR** (sözleşmeler netleşince) |
| 10 | **Ödeme / merchant-of-record** (Stripe) | Evet (ücretli plan) | **Evet** | Stripe **bireysel hesap** destekler; hesap sahibi = işletici (gerçek kişi) | **YENİDEN-YAZ** (B2) |
| 11 | **Mesafeli satış — satıcı bilgisi** | Evet | Evet | Satıcı = işletici (gerçek kişi); ad+vergi+adres+iletişim | **YENİDEN-YAZ** (yapıldı) |
| 12 | **Devir/birleşme klozu** (Kullanım Koşulları) | Hayır | — | Geçerli kalır (işletici ileride devir/kuruluş YAPARSA kapsar; varsayım değil) | **KORUNDU** (varsayım değil) |

## 2. Beta için gerçek gereksinim (şirket DEĞİL)
Beta yayını için gereken = **operatör (gerçek kişi) bilgileri ve faaliyet gösterilecek ülkeye göre
gerekli hukuki/vergisel bilgiler** — kimlik + iletişim + vergi mükellefiyeti + (hukuki karar
gerektiren) MERSİS/KEP/VERBİS/aktarım değerlendirmesi. **Şirket gerektirmez ≠ hiçbir hukuki bilgi
gerekmez:** gereklilikler **faaliyet ülkesine göre değişir**. **"Şirket kurulması" bir önkoşul DEĞİLDİR.**

## 3. Hâlâ hukuki karar gerektiren (işletici/danışman kararı)
MERSİS (kayıt türü) · KEP (zorunluluk) · VERBİS (istisna/eşik) · yurt-dışı aktarım mekanizması ·
vergi mükellefiyet türü · mesafeli-satış/tüketici yükümlülüklerinin gerçek-kişi kapsamı. Bunlar
metinlerde **placeholder + "hukuki karar gerektirir"** olarak işaretlidir; otomatik varsayım YOK.

## 4. İlgili dokümanlar
Legal metinleri (8 TR doküman, gerçek-kişi reframe yapıldı, version bump YOK → re-consent yok) ·
[PRODUCT-LEGAL-PRINCIPLES.md](./PRODUCT-LEGAL-PRINCIPLES.md) · [LEGAL-PACKAGE-PLAN.md](./LEGAL-PACKAGE-PLAN.md)
· [BETA-READINESS-PLAN.md](./BETA-READINESS-PLAN.md) · [PHASE2-ROADMAP.md](./PHASE2-ROADMAP.md) ·
[ROADMAP-REASSESSMENT-2026-06.md](./ROADMAP-REASSESSMENT-2026-06.md) · [STRIPE-S7-RUNBOOK.md](./STRIPE-S7-RUNBOOK.md).
