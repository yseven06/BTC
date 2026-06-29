# CAPTCHA / Bot Koruması — Mimari Karar Kaydı (ADR)

**Durum:** Onaylandı (2026-06-29). **UYGULANDI (2026-06-29):** `backend/app/challenge.py`
(tek-kaynak adaptif `require_challenge` dependency) + `frontend/src/lib/challenge.ts`
(apiFetch 428 akışı); login/register/google-login/checkout'a bağlandı. **Env-gated/no-op**
(Turnstile anahtarları kullanıcı tarafından sağlanır). Bu belge tasarım/karar kaydıdır.

İlgili katman: [Rate Limiting](../backend/app/rate_limit.py) (Madde 4, tamam).
Gizlilik ifşası: [Legal/KVKK paketi](./) (Madde 5) bu belgenin §9'unu kullanacak.

---

## 1. Onaylanan kararlar (özet)
1. **Sağlayıcı: Cloudflare Turnstile** — ücretsiz/sınırsız, görsel-puzzle'sız, KVKK-dostu.
2. **Adaptif iki-eşikli model:** tek per-IP sayaç, üç bant — `<SOFT` izin, `SOFT–HARD` challenge, `≥HARD` 429. Normal kullanıcı hiçbir şey görmez.
3. **`refresh` endpoint'i challenge dışında** (arka planda sessiz çağrılır; yalnız rate-limit).
4. **Fail-open/fail-closed ayrımı:** login → fail-open ama rate-limit'li; signup + checkout → fail-closed.
5. **Privacy/KVKK metinlerine baştan işlenir** (Cloudflare/Turnstile ifşası — §9).
6. **(EK) Admin + güvenilir internal hesaplar için challenge bypass** — §8.

**İlke:** Sentry/PostHog/rate-limit gibi **env-gated / no-op** — anahtar yoksa widget render olmaz, backend doğrulamayı atlar; dev'de sıfır friction. Turnstile **tek katman değildir**: rate limiting + credential-stuffing koruması bağımsız kalır.

---

## 2. Neden Turnstile (alternatiflere karşı)
- **vs reCAPTCHA v3:** Google çapraz-site reklam profili → AB'de yükleme öncesi açık rıza baskısı. Turnstile çapraz-site takip/reklam yapmaz → bu rıza yükü yok.
- **vs hCaptcha:** hCaptcha çözüm verisini ML eğitiminde kullanır + görsel puzzle. Turnstile minimal oturum verisi, varsayılan puzzle yok.
- **Maliyet/UX:** efektif sınırsız ücretsiz; çoğu meşru kullanıcı için görünmez. Küçük Türk SaaS için en düşük-friction seçenek.

---

## 3. Adaptif model — tek sayaç, üç bant
Mevcut slowapi sayacımız (per-IP, leftmost X-Forwarded-For) hem rate-limit hem challenge kararını sürer.

```
istek → client IP (mevcut client_ip_key)
       → sayac = penceredeki deneme (+ auth-fail sayacı)

  sayac < SOFT          → İZİN VER                       (token gerekmez; mutlu yol)
  SOFT ≤ sayac < HARD   → CHALLENGE BANDI:
        bypass? (admin rol / internal secret — §8) → izin
        geçerli chal_ok cookie?                    → izin
        istekte geçerli Turnstile token?           → siteverify (1×) → chal_ok bas → izin
        aksi halde                                 → 428 challenge_required (widget göster, tekrar dene)
  sayac ≥ HARD          → 429 hard block + Retry-After   (MEVCUT handler — DEĞİŞMEZ)
```

**Kritik kurallar:**
- Challenge geçmek **hard sayacı sıfırlamaz** (bir kez çözen sınırsız bütçe kazanmasın).
- **A3 auth-failure** sayaç eşiğinden bağımsız challenge'ı tetikler (credential-stuffing düşük hızlıdır).
- `428` (challenge) ile `429` (hard) **ayrı** → frontend net dallanır; mevcut 429 handler'a dokunulmaz.

---

## 4. Tetikleme sinyalleri (kolaylık/değer)
| Sıra | Sinyal | Değer | Efor | Not |
|---|---|---|---|---|
| A1 | Soft eşiğe yaklaşma | Yüksek | Çok düşük | Mevcut sayaç; belkemiği |
| A2 | Velocity | Yüksek | Çok düşük | Aynı sayaç, dar pencere |
| A3 | Tekrarlı auth-failure (IP/email) | **Çok yüksek** | Düşük | **İlk inşa edilecek ek** |
| B1 | IP reputation | Yüksek | CF arkasındaysa ücretsiz | Turnstile içsel kullanır |
| B2 | Yeni IP/cihaz | Orta-Yüksek | Orta | Per-user geçmiş (sonra) |
| B3 | Coğrafi anomali | Orta | CF varsa düşük | B2'ye bağlı (sonra) |

İnşa sırası: A1 → A3 → B1 → B2/B3. Paralı reputation/geo feed'leri atla.

---

## 5. Widget modu + sinyal + token taşıma
- **Mod:** Managed/Invisible, `language: auto` (fallback `tr`). Auth + checkout formlarında **herkese sessizce** render; meşru kullanıcının çoğu görmeden geçer.
- **Backend→Frontend sinyali:** `428 Precondition Required` + `{ "error": "challenge_required", "challenge": "turnstile", "sitekey": "<public>" }`. Pre-flight probe **yok** (her isteğe round-trip eklemez).
- **Token taşıma:** HTTP header `cf-turnstile-response`, `apiFetch`'te **tek noktadan**. 5 pydantic şeması (UserCreate/UserLogin/GoogleLoginRequest/RefreshTokenRequest/CheckoutRequest) **değişmez**.

---

## 6. Clearance durumu (tekrar-challenge önleme)
- Turnstile token'ı **tek-kullanımlık, 300 sn**. siteverify **bir kez** (`idempotency_key` ile), `success` + `hostname` + `action` doğrulanır.
- Sonra **kendi imzalı cookie'miz**: `chal_ok`, HttpOnly, IP-bağlı, HMAC (mevcut JWT secret), **TTL ≈10 dk**. Geçerli `chal_ok` varsa yeniden challenge yok.
- Cookie stateless → tek-replica restart'a dayanıklı. (Uygulama Cloudflare arkasına alınırsa CF **pre-clearance** `cf_clearance` cookie'sine geçilebilir.)

---

## 7. Bağlanacağı endpoint'ler
| Endpoint | Rate-limit | Challenge | Not |
|---|---|---|---|
| `POST /auth/login` | ✅ | ✅ | fail-open (rate-limit'li) |
| `POST /auth/register` | ✅ | ✅ | fail-closed |
| `POST /auth/google-login` | ✅ | ✅ | |
| `POST /auth/refresh` | ✅ | ❌ | arka plan; challenge çözecek kullanıcı yok |
| `POST /billing/checkout` | ✅ | ✅ | fail-closed; authenticated → admin rol bypass uygun |
| `POST /auth/change-password` | (sonra) | (sonra) | authenticated; ileride aday |

---

## 8. Admin / internal challenge bypass (EK — yönetim/geliştirme kolaylığı)
**Amaç:** admin ve güvenilir internal/otomasyon çağrılarını challenge'tan muaf tutmak — **normal kullanıcı güvenliğini etkilemeden.** İki mekanizma, çağıran tipine göre:

### (A) Rol-bazlı bypass — *authenticated* endpoint'ler
- **Kapsam:** checkout, (ileride) change-password — yani geçerli JWT taşıyan akışlar. **login/register/google-login HARİÇ** (pre-auth, JWT yok).
- **Kural:** istekte geçerli JWT var ve `user.role ∈ {admin, super_admin}` ise challenge bandı atlanır.
- **Neden güvenli:** geçerli admin oturumu gerektirir; anonim saldırganda yoktur. Sızacak sır yok.

### (B) Güvenilir-internal secret header — *tüm* challenge endpoint'leri (login/register dahil)
- **Mekanizma:** `X-Internal-Challenge-Bypass: <secret>` header'ı, `CHALLENGE_BYPASS_SECRET` env'i ile **constant-time** karşılaştırılır.
- **Kimler için:** internal servisler, CI/E2E otomasyonu, login/register'a programatik vuran admin araçları.
- **Env-gated:** secret boşsa mekanizma **kapalı** (bypass imkânsız). **Asla `NEXT_PUBLIC_*` değil**, asla tarayıcı koduna girmez.
- **Sertleştirme:** güçlü rastgele (≥32 byte), periyodik rotasyon, constant-time compare, **her kullanımda WARN log** (endpoint + IP), opsiyonel IP allowlist (aşağıdaki uyarıyla).

### Normal kullanıcı güvenliğini koruyan kısıtlar (kritik)
- **Bypass yalnız CHALLENGE'ı atlar, HARD rate-limit'i ATLAMAZ** — bypass'lı çağrı da `≥HARD`'da 429 yer (defense-in-depth). Internal otomasyon gerçekten daha yüksek throughput istiyorsa secret yoluna **ayrı, daha yüksek limit** verilir (sınırsız değil).
- **Public frontend'den erişilemez** — site key / secret key ayrımı sayesinde tarayıcı bypass sırrını asla tutmaz; gerçek kullanıcı için **tek yol adaptif akıştır.**
- **Audit:** her bypass (rol veya secret) hesap verebilirlik için loglanır.
- **Sızıntı kontrolü:** secret sızsa bile saldırgan hâlâ rate-limit + auth-failure lockout'a takılır → bypass ≠ tam ele geçirme. Şüphede rotate et.
- **IP-allowlist uyarısı:** rate-limit key'imiz **spoof'lanabilir leftmost X-Forwarded-For** okur; bir IP allowlist bunu **kullanmamalı** (saldırgan XFF'i forge edip "bypass IP'siyim" diyebilir). IP allowlist yalnız **proxy-doğrulamalı** IP ile (ör. Cloudflare `CF-Connecting-IP` / Railway-trusted) güvenlidir — aksi halde sadece secret header tercih edilir.

### İnteraktif admin login notu
Widget invisible/managed olduğundan, normal tarayıcıdan giriş yapan admin zaten **sessizce** geçer — insan admin login UX'i için ayrı bypass gerekmez. (B) headless/otomasyon için, (A) authenticated kolaylık için.

---

## 9. Gizlilik / KVKK — Madde 5 için ifşa checklist'i
Turnstile şu sinyalleri işler: **IP, TLS parmak izi, User-Agent, sitekey, origin + davranışsal sinyaller** (IP dahil → KVKK'da kişisel veri). Privacy/KVKK metnine:
- Toplanan sinyaller (yukarıdaki liste).
- Challenge sırasında **zorunlu/strictly-necessary işlevsel cookie** set edilebilir; **reklam/takip cookie'si yok** → çoğu durumda **opt-in rıza gerektirmez** (avantaj).
- Cloudflare'in **çift rolü:** bizim için **veri işleyen** + kendi algoritmasını geliştirmek için **veri sorumlusu** (meşru menfaat).
- Amaç: bot/suistimal/dolandırıcılık önleme (KVKK m.5 meşru menfaat).
- **Yurt dışına aktarım** (Cloudflare ABD/global edge) + aktarım mekanizması.
- Cloudflare Turnstile gizlilik politikası linki + DPA/iletişim noktası.

---

## 10. Erişilebilirlik + Conversion
- **Conversion:** Managed (adaptif) + `language: auto` → meşru kullanıcıların çoğu sessizce geçer; Türkçe otomatik.
- **Erişilebilirlik:** Turnstile'ın **sesli/alternatif yolu yok**; challenge-loop'ları VPN/ekran-okuyucu kullanıcılarını kilitleyebilir → widget yanında **erişilebilir kaçış yolu** (destek/alternatif doğrulama linki) + net Türkçe hata mesajı şart. (Cloudflare 2026 başı redesign WCAG 2.2 AAA hedefliyor, ama kaçış yolu yine gerekli.)

---

## 11. Tehdit modeli
- **Durdurur (ucuza):** commodity botlar, naif scripted signup, temel credential-stuffing/form spam (pasif IP/TLS/UA parmak izi).
- **Durdurmaz:** solver servisleri (2Captcha/CapMonster…) tüm türleri saniyeler içinde çözer. → Turnstile **hacmi** azaltır; rate-limit + auth-fail lockout **blast-radius'u** sınırlar. Birlikte gerekir.

---

## 12. Env değişkenleri (gated/no-op)
**Backend:**
```
TURNSTILE_SECRET_KEY=            # boş = doğrulama atlanır (no-op)
CHALLENGE_ENABLED=true
CHALLENGE_LOGIN_SOFT=6/minute    # hard limit RATE_LIMIT_LOGIN'in altında
CHALLENGE_AUTH_FAIL_THRESHOLD=3
CHALLENGE_CLEARANCE_TTL=600      # chal_ok cookie ömrü (sn)
CHALLENGE_BYPASS_SECRET=         # boş = internal bypass kapalı (§8B)
CHALLENGE_BYPASS_IPS=            # opsiyonel; yalnız proxy-doğrulamalı IP ile (§8 uyarı)
```
**Frontend:**
```
NEXT_PUBLIC_TURNSTILE_SITE_KEY=  # boş = widget render olmaz
```
**Dev/CI:** Cloudflare test anahtarları (always-pass `1x…AA` / secret `1x…AA`); veya hepsini boş bırak → tam no-op.

---

## 13. Uygulama sırası (Legal'den SONRA)
1. **A3 auth-failure sayacı** (login/google-login'de 401'de `INCR`, başarıda temizle) — Turnstile'sız bile en yüksek değer.
2. **Soft eşik bandı** (mevcut sayaca ikinci, düşük limit).
3. **Backend `app/challenge.py`** dependency (env-gated): IP → soft/auth-fail kontrol → bypass (§8) → `chal_ok` cookie veya siteverify → `428`.
4. **Frontend** invisible widget (auth + pricing) + `apiFetch` header + `428` → interaktif widget akışı + erişilebilir kaçış yolu.
5. (Sonra) B2/B3 yeni-IP/cihaz geçmişi.

---

## 14. Storage / ölçekleme notu
Tüm sayaçlar (rate-limit + soft + auth-fail) tek-replica + `--workers 1` olduğundan **in-memory tutarlı**. Yatay ölçeklemede bu sayaçlar **Upstash Redis**'e taşınır (`UPSTASH_REDIS_URL` config'te mevcut). İmzalı `chal_ok` cookie **stateless** → taşınmaz.
