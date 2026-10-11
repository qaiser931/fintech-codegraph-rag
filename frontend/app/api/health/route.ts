import {
  backendRequest,
  proxyError,
  readBackendJson,
  safeJson,
  upstreamError,
} from "@/lib/server/codegraph"
export const runtime = "nodejs"
export const maxDuration = 60
export async function GET() {
  try {
    const response = await backendRequest("/health", null)
    if (!response.ok) return upstreamError(response.status)
    const data = await readBackendJson(response)
    return safeJson({
      ...data,
      ok: data.status === "healthy" && data.indexed === true,
      checked_at: new Date().toISOString(),
    })
  } catch (error) {
    return proxyError(error)
  }
}
