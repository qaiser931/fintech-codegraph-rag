import type { Metadata } from "next"
import "./globals.css"
import "./codegraph.css"
export const metadata: Metadata = {
  title: "CodeGraph — Follow the code. Find the evidence.",
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
