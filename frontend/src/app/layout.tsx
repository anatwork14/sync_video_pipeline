import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VideoSync Pipeline — Multi-Camera Dashboard",
  description:
    "Real-time multi-camera video ingestion, synchronization, and stitching platform",
};

import { ToastProvider } from "@/components/Toast";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="bg-mesh" />
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
