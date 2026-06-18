import { NextResponse } from 'next/server';

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
];

interface NewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  published_at: string;
  summary: string;
}

function extractTag(xml: string, tag: string): string {
  const match = xml.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/${tag}>`, 'i'));
  return (match?.[1] ?? '').trim();
}

function parseRSS(xml: string, sourceName: string, limit = 7): NewsItem[] {
  const items: NewsItem[] = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/gi;
  let match: RegExpExecArray | null;

  while ((match = itemRegex.exec(xml)) !== null && items.length < limit) {
    const block = match[1];
    const title = extractTag(block, 'title');
    const link  = extractTag(block, 'link') || extractTag(block, 'guid');
    const pubDate = extractTag(block, 'pubDate');
    const desc  = extractTag(block, 'description').replace(/<[^>]+>/g, '').slice(0, 180);

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
      const res = await fetch(url, {
        next: { revalidate: 300 },
        headers: { 'User-Agent': 'TradeMinds/1.0 RSS Reader' },
      });
      if (!res.ok) throw new Error(`${name}: ${res.status}`);
      return parseRSS(await res.text(), name);
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
    global: global.slice(0, 20),
    turkish: turkish.slice(0, 20),
    cached_at: new Date().toISOString(),
  });
}
