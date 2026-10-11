import { proxyInvestigation } from "@/lib/server/codegraph"
export const runtime = "nodejs"
export const maxDuration = 300
export async function POST(request: Request) {
  return proxyInvestigation(request, "/retrieve")
}
