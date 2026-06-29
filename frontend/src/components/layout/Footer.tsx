import Link from 'next/link';
import { listLegalDocs } from '@/lib/legal/registry';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { CookieSettingsLink } from '@/components/consent/CookieSettingsLink';

/**
 * Global footer — rendered on every page (public via LayoutShell, authenticated
 * via MainLayout). Carries the single-source investment disclaimer and the legal
 * links (sourced from the legal registry, so the list stays in sync with the docs).
 */
export function Footer() {
  const docs = listLegalDocs();
  const year = new Date().getFullYear();

  return (
    <footer className="mt-8 border-t border-white/10 bg-bg-secondary/40">
      <div className="mx-auto w-full max-w-7xl px-4 py-8 md:px-6">
        <InvestmentDisclaimer variant="footer" className="mb-6 max-w-3xl" />

        <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-sm font-semibold text-text-primary">TradeMinds AI</p>
            <p className="mt-1 max-w-xs text-xs text-text-muted">
              Yapay zekâ destekli analiz ve karar destek platformu.
            </p>
            <p className="mt-3 text-xs text-text-muted">
              © {year} TradeMinds AI. Tüm hakları saklıdır.
            </p>
          </div>

          <nav aria-label="Yasal belgeler" className="min-w-[180px]">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Yasal
            </p>
            <ul className="space-y-1.5">
              {docs.map((d) => (
                <li key={d.slug}>
                  <Link
                    href={`/yasal/${d.slug}`}
                    className="text-xs text-text-muted transition-colors hover:text-text-primary hover:underline"
                  >
                    {d.title}
                  </Link>
                </li>
              ))}
              <li>
                <Link
                  href="/yasal"
                  className="text-xs text-text-muted transition-colors hover:text-text-primary hover:underline"
                >
                  Tüm Yasal Belgeler
                </Link>
              </li>
              <li>
                <CookieSettingsLink className="text-xs text-text-muted transition-colors hover:text-text-primary hover:underline" />
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </footer>
  );
}
