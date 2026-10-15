import type { Metadata } from "next"
import "./globals.css"
import "./stackwise.css"
export const metadata: Metadata = {
  title: "Stackwise — Know which repository needs you next.",
  description:
    "An evidence-led maintenance desk for agencies. Review pull requests, watch dependencies and create client-ready reports.",
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
