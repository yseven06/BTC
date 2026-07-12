// CP-7 · Tek Sayı Sözlüğü (Design Constitution §4/§6): "aktif sinyal" tanımı
// TEK YERDE — bu modülde — yaşar; her kullanıcı-yüzeyi aynı sayıyı söyler.
//
// KANONİK TANIM: aktif sinyal = canlı (outcome=active) VE actionable (AL/SAT;
// HOLD/BEKLE hariç). Sinyal Merkezi'nin default görünümüyle birebir — dashboard
// SC'den fazla tür gösteremez (süperset kuralı, Constitution §7). HOLD'un nihai
// görünürlük yeri K-E/CP-8 kararıdır; bu modül yalnız SAYIM tanımını kilitler.
//
// Kullanım:
//  - Liste çeken yüzeyler: fetchActiveSignals({ ...ACTIVE_SIGNAL_PARAMS, ... })
//  - Yalnız toplam gereken yüzeyler: fetchActionableActiveTotal()
//  - Landing proof route'u (app/api/landing/proof/route.ts) server-side kendi
//    fetch'inde AYNI parametreyi kullanır ve bu modüle atıf verir (client api
//    katmanını import edemez — tanım-eşitliği yorum-atfıyla bağlıdır).
//  - perf.active_count / history-stats.active_count HOLD içerir (şişkin okunur);
//    kullanıcı-yüzeyi sayaçlarında KULLANILMAZ (admin operatör-görünümü hariç).
import { fetchActiveSignals } from '@/lib/api';

export const ACTIVE_SIGNAL_PARAMS = { only_actionable: true } as const;

/** Kanonik "aktif sinyal" toplamı — tek sayı sözlüğünün sayaç-yüzü. */
export async function fetchActionableActiveTotal(): Promise<number> {
  const res = await fetchActiveSignals({ ...ACTIVE_SIGNAL_PARAMS, page_size: 1 });
  return res.total;
}
