/**
 * Legal-document registry — thin typed accessor over the generated manifest.
 *
 * Source of truth = the Markdown files in src/content/legal/<locale>/*.md.
 * Run `npm run legal:gen` after editing any .md to regenerate meta/bodies.
 * Meta (slug/version/effectiveDate/hash) is safe to import anywhere (small);
 * bodies are imported only by the server-rendered legal page.
 */
import { LEGAL_META, LEGAL_ORDER, type LegalDocMeta } from './generated/meta';

export type { LegalDocMeta };
export { LEGAL_META, LEGAL_ORDER };

/** All legal docs in display/footer order. */
export function listLegalDocs(): LegalDocMeta[] {
  return LEGAL_ORDER.map((slug) => LEGAL_META[slug]).filter(Boolean);
}

/** Metadata for a single doc (undefined if the slug is unknown). */
export function getLegalMeta(slug: string): LegalDocMeta | undefined {
  return LEGAL_META[slug];
}

/** Valid slugs (for generateStaticParams / route validation). */
export const LEGAL_SLUGS: string[] = LEGAL_ORDER;
