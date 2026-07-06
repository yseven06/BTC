'use client';

import { useState } from 'react';
import Link from 'next/link';

/**
 * Pre-payment confirmation. Shows ALL critical subscription info clearly and
 * readably (no tooltips, no fine print) right before the pay button: package,
 * billing period, amount, next auto-renewal date, how to cancel, that it
 * auto-renews unless canceled, and the withdrawal right + its exception. The
 * user must tick two separate consents before "Ödemeye Geç" enables.
 */
export function CheckoutConfirmModal({
  planName,
  cycleLabel,
  months,
  amountUsd,
  nextRenewalStr,
  processing,
  onConfirm,
  onClose,
}: {
  planName: string;
  cycleLabel: string;
  months: number;
  amountUsd: number;
  nextRenewalStr: string;
  processing: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptWaiver, setAcceptWaiver] = useState(false);
  const canConfirm = acceptTerms && acceptWaiver && !processing;

  const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <span className="text-text-muted">{label}</span>
      <span className="text-right font-medium text-text-primary">{value}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-e-0/60 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-panel glass-e3-overlay p-5">
        <h2 className="text-base font-bold text-text-primary">Aboneliği Onayla</h2>
        <p className="mt-1 text-xs text-text-muted">
          Satın almadan önce lütfen aşağıdaki bilgileri inceleyin.
        </p>

        {/* Critical info — clearly visible, normal size, not hidden */}
        <div className="mt-4 divide-y divide-white/5 rounded-xl border border-white/10 bg-bg-primary/40 px-4 py-2 text-sm">
          <Row label="Paket" value={planName} />
          <Row label="Abonelik süresi" value={cycleLabel} />
          <Row label="Tahsil edilecek tutar" value={`$${amountUsd}`} />
          <Row label="Sonraki otomatik yenileme" value={`${nextRenewalStr} · $${amountUsd}`} />
        </div>

        <div className="mt-3 space-y-2 rounded-xl border border-white/10 bg-bg-primary/40 px-4 py-3 text-xs leading-relaxed text-text-secondary">
          <p>
            <strong className="text-text-primary">Otomatik yenileme:</strong> Aboneliğiniz, iptal
            etmediğiniz sürece her dönem sonunda <strong className="text-text-primary">aynı süre ve
            bedelle otomatik olarak yenilenir</strong>.
          </p>
          <p>
            <strong className="text-text-primary">İptal:</strong> Hesap/Ayarlar bölümünden veya
            Fiyatlandırma sayfasındaki “Yenilemeyi Durdur” ile dilediğiniz zaman iptal edebilirsiniz;
            iptal, içinde bulunulan dönemin sonunda geçerli olur ve sonraki dönem için tahsilat yapılmaz.
          </p>
          <p>
            <strong className="text-text-primary">Cayma hakkı:</strong> Tüketici olarak 14 gün cayma
            hakkınız vardır; ancak hizmetin onayınızla derhal başlaması hâlinde mevzuat gereği cayma
            hakkı sona erer. Ayrıntı:{' '}
            <Link
              href="/yasal/mesafeli-satis"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-primary hover:underline"
            >
              Mesafeli Satış Sözleşmesi ve Ön Bilgilendirme ↗
            </Link>
          </p>
        </div>

        {/* Two separate, explicit consents */}
        <div className="mt-4 space-y-2">
          <label className="flex items-start gap-2 text-xs leading-relaxed text-text-secondary">
            <input
              type="checkbox"
              checked={acceptTerms}
              onChange={(e) => setAcceptTerms(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-accent-primary"
            />
            <span>
              Abonelik ve otomatik yenileme koşullarını ve Mesafeli Satış Sözleşmesi / Ön
              Bilgilendirme’yi okudum, kabul ediyorum.
            </span>
          </label>
          <label className="flex items-start gap-2 text-xs leading-relaxed text-text-secondary">
            <input
              type="checkbox"
              checked={acceptWaiver}
              onChange={(e) => setAcceptWaiver(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-accent-primary"
            />
            <span>
              Hizmetin onayımla derhal başlamasını istiyorum ve bu nedenle 14 günlük cayma hakkımı
              yitireceğimi kabul ediyorum.
            </span>
          </label>
        </div>

        <div className="mt-4 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={processing}
            className="text-xs font-semibold text-text-muted transition-colors hover:text-text-primary disabled:opacity-50"
          >
            Vazgeç
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canConfirm}
            className="rounded-lg bg-accent-primary px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {processing ? 'İşleniyor...' : 'Ödemeye Geç'}
          </button>
        </div>
      </div>
    </div>
  );
}
