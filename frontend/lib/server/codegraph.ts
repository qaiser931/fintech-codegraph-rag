import "server-only"
import { NextResponse } from "next/server"
import { load } from "cheerio"

export const roles = ["Junior Dev", "Senior Dev", "Security Lead"] as const
export type Role = (typeof roles)[number]
class ProxyFailure extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
  }
}
export function validateRole(value: unknown): asserts value is Role {
  if (typeof value !== "string" || !roles.includes(value as Role))
    throw new ProxyFailure(400, "Choose a valid investigator role.")
}
export function getBackendConfig(role: Role | null) {
  let url: URL
  try {
    url = new URL(process.env.CODEGRAPH_API_URL || "")
  } catch {
    throw new ProxyFailure(503, "The backend connection is not configured.")
  }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.protocol !== "https:" && !(local && url.protocol === "http:"))
  ) {
    throw new ProxyFailure(
      503,
      "Configure an HTTPS backend URL, or localhost for local development."
    )
  }
  const baseUrl = url.toString().replace(/\/$/, "")
  if (role === null) return { baseUrl, token: null }
  let tokens: unknown
  try {
    tokens = JSON.parse(process.env.API_ROLE_TOKENS || "")
  } catch {
    throw new ProxyFailure(503, "Backend role credentials are not configured.")
  }
  if (!tokens || typeof tokens !== "object" || Array.isArray(tokens))
    throw new ProxyFailure(503, "Backend role credentials are not configured.")
  const token = Object.entries(tokens).find(
    ([key, value]) =>
      value === role &&
      key.trim() === key &&
      key.length >= 16 &&
      !/[\r\n]/.test(key)
  )?.[0]
  if (!token)
    throw new ProxyFailure(
      503,
      "A backend credential is not configured for the selected role."
    )
  return { baseUrl, token }
}
export function safeJson(data: unknown, status = 200) {
  return NextResponse.json(data, {
    status,
    headers: { "Cache-Control": "no-store" },
  })
}
export function proxyError(error: unknown) {
  if (error instanceof ProxyFailure)
    return safeJson({ error: error.message }, error.status)
  if (
    error instanceof Error &&
    ["AbortError", "TimeoutError"].includes(error.name)
  ) {
    return safeJson(
      {
        error:
          "The backend took too long to respond. Check its connection before trying again.",
      },
      504
    )
  }
  return safeJson(
    {
      error:
        "Unable to reach the backend. Check that the API and its HTTPS tunnel are running.",
    },
    502
  )
}
export async function backendRequest(
  path: string,
  role: Role | null,
  init?: RequestInit
) {
  const { baseUrl, token } = getBackendConfig(role)
  const headers = new Headers(init?.headers)
  headers.set(
    "Accept",
    path.startsWith("/source/") ? "text/html" : "application/json"
  )
  if (token) headers.set("Authorization", `Bearer ${token}`)
  const timeout =
    path === "/query" ? 240_000 : path === "/retrieve" ? 120_000 : 30_000
  return fetch(`${baseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.any([
      AbortSignal.timeout(timeout),
      ...(init?.signal ? [init.signal] : []),
    ]),
  })
}
export async function readJsonBody(request: Request) {
  let body: Record<string, unknown>
  try {
    body = await request.json()
  } catch {
    throw new ProxyFailure(400, "Send a valid JSON request.")
  }
  if (!body || typeof body !== "object" || Array.isArray(body))
    throw new ProxyFailure(400, "Send a valid question and investigator role.")
  validateRole(body.role)
  const query = typeof body.query === "string" ? body.query.trim() : ""
  if (query.length < 3 || query.length > 2000)
    throw new ProxyFailure(400, "The question must contain 3–2000 characters.")
  if (body.stack_trace != null && typeof body.stack_trace !== "string")
    throw new ProxyFailure(400, "The stack trace must be text.")
  const stack_trace =
    typeof body.stack_trace === "string" ? body.stack_trace.trim() : null
  if (stack_trace && stack_trace.length > 8000)
    throw new ProxyFailure(
      400,
      "The stack trace is limited to 8000 characters."
    )
  return { query, role: body.role, stack_trace: stack_trace || null }
}
export function upstreamError(status: number) {
  const messages: Record<number, string> = {
    400: "The backend rejected this request.",
    401: "The backend role credential was rejected.",
    403: "Access was denied. Your selected role may not have access to this source.",
    404: "The requested source or API endpoint was not found.",
    422: "The backend rejected the request format. Check the deployed API version.",
    429: "The service is busy or its request quota has been reached. Try again later.",
    503: "The backend or generation provider is unavailable. Check its configuration.",
    504: "Generation timed out. Check the backend connection before trying again.",
  }
  return safeJson(
    {
      error: messages[status] || "The backend could not complete this request.",
    },
    status >= 400 && status <= 599 ? status : 502
  )
}
export async function readBackendJson(response: Response) {
  try {
    const data: unknown = await response.json()
    if (!data || typeof data !== "object" || Array.isArray(data))
      throw new Error()
    return data as Record<string, unknown>
  } catch (error) {
    if (
      error instanceof Error &&
      ["AbortError", "TimeoutError"].includes(error.name)
    )
      throw error
    throw new ProxyFailure(502, "The backend returned an invalid response.")
  }
}
export async function proxyInvestigation(
  request: Request,
  endpoint: "/query" | "/retrieve"
) {
  try {
    const body = await readJsonBody(request)
    const response = await backendRequest(endpoint, body.role, {
      method: "POST",
      signal: request.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!response.ok) return upstreamError(response.status)
    const data = await readBackendJson(response)
    const list = endpoint === "/query" ? data.citations : data.sources
    if (
      !Array.isArray(list) ||
      !Array.isArray(data.call_path) ||
      (endpoint === "/query" &&
        (typeof data.answer !== "string" ||
          ![
            "SUPPORTED",
            "PARTIALLY_SUPPORTED",
            "CONFLICTING_EVIDENCE",
            "INSUFFICIENT_EVIDENCE",
          ].includes(String(data.status))))
    )
      throw new ProxyFailure(
        502,
        "The backend response does not match the expected API version."
      )
    return safeJson(data)
  } catch (error) {
    return proxyError(error)
  }
}
export function sourcePath(parts: string[]) {
  if (
    parts.length < 3 ||
    parts[0] !== "data" ||
    parts[1] !== "sample_codebase" ||
    !parts.at(-1)?.endsWith(".py") ||
    parts.some((p) => !/^[a-zA-Z0-9_.-]+$/.test(p) || p === "." || p === "..")
  ) {
    throw new ProxyFailure(
      400,
      "Choose a Python source inside the sample codebase."
    )
  }
  return parts.map(encodeURIComponent).join("/")
}
export function sourceHtmlToCode(html: string) {
  const $ = load(html)
  const code = $("pre code").first()
  if (!code.length)
    throw new ProxyFailure(
      502,
      "The backend returned an unsupported source format."
    )
  const numbered = code.find('span[id^="L"]')
  return numbered.length
    ? numbered
        .toArray()
        .map((node) => {
          const line = $(node).text()
          return line === "\u00a0" ? "" : line
        })
        .join("\n")
    : code.text()
}
