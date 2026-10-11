import {
  backendRequest,
  proxyError,
  safeJson,
  sourceHtmlToCode,
  sourcePath,
  upstreamError,
  validateRole,
} from "@/lib/server/codegraph"
export const runtime = "nodejs"
export const maxDuration = 60
export async function GET(
  request: Request,
  context: { params: Promise<{ file_path: string[] }> }
) {
  try {
    const { file_path } = await context.params
    const role = new URL(request.url).searchParams.get("role")
    validateRole(role)
    const response = await backendRequest(
      `/source/${sourcePath(file_path)}?role=${encodeURIComponent(role)}`,
      role,
      { signal: request.signal }
    )
    if (!response.ok) return upstreamError(response.status)
    return safeJson({
      code: sourceHtmlToCode(await response.text()),
      file_path: file_path.join("/"),
    })
  } catch (error) {
    return proxyError(error)
  }
}
