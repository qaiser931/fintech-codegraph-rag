import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Investigation Workspace — CodeGraph",
  description:
    "Explore source references, execution paths and code-grounded answers with your selected demo role.",
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
