import type { Metadata } from "next";
import { ReactNode } from "react";

export const metadata: Metadata = {
  title: "AegisQuant | Instrument-Grade AI Trading Bot",
  description: "MetaTrader 5 EA Bridge and AI Quantitative Trading Platform",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#090A0F] text-[#F8FAFC] antialiased">
        {children}
      </body>
    </html>
  );
}
