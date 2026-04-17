import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CryptoAnalyzer — منصة تحليل العملات الرقمية",
  description: "منصة تحليل وتداول العملات الرقمية بمنهجية محايدة وواقعية",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
