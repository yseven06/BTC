import type { Metadata } from "next";
import "./globals.css";
import { LanguageProvider } from "@/lib/language-context";
import { AuthProvider } from "@/lib/auth-context";
import { AnalyticsProvider } from "@/components/AnalyticsProvider";
import { CookieConsentBanner } from "@/components/consent/CookieConsentBanner";
import { ReconsentGate } from "@/components/consent/ReconsentGate";
import LayoutShell from "@/components/layout/LayoutShell";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
const SITE_TITLE = "TradeMinds AI - Advanced Trading Intelligence Platform";
const SITE_DESCRIPTION = "AI-Powered trading signals, technical market structure analysis, and automated risk scoring for Crypto and BIST markets.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    siteName: "TradeMinds AI",
    images: [{ url: "/og-image.jpg", width: 1200, height: 630, alt: "TradeMinds AI — Institutional Trading Intelligence Platform" }],
    locale: "tr_TR",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: ["/og-image.jpg"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body className="antialiased">
        <LanguageProvider>
          <AuthProvider>
            <AnalyticsProvider />
            <LayoutShell>{children}</LayoutShell>
            <CookieConsentBanner />
            <ReconsentGate />
          </AuthProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
