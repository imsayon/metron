import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Metron / experimental nowcasting desk",
  description: "Evidence-first convective hazard guidance for replay and review."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
