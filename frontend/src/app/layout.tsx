import type { Metadata } from "next";
import "./globals.css";
import { LanguageProvider } from "@/lib/language-context";
import { AuthProvider } from "@/lib/auth-context";
import LayoutShell from "@/components/layout/LayoutShell";

export const metadata: Metadata = {
  title: "TradeMinds AI - Advanced Trading Intelligence Platform",
  description: "AI-Powered trading signals, technical market structure analysis, and automated risk scoring for Crypto and BIST markets.",
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
            <LayoutShell>{children}</LayoutShell>
          </AuthProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
