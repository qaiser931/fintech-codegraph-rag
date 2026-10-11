import type { Metadata } from "next"
import "./globals.css"
export const metadata: Metadata = {
  title: "CodeGraph — Fintech Code Investigation",
  description:
    "Explore symbols, trace execution paths, and inspect grounded answers in a synthetic fintech codebase.",
}
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="antialiased">
      <body>{children}</body>
    </html>
  )
}
