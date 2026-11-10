import type { Metadata } from "next";
import { vi } from "@/messages/vi";
import "@xyflow/react/dist/style.css";
import "./globals.css";
export const metadata: Metadata = {
  title: `${vi.app} — ${vi.tagline}`,
  description: vi.intro,
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
