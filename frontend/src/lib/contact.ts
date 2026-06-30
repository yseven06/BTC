/**
 * Single source of truth for public support-contact channels (A2a).
 *
 * EMPTY until the operator's real contact info is set (B1 Legal v1.0). The project
 * does NOT assume a company will be formed — these are the individual operator's
 * (gerçek kişi / işletici) public channels. When set, fill the SAME values into the
 * legal künye (src/content/legal/tr/iletisim-kunye.md) so help page and künye never diverge.
 *
 * Empty string = "not yet published": the UI must NOT fabricate or show a placeholder
 * contact — it links users to the künye instead. Do not hardcode contact values
 * anywhere else; import from here.
 */
export const SUPPORT_EMAIL = ''; // e.g. 'destek@<resmi-domain>'
export const SUPPORT_TELEGRAM = ''; // e.g. '@<resmi-handle>' (without the t.me/ prefix)
export const KUNYE_PATH = '/yasal/iletisim-kunye';

export const hasSupportEmail = (): boolean => SUPPORT_EMAIL.trim().length > 0;
export const hasSupportTelegram = (): boolean => SUPPORT_TELEGRAM.trim().length > 0;
export const hasAnySupportChannel = (): boolean => hasSupportEmail() || hasSupportTelegram();

/** Telegram handle ('@x') -> full t.me URL; '' when unset. */
export const telegramUrl = (): string =>
  hasSupportTelegram() ? `https://t.me/${SUPPORT_TELEGRAM.replace(/^@/, '')}` : '';
