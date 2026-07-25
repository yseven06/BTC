/**
 * Single source of truth for the product brand (rebrand CP · 2026-07-25).
 *
 * Kullanım ilkesi:
 *  - Kullanıcıya görünen her yüzey (UI, metadata, legal, e-posta metni): BRAND_NAME.
 *  - Kompakt teknik/PascalCase bağlam (UA string'i, config etiketi):      BRAND_COMPACT.
 *  - Slug/lowercase teknik kullanım (dosya adları, host):                 BRAND_SLUG.
 *
 * Yasal not: bu MARKA adıdır; kayıtlı şirket/unvan bilgisi DEĞİLDİR. İşletici
 * kimliği tek-kaynak olarak lib/contact.ts + legal künye üzerinden yönetilir.
 */
export const BRAND_NAME = 'Zate Trade';
export const BRAND_COMPACT = 'ZateTrade';
export const BRAND_SLUG = 'zatetrade';
export const BRAND_DOMAIN = 'zatetrade.com';
export const SITE_URL = 'https://zatetrade.com';
