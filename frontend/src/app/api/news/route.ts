import { NextResponse } from 'next/server';

// Dynamic so user can force fresh with ?t=... query param.
export const dynamic = 'force-dynamic';
export const revalidate = 300;

const GLOBAL_SOURCES = [
  { name: 'CoinDesk',      url: 'https://www.coindesk.com/arc/outboundfeeds/rss/' },
  { name: 'CoinTelegraph', url: 'https://cointelegraph.com/rss' },
  { name: 'Decrypt',       url: 'https://decrypt.co/feed' },
];

const TURKISH_SOURCES = [
  { name: 'CoinTürk',     url: 'https://cointurk.com/feed/' },
  { name: 'BitcoinHaber', url: 'https://www.bitcoinhaber.net/feed' },
  { name: 'Coinkolik',    url: 'https://coinkolik.com/feed/' },
  { name: 'Kriptokoin',   url: 'https://kriptokoin.com/feed/' },
  { name: 'Uzmancoin',    url: 'https://uzmancoin.com/feed' },
];

interface NewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  published_at: string;
  summary: string;
}

/** Decode common HTML entities + numeric refs to real characters. */
function decodeEntities(s: string): string {
  if (!s) return s;
  return s
    // numeric decimal: &#1234;
    .replace(/&#(\d+);/g, (_, n) => {
      try { return String.fromCodePoint(parseInt(n, 10)); } catch { return ''; }
    })
    // numeric hex: &#x4F;
    .replace(/&#x([0-9a-fA-F]+);/g, (_, n) => {
      try { return String.fromCodePoint(parseInt(n, 16)); } catch { return ''; }
    })
    // named
    .replace(/&amp;/g,  '&')
    .replace(/&lt;/g,   '<')
    .replace(/&gt;/g,   '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&#039;/g, "'")
    .replace(/&hellip;/g, '…')
    .replace(/&laquo;/g, '«')
    .replace(/&raquo;/g, '»')
    .replace(/&ndash;/g, '–')
    .replace(/&mdash;/g, '—')
    .replace(/&rsquo;/g, '’')
    .replace(/&lsquo;/g, '‘')
    .replace(/&rdquo;/g, '”')
    .replace(/&ldquo;/g, '“');
}

/** Fetch RSS with correct charset (Content-Type → XML decl → utf-8 fallback). */
async function fetchUtf8(url: string): Promise<string | null> {
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': 'TradeMinds/1.0 RSS Reader' },
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();

    // Charset detection order:
    //   1) Content-Type response header
    //   2) <?xml version="1.0" encoding="..."?> declaration in body
    //   3) UTF-8 fallback
    let charset: string | null = null;

    const contentType = res.headers.get('content-type') ?? '';
    const ctMatch = contentType.match(/charset=([^\s;]+)/i);
    if (ctMatch) charset = ctMatch[1].toLowerCase();

    if (!charset) {
      // Peek first 200 bytes as latin1 to read XML declaration
      const headBytes = new Uint8Array(buf.slice(0, 200));
      const peek = new TextDecoder('latin1').decode(headBytes);
      const xmlMatch = peek.match(/encoding\s*=\s*["']([^"']+)["']/i);
      if (xmlMatch) charset = xmlMatch[1].toLowerCase();
    }

    if (!charset) charset = 'utf-8';

    // Normalize aliases TextDecoder doesn't recognize
    const charsetMap: Record<string, string> = {
      'utf8': 'utf-8',
      'iso88591': 'iso-8859-1',
      'iso88599': 'iso-8859-9',
      'windows1254': 'windows-1254',
      'cp1254': 'windows-1254',
    };
    const key = charset.replace(/[-_]/g, '');
    if (charsetMap[key]) charset = charsetMap[key];

    try {
      return new TextDecoder(charset, { fatal: false }).decode(buf);
    } catch {
      return new TextDecoder('utf-8', { fatal: false }).decode(buf);
    }
  } catch {
    return null;
  }
}

function extractTag(xml: string, tag: string): string {
  const match = xml.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/${tag}>`, 'i'));
  return decodeEntities((match?.[1] ?? '').trim());
}

function parseRSS(xml: string, sourceName: string, limit = 8): NewsItem[] {
  const items: NewsItem[] = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/gi;
  let match: RegExpExecArray | null;

  while ((match = itemRegex.exec(xml)) !== null && items.length < limit) {
    const block = match[1];
    const title = extractTag(block, 'title');
    const link  = extractTag(block, 'link') || extractTag(block, 'guid');
    const pubDate = extractTag(block, 'pubDate');
    const desc  = extractTag(block, 'description')
      .replace(/<[^>]+>/g, '')   // strip embedded HTML
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 220);

    if (!title || !link) continue;

    items.push({
      id: `${sourceName}-${Buffer.from(link).toString('base64').slice(0, 16)}`,
      title,
      source: sourceName,
      url: link,
      published_at: pubDate ? new Date(pubDate).toISOString() : new Date().toISOString(),
      summary: desc || title,
    });
  }

  return items;
}

async function fetchSources(sources: { name: string; url: string }[]): Promise<NewsItem[]> {
  const results = await Promise.allSettled(
    sources.map(async ({ name, url }) => {
      const xml = await fetchUtf8(url);
      if (!xml) return [];
      return parseRSS(xml, name);
    })
  );

  const all: NewsItem[] = [];
  for (const r of results) {
    if (r.status === 'fulfilled') all.push(...r.value);
  }
  return all.sort((a, b) => new Date(b.published_at).getTime() - new Date(a.published_at).getTime());
}

export async function GET() {
  const [global, turkish] = await Promise.all([
    fetchSources(GLOBAL_SOURCES),
    fetchSources(TURKISH_SOURCES),
  ]);

  return NextResponse.json({
    global:    global.slice(0, 25),
    turkish:   turkish.slice(0, 25),
    cached_at: new Date().toISOString(),
  });
}
