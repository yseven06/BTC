# Stripe S7 — Live E2E Runbook (A3)

S1–S6 kodu tamam ([billing.py](../backend/app/api/routes/billing.py)). **S7 = gerçek anahtarlarla
uçtan-uca doğrulama.** Çalıştırması senin Stripe **test** anahtarlarını gerektirir. Mock free-upgrade
kodda kapalı (A3: `_mock_activation_allowed` = yalnız `DEBUG && ENVIRONMENT=='development'`).

## 0. Ön koşullar (anahtarlar — senin)
| Env (backend) | Değer |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_...` (Dashboard → Developers → API keys) |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` (webhook endpoint **veya** `stripe listen` çıktısı) |
| `STRIPE_PUBLISHABLE_KEY` | `pk_test_...` |
| `FRONTEND_BASE_URL` | success/cancel URL tabanı (`/settings?upgraded=1`, `/pricing?canceled=1`) |
- **Webhook endpoint:** `https://<api-domain>/api/v1/billing/webhooks/stripe` (Dashboard'da kaydet) **veya**
  local: `stripe listen --forward-to http://localhost:8000/api/v1/billing/webhooks/stripe`.
- `stripe` paketi prod image'de pinli ([requirements.txt](../backend/requirements.txt) `stripe==15.3.0`) —
  lazy import (yoksa 500). **NOT:** SDK bump (15→17+) **A1 değil**, S7 ile birlikte (API-version/obj kayması canlı doğrulanır).
- Test kartları: **4242 4242 4242 4242** (başarı) · **4000 0000 0000 0341** (decline) · **4000 0000 0000 9995** (yetersiz bakiye).

## 1. Mock-gate doğrulama (anahtarsız — ÖNCE)
- Boş `STRIPE_SECRET_KEY` + **non-dev** ortam → `POST /api/v1/billing/checkout` **503** (mock YOK).
- Yalnız `DEBUG=true` + `ENVIRONMENT=development` → mock (yerel UI testi). (A3 gate-matrix testi: `tests/test_a3_mock_gate.py`.)

## 2. Canlı E2E senaryoları (test anahtarlarıyla)
1. **Checkout → ACTIVE:** `stripe listen` aç; UI'dan "Yükselt" → Checkout → 4242 ile öde.
   - `session.mock=false`; `checkout.session.completed` → abonelik **ACTIVE** + doğru tier/cycle;
     `invoice.paid` → `Payment(method='stripe')`; `GET /billing/subscription` tier'ı yansıtır.
2. **Idempotency:** `stripe events resend <evt_id>` → ikinci çağrı `{status:duplicate}`, **çift Payment YOK**
   (StripeEvent PK; [billing.py:505-508]).
3. **Cancel:** `POST /billing/cancel` → gerçek `stripe.Subscription.modify(cancel_at_period_end=True)`;
   `subscription.updated` webhook `cancel_at_period_end=true` senkron; `subscription.deleted` → tier **FREE**.
4. **Payment-failed:** `4000...0341` ile fail → `invoice.payment_failed` → abonelik **PAST_DUE**.
5. **Re-buy guard:** aynı tier+cycle ACTIVE iken `POST /billing/checkout` → **409**.
6. **Public:** `GET /billing/plans` → 200 (auth'suz).

## 3. Prod yayın öncesi (S7 sonrası)
- `ENVIRONMENT=production` + `DEBUG=false` (validator zorlar) → mock erişilemez.
- `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` prod'da set; webhook endpoint prod URL'iyle kayıtlı; **prod
  webhook secret** ile imza doğrulanır.
- Boş key ile prod → checkout **503** (tasarım; sessiz free-upgrade YOK).
- Smoke: [SMOKE-TEST.md](./SMOKE-TEST.md) item-7 + post-deploy 65-67; rollback: [RELEASE-RUNBOOK.md](./RELEASE-RUNBOOK.md).

> S7 = **kullanıcıya bağlı (B2)**: Stripe test/prod anahtarları + webhook kaydı sağlanınca yukarıdaki
> 2. adım çalıştırılır. Sertleştirme (A3) anahtarsız tamamlandı.
