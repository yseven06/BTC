import Link from 'next/link';
import { listLegalDocs } from '@/lib/legal/registry';
import { InvestmentDisclaimer } from '@/components/legal/InvestmentDisclaimer';
import { CookieSettingsLink } from '@/components/consent/CookieSettingsLink';

/**
 * Global footer — rendered on every page (public via LayoutShell, authenticated
 * via MainLayout). Minimal/restrained: the legal links (sourced from the registry
 * so they stay in sync with the docs) flow as one quiet inline row separated by
 * thin middots, with a single brand/copyright line beneath. Carries the
 * single-source investment disclaimer.
 */
export function Footer() {
  const docs = listLegalDocs();
  const year = new Date().getFullYear();

  // S8/a11y: --tx3 (text-muted) token-dokümanı gereği OKUNUR METİN DEĞİL (<4.5:1;
  // Lighthouse 3.49) → linkler tx2'ye çıkar; py-1 dokunma-alanını ≥24px'e taşır
  // (target-size), görsel yoğunluk değişmez (padding şeffaf).
  const linkClass = 'inline-flex items-center py-1 text-text-secondary transition-colors hover:text-text-primary';

  // Flatten registry docs + the two standing links into one ordered list so we
  // can interleave subtle separators between them.
  const links = [
    ...docs.map((d) => ({
      key: d.slug,
      node: (
        <Link href={`/yasal/${d.slug}`} className={linkClass}>
          {d.title}
        </Link>
      ),
    })),
    { key: '__all', node: <Link href="/yasal" className={linkClass}>Tüm Yasal Belgeler</Link> },
    { key: '__cookie', node: <CookieSettingsLink className={linkClass} /> },
  ];

  return (
    <footer className="mt-8 border-t border-white/10 bg-bg-secondary/30">
      <div className="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <InvestmentDisclaimer variant="footer" className="mb-4 max-w-3xl" />

        <nav aria-label="Yasal belgeler">
          <ul className="flex flex-wrap items-center text-micro leading-relaxed">
            {links.map((l, i) => (
              <li key={l.key} className="flex items-center">
                {l.node}
                {i < links.length - 1 && (
                  <span aria-hidden className="mx-2.5 select-none text-white/15">
                    ·
                  </span>
                )}
              </li>
            ))}
          </ul>
        </nav>

        {/* S8/a11y: okunur satırlar tx2 (tx3 yalnız dekor) — sessizlik boyutla korunur. */}
        <div className="mt-4 flex flex-col gap-1 border-t border-white/5 pt-4 text-micro text-text-secondary sm:flex-row sm:items-center sm:justify-between">
          <p>
            <span className="font-medium text-text-secondary">Zate Trade</span>
            <span aria-hidden className="mx-1.5 text-white/20">·</span>
            Yapay zekâ destekli analiz ve karar destek platformu
          </p>
          <p>© {year} Zate Trade. Tüm hakları saklıdır.</p>
        </div>
      </div>
    </footer>
  );
}
