import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Servio by Softnix · AI Service Agents",
    template: "%s · Servio",
  },
  description:
    "AI chat and voice agents that answer customers from your knowledge base, open tickets, and hand off to your team when a person is needed.",
  applicationName: "Servio",
  icons: {
    icon: "/softnix-favicon-32.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        {/* Softnix CI type: Inter (UI) + Noto Sans Thai, JetBrains Mono for code — same as EDC1 */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- root app layout, so this loads on every route */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Thai:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body className="antialiased h-full">{children}</body>
    </html>
  );
}
