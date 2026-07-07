import type { Metadata } from 'next';
import Link from 'next/link';
import { listLegalDocs } from '@/lib/legal/registry';

export const metadata: Metadata = { title: 'Yasal Belgeler — TradeMinds AI' };

export default function LegalIndexPage() {
  const docs = listLegalDocs();
  return (
    <main className="min-h-screen bg-bg-primary text-text-primary">
      <div className="mx-auto max-w-3xl px-5 py-12">
        <Link href="/" className="text-sm text-accent-primary hover:underline">
          ← Ana sayfa
        </Link>

        <h1 className="mt-4 text-h1 font-display">Yasal Belgeler</h1>
        <p className="mt-2 text-sm text-text-muted">
          Gizlilik, kullanım koşulları, çerez ve risk bildirimi dahil tüm yasal metinler.
        </p>

        <ul className="mt-8 divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-bg-secondary">
          {docs.map((d) => (
            <li key={d.slug}>
              <Link
                href={`/yasal/${d.slug}`}
                className="flex items-center justify-between px-5 py-4 transition-colors hover:bg-e-2"
              >
                <span className="font-medium">{d.title}</span>
                <span className="shrink-0 pl-4 text-xs text-text-muted">Sürüm {d.version}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
