# Legal Paketi — Kapsam & Uygulama Planı (Madde 5)

**Durum:** Onaylandı (2026-06-29). Kod adımları aşağıdaki commit sırasıyla.
**⚠️ Hukuki not:** Bu belge mühendislik planıdır, hukuki danışmanlık değildir. Yasal
metinler **uluslararası best practice + SPK + KVKK + ETK + tüketici mevzuatına** göre
hazırlanır ve bu standartlara göre sürekli geliştirilir; her değişiklik için **"avukat
bekleniyor" varsayımı YAPILMAZ** (avukat nihai gözden geçirme şimdilik beklemede ve
opsiyoneldir, metin geliştirmenin önünde blokaj değildir). Şirket kuruluşundan önce
**yalnızca şirket bilgileri** doldurulur. Bağlayıcı ilkeler:
[PRODUCT-LEGAL-PRINCIPLES.md](./PRODUCT-LEGAL-PRINCIPLES.md).

İlgili: [CAPTCHA-STRATEGY.md](./CAPTCHA-STRATEGY.md) (§9 KVKK ifşası buraya bağlanır),
[production-readiness] sprint Madde 5.

---

## 0. Onaylanan kararlar
- **SPK konumlandırma (genel/bilgilendirme):** Ürün = **AI destekli analiz ve karar
  destek platformu**. Finansal veri, teknik analiz ve olasılıklar sunulur; **nihai
  yatırım kararı tamamen kullanıcıya aittir.** Kişiye özel yatırım danışmanlığı
  verilmez, yatırım tavsiyesi sunulmaz, geçmiş performans gelecekteki sonuçları
  garanti etmez. Metinler "eğitim sitesi" gibi küçümseyici değil, **profesyonel**;
  en koruyucu (defensif) dille; SPK/KVKK/ETK/tüketici + uluslararası best practice'e göre.
- **Pazarlama/ETK:** Beta'da **pazarlama iletisi YOK** — yalnız zorunlu sistem
  e-postaları (hesap, güvenlik, ödeme, fatura). ETK/İYS **altyapıya hazır ama pasif**
  (UI'da yer tutucu; İYS entegrasyonu sonraya). ETK aydınlatma dokümanı yine yazılır.
- **Dil:** Beta **yalnız Türkçe**; mimari çok-dile hazır (registry locale destekli),
  ileride profesyonel çeviriyle EN eklenir.
- **Şirket bilgileri:** Şimdilik **placeholder** (`[ŞİRKET UNVANI / MERSİS / vergi /
  adres / KEP]`); tüzel kişilik kurulunca doldurulacak. Mimari hazır (metinlerde yer
  tutucu, KVKK Aydınlatma'da zorunlu alanlar).
- **Yaş:** **18+** (18 yaşından küçükler Hizmet'i kullanamaz).
- **Abonelik modeli:** **1 / 3 / 6 / 12 ay** paketleri; kullanıcı iptal etmedikçe
  **aynı süreyle otomatik yenileme**; iptal **dönem sonunda** yürürlüğe girer; yenileme
  tarihi = dönem bitişi; ücret değişikliği önceden bildirilir. ⚠️ **Billing kod boşluğu:**
  mevcut checkout `mode="payment"` (tek seferlik) → **gerçek otomatik yenileme için Stripe
  `mode="subscription"` (recurring) yükseltmesi gerekir** (ayrı billing takip işi —
  `task_a410541a`; metinler hedeflenen modeli anlatıyor).
- **Açık onay / "gizli abonelik yok" ilkesi:** Otomatik yenileme yalnızca **checkout'ta açık
  onayla** geçerli (ToS §5.3). Checkout ekranı; otomatik yenileme, periyot (1/3/6/12 ay),
  **bir sonraki tahsilat tarihi** ve iptal yöntemini **açık/görünür** göstermeli ve açıkça
  kabul ettirmeli (uygulama: Madde **5i** checkout adımı). Gizli/fark edilmeyen abonelik yok.
- **"Platform işlem yapmaz" maddesi:** Risk Bildirimi §5 + Kullanım Koşulları §6'ya eklendi
  — Platform kullanıcı adına emir/işlem/portföy/hesap erişimi yapmaz; yalnız analiz/karar
  destek; kararlar kullanıcıya ait.
- **Gelecek: Auto-Trade (API otomatik işlem):** eklenirse **ayrı sözleşme + ayrı açık onay +
  ayrı risk bildirimi** gerektirir; mevcut metinler **yalnız bugünkü** davranışı kapsar
  (Risk §5 + ToS §6'da not edildi). [[production-readiness-sprint]]

## 1. Sayfa envanteri (`/yasal/<slug>`)
| Doküman | slug | Not |
|---|---|---|
| KVKK Aydınlatma Metni (Privacy) | `aydinlatma-metni` | KVKK başvuru bölümü içeride |
| KVKK Açık Rıza Metni | `acik-riza` | Ayrı metin; yalnız pazarlama/analitik için |
| Kullanım Koşulları (ToS) | `kullanim-kosullari` | Ana sözleşme |
| Çerez Politikası | `cerez-politikasi` | PostHog → banner şart |
| Risk Bildirimi / YTD | `risk-bildirimi` | SPK metni birebir; en kritik |
| Mesafeli Satış + Ön Bilgilendirme | `mesafeli-satis` | Ücretli → cayma hakkı + feragat |
| Ticari İleti (ETK) Aydınlatma | `ticari-ileti` | Yazılır; beta'da pasif |

**Ayrı kalmak zorunda:** Aydınlatma ≠ Açık Rıza ≠ ETK (KVKK 2018/90 + 2026/347).

## 2. Onay (consent) mimarisi — ispat edilebilir
**ToS = sözleşme** (consent değil) → kayıt için zorunlu meşru. Açık rıza/ETK özgür
irade → ToS'a gömülemez, ön-işaretsiz + opsiyonel.

**Kayıt — ayrı tik'ler:**
- Bloklayan: ① Kullanım Koşulları kabul ② Aydınlatma "okudum" ③ **Risk Bildirimi
  "okudum; yatırım tavsiyesi değildir, tüm işlemler kendi sorumluluğumda"** (ayrı tik)
- Opsiyonel, ön-işaretsiz: ④ Ticari ileti (ETK — beta'da pasif). Genel açık-rıza
  checkbox'ı **eklenmez** (çekirdek işleme = sözleşmenin ifası hukuki sebebi).

**ConsentLog (append-only):** `user_id · event_type · doc_slug · doc_version · 
content_hash(SHA-256) · locale · accepted_at(UTC) · ip · user_agent · source · 
checkbox_state`. Üzerine yazılmaz; geri çekme = yeni satır. Sürüm artışında yeniden
onay (MINOR/MAJOR → modal, PATCH → sessiz). Hash → tam olarak hangi metnin kabul
edildiğini kanıtlar.

## 3. Çerez banner ↔ analytics
Eşit ağırlıklı Kabul/Reddet + "Ayarları Yönet"; analitik **varsayılan KAPALI**.
Analitik ON → `setAnalyticsConsent(true)`, OFF → `false`. PostHog zaten
`opt_out_by_default:true` (Madde 2d) — uyumlu. Banner durumu ConsentLog'a yazılır.

## 4. İçerik mimarisi (kolay güncellenebilir)
- **Versiyonlu Markdown** `frontend/src/content/legal/tr/<slug>.md` + frontmatter
  (`version, effectiveDate, slug, locale`).
- **Build-time SHA-256** → `manifest.generated.json`; registry okur.
- **Tek dinamik route** `app/yasal/[slug]/page.tsx` + `/yasal` index (sürüm/yürürlük).
- Düzenleme = tek .md (kod değil), git-diff incelenebilir, hash consent log'a bağlı.
  (MDX gerekmez — yasal metinde JSX yok; markdown render yeterli.)

## 5. Site-geneli YTD disclaimer — tek kaynak
Tek sabit (`lib/legal/disclaimer.ts`) + tek `InvestmentDisclaimer` component
(`variant: footer | inline | backtest | checkout`). SPK metni birebir, tek yerde.
Yerleşim: footer (her sayfa), sinyal detayı, performans/backtest/strategy-lab, pricing.

## 6. Backend/şema
Yeni **ConsentLog** tablosu + `User`'a `terms_accepted_at, privacy_acked_at,
risk_acked_at, marketing_consent, legal_version`. Prod şema Supabase'de, `init_db`
yalnız DEBUG → bu değişiklik için **tek forward Alembic migration** (veya kontrollü
SQL). Admin audit-log ayrı kalır.

## 7. Commit sırası (küçük adımlar)
| Commit | Kapsam |
|---|---|
| 5a | İçerik altyapısı: Markdown registry + hash manifest + `/yasal/[slug]` + `/yasal` index (placeholder dokümanlar) |
| 5b | 7 yasal doküman taslağı (tr, profesyonel/defensif metin) |
| 5c | `InvestmentDisclaimer` (tek kaynak) + Footer + "Yasal" linkleri |
| 5d | Site-geneli disclaimer yerleşimi (sinyal/performans/backtest/pricing) |
| 5e | Çerez banner + `setAnalyticsConsent` + çerez politikası linki |
| 5f | Backend: ConsentLog tablosu + User consent alanları + migration |
| 5g | Register: ayrı checkbox'lar + payload + backend ConsentLog yazımı |
| 5h | Re-consent (sürüm karşılaştırma) modalı |
| 5i | Checkout: mesafeli satış ön-bilgilendirme + cayma-hakkı feragat tik'i + ConsentLog |

ETK/İYS opt-in akışı (pasif → aktif) ve EN çeviri **ertelenen** opsiyonel adımlar.
Her commit ayrı doğrulama + rapor. TM v2/scheduler/Signal Generator/BIST/veri
toplamaya dokunulmaz.

## 8. Açık kalan (işletme/mevzuat) noktalar
> Bu maddeler yukarıdaki çerçevelere göre **proaktif** ele alınır; "avukat bekleniyor" diye
> ertelenmez. Public yayın için **tek zorunlu blokaj: gerçek şirket bilgileri**.
- SPK yetkilendirme posizyonu nihai onayı (lansman öncesi hard gate).
- Veri sorumlusu tüzel kişilik + VERBİS kaydı gerekliliği.
- Yurt dışı aktarım mekanizması (Sentry/PostHog/Vercel/Supabase alt-işleyiciler).
- Abonelik otomatik yenileme → ek tüketici bildirim yükümlülükleri.
- Consent log yasal saklama süresi (finans bağlamı zamanaşımı).
