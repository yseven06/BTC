import type { Metadata, Viewport } from "next";
import "./globals.css";
import { LanguageProvider } from "@/lib/language-context";
import { AuthProvider } from "@/lib/auth-context";
import { AnalyticsProvider } from "@/components/AnalyticsProvider";
import { CookieConsentBanner } from "@/components/consent/CookieConsentBanner";
import { ReconsentGate } from "@/components/consent/ReconsentGate";
import LayoutShell from "@/components/layout/LayoutShell";
import { ToastProvider } from "@/components/ui/Toast";
import { PWARegister } from "@/components/PWARegister";
import { Inter } from "next/font/google";

// Self-hosted via next/font — Inter YALNIZ numeral/display rolu (Bible typo-font-family, P8/D1);
// fallback (CLS=0), latin-ext subset for full Turkish glyph coverage (şğıİÇÖÜ).
// govde system-ui, mono ui-monospace OS-native (webfont mono kaldirildi, P8/D2).
const inter = Inter({ subsets: ["latin", "latin-ext"], variable: "--font-sans", display: "swap" });

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
const SITE_TITLE = "TradeMinds AI — Kripto Sinyal ve Analiz Platformu";
const SITE_DESCRIPTION = "9 AI motoruyla kripto piyasaları için sinyal üretimi, piyasa yapısı analizi ve otomatik risk skorlaması.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  applicationName: "TradeMinds AI",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "TradeMinds" },
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    siteName: "TradeMinds AI",
    images: [{ url: "/og-image.jpg", width: 1200, height: 630, alt: "TradeMinds AI — Kripto Sinyal ve Analiz Platformu" }],
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

export const viewport: Viewport = {
  // = --e0 (globals.css :root tek-kaynak). JS bağlamı CSS var() okuyamaz →
  // değer elle senkron tutulur. Aynı kural: public/manifest.webmanifest
  // theme_color/background_color. Bible §01 COL-01; lint gate-1 izin-listesi (P1-F/g).
  themeColor: "#070B14",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr" className={inter.variable}>
      <body className="antialiased">
        <LanguageProvider>
          <AuthProvider>
            <ToastProvider>
              <AnalyticsProvider />
              <PWARegister />
              <LayoutShell>{children}</LayoutShell>
              <CookieConsentBanner />
              <ReconsentGate />
            </ToastProvider>
          </AuthProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
