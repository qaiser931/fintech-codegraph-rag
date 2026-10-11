"use client"

import { FormEvent, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  BookOpen,
  Check,
  ChevronRight,
  Code2,
  Database,
  GitBranch,
  Loader2,
  LockKeyhole,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Timer,
  TriangleAlert,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

type Role = "Junior Dev" | "Senior Dev" | "Security Lead"
type Citation = {
  doc_id: string
  symbol_name: string
  file_path: string
  start_line: number
  end_line: number
}
type Result = {
  answer?: string
  status?: string
  query?: string
  role?: string
  citations?: Citation[]
  retrieved_items?: unknown[]
  call_path?: string[]
  provider?: string
  model?: string
  latency_ms?: number
  prompt_tokens?: number
  completion_tokens?: number
  sources?: Citation[]
}
type Source = { path: string; code: string; start: number; end: number }
type Health = {
  ok: boolean
  chunks?: number
  graph_nodes?: number
  graph_edges?: number
  checked_at?: string
}
const roles: { value: Role; detail: string }[] = [
  {
    value: "Junior Dev",
    detail: "General code and public integration context",
  },
  { value: "Senior Dev", detail: "Business logic and integration context" },
  { value: "Security Lead", detail: "Security and infrastructure context" },
]
const examples = [
  "What is the expected 1LINK latency during peak traffic?",
  "Trace the JazzCash callback verification path.",
]

function StatusBadge({ status }: { status?: string }) {
  const tone =
    status === "SUPPORTED"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : status === "CONFLICTING_EVIDENCE"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : status === "PARTIALLY_SUPPORTED"
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : status === "INSUFFICIENT_EVIDENCE"
            ? "border-amber-200 bg-amber-50 text-amber-800"
            : "border-blue-200 bg-blue-50 text-blue-700"
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] font-semibold tracking-wide", tone)}
    >
      {status ? status.replaceAll("_", " ") : "CODE EVIDENCE"}
    </Badge>
  )
}

async function requestJson(
  url: string,
  controller: AbortController,
  timeout: number,
  init?: RequestInit
) {
  const response = await fetch(url, {
    ...init,
    cache: "no-store",
    signal: AbortSignal.any([controller.signal, AbortSignal.timeout(timeout)]),
  })
  let data
  try {
    data = await response.json()
  } catch {
    throw new Error(
      "The service returned an unreadable response. Check the backend connection."
    )
  }
  if (!response.ok || data.error)
    throw new Error(
      data.error || "The service could not complete this request."
    )
  return data
}
function message(error: unknown) {
  if (error instanceof Error && error.name === "TimeoutError")
    return "The request timed out. Check the backend connection before trying again."
  return error instanceof Error ? error.message : "The service is unavailable."
}

export default function Page() {
  const [role, setRole] = useState<Role>("Senior Dev")
  const [query, setQuery] = useState("")
  const [stackTrace, setStackTrace] = useState("")
  const [result, setResult] = useState<Result | null>(null)
  const [source, setSource] = useState<Source | null>(null)
  const [tab, setTab] = useState<"sources" | "paths" | "telemetry">("sources")
  const [busy, setBusy] = useState<"query" | "retrieve" | null>(null)
  const [sourceBusy, setSourceBusy] = useState(false)
  const [healthBusy, setHealthBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const version = useRef(0)
  const sourceVersion = useRef(0)
  const queryRequest = useRef<AbortController | null>(null)
  const sourceRequest = useRef<AbortController | null>(null)
  const healthRequest = useRef<AbortController | null>(null)
  const questionInput = useRef<HTMLTextAreaElement | null>(null)
  const resultPanel = useRef<HTMLDivElement | null>(null)
  const selectedRole = roles.find((item) => item.value === role)!
  const citations = result?.citations || result?.sources || []

  useEffect(
    () => () => {
      queryRequest.current?.abort()
      sourceRequest.current?.abort()
      healthRequest.current?.abort()
    },
    []
  )

  function resetEvidence() {
    version.current++
    sourceVersion.current++
    queryRequest.current?.abort()
    sourceRequest.current?.abort()
    setResult(null)
    setSource(null)
    setError(null)
    setBusy(null)
    setSourceBusy(false)
  }
  function selectQuestion(value: string) {
    resetEvidence()
    setQuery(value)
    questionInput.current?.focus()
  }

  async function submit(kind: "query" | "retrieve") {
    if (query.trim().length < 3 || busy) return
    resetEvidence()
    const current = version.current
    const controller = new AbortController()
    queryRequest.current = controller
    setBusy(kind)
    setTab("sources")
    try {
      const data = await requestJson(
        `/api/${kind}`,
        controller,
        kind === "query" ? 245_000 : 125_000,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: query.trim(),
            role,
            stack_trace: stackTrace.trim() || null,
          }),
        }
      )
      if (current === version.current && !controller.signal.aborted)
        setResult(data)
    } catch (err) {
      if (current === version.current && !controller.signal.aborted)
        setError(message(err))
    } finally {
      if (current === version.current) setBusy(null)
    }
  }

  async function checkHealth() {
    if (
      healthRequest.current &&
      !healthRequest.current.signal.aborted &&
      healthBusy
    )
      return
    const controller = new AbortController()
    healthRequest.current = controller
    setHealthBusy(true)
    try {
      const data = await requestJson("/api/health", controller, 35_000)
      if (!controller.signal.aborted) setHealth(data)
    } catch (err) {
      if (!controller.signal.aborted) {
        setHealth({ ok: false, checked_at: new Date().toISOString() })
        setError(message(err))
      }
    } finally {
      if (!controller.signal.aborted) setHealthBusy(false)
    }
  }

  async function loadSource(citation: Citation) {
    if (!citation.file_path) return
    sourceRequest.current?.abort()
    const current = ++sourceVersion.current
    const scope = version.current
    const controller = new AbortController()
    sourceRequest.current = controller
    setSource(null)
    setSourceBusy(true)
    setError(null)
    try {
      const path = citation.file_path
        .split("/")
        .map(encodeURIComponent)
        .join("/")
      const data = await requestJson(
        `/api/source/${path}?role=${encodeURIComponent(role)}`,
        controller,
        35_000
      )
      if (
        current === sourceVersion.current &&
        scope === version.current &&
        !controller.signal.aborted
      ) {
        setSource({
          path: citation.file_path,
          code: data.code,
          start: citation.start_line,
          end: citation.end_line,
        })
      }
    } catch (err) {
      if (
        current === sourceVersion.current &&
        scope === version.current &&
        !controller.signal.aborted
      )
        setError(message(err))
    } finally {
      if (current === sourceVersion.current && scope === version.current)
        setSourceBusy(false)
    }
  }
  function closeSource() {
    sourceRequest.current?.abort()
    sourceVersion.current++
    setSource(null)
    setSourceBusy(false)
  }
  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void submit("query")
  }
  function showPaths() {
    setTab("paths")
    if (result)
      resultPanel.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      })
    else {
      setError(
        "Explore code or generate an answer to inspect its execution paths."
      )
      questionInput.current?.focus()
    }
  }

  return (
    <SidebarProvider>
      <div className="flex min-h-dvh w-full bg-slate-50">
        <Sidebar className="border-r border-slate-200 bg-white">
          <SidebarContent className="px-3 py-5">
            <div className="flex items-center gap-3 px-2 pb-6">
              <div className="flex size-9 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
                <Network className="size-5" />
              </div>
              <div>
                <p className="text-base font-semibold tracking-tight text-slate-950">
                  CodeGraph
                </p>
                <p className="text-[11px] text-slate-500">
                  Fintech investigation
                </p>
              </div>
            </div>
            <SidebarGroup>
              <SidebarGroupLabel className="text-[10px] tracking-widest text-slate-400 uppercase">
                Workspace
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      isActive
                      onClick={() => questionInput.current?.focus()}
                    >
                      <Search />
                      Investigate
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton onClick={showPaths}>
                      <GitBranch />
                      Execution paths
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      onClick={() => void checkHealth()}
                      disabled={healthBusy}
                    >
                      <Database />
                      Index status
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
            <Separator className="my-4" />
            <SidebarGroup>
              <SidebarGroupLabel className="text-[10px] tracking-widest text-slate-400 uppercase">
                Demo access
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <div className="px-2">
                  <label
                    htmlFor="role"
                    className="mb-2 block text-xs font-medium text-slate-700"
                  >
                    Investigator role
                  </label>
                  <select
                    id="role"
                    value={role}
                    onChange={(event) => {
                      resetEvidence()
                      setRole(event.target.value as Role)
                    }}
                    className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  >
                    {roles.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.value}
                      </option>
                    ))}
                  </select>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                    {selectedRole.detail}. Available files depend on the
                    selected role.
                  </p>
                </div>
              </SidebarGroupContent>
            </SidebarGroup>
            <div className="mt-auto rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-700">
                  Backend connection
                </span>
                <span
                  className={cn(
                    "size-2 rounded-full",
                    health?.ok
                      ? "bg-emerald-500"
                      : health
                        ? "bg-amber-500"
                        : "bg-slate-300"
                  )}
                />
              </div>
              <p className="mt-1.5 text-[11px] text-slate-500">
                {health
                  ? health.ok
                    ? "Available at last check"
                    : "Unavailable at last check"
                  : "Not checked yet"}
              </p>
              {health?.checked_at && (
                <p className="mt-1 text-[10px] text-slate-400">
                  Checked {new Date(health.checked_at).toLocaleTimeString()}
                </p>
              )}
              {health?.ok && (
                <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
                  <div>
                    <dt>Code chunks</dt>
                    <dd className="font-mono font-semibold text-slate-800">
                      {health.chunks ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Graph nodes</dt>
                    <dd className="font-mono font-semibold text-slate-800">
                      {health.graph_nodes ?? "—"}
                    </dd>
                  </div>
                </dl>
              )}
              <Button
                variant="outline"
                size="sm"
                className="mt-3 h-8 w-full text-xs"
                onClick={() => void checkHealth()}
                disabled={healthBusy}
              >
                {healthBusy ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <RefreshCw className="size-3" />
                )}
                Check connection
              </Button>
            </div>
          </SidebarContent>
        </Sidebar>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-7">
            <div className="flex items-center gap-3">
              <SidebarTrigger />
              <Separator orientation="vertical" className="h-5" />
              <div>
                <p className="text-sm font-semibold text-slate-950">
                  Code investigation
                </p>
                <p className="hidden text-[11px] text-slate-500 sm:block">
                  Synthetic fintech codebase / Workspace
                </p>
              </div>
            </div>
            <Badge
              variant="outline"
              className="gap-1.5 border-blue-200 bg-blue-50 text-blue-700"
            >
              <LockKeyhole className="size-3" />
              Demo access
            </Badge>
          </header>
          <main className="mx-auto flex w-full max-w-[1440px] flex-1 flex-col gap-6 p-4 sm:p-7">
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
              <section className="flex min-w-0 flex-col gap-5">
                <div>
                  <p className="mb-2 text-[11px] font-semibold tracking-[0.18em] text-blue-600 uppercase">
                    Ask the graph
                  </p>
                  <h1 className="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
                    What do you want to investigate?
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500">
                    Follow the code, inspect the evidence, and get answers
                    grounded in source references.
                  </p>
                </div>
                <Card className="gap-0 border-slate-200 py-0 shadow-sm">
                  <CardContent className="p-4 sm:p-5">
                    <form onSubmit={onSubmit} className="flex flex-col gap-3">
                      <label
                        htmlFor="question"
                        className="text-xs font-semibold text-slate-700"
                      >
                        Investigation question
                      </label>
                      <textarea
                        ref={questionInput}
                        id="question"
                        maxLength={2000}
                        value={query}
                        onChange={(event) => selectQuestion(event.target.value)}
                        placeholder="Ask about payment flows, integration behaviour, or a stack trace…"
                        className="min-h-28 resize-y rounded-xl border border-slate-200 bg-slate-50/60 p-3 text-sm leading-relaxed text-slate-900 outline-none placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                      />
                      <details className="group">
                        <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-medium text-slate-500">
                          <ChevronRight className="size-3 transition-transform group-open:rotate-90" />
                          Add optional stack trace
                        </summary>
                        <label className="sr-only" htmlFor="stack-trace">
                          Stack trace
                        </label>
                        <textarea
                          id="stack-trace"
                          maxLength={8000}
                          value={stackTrace}
                          onChange={(event) => {
                            resetEvidence()
                            setStackTrace(event.target.value)
                          }}
                          placeholder="Paste an exception or stack trace"
                          className="mt-3 min-h-24 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs outline-none focus:border-blue-500"
                        />
                      </details>
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                        <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
                          <ShieldCheck className="size-3.5 text-emerald-600" />{" "}
                          Role-scoped retrieval
                        </span>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={query.trim().length < 3 || !!busy}
                            onClick={() => void submit("retrieve")}
                          >
                            {busy === "retrieve" ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <BookOpen />
                            )}
                            Explore code
                          </Button>
                          <Button
                            type="submit"
                            size="sm"
                            disabled={query.trim().length < 3 || !!busy}
                            className="bg-blue-600 text-white hover:bg-blue-700"
                          >
                            {busy === "query" ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <Sparkles />
                            )}
                            Generate answer
                          </Button>
                        </div>
                      </div>
                    </form>
                  </CardContent>
                </Card>
                {!result && !busy && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] text-slate-500">
                      Try asking
                    </span>
                    {examples.map((example) => (
                      <button
                        key={example}
                        onClick={() => selectQuestion(example)}
                        className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-[11px] text-slate-600 transition hover:border-blue-300 hover:text-blue-700"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                )}
                {error && (
                  <div
                    role="alert"
                    className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
                  >
                    <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                    <div>
                      <p className="font-medium">
                        {error.includes("configured")
                          ? "Configuration needed"
                          : "Request unavailable"}
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-amber-700">
                        {error}
                      </p>
                    </div>
                    <button
                      className="ml-auto"
                      onClick={() => setError(null)}
                      aria-label="Dismiss error"
                    >
                      <X className="size-4" />
                    </button>
                  </div>
                )}
                {result ? (
                  <Card
                    ref={resultPanel}
                    className="scroll-mt-24 gap-0 border-slate-200 py-0 shadow-sm"
                  >
                    <CardHeader className="gap-3 border-b border-slate-100 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <Terminal className="size-4 text-blue-600" />
                          {result.answer
                            ? "Investigation result"
                            : "Code exploration"}
                        </CardTitle>
                        <StatusBadge status={result.status} />
                      </div>
                      <p className="text-xs leading-relaxed text-slate-600">
                        {result.query || query}
                      </p>
                      <div className="flex flex-wrap gap-4 text-[11px] text-slate-500">
                        <span className="flex items-center gap-1">
                          <Timer className="size-3" />
                          {result.latency_ms != null
                            ? `${(result.latency_ms / 1000).toFixed(2)} s`
                            : "—"}
                        </span>
                        <span className="flex items-center gap-1">
                          <GitBranch className="size-3" />
                          {result.call_path?.length ?? 0} execution paths
                        </span>
                        <span>{role}</span>
                        {result.model && (
                          <span>
                            {result.provider} / {result.model}
                          </span>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="p-4 sm:p-5">
                      {result.answer ? (
                        <article className="answer-markdown">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                            {result.answer}
                          </ReactMarkdown>
                        </article>
                      ) : (
                        <p className="text-sm text-slate-500">
                          Retrieved code references and call paths. Select a
                          source to inspect the evidence.
                        </p>
                      )}
                      <div
                        className="mt-5 flex gap-1 border-b border-slate-200"
                        aria-label="Result sections"
                      >
                        {(["sources", "paths", "telemetry"] as const).map(
                          (item) => (
                            <button
                              key={item}
                              aria-pressed={tab === item}
                              onClick={() => setTab(item)}
                              className={cn(
                                "border-b-2 px-3 py-2 text-xs font-medium capitalize",
                                tab === item
                                  ? "border-blue-600 text-blue-700"
                                  : "border-transparent text-slate-500"
                              )}
                            >
                              {item}
                              {item === "sources"
                                ? ` (${citations.length})`
                                : item === "paths"
                                  ? ` (${result.call_path?.length ?? 0})`
                                  : ""}
                            </button>
                          )
                        )}
                      </div>
                      {tab === "sources" && (
                        <div className="flex flex-col gap-2 pt-4">
                          {citations.length ? (
                            citations.map((citation, index) => (
                              <button
                                key={`${citation.doc_id}-${index}`}
                                onClick={() => void loadSource(citation)}
                                className="group flex items-start gap-3 rounded-xl border border-slate-200 p-3 text-left transition hover:border-blue-300 hover:bg-blue-50/40"
                              >
                                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-blue-50 font-mono text-xs font-semibold text-blue-700">
                                  {String(index + 1).padStart(2, "0")}
                                </span>
                                <span className="min-w-0">
                                  <span className="block truncate text-xs font-semibold text-slate-800">
                                    {citation.symbol_name || "Unnamed symbol"}
                                  </span>
                                  <span className="mt-1 block font-mono text-[11px] break-all text-slate-500">
                                    {citation.file_path}
                                  </span>
                                  <span className="mt-1 block text-[10px] text-slate-400">
                                    Lines {citation.start_line}–
                                    {citation.end_line}
                                  </span>
                                </span>
                                <ChevronRight className="mt-1 ml-auto size-4 shrink-0 text-slate-300 group-hover:text-blue-500" />
                              </button>
                            ))
                          ) : (
                            <p className="py-4 text-sm text-slate-500">
                              No citations returned.
                            </p>
                          )}
                        </div>
                      )}
                      {tab === "paths" && (
                        <div className="flex flex-col gap-2 pt-4">
                          {result.call_path?.length ? (
                            result.call_path.map((path, index) => (
                              <div
                                key={index}
                                className="flex gap-3 rounded-lg bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-600"
                              >
                                <span className="text-blue-600">
                                  {String(index + 1).padStart(2, "0")}
                                </span>
                                <span className="min-w-0 break-words">
                                  {path}
                                </span>
                              </div>
                            ))
                          ) : (
                            <p className="py-4 text-sm text-slate-500">
                              No execution paths returned.
                            </p>
                          )}
                        </div>
                      )}
                      {tab === "telemetry" && (
                        <div className="grid gap-3 pt-4 sm:grid-cols-3">
                          {[
                            [
                              "Latency",
                              result.latency_ms != null
                                ? `${result.latency_ms} ms`
                                : "—",
                            ],
                            ["Prompt tokens", result.prompt_tokens ?? "—"],
                            [
                              "Completion tokens",
                              result.completion_tokens ?? "—",
                            ],
                          ].map(([label, value]) => (
                            <div
                              key={label}
                              className="rounded-xl border border-slate-200 p-3"
                            >
                              <p className="text-[11px] text-slate-500">
                                {label}
                              </p>
                              <p className="mt-2 font-mono text-sm font-semibold text-slate-800">
                                {value}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ) : (
                  !busy && (
                    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-6 py-14 text-center">
                      <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                        <Code2 className="size-6" />
                      </div>
                      <h2 className="text-sm font-semibold text-slate-800">
                        Start with a question
                      </h2>
                      <p className="mt-2 max-w-sm text-xs leading-relaxed text-slate-500">
                        Explore source code first, or generate an answer with
                        citations you can inspect.
                      </p>
                    </div>
                  )
                )}
                {busy && (
                  <div
                    role="status"
                    className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-10 text-sm text-slate-500"
                  >
                    <Loader2 className="size-4 animate-spin text-blue-600" />
                    {busy === "retrieve"
                      ? "Exploring the code graph…"
                      : "Generating a grounded answer…"}
                  </div>
                )}
              </section>
              <aside className="flex min-w-0 flex-col gap-4">
                <Card className="gap-0 border-slate-200 py-0 shadow-sm">
                  <CardHeader className="border-b border-slate-100 p-4">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <Code2 className="size-4 text-blue-600" />
                      Source viewer
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="gap-0 p-0">
                    {sourceBusy ? (
                      <div
                        role="status"
                        className="flex min-h-52 items-center justify-center gap-2 text-xs text-slate-500"
                      >
                        <Loader2 className="size-4 animate-spin" />
                        Loading source…
                      </div>
                    ) : source ? (
                      <div>
                        <div className="flex items-start justify-between gap-3 border-b border-slate-100 bg-slate-50 px-4 py-3">
                          <div className="min-w-0">
                            <p className="font-mono text-[11px] break-all text-slate-600">
                              {source.path}
                            </p>
                            <p className="mt-1 text-[10px] text-blue-600">
                              Highlighted lines {source.start}–{source.end}
                            </p>
                          </div>
                          <button
                            onClick={closeSource}
                            aria-label="Close source"
                          >
                            <X className="size-4 text-slate-500" />
                          </button>
                        </div>
                        <pre className="max-h-[600px] overflow-auto py-3 text-[11px] leading-6 text-slate-700">
                          {source.code.split("\n").map((line, index) => (
                            <code
                              className={cn(
                                "block min-w-max px-3",
                                index + 1 >= source.start &&
                                  index + 1 <= source.end &&
                                  "border-l-2 border-blue-500 bg-blue-50 text-blue-950"
                              )}
                              key={index}
                            >
                              <span className="mr-4 inline-block w-7 text-right text-slate-400 select-none">
                                {index + 1}
                              </span>
                              {line || " "}
                            </code>
                          ))}
                        </pre>
                      </div>
                    ) : (
                      <div className="flex min-h-52 flex-col items-center justify-center px-6 text-center">
                        <BookOpen className="size-7 text-slate-300" />
                        <p className="mt-3 text-xs font-medium text-slate-600">
                          Your evidence, one click away
                        </p>
                        <p className="mt-2 max-w-56 text-[11px] leading-relaxed text-slate-500">
                          Select a citation to read the source and inspect its
                          referenced lines.
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
                <Card className="gap-0 border-blue-100 bg-blue-50/50 py-0 shadow-none">
                  <CardContent className="p-4">
                    <p className="text-xs font-semibold text-slate-800">
                      Follow the evidence
                    </p>
                    <div className="mt-1 flex flex-col gap-3 text-[11px] leading-relaxed text-slate-600">
                      <span className="flex gap-2">
                        <Check className="mt-0.5 size-3.5 shrink-0 text-blue-600" />
                        Answers show whether the retrieved evidence supports
                        them.
                      </span>
                      <span className="flex gap-2">
                        <Check className="mt-0.5 size-3.5 shrink-0 text-blue-600" />
                        Source references respect the selected demo role.
                      </span>
                      <span className="flex gap-2">
                        <Check className="mt-0.5 size-3.5 shrink-0 text-blue-600" />
                        This project uses synthetic payment examples.
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </aside>
            </div>
          </main>
          <footer className="border-t border-slate-200 bg-white px-4 py-4 text-center text-[11px] text-slate-500">
            CodeGraph · Project 10 · Synthetic fintech codebase
          </footer>
        </div>
      </div>
    </SidebarProvider>
  )
}
