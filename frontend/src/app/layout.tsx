import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import { Providers } from "./providers";
import { Header } from "@/components/layout/Header";
import { ScrapeProgressToast } from "@/components/scrape/ScrapeProgressToast";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "Immo - Aggregatore Immobiliare",
  description: "Cerca e confronta annunci immobiliari da tutti i portali in un unico posto",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-[var(--background)] text-[var(--foreground)]`}>
        <Providers>
          {/* useSearchParams in Header requires a Suspense boundary in
              the App Router so the route doesn't have to bail out of
              prerendering even when there are no query params yet. */}
          <Suspense fallback={<div className="h-14 border-b border-[var(--border)]" />}>
            <Header />
          </Suspense>
          <main>{children}</main>
          {/* Persistent scrape progress toast — bottom-right, survives
              route changes, only renders when a scrape is running or
              just completed. */}
          <ScrapeProgressToast />
        </Providers>
      </body>
    </html>
  );
}
