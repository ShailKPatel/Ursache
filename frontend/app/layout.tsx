import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Ursache",
  description: "Evidence-grounded root-cause analysis (8D, D4) for a simulated hot-rolling mill",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
