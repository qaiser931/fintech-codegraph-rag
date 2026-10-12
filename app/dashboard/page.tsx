"use client"

import { FormEvent, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import Link from "next/link"
import {
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  Code2,
  Database,
  GitBranch,
  GitFork,
  Layers3,
  Loader2,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Timer,
  TriangleAlert,
  X,
  Check,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { CodeGraphBrand, GraphIllustration } from "@/components/codegraph-brand"
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
    <div className="cg-dashboard">
      <a className="cg-skip" href="#workspace-main">
        Skip to workspace
      </a>
      <aside className="cg-sidebar" aria-label="Workspace sidebar">
        <Link href="/" aria-label="CodeGraph home">
          <CodeGraphBrand compact />
        </Link>
        <div className="cg-workspace-card">
          <span className="cg-workspace-icon">
            <Layers3 size={19} />
          </span>
          <div>
            <strong>Fintech codebase</strong>
            <small>Synthetic payment integrations</small>
          </div>
        </div>
        <div className="cg-nav-label">WORKSPACE</div>
        <nav className="cg-workspace-nav" aria-label="Workspace navigation">
          <button
            className="is-active"
            onClick={() => questionInput.current?.focus()}
          >
            <Search size={18} /> Investigate <ChevronRight size={15} />
          </button>
          <button onClick={showPaths}>
            <GitBranch size={18} /> Execution paths
          </button>
          <button
            disabled={!result}
            onClick={() => {
              setTab("sources")
              resultPanel.current?.scrollIntoView({
                behavior: "smooth",
                block: "start",
              })
            }}
          >
            <BookOpen size={18} /> Source references
          </button>
          <button onClick={() => void checkHealth()} disabled={healthBusy}>
            <Database size={18} /> Index status
          </button>
        </nav>
        <div className="cg-sidebar-access">
          <div className="cg-nav-label">ACCESS CONTEXT</div>
          <label htmlFor="role">Investigator role</label>
          <div className="cg-role-select">
            <ShieldCheck size={16} />
            <select
              id="role"
              value={role}
              onChange={(event) => {
                resetEvidence()
                setRole(event.target.value as Role)
              }}
            >
              {roles.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.value}
                </option>
              ))}
            </select>
          </div>
          <p>
            {selectedRole.detail}. Available files depend on the selected role.
          </p>
        </div>
        <div className="cg-connection-panel">
          <div>
            <span
              className={cn(
                "cg-connection-dot",
                health?.ok ? "is-healthy" : health ? "is-unavailable" : ""
              )}
            />
            <strong>Backend connection</strong>
          </div>
          <p>
            {health
              ? health.ok
                ? "Available at last check"
                : "Unavailable at last check"
              : "Not checked yet"}
          </p>
          {health?.checked_at && (
            <small>
              Checked {new Date(health.checked_at).toLocaleTimeString()}
            </small>
          )}
          {health?.ok && (
            <dl>
              <div>
                <dt>Code chunks</dt>
                <dd>{health.chunks ?? "—"}</dd>
              </div>
              <div>
                <dt>Graph nodes</dt>
                <dd>{health.graph_nodes ?? "—"}</dd>
              </div>
            </dl>
          )}
          <button
            className="cg-button cg-button-outline cg-button-small"
            onClick={() => void checkHealth()}
            disabled={healthBusy}
          >
            {healthBusy ? (
              <Loader2 size={14} className="cg-spin" />
            ) : (
              <RefreshCw size={14} />
            )}{" "}
            Check connection
          </button>
        </div>
        <div className="cg-sidebar-footer">
          <span>PROJECT 10</span>
          <Link href="/">
            Project overview <ArrowUpRight size={14} />
          </Link>
          <a
            href="https://github.com/qaiser931/fintech-codegraph-rag"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub repository <GitFork size={14} />
          </a>
        </div>
      </aside>
      <div className="cg-workspace-body">
        <header className="cg-workspace-header">
          <div>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>Investigation</strong>
          </div>
          <button
            className="cg-button cg-button-outline cg-button-small"
            onClick={() => {
              resetEvidence()
              setQuery("")
              setStackTrace("")
              setTab("sources")
              questionInput.current?.focus()
            }}
          >
            <Plus size={15} /> New investigation
          </button>
        </header>
        <main id="workspace-main" className="cg-workspace-main">
          <div className="cg-workspace-heading">
            <div>
              <span className="cg-eyebrow">YOUR CODE. CONNECTED.</span>
              <h1>Connect the dots.</h1>
              <p>
                Ask a question. Follow the execution path. Inspect the evidence.
              </p>
            </div>
            <span className="cg-demo-label">
              <span /> Synthetic codebase
            </span>
          </div>
          <div
            className="cg-metric-grid"
            aria-label="Current investigation metrics"
          >
            <div>
              <span className="cg-metric-icon">
                <BookOpen size={17} />
              </span>
              <span>
                <small>Source references</small>
                <strong>{result ? citations.length : "—"}</strong>
              </span>
            </div>
            <div>
              <span className="cg-metric-icon mint">
                <GitBranch size={17} />
              </span>
              <span>
                <small>Execution paths</small>
                <strong>
                  {result ? (result.call_path?.length ?? 0) : "—"}
                </strong>
              </span>
            </div>
            <div>
              <span className="cg-metric-icon peach">
                <Timer size={17} />
              </span>
              <span>
                <small>Response time</small>
                <strong>
                  {result?.latency_ms != null ? (
                    <>
                      {(result.latency_ms / 1000).toFixed(2)}
                      <em> s</em>
                    </>
                  ) : (
                    "—"
                  )}
                </strong>
              </span>
            </div>
            <div>
              <span className="cg-metric-icon">
                <ShieldCheck size={17} />
              </span>
              <span>
                <small>Active role</small>
                <strong className="cg-metric-role">{role}</strong>
              </span>
            </div>
          </div>
          <div className="cg-investigation-grid">
            <section
              className="cg-investigation-column"
              aria-label="Investigation"
            >
              <div className="cg-composer cg-panel">
                <div className="cg-panel-heading">
                  <div>
                    <span className="cg-panel-icon">
                      <Sparkles size={17} />
                    </span>
                    <strong>Ask the codebase</strong>
                  </div>
                  <span className="cg-scope-label">
                    <LockKeyhole size={12} /> Role-scoped
                  </span>
                </div>
                <form onSubmit={onSubmit}>
                  <label htmlFor="question">Investigation question</label>
                  <textarea
                    ref={questionInput}
                    id="question"
                    maxLength={2000}
                    value={query}
                    onChange={(event) => selectQuestion(event.target.value)}
                    placeholder="What would you like to understand about the code?"
                  />
                  <div className="cg-composer-meta">
                    <details>
                      <summary>
                        <ChevronRight size={13} /> Add optional stack trace
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
                      />
                    </details>
                    <span>{query.length} / 2000</span>
                  </div>
                  <div className="cg-composer-actions">
                    <span>
                      <ShieldCheck size={14} /> Evidence you can inspect
                    </span>
                    <div>
                      <button
                        type="button"
                        className="cg-button cg-button-outline cg-button-small"
                        disabled={query.trim().length < 3 || !!busy}
                        onClick={() => void submit("retrieve")}
                      >
                        {busy === "retrieve" ? (
                          <Loader2 size={16} className="cg-spin" />
                        ) : (
                          <Search size={16} />
                        )}{" "}
                        Explore code
                      </button>
                      <button
                        type="submit"
                        className="cg-button cg-button-small"
                        disabled={query.trim().length < 3 || !!busy}
                      >
                        {busy === "query" ? (
                          <Loader2 size={16} className="cg-spin" />
                        ) : (
                          <Sparkles size={16} />
                        )}{" "}
                        Generate answer
                      </button>
                    </div>
                  </div>
                </form>
              </div>
              {!result && !busy && (
                <div className="cg-starters">
                  <span className="cg-nav-label">A GOOD PLACE TO START</span>
                  <div>
                    {examples.map((example, index) => (
                      <button
                        key={example}
                        onClick={() => selectQuestion(example)}
                      >
                        <span className="cg-starter-icon">
                          {index === 0 ? (
                            <Timer size={17} />
                          ) : (
                            <GitBranch size={17} />
                          )}
                        </span>
                        <span>
                          <strong>
                            {index === 0
                              ? "Understand 1LINK behavior"
                              : "Follow a JazzCash callback"}
                          </strong>
                          <small>{example}</small>
                        </span>
                        <ArrowUpRight size={16} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {error && (
                <div role="alert" className="cg-error">
                  <TriangleAlert size={18} />
                  <div>
                    <strong>
                      {error.includes("configured")
                        ? "Configuration needed"
                        : "Request unavailable"}
                    </strong>
                    <p>{error}</p>
                  </div>
                  <button
                    onClick={() => setError(null)}
                    aria-label="Dismiss error"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              {result ? (
                <div ref={resultPanel} className="cg-panel cg-result">
                  <div className="cg-result-heading">
                    <div>
                      <span className="cg-eyebrow">INVESTIGATION OUTPUT</span>
                      <h2>
                        {result.answer
                          ? "Investigation result"
                          : "Code exploration"}
                      </h2>
                    </div>
                    <StatusBadge status={result.status} />
                  </div>
                  <p className="cg-result-question">{result.query || query}</p>
                  <div className="cg-result-meta">
                    <span>
                      <Timer size={12} />
                      {result.latency_ms != null
                        ? `${(result.latency_ms / 1000).toFixed(2)} s`
                        : "—"}
                    </span>
                    <span>
                      <GitBranch size={12} />
                      {result.call_path?.length ?? 0} execution paths
                    </span>
                    <span>{role}</span>
                    {result.model && (
                      <span>
                        {result.provider} / {result.model}
                      </span>
                    )}
                  </div>
                  {result.answer ? (
                    <article className="answer-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                        {result.answer}
                      </ReactMarkdown>
                    </article>
                  ) : (
                    <p className="cg-exploration-note">
                      Retrieved code references and call paths. Select a source
                      to inspect the evidence.
                    </p>
                  )}
                  <div className="cg-result-tabs" aria-label="Result sections">
                    {(["sources", "paths", "telemetry"] as const).map(
                      (item) => (
                        <button
                          key={item}
                          aria-pressed={tab === item}
                          onClick={() => setTab(item)}
                          className={tab === item ? "is-selected" : ""}
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
                    <div className="cg-citations">
                      {citations.length ? (
                        citations.map((citation, index) => (
                          <button
                            key={`${citation.doc_id}-${index}`}
                            onClick={() => void loadSource(citation)}
                          >
                            <span className="cg-citation-number">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <span>
                              <strong>
                                {citation.symbol_name || "Unnamed symbol"}
                              </strong>
                              <small>{citation.file_path}</small>
                              <em>
                                Lines {citation.start_line}–{citation.end_line}
                              </em>
                            </span>
                            <ArrowUpRight size={16} />
                          </button>
                        ))
                      ) : (
                        <p>No citations returned.</p>
                      )}
                    </div>
                  )}
                  {tab === "paths" && (
                    <div className="cg-execution-paths">
                      {result.call_path?.length ? (
                        result.call_path.map((path, index) => (
                          <div key={index}>
                            <span>{String(index + 1).padStart(2, "0")}</span>
                            <p>{path}</p>
                          </div>
                        ))
                      ) : (
                        <p>No execution paths returned.</p>
                      )}
                    </div>
                  )}
                  {tab === "telemetry" && (
                    <div className="cg-telemetry">
                      {[
                        [
                          "Latency",
                          result.latency_ms != null
                            ? `${result.latency_ms} ms`
                            : "—",
                        ],
                        ["Prompt tokens", result.prompt_tokens ?? "—"],
                        ["Completion tokens", result.completion_tokens ?? "—"],
                      ].map(([label, value]) => (
                        <div key={label}>
                          <small>{label}</small>
                          <strong>{value}</strong>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                !busy && (
                  <div className="cg-empty-evidence cg-panel">
                    <div>
                      <span className="cg-eyebrow">
                        LET THE CODE TELL THE STORY
                      </span>
                      <h2>Start with a question</h2>
                      <p>
                        Explore source code first, or generate an answer with
                        citations you can inspect.
                      </p>
                    </div>
                    <GraphIllustration compact />
                    <span className="cg-feature-caption">
                      Illustrative workflow · Your results will appear here
                    </span>
                  </div>
                )
              )}
              {busy && (
                <div role="status" className="cg-loading cg-panel">
                  <div className="cg-loading-orbit">
                    <Loader2 size={26} className="cg-spin" />
                  </div>
                  <strong>
                    {busy === "retrieve"
                      ? "Exploring the code graph…"
                      : "Generating a grounded answer…"}
                  </strong>
                  <p>
                    {busy === "retrieve"
                      ? "Finding relevant symbols and their connections."
                      : "Building a response from the retrieved context."}
                  </p>
                  <button className="cg-text-link" onClick={resetEvidence}>
                    Stop waiting <X size={13} />
                  </button>
                </div>
              )}
            </section>
            <aside
              className="cg-inspector-column"
              aria-label="Source inspector"
            >
              <div className="cg-panel cg-inspector">
                <div className="cg-panel-heading">
                  <div>
                    <Code2 size={17} />
                    <strong>Source viewer</strong>
                  </div>
                  <span className="cg-inspector-lang">PYTHON</span>
                </div>
                {sourceBusy ? (
                  <div role="status" className="cg-source-empty">
                    <Loader2 size={24} className="cg-spin" />
                    <p>Loading source…</p>
                  </div>
                ) : source ? (
                  <div>
                    <div className="cg-source-filename">
                      <div>
                        <strong>{source.path.split("/").at(-1)}</strong>
                        <small>{source.path}</small>
                        <span>
                          Highlighted lines {source.start}–{source.end}
                        </span>
                      </div>
                      <button onClick={closeSource} aria-label="Close source">
                        <X size={16} />
                      </button>
                    </div>
                    <pre className="cg-source-code">
                      {source.code.split("\n").map((line, index) => (
                        <code
                          className={
                            index + 1 >= source.start && index + 1 <= source.end
                              ? "is-highlighted"
                              : ""
                          }
                          key={index}
                        >
                          <span>{index + 1}</span>
                          {line || " "}
                        </code>
                      ))}
                    </pre>
                  </div>
                ) : (
                  <div className="cg-source-empty">
                    <span className="cg-source-placeholder">
                      <Code2 size={27} />
                    </span>
                    <strong>Your evidence, one click away</strong>
                    <p>
                      Select a source reference to inspect the original file and
                      its highlighted lines.
                    </p>
                    <div className="cg-code-placeholder" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                      <i />
                    </div>
                  </div>
                )}
              </div>
              <div className="cg-evidence-guide">
                <span className="cg-feature-icon">
                  <ShieldCheck size={19} />
                </span>
                <h3>Every claim needs context.</h3>
                <p>
                  Use source references to evaluate the answer. Evidence status
                  is a guide, not proof of correctness.
                </p>
                <div>
                  <Check size={14} /> Inspect the referenced lines
                </div>
                <div>
                  <Check size={14} /> Check the selected role
                </div>
                <div>
                  <Check size={14} /> Distinguish facts from inference
                </div>
              </div>
              <div className="cg-sample-note">
                <span>THE SAMPLE CODEBASE</span>
                <div>
                  <i>JC</i> JazzCash <i>1L</i> 1LINK <i>EP</i> EasyPaisa
                </div>
                <p>Synthetic integrations for learning and investigation.</p>
              </div>
            </aside>
          </div>
          <footer className="cg-workspace-footer">
            <span>CodeGraph / Fintech code intelligence</span>
            <span>Project 10 · Synthetic demonstration</span>
          </footer>
        </main>
      </div>
    </div>
  )
}
