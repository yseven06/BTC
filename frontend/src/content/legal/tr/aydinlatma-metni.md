---
slug: aydinlatma-metni
title: KVKK Aydınlatma Metni
version: 0.9.2
effectiveDate: 2026-06-29
locale: tr
---

# KVKK Aydınlatma Metni

> 6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") m.10 kapsamında
> hazırlanmıştır. Bu metin bir **bilgilendirmedir**; açık rıza gerektiren işlemeler için
> ayrıca [Açık Rıza Metni](/yasal/acik-riza) sunulur.
> _Metin yürürlüğe hazır taslaktır; nihai hukuki inceleme tamamlanmak üzeredir._

## 1. Veri Sorumlusu

Kişisel verileriniz, veri sorumlusu sıfatıyla TradeMinds AI ("**Platform**") tarafından
işlenir.

> _[Şirket tüzel kişiliği kurulduğunda; ticaret unvanı, MERSİS numarası, vergi dairesi ve
> numarası, açık adres ile resmî iletişim (KEP/e-posta/telefon) bilgileri burada yer
> alacaktır. Gerekirse VERBİS kaydı bilgisi eklenecektir.]_

## 2. İşlenen Kişisel Veriler

| Kategori | Veriler |
|---|---|
| Kimlik | Ad-soyad (sağlanmışsa) |
| İletişim | E-posta adresi |
| Müşteri İşlem | Abonelik/plan, ödeme durumu, talep ve kayıtlar |
| İşlem Güvenliği | IP adresi, cihaz/tarayıcı bilgisi, oturum ve log kayıtları |
| Pazarlama | Tercihler ve onay durumu (yalnızca onay verildiyse) |
| Görsel | Profil görseli (yüklediyseniz) |

Hassas (özel nitelikli) kişisel veri işlenmesi amaçlanmamaktadır.

## 3. İşleme Amaçları

- Üyelik oluşturulması ve hesabın yönetilmesi,
- Hizmet'in (analiz ve karar destek) sunulması ve iyileştirilmesi,
- Abonelik ve ödeme süreçlerinin yürütülmesi,
- Bilgi ve güvenlik yükümlülüklerinin yerine getirilmesi, kötüye kullanımın önlenmesi,
- Yasal yükümlülüklerin (vergi, ticari kayıt vb.) yerine getirilmesi,
- Talep ve şikâyetlerin yönetilmesi,
- (Yalnızca açık rıza ile) ürün analitiği ve ticari elektronik ileti gönderimi.

## 4. İşlemenin Hukuki Sebepleri (KVKK m.5)

- **Sözleşmenin kurulması/ifası:** hesap, abonelik, ödeme ve Hizmet'in sunulması.
- **Hukuki yükümlülük:** mali/ticari kayıt ve mevzuattan doğan saklama yükümlülükleri.
- **Meşru menfaat:** güvenlik, dolandırıcılık/kötüye kullanım önleme, hizmet iyileştirme
  (ilgili kişinin hak ve özgürlüklerine zarar vermemek kaydıyla).
- **Açık rıza:** yalnızca başka bir hukuki sebebe dayanmayan işlemeler (isteğe bağlı ürün
  analitiği ve ticari elektronik ileti).

## 5. Toplama Yöntemi

Kişisel verileriniz; kayıt ve form alanları, Hizmet'i kullanımınız sırasında otomatik
yollarla (çerezler ve sunucu/uygulama kayıtları) ve ödeme süreçleri aracılığıyla
elektronik ortamda toplanır.

## 6. Aktarım ve Alıcı Grupları (Yurt İçi / Yurt Dışı)

Hizmet'in sunulabilmesi için kişisel verileriniz, yetkili kıldığımız **alt işleyici** ve
hizmet sağlayıcılarla paylaşılabilir. Bunların bir kısmı yurt dışında bulunabilir ve bu
durumda aktarım **KVKK'nın yurt dışına aktarım hükümleri** çerçevesinde gerçekleştirilir:

- **Barındırma / altyapı / veritabanı:** (ör. Supabase, Vercel, Railway),
- **Hata izleme ve ürün analitiği:** (ör. Sentry; PostHog — yalnızca onayla),
- **Ödeme:** ödeme/abonelik hizmet sağlayıcısı (ör. Stripe),
- **Bot/kötüye kullanım koruması:** Cloudflare Turnstile (adaptif doğrulama),
- **Piyasa veri sağlayıcıları:** Binance, MEXC, Yahoo Finance, CoinGecko, TradingView
  (kural olarak kişisel veri içermeyen piyasa verileri).

**Bot/kötüye kullanım koruması (Cloudflare Turnstile):** Giriş, kayıt ve ödeme gibi
işlemlerde bot/otomasyon tespiti amacıyla Cloudflare Turnstile kullanılabilir. Bu kapsamda
IP adresi, TLS/cihaz parmak izi, tarayıcı (User-Agent) bilgisi ve davranışsal sinyaller
işlenir ve veriler Cloudflare'in yurt dışı altyapısına aktarılır. İşleme amacı bot/dolandırıcılık
önleme olup KVKK m.5/1(f) **meşru menfaat** hukuki sebebine dayanır; reklam veya çapraz-site
takip yapılmaz.

Ayrıca yasal yükümlülük hâlinde yetkili kamu kurum ve kuruluşlarına aktarım yapılabilir.

> _[Aktif alt işleyici listesi ve her biri için aktarım mekanizması (yeterlilik kararı /
> standart sözleşme / taahhütname / istisna) tüzel kişilik ve sözleşmeler netleştiğinde
> kesinleştirilecektir.]_

## 7. Saklama Süresi

Kişisel verileriniz, işleme amacının gerektirdiği süre ve ilgili mevzuatta öngörülen
zamanaşımı/saklama süreleri boyunca saklanır; sürenin sonunda silinir, yok edilir veya
anonim hâle getirilir. Örnek olarak: hesap ve üyelik verileri üyelik süresince ve sona
ermesinden itibaren ilgili zamanaşımı süresince; mali/ödeme kayıtları vergi ve ticaret
mevzuatı uyarınca asgari 10 yıl; log ve işlem güvenliği kayıtları ilgili mevzuatta öngörülen
süre boyunca; açık rızaya dayalı işlemeler ise rıza geri alınana kadar saklanır.

## 8. İlgili Kişinin Hakları (KVKK m.11)

Kişisel verileriniz bakımından; işlenip işlenmediğini öğrenme, bilgi talep etme, işlenme
amacını ve amaca uygun kullanılıp kullanılmadığını öğrenme, yurt içi/yurt dışı aktarılan
üçüncü kişileri bilme, eksik/yanlış işlenmişse düzeltilmesini, şartları oluştuğunda
silinmesini/yok edilmesini ve bunların aktarıldığı üçüncü kişilere bildirilmesini isteme,
münhasıran otomatik analizle aleyhinize bir sonucun ortaya çıkmasına itiraz etme ve
kanuna aykırı işleme nedeniyle zararın giderilmesini talep etme haklarına sahipsiniz.

## 9. Başvuru Yöntemi

Haklarınızı kullanmak için taleplerinizi, kimliğinizi tevsik eden bilgilerle birlikte
Platform'un resmî iletişim/başvuru kanalları üzerinden iletebilirsiniz. Başvurularınız,
talebin niteliğine göre en kısa sürede ve her hâlde en geç **otuz (30) gün** içinde ücretsiz
olarak sonuçlandırılır; işlemin ayrıca bir maliyet gerektirmesi hâlinde Kurul'ca belirlenen
tarifedeki ücret alınabilir. Başvurunuzun reddi hâlinde, Kişisel Verileri Koruma Kurulu'na
şikâyette bulunma hakkınız saklıdır.

> _[Başvuru için resmî e-posta/KEP adresi ve varsa başvuru formu bağlantısı tüzel kişilik
> kurulduğunda eklenecektir.]_
