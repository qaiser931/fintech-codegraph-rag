export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message)
  }
}
export async function api<T>(
  path: string,
  options: {
    method?: string
    body?: unknown
    csrf?: string
    signal?: AbortSignal
  } = {}
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: options.method || "GET",
    credentials: "same-origin",
    cache: "no-store",
    signal: options.signal,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.csrf ? { "X-CSRF-Token": options.csrf } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok)
    throw new ApiError(
      typeof data.error === "string"
        ? data.error.slice(0, 700)
        : `Request failed (HTTP ${response.status}).`,
      response.status
    )
  return data as T
}

export function download(text: string, filename: string) {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/plain;charset=utf-8" })
  )
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
