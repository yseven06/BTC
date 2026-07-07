import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getLegalMeta, LEGAL_SLUGS } from '@/lib/legal/registry';
import { LEGAL_BODIES } from '@/lib/legal/generated/bodies';

export function generateStaticParams() {
  return LEGAL_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const meta = getLegalMeta(slug);
  return { title: meta ? `${meta.title} — TradeMinds AI` : 'Yasal Belge' };
}

export default async function LegalDocPage(
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const meta = getLegalMeta(slug);
  const body = LEGAL_BODIES[slug];
  if (!meta || !body) notFound();

  return (
    <main className="min-h-screen bg-bg-primary text-text-primary">
      <div className="mx-auto max-w-3xl px-5 py-12">
        <Link href="/yasal" className="text-sm text-accent-primary hover:underline">
          ← Yasal Belgeler
        </Link>

        <header className="mt-4 mb-8 border-b border-white/10 pb-4">
          <h1 className="text-h1 font-display">{meta.title}</h1>
          <p className="mt-2 text-xs text-text-muted">
            Sürüm {meta.version}
            {meta.effectiveDate ? ` · Yürürlük tarihi: ${meta.effectiveDate}` : ''}
          </p>
        </header>

        {/* The markdown body repeats the title as an h1 — hide it (we render the
            title from metadata above) and style the rest with the app theme. */}
        <article
          className="
            [&_h1]:hidden
            [&_h2]:mt-8 [&_h2]:mb-3 [&_h2]:text-xl [&_h2]:font-display [&_h2]:text-text-primary
            [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-display [&_h3]:text-text-primary
            [&_p]:mb-4 [&_p]:leading-relaxed [&_p]:text-text-secondary
            [&_ul]:mb-4 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:text-text-secondary
            [&_ol]:mb-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:text-text-secondary
            [&_li]:mb-1
            [&_a]:text-accent-primary [&_a]:underline
            [&_strong]:text-text-primary
            [&_blockquote]:my-4 [&_blockquote]:border-l-2 [&_blockquote]:border-accent-primary/50
            [&_blockquote]:bg-bg-secondary [&_blockquote]:px-4 [&_blockquote]:py-2 [&_blockquote]:text-text-muted
            [&_table]:my-4 [&_table]:w-full [&_table]:text-sm
            [&_th]:border-b [&_th]:border-white/10 [&_th]:py-1 [&_th]:text-left [&_th]:text-text-primary
            [&_td]:border-b [&_td]:border-white/5 [&_td]:py-1 [&_td]:text-text-secondary
          "
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
        </article>
      </div>
    </main>
  );
}
