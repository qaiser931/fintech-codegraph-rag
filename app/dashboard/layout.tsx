import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Agency workspace — Stackwise",
  description:
    "Review client code, inspect evidence and prioritize repository maintenance.",
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
