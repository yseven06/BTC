/**
 * SINGLE SOURCE OF TRUTH for the investment disclaimer shown across the app.
 *
 * Every surface (footer, signal detail, pricing, backtest, strategy lab, and any
 * future Auto Trade page) renders the <InvestmentDisclaimer /> component, which
 * reads ONLY from this file. Change the wording HERE and the whole application
 * updates automatically — never hard-code disclaimer text in a page.
 *
 * Tone: professional/corporate, legally strong but not alarmist. The message is
 * consistent everywhere: AI analysis & decision-support platform · content is not
 * investment advice · the decision is entirely the user's · the Platform does not
 * trade on the user's behalf.
 *
 * The authoritative long-form text is the Risk Bildirimi legal page
 * (/yasal/risk-bildirimi); these UI strings must stay aligned with it.
 */

/** Canonical link to the full Risk Bildirimi legal document. */
export const DISCLAIMER_LINK = '/yasal/risk-bildirimi';

/** One-sentence summary — footer and compact placements. */
export const DISCLAIMER_SHORT =
  'TradeMinds AI, yapay zekâ destekli bir analiz ve karar destek platformudur. ' +
  'Sunulan içerikler genel niteliktedir ve yatırım tavsiyesi değildir; yatırım ' +
  'kararları tamamen size aittir ve Platform sizin adınıza işlem gerçekleştirmez.';

/** Full paragraph — inline placements on signal/decision surfaces. */
export const DISCLAIMER_FULL =
  'TradeMinds AI, yapay zekâ destekli bir analiz ve karar destek platformudur. ' +
  'Burada yer alan analiz, sinyal ve değerlendirmeler genel niteliktedir ve ' +
  'yatırım danışmanlığı/yatırım tavsiyesi kapsamında değildir. Nihai yatırım kararı ' +
  'tamamen size aittir; Platform sizin adınıza emir iletmez, işlem yapmaz veya ' +
  'portföy yönetmez. Geçmiş performans gelecekteki sonuçları garanti etmez.';

/** Appended on backtest / performance / simulated-result surfaces. */
export const DISCLAIMER_BACKTEST_EXTRA =
  'Backtest ve simülasyon sonuçları tamamen varsayımsaldır; gerçek işlem ' +
  'sonuçlarını temsil etmez ve garanti etmez.';
