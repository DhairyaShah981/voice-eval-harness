import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "voice-eval-harness",
  description: "Runs dashboard for voice-eval-harness",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex flex-col">
          <header className="border-b border-neutral-200 bg-white">
            <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
              <a href="/" className="font-semibold tracking-tight">
                voice-eval-harness
              </a>
              <span className="text-xs text-neutral-500">v0.2 dashboard</span>
            </div>
          </header>
          <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
            {children}
          </main>
        </div>
        <Analytics />
      </body>
    </html>
  );
}
