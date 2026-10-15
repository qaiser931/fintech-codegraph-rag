"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Code2,
  Copy,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  GitBranch,
  GitPullRequest,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react"
import { StackwiseBrand } from "@/components/stackwise-brand"
import { ApiError, api, download } from "@/lib/stackwise/api"
import type {
  Evidence,
  Finding,
  Job,
  Portfolio,
  Report,
  Review,
  Session,
} from "@/lib/stackwise/types"

type View =
  | "Overview"
  | "Workspaces"
  | "Code reviews"
  | "Dependencies"
  | "Reports"
  | "Settings"
const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Workspaces", icon: Layers3 },
  { name: "Code reviews", icon: GitPullRequest },
  { name: "Dependencies", icon: ShieldCheck },
  { name: "Reports", icon: FileText },
  { name: "Settings", icon: Settings2 },
] as const
const EMPTY: Portfolio = {
  demo: false,
  workspaces: [],
  repositories: [],
  reviews: [],
  findings: [],
  jobs: [],
  reports: [],
  audit: [],
}
const relative = (t?: number | null) =>
  !t
    ? "Not yet"
    : new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(t * 1000)
const label = (s?: string) => (s || "not available").replaceAll("_", " ")
const severityRank: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
  info: 3,
}

function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode
  tone?: string
}) {
  return <span className={`sw-badge sw-badge-${tone}`}>{children}</span>
}
function Empty({
  title,
  children,
  action,
}: {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div className="sw-empty">
      <span>
        <Layers3 size={25} strokeWidth={1.5} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  )
}
function Panel({
  title,
  hint,
  children,
  className = "",
  action,
}: {
  title: string
  hint?: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}) {
  return (
    <section className={`sw-panel ${className}`}>
      <div className="sw-panel-heading">
        <div>
          <h2>{title}</h2>
          {hint && <p>{hint}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function Dialog({
  title,
  children,
  close,
}: {
  title: string
  children: React.ReactNode
  close: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const old = document.activeElement as HTMLElement | null
    const root = ref.current!
    const focusable = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]"
        )
      )
    focusable()[0]?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") close()
      if (event.key === "Tab") {
        const elements = focusable(),
          first = elements[0],
          last = elements.at(-1)
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }
    }
    root.addEventListener("keydown", key)
    return () => {
      root.removeEventListener("keydown", key)
      old?.focus()
    }
  }, [close])
  return (
    <div className="sw-modal-backdrop">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="sw-modal"
      >
        <div className="sw-panel-heading">
          <h2>{title}</h2>
          <button
            type="button"
            className="sw-icon-btn"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={19} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export default function StackwiseApp() {
  const contextVersion = useRef(0)
  const [mode, setMode] = useState<"loading" | "login" | "demo" | "live">(
    "loading"
  )
  const [session, setSession] = useState<Session>({ user: null, setup: {} })
  const [data, setData] = useState<Portfolio>(EMPTY)
  const [snapshotTime, setSnapshotTime] = useState(0)
  const [view, setView] = useState<View>("Overview")
  const [workspace, setWorkspace] = useState("all")
  const [range, setRange] = useState("30")
  const [search, setSearch] = useState("")
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [menu, setMenu] = useState(false)
  const [modal, setModal] = useState<
    "workspace" | "repository" | "review" | "connection" | "access" | null
  >(null)
  const [formWorkspace, setFormWorkspace] = useState("")
  const [formRepo, setFormRepo] = useState("")
  const [name, setName] = useState("")
  const [number, setNumber] = useState("")
  const [githubToken, setGithubToken] = useState("")
  const [webhookSecret, setWebhookSecret] = useState("")
  const [accessRole, setAccessRole] = useState("viewer")
  const [newKey, setNewKey] = useState("")
  const [keys, setKeys] = useState<
    {
      id: string
      workspace_id: string
      name: string
      role: string
      revoked: number
    }[]
  >([])
  const [reviewId, setReviewId] = useState("")
  const [review, setReview] = useState<Review | null>(null)
  const [focusFinding, setFocusFinding] = useState("")
  const [report, setReport] = useState<Report | null>(null)
  const [question, setQuestion] = useState("")
  const [askRepo, setAskRepo] = useState("")
  const [answer, setAnswer] = useState<{
    answer: string
    status: string
    citations: Evidence[]
  } | null>(null)
  const [loginKey, setLoginKey] = useState("")
  const user = session.user
  const isDemo = mode === "demo",
    owner = user?.role === "owner",
    canWrite = isDemo || (!!user && user.role !== "viewer")

  const load = useCallback(async (demo = false) => {
    const next = await api<Portfolio>(demo ? "demo" : "portfolio")
    setData(next)
    setSnapshotTime(Date.now())
    return next
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    api<Session>("session", { signal: controller.signal })
      .then(async (value) => {
        if (controller.signal.aborted) return
        setSession(value)
        if (new URLSearchParams(window.location.search).get("demo") === "1") {
          await load(true)
          setMode("demo")
        } else if (value.user) {
          await load()
          setMode("live")
        } else setMode("login")
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(e.message)
          setMode("login")
        }
      })
    return () => controller.abort()
  }, [load])

  // Refresh status only. Provider calls and explicit retries are never triggered by polling.
  useEffect(() => {
    if (
      mode !== "live" ||
      !data.jobs.some((j) => ["queued", "running"].includes(j.status))
    )
      return
    const timer = setInterval(() => {
      load().catch((e) => setError(e.message))
    }, 6000)
    return () => clearInterval(timer)
  }, [mode, data.jobs, load])

  useEffect(() => {
    if (!reviewId) return
    const controller = new AbortController()
    const promise = isDemo
      ? Promise.resolve(data.reviews.find((r) => r.id === reviewId) || null)
      : api<Review>(`reviews/${reviewId}`, { signal: controller.signal })
    promise
      .then((r) => {
        if (!controller.signal.aborted) setReview(r)
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message)
      })
    return () => controller.abort()
  }, [reviewId, isDemo, data.reviews])

  const closeModal = useCallback(() => {
    setModal(null)
    setGithubToken("")
    setWebhookSecret("")
    setNewKey("")
  }, [])
  const filtered = <T extends { workspace_id: string }>(rows: T[]) =>
    rows.filter((r) => workspace === "all" || r.workspace_id === workspace)
  const matches = (text: string) =>
    text.toLowerCase().includes(search.toLowerCase())
  const repos = filtered(data.repositories).filter((r) => matches(r.full_name))
  const reviews = filtered(data.reviews).filter(
    (r) =>
      matches(r.title + " " + r.number) &&
      (isDemo || r.created >= snapshotTime / 1000 - +range * 86400)
  )
  const findings = filtered(data.findings).filter((f) =>
    matches(f.title + " " + f.evidence.path)
  )
  const open = findings.filter((f) => f.status === "open")
  const risks = repos.flatMap((r) =>
    (r.dependencies.packages || [])
      .filter((p) => p.advisories.length)
      .map((p) => ({ ...p, repo: r }))
  )
  const selectedWorkspaces = data.workspaces.filter(
    (w) => workspace === "all" || workspace === w.id
  )
  const workspaceName = (id: string) =>
    data.workspaces.find((w) => w.id === id)?.name || "Workspace"
  const repoName = (id: string) =>
    data.repositories.find((r) => r.id === id)?.full_name || "Repository"

  async function perform(message: string, fn: () => Promise<void>) {
    if (busy) return
    setBusy(message)
    setError("")
    setNotice("")
    try {
      await fn()
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The action could not complete."
      )
      if (e instanceof ApiError && e.status === 401) {
        contextVersion.current++
        setData(EMPTY)
        setReview(null)
        setReviewId("")
        setReport(null)
        setAnswer(null)
        setMode("login")
      }
    } finally {
      setBusy("")
    }
  }
  const mutate = <T,>(path: string, body?: unknown) =>
    api<T>(path, { method: "POST", body, csrf: user?.csrf })
  function navigate(next: View) {
    contextVersion.current++
    setView(next)
    setMenu(false)
    setSearch("")
    setAnswer(null)
    setQuestion("")
    setReviewId("")
    setReview(null)
    setReport(null)
  }
  function changeWorkspace(id: string) {
    contextVersion.current++
    setWorkspace(id)
    setSearch("")
    setReviewId("")
    setReview(null)
    setFocusFinding("")
    setReport(null)
    setAskRepo("")
    setQuestion("")
    setAnswer(null)
  }
  function openReview(id: string, finding = "") {
    setView("Code reviews")
    setReview(null)
    setReviewId(id)
    setFocusFinding(finding)
    setMenu(false)
  }
  function openModal(next: typeof modal) {
    setFormWorkspace(
      workspace !== "all" ? workspace : data.workspaces[0]?.id || ""
    )
    setFormRepo(repos[0]?.id || "")
    setName("")
    setNumber("")
    setNewKey("")
    setGithubToken("")
    setWebhookSecret("")
    setModal(next)
  }

  async function submitModal(event: React.FormEvent) {
    event.preventDefault()
    if (isDemo) {
      setNotice(
        "Repository connections and access keys require a signed-in agency. The sample review is available in Code reviews."
      )
      closeModal()
      return
    }
    await perform("Saving workspace changes…", async () => {
      if (modal === "workspace") await mutate("workspaces", { name })
      if (modal === "repository")
        await mutate(`workspaces/${formWorkspace}/repositories`, {
          repository: name,
        })
      if (modal === "review")
        await mutate(`repositories/${formRepo}/reviews`, { number: +number })
      if (modal === "connection")
        await mutate(`workspaces/${formWorkspace}/connection`, {
          github_token: githubToken || null,
          webhook_secret: webhookSecret || null,
        })
      if (modal === "access") {
        const value = await mutate<{ key: string }>(
          `workspaces/${formWorkspace}/access`,
          { name, role: accessRole }
        )
        setNewKey(value.key)
        setName("")
        await refreshKeys()
        return
      }
      await load()
      closeModal()
      setNotice(
        "Saved. Repository jobs appear below; progress is retained between sessions."
      )
    })
  }
  async function refreshKeys() {
    const value = await api<{ keys: typeof keys }>("access")
    setKeys(value.keys)
  }
  async function updateFinding(
    finding: Finding,
    status: string,
    feedback: string | null = finding.feedback
  ) {
    await perform("Recording your review decision…", async () => {
      const updated = isDemo
        ? { ...finding, status, feedback }
        : await mutate<Finding>(`findings/${finding.id}`, { status, feedback })
      setData((old) => ({
        ...old,
        findings: old.findings.map((f) => (f.id === updated.id ? updated : f)),
      }))
      setNotice(
        isDemo
          ? "Demo decision updated for this browser session. No repository changed."
          : "Decision saved. A resolved finding is reviewer-reported; no code was changed."
      )
    })
  }
  async function reviewDecision(status: string) {
    if (!review) return
    await perform("Recording review decision…", async () => {
      const updated = isDemo
        ? { ...review, status }
        : await mutate<Review>(`reviews/${review.id}/decision`, { status })
      setReview((previous) =>
        previous ? { ...previous, ...updated } : updated
      )
      setData((old) => ({
        ...old,
        reviews: old.reviews.map((r) => (r.id === updated.id ? updated : r)),
      }))
      setNotice(
        "Review decision recorded. GitHub PR state and repository code were not changed."
      )
    })
  }
  async function handleJob(job: Job, retry = false) {
    await perform(
      retry ? "Retrying the saved stage…" : "Processing one saved stage…",
      async () => {
        await mutate(`jobs/${job.id}/${retry ? "retry" : "run"}`)
        await load()
      }
    )
  }
  async function generateReport(id: string) {
    const version = contextVersion.current
    await perform("Preparing your client report…", async () => {
      let next: Report
      if (isDemo) {
        const items = data.findings.filter((f) => f.workspace_id === id)
        next = {
          id: "demo-report",
          workspace_id: id,
          period: "Sample week",
          title: `${workspaceName(id)} · Sample weekly report`,
          created: Date.now() / 1000,
          markdown: `# ${workspaceName(id)} · Sample weekly maintenance report\n\n**Illustrative demo. No live client measurements.**\n\n## What changed\n${data.reviews.filter((r) => r.workspace_id === id).length} sample pull request reviewed.\n\n## Open risks\n${items.filter((f) => f.status === "open").length} potential issues await review.\n\n${items.map((f) => `- **${f.title}** (${f.status})\n  Next step: ${f.next_step}\n  Evidence: \`${f.evidence.path}:${f.evidence.start}-${f.evidence.end}\` at \`${f.evidence.sha}\`.`).join("\n")}\n\n## Next steps\nValidate ownership controls and review the TLS patch preview. Add regression tests before merging.\n\n## Coverage\nTests were not executed. Resolved states are reviewer-reported. Stackwise did not modify or deploy any code.`,
        }
      } else {
        next = await mutate<Report>(`workspaces/${id}/reports`)
        await load()
      }
      if (version === contextVersion.current) {
        setReport(next)
        setView("Reports")
      }
    })
  }

  if (mode === "loading")
    return (
      <div className="sw-loading">
        <StackwiseBrand />
        <LoaderCircle className="sw-spin" size={22} />
        <p>Opening your maintenance desk…</p>
      </div>
    )
  if (mode === "login")
    return (
      <div className="sw-login">
        <Link href="/" aria-label="Stackwise home">
          <StackwiseBrand />
        </Link>
        <main>
          <span className="sw-eyebrow">WELCOME TO YOUR MAINTENANCE DESK</span>
          <h1>
            Good work starts
            <br />
            with a clear view.
          </h1>
          <p>
            Sign in with your agency or workspace access key. Client keys open
            only their assigned workspace.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void perform("Signing in…", async () => {
                await api("login", { method: "POST", body: { key: loginKey } })
                setLoginKey("")
                const next = await api<Session>("session")
                setSession(next)
                await load()
                setMode("live")
              })
            }}
          >
            <label>
              Access key
              <input
                autoComplete="current-password"
                type="password"
                value={loginKey}
                onChange={(e) => setLoginKey(e.target.value)}
                required
                minLength={16}
                placeholder="Enter your private access key"
              />
            </label>
            <button className="sw-btn sw-btn-green" disabled={!!busy}>
              {busy || "Open workspace"}
              <ArrowRight size={16} />
            </button>
          </form>
          {error && (
            <p role="alert" className="sw-error">
              {error}
            </p>
          )}
          <div className="sw-login-divider">OR TAKE A LOOK AROUND</div>
          <button
            className="sw-btn sw-btn-outline"
            disabled={!!busy}
            onClick={() =>
              void perform("Opening sample portfolio…", async () => {
                await load(true)
                setMode("demo")
              })
            }
          >
            Explore the interactive demo <ArrowUpRight size={16} />
          </button>
          <small>Sample data only. No account or API key needed.</small>
          {Object.values(session.setup).length > 0 &&
            (!session.setup.database || !session.setup.owner_key) && (
              <details className="sw-setup-note">
                <summary>Deployment setup required</summary>
                <p>
                  Connect Postgres and configure STACKWISE_ADMIN_TOKEN and
                  STACKWISE_APP_URL in Vercel. See docs/STACKWISE_DEPLOY.md.
                  Secret values belong in Vercel, never in chat.
                </p>
              </details>
            )}
        </main>
        <div className="sw-login-foot">
          <LockKeyhole size={14} /> Private sessions · Workspace-scoped access
        </div>
      </div>
    )

  return (
    <div className={`sw-app ${menu ? "sw-menu-open" : ""}`}>
      <a className="sw-skip" href="#workspace-main">
        Skip to workspace
      </a>
      {menu && (
        <button
          className="sw-mobile-shade"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className="sw-sidebar">
        <Link href="/" aria-label="Stackwise home">
          <StackwiseBrand />
        </Link>
        <div className="sw-agency">
          <span className="sw-agency-icon">{isDemo ? "A" : "S"}</span>
          <div>
            <strong>{isDemo ? "Acme Studio" : "Agency workspace"}</strong>
            <small>
              {isDemo
                ? "Sample portfolio"
                : user?.role === "owner"
                  ? "Agency owner"
                  : "Client workspace"}
            </small>
          </div>
          <ChevronDown size={14} />
        </div>
        <span className="sw-nav-label">WORKSPACE</span>
        <nav aria-label="Workspace navigation">
          {navigation.map((n) => (
            <button
              key={n.name}
              onClick={() => navigate(n.name)}
              className={view === n.name ? "active" : ""}
              aria-current={view === n.name ? "page" : undefined}
            >
              <n.icon size={17} strokeWidth={1.6} />
              {n.name}
              {n.name === "Code reviews" && open.length > 0 && (
                <span>{open.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sw-sidebar-bottom">
          <div className="sw-sidebar-note">
            <ShieldCheck size={18} />
            <strong>Your team makes the call.</strong>
            <p>Every suggestion stays a suggestion until a human approves.</p>
          </div>
          <button className="sw-user" onClick={() => navigate("Settings")}>
            <span className="sw-avatar">
              {isDemo ? "AS" : user?.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong>{isDemo ? "Demo workspace" : user?.name}</strong>
              <small>{isDemo ? "Explore freely" : label(user?.role)}</small>
            </div>
            <Settings2 size={15} />
          </button>
        </div>
      </aside>
      <div className="sw-app-main">
        <header className="sw-topbar">
          <div>
            <button
              className="sw-icon-btn sw-mobile-toggle"
              onClick={() => setMenu(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{view}</strong>
          </div>
          <div>
            <span className="sw-topbar-status">
              <span className="sw-live-dot" />
              {isDemo ? "Sample mode" : "Connected workspace"}
            </span>
            <a
              className="sw-icon-btn"
              href="https://github.com/qaiser931/fintech-codegraph-rag/blob/main/docs/STACKWISE_DEPLOY.md"
              target="_blank"
              rel="noreferrer"
              aria-label="Deployment documentation"
            >
              <BookOpen size={17} />
            </a>
          </div>
        </header>
        {isDemo && (
          <div className="sw-demo-bar">
            <span>
              <Sparkles size={14} /> You’re exploring a sample portfolio. All
              metrics and findings are illustrative; decisions stay in this
              session.
            </span>
            <button
              onClick={() => {
                setData(EMPTY)
                setReview(null)
                setReviewId("")
                setAnswer(null)
                setReport(null)
                setMode("login")
                window.history.replaceState(null, "", "/dashboard")
              }}
            >
              Connect your repositories <ArrowRight size={13} />
            </button>
          </div>
        )}
        <main id="workspace-main" className="sw-workspace-main">
          <div className="sw-page-heading">
            <div>
              <span className="sw-eyebrow">
                {isDemo ? "ACME STUDIO" : "YOUR MAINTENANCE DESK"}
              </span>
              <h1>
                {view === "Overview"
                  ? "Agency overview"
                  : view === "Code reviews" && reviewId
                    ? "Review the change"
                    : view}
              </h1>
              <p>
                {
                  {
                    Overview:
                      "One clear view of what needs your team’s attention.",
                    Workspaces:
                      "Keep every client’s code, context and priorities together.",
                    "Code reviews":
                      "Understand the change. Inspect the evidence. Make the call.",
                    Dependencies:
                      "Known advisory matches, with coverage you can inspect.",
                    Reports:
                      "Technical findings, translated into clear next steps.",
                    Settings:
                      "Connections, access and a few important boundaries.",
                  }[view]
                }
              </p>
            </div>
            <div className="sw-heading-actions">
              {view === "Overview" && (
                <button
                  className="sw-btn sw-btn-outline sw-btn-small"
                  disabled={!!busy}
                  onClick={() =>
                    void perform("Refreshing portfolio…", async () => {
                      await load(isDemo)
                      setNotice("Portfolio refreshed.")
                    })
                  }
                >
                  <RefreshCw size={14} />
                  Refresh
                </button>
              )}
              {(["Workspaces", "Overview"] as View[]).includes(view) &&
                (owner || isDemo) && (
                  <button
                    className="sw-btn sw-btn-green sw-btn-small"
                    onClick={() => openModal("workspace")}
                  >
                    <Plus size={15} />
                    Add workspace
                  </button>
                )}
              {view === "Code reviews" && canWrite && (
                <button
                  className="sw-btn sw-btn-green sw-btn-small"
                  disabled={!repos.length || !!busy}
                  onClick={() =>
                    isDemo ? openReview("demo-review") : openModal("review")
                  }
                >
                  <GitPullRequest size={15} />
                  Review a PR
                </button>
              )}
            </div>
          </div>
          {error && (
            <div role="alert" className="sw-alert sw-alert-error">
              <CircleAlert size={17} />
              <span>{error}</span>
              <button
                className="sw-icon-btn"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="sw-alert sw-alert-success">
              <Check size={17} />
              <span>{notice}</span>
              <button
                className="sw-icon-btn"
                aria-label="Dismiss notice"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {busy && (
            <div role="status" className="sw-busy">
              <LoaderCircle size={15} className="sw-spin" />
              {busy}
            </div>
          )}
          {view !== "Settings" && !reviewId && (
            <div className="sw-filter-row">
              <div className="sw-select-wrap">
                <Layers3 size={14} />
                <select
                  aria-label="Filter workspace"
                  value={workspace}
                  onChange={(e) => changeWorkspace(e.target.value)}
                >
                  <option value="all">All workspaces</option>
                  {data.workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sw-select-wrap">
                <Activity size={14} />
                <select
                  aria-label="Review period"
                  value={range}
                  onChange={(e) => setRange(e.target.value)}
                >
                  <option value="7">Last 7 days</option>
                  <option value="30">Last 30 days</option>
                  <option value="90">Last 90 days</option>
                </select>
              </div>
              <label className="sw-search">
                <Search size={15} />
                <input
                  aria-label="Search loaded records"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Find a repository or finding…"
                />
              </label>
            </div>
          )}

          {view === "Overview" && (
            <>
              <div className="sw-stats">
                {[
                  {
                    name: "Repositories",
                    value: repos.length,
                    meta: `${repos.filter((r) => r.status === "indexed").length} indexed`,
                    icon: GitBranch,
                    tone: "green",
                  },
                  {
                    name: "Open findings",
                    value: open.length,
                    meta: `${open.filter((f) => f.severity === "high").length} high priority`,
                    icon: CircleAlert,
                    tone: "high",
                  },
                  {
                    name: "PRs reviewed",
                    value: reviews.length,
                    meta: isDemo ? "Sample review" : `Last ${range} days`,
                    icon: GitPullRequest,
                    tone: "green",
                  },
                  {
                    name: "Dependency risks",
                    value: risks.length,
                    meta: "Direct versions with advisories",
                    icon: ShieldCheck,
                    tone: "medium",
                  },
                ].map((s) => (
                  <div className="sw-stat" key={s.name}>
                    <div>
                      <span>{s.name}</span>
                      <s.icon size={17} strokeWidth={1.5} />
                    </div>
                    <strong>
                      {s.value}
                      <small className={`sw-meta-${s.tone}`}>{s.meta}</small>
                    </strong>
                  </div>
                ))}
              </div>
              <div className="sw-overview-grid">
                <Panel
                  title={isDemo ? "Repository health trend" : "Review activity"}
                  hint={
                    isDemo
                      ? "Illustrative sample trend · not a measured health score"
                      : "Completed review records over the last 7 days"
                  }
                  action={
                    <Badge>{isDemo ? "Illustrative" : "Last 7 days"}</Badge>
                  }
                >
                  <Trend
                    data={data}
                    workspace={workspace}
                    demo={isDemo}
                    at={snapshotTime}
                  />
                  <div className="sw-chart-legend">
                    <span className="sw-live-dot" />
                    {isDemo ? "Sample portfolio health" : "Reviews completed"}
                    <span>Human approval always required</span>
                  </div>
                </Panel>
                <Panel
                  title="Priority actions"
                  hint="The next useful thing to do"
                  action={<Badge tone="high">{open.length} open</Badge>}
                >
                  <div className="sw-priorities">
                    {open
                      .sort(
                        (a, b) =>
                          (severityRank[a.severity] ?? 4) -
                          (severityRank[b.severity] ?? 4)
                      )
                      .slice(0, 3)
                      .map((f) => (
                        <button
                          key={f.id}
                          onClick={() => openReview(f.review_id, f.id)}
                        >
                          <div>
                            <Badge tone={f.severity}>
                              {f.severity.toUpperCase()}
                            </Badge>
                            <small>{workspaceName(f.workspace_id)}</small>
                          </div>
                          <strong>{f.title}</strong>
                          <p>{f.next_step}</p>
                          {new Set(
                            data.findings
                              .filter(
                                (item) =>
                                  item.title === f.title &&
                                  item.evidence.path === f.evidence.path &&
                                  item.workspace_id === f.workspace_id
                              )
                              .map((item) => item.review_id)
                          ).size > 1 && (
                            <small>
                              Seen across{" "}
                              {
                                new Set(
                                  data.findings
                                    .filter(
                                      (item) =>
                                        item.title === f.title &&
                                        item.evidence.path ===
                                          f.evidence.path &&
                                        item.workspace_id === f.workspace_id
                                    )
                                    .map((item) => item.review_id)
                                ).size
                              }{" "}
                              reviews
                            </small>
                          )}
                          <span>
                            Inspect evidence <ArrowUpRight size={12} />
                          </span>
                        </button>
                      ))}
                    {!open.length && (
                      <Empty title="Your next step is clear">
                        {repos.length
                          ? "No open findings in this view. Review a pull request to build the evidence."
                          : "Connect a repository to begin reviewing code."}
                      </Empty>
                    )}
                  </div>
                </Panel>
              </div>
              <Panel
                title="Workspace health"
                hint="Client boundaries stay intact as you move between projects"
                action={
                  <button
                    className="sw-text-link"
                    onClick={() => navigate("Workspaces")}
                  >
                    View workspaces <ArrowRight size={14} />
                  </button>
                }
              >
                <div className="sw-table-scroll">
                  <table className="sw-table">
                    <thead>
                      <tr>
                        <th>WORKSPACE</th>
                        <th>REPOSITORIES</th>
                        <th>OPEN RISKS</th>
                        <th>LAST REVIEW</th>
                        <th>STATUS</th>
                        <th>
                          <span className="sw-sr-only">Open workspace</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedWorkspaces.map((w) => {
                        const rs = data.repositories.filter(
                            (r) => r.workspace_id === w.id
                          ),
                          fs = data.findings.filter(
                            (f) =>
                              f.workspace_id === w.id && f.status === "open"
                          ),
                          last = data.reviews.find(
                            (r) => r.workspace_id === w.id
                          )
                        return (
                          <tr key={w.id}>
                            <td>
                              <div className="sw-cell-name">
                                <span
                                  className={`sw-avatar sw-avatar-${w.color}`}
                                >
                                  {w.name.slice(0, 1)}
                                </span>
                                <div>
                                  <strong>{w.name}</strong>
                                  <small>Client workspace</small>
                                </div>
                              </div>
                            </td>
                            <td>
                              {rs.length}
                              <small className="sw-muted"> repositories</small>
                            </td>
                            <td>
                              {fs.length}
                              <small className="sw-muted"> open</small>
                            </td>
                            <td>
                              {isDemo && last
                                ? "Sample review"
                                : relative(last?.created)}
                            </td>
                            <td>
                              <Badge
                                tone={
                                  fs.length
                                    ? "high"
                                    : rs.some((r) => !r.indexed)
                                      ? "medium"
                                      : "green"
                                }
                              >
                                {fs.length
                                  ? "Needs attention"
                                  : rs.some((r) => !r.indexed) || !rs.length
                                    ? "Awaiting index"
                                    : "No open findings"}
                              </Badge>
                            </td>
                            <td>
                              <button
                                className="sw-icon-btn"
                                aria-label={`Open ${w.name}`}
                                onClick={() => {
                                  changeWorkspace(w.id)
                                  setView("Workspaces")
                                }}
                              >
                                <ChevronRight size={17} />
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  {!selectedWorkspaces.length && (
                    <Empty
                      title="Your portfolio starts here"
                      action={
                        owner ? (
                          <button
                            className="sw-btn sw-btn-green"
                            onClick={() => openModal("workspace")}
                          >
                            Add your first workspace
                          </button>
                        ) : undefined
                      }
                    >
                      Create a separate workspace for each client, then connect
                      their repositories.
                    </Empty>
                  )}
                </div>
              </Panel>
              <div className="sw-bottom-note">
                <LockKeyhole size={14} /> Code context is retrieved within the
                selected workspace.
                <span>
                  {isDemo
                    ? "Demo data"
                    : "Metrics describe loaded records; no composite health score is inferred."}
                </span>
              </div>
            </>
          )}

          {view === "Workspaces" && (
            <>
              <div className="sw-workspace-cards">
                {selectedWorkspaces.map((w) => (
                  <article className="sw-panel sw-workspace-card" key={w.id}>
                    <span className={`sw-avatar sw-avatar-${w.color}`}>
                      {w.name[0]}
                    </span>
                    <h2>{w.name}</h2>
                    <p>
                      {
                        data.repositories.filter((r) => r.workspace_id === w.id)
                          .length
                      }{" "}
                      repositories ·{" "}
                      {
                        data.findings.filter(
                          (f) => f.workspace_id === w.id && f.status === "open"
                        ).length
                      }{" "}
                      open findings
                    </p>
                    <div>
                      <Badge tone={w.github_connected ? "green" : "neutral"}>
                        {isDemo
                          ? "Sample workspace"
                          : w.github_connected
                            ? "GitHub token stored"
                            : "Public repositories"}
                      </Badge>
                      <button
                        className="sw-text-link"
                        onClick={() => changeWorkspace(w.id)}
                      >
                        Focus <ArrowRight size={14} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
              <Panel
                title="Connected repositories"
                hint="Snapshots are pinned to a commit; a successful refresh replaces only that repository’s current index."
                action={
                  (owner || isDemo) && (
                    <button
                      className="sw-btn sw-btn-outline sw-btn-small"
                      disabled={!data.workspaces.length}
                      onClick={() => openModal("repository")}
                    >
                      <Plus size={14} />
                      Connect repository
                    </button>
                  )
                }
              >
                <div className="sw-repo-list">
                  {repos.map((r) => (
                    <article key={r.id}>
                      <div className="sw-repo-icon">
                        <GitBranch size={21} />
                      </div>
                      <div className="sw-repo-info">
                        <strong>{r.full_name}</strong>
                        <p>
                          {workspaceName(r.workspace_id)} · {r.file_count}{" "}
                          supported files · {r.branch || "Default branch"}
                        </p>
                        <small>
                          {r.sha
                            ? `SHA ${r.sha.slice(0, 12)}`
                            : "Waiting for first index"}{" "}
                          · {relative(r.indexed)}
                        </small>
                        <div className="sw-repo-pulls">
                          {r.prs.slice(0, 3).map((pr) => (
                            <button
                              key={pr.number}
                              className="sw-text-link"
                              disabled={!canWrite || !!busy}
                              onClick={() => {
                                if (isDemo) openReview("demo-review")
                                else {
                                  setFormWorkspace(r.workspace_id)
                                  setFormRepo(r.id)
                                  setNumber(String(pr.number))
                                  setModal("review")
                                }
                              }}
                            >
                              <GitPullRequest size={12} />#{pr.number}{" "}
                              {pr.title}
                              {pr.draft ? " · Draft" : ""}
                            </button>
                          ))}
                          {r.prs.length > 3 && (
                            <small>
                              +{r.prs.length - 3} more open PRs in the loaded
                              GitHub results
                            </small>
                          )}
                        </div>
                      </div>
                      <Badge tone={r.status === "indexed" ? "green" : "medium"}>
                        {label(r.status)}
                      </Badge>
                      {canWrite && (
                        <button
                          className="sw-icon-btn"
                          aria-label={`Refresh ${r.full_name}`}
                          disabled={!!busy || isDemo}
                          onClick={() =>
                            void perform(
                              "Starting a repository refresh…",
                              async () => {
                                await mutate(`repositories/${r.id}/index`)
                                await load()
                              }
                            )
                          }
                        >
                          <RefreshCw size={16} />
                        </button>
                      )}
                    </article>
                  ))}
                  {!repos.length && (
                    <Empty title="Connect your first repository">
                      Add an owner/repository name or GitHub URL. For private
                      code, configure a read-only token in Settings first.
                    </Empty>
                  )}
                </div>
              </Panel>
              {!!repos.length && (
                <Panel
                  title="Ask your codebase"
                  hint="Answers use source citations from this repository’s indexed commit. Lexical CodeRAG; no scripts are executed."
                >
                  <form
                    className="sw-ask-form"
                    onSubmit={(e) => {
                      e.preventDefault()
                      setAnswer(null)
                      void perform("Finding relevant code…", async () => {
                        const version = contextVersion.current
                        if (isDemo) {
                          setAnswer({
                            answer:
                              "In the sample account route, get_account passes the request’s user_id to fetch_account. The shown route does not perform an ownership check. Inspect auth/routes.py lines 7–9; other upstream controls are not demonstrated.",
                            status: "authored_demo",
                            citations: data.findings
                              .slice(0, 1)
                              .map((f) => f.evidence),
                          })
                        } else {
                          const response = await mutate<{
                            answer: string
                            status: string
                            citations: Evidence[]
                          }>(`repositories/${askRepo || repos[0].id}/ask`, {
                            question,
                          })
                          if (version === contextVersion.current)
                            setAnswer(response)
                        }
                      })
                    }}
                  >
                    <select
                      aria-label="Repository to ask"
                      value={askRepo || repos[0].id}
                      onChange={(e) => {
                        contextVersion.current++
                        setAskRepo(e.target.value)
                        setAnswer(null)
                        setQuestion("")
                      }}
                    >
                      {repos.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.full_name}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="Codebase question"
                      value={question}
                      onChange={(e) => {
                        contextVersion.current++
                        setQuestion(e.target.value)
                        setAnswer(null)
                      }}
                      minLength={3}
                      maxLength={1500}
                      required
                      placeholder="How is account ownership checked?"
                    />
                    <button
                      className="sw-btn sw-btn-green"
                      disabled={!!busy || !canWrite}
                    >
                      Ask code <ArrowRight size={15} />
                    </button>
                  </form>
                  {answer && (
                    <div className="sw-answer">
                      <Badge>{label(answer.status)}</Badge>
                      <p>{answer.answer}</p>
                      {answer.citations.map((e, i) => (
                        <EvidenceBlock evidence={e} key={i} />
                      ))}
                    </div>
                  )}
                </Panel>
              )}
            </>
          )}

          {view === "Code reviews" &&
            (reviewId ? (
              <>
                {
                  <button
                    className="sw-text-link sw-back"
                    onClick={() => {
                      setReviewId("")
                      setReview(null)
                    }}
                  >
                    <ArrowLeft size={14} />
                    All code reviews
                  </button>
                }
                {review ? (
                  <ReviewDesk
                    key={review.id}
                    review={review}
                    findings={(
                      review.findings ||
                      data.findings.filter((f) => f.review_id === review.id)
                    ).map((f) => {
                      const current = data.findings.find(
                        (item) => item.id === f.id
                      )
                      return current
                        ? {
                            ...f,
                            status: current.status,
                            feedback: current.feedback,
                          }
                        : f
                    })}
                    repoName={repoName(review.repo_id)}
                    workspaceName={workspaceName(review.workspace_id)}
                    focus={focusFinding}
                    canWrite={canWrite}
                    busy={!!busy}
                    demo={isDemo}
                    onDecision={updateFinding}
                    onReviewDecision={reviewDecision}
                    onRetryAI={() =>
                      void perform(
                        "Retrying unavailable AI review…",
                        async () => {
                          await mutate(`reviews/${review.id}/retry-ai`)
                          await load()
                          setNotice(
                            "Explicit AI retry saved. Existing human decisions are retained; a changed PR head requires a new review."
                          )
                        }
                      )
                    }
                  />
                ) : (
                  <div className="sw-empty">
                    <LoaderCircle className="sw-spin" />
                    <p>Loading commit-pinned evidence…</p>
                  </div>
                )}
              </>
            ) : (
              <Panel
                title="Pull request reviews"
                hint="Potential issues stay open for your team’s decision"
              >
                <div className="sw-review-list">
                  {reviews.map((r) => {
                    const fs = data.findings.filter(
                        (f) => f.review_id === r.id
                      ),
                      active = fs.filter((f) => f.status === "open")
                    return (
                      <button key={r.id} onClick={() => openReview(r.id)}>
                        <span className="sw-review-glyph">
                          <GitPullRequest size={21} />
                        </span>
                        <div>
                          <small>
                            {workspaceName(r.workspace_id)} /{" "}
                            {repoName(r.repo_id)}
                          </small>
                          <strong>
                            #{r.number} <span>{r.title}</span>
                          </strong>
                          <p>
                            {active.length} open findings ·{" "}
                            {isDemo ? "Sample PR" : relative(r.created)} ·{" "}
                            {r.sha.slice(0, 8)}
                          </p>
                        </div>
                        <Badge tone={active.length ? "medium" : "green"}>
                          {active.length ? "Needs review" : "Reviewed"}
                        </Badge>
                        <ChevronRight size={17} />
                      </button>
                    )
                  })}
                  {!reviews.length && (
                    <Empty title="A second pair of eyes for your next PR">
                      Connect a repository, then start a review by PR number.
                      Static checks and optional AI suggestions include
                      inspectable source references.
                    </Empty>
                  )}
                </div>
              </Panel>
            ))}

          {view === "Dependencies" && (
            <>
              <div className="sw-alert sw-alert-info">
                <ShieldCheck size={17} />
                <span>
                  Checks cover exact direct npm/PyPI versions. Version ranges
                  and transitive dependencies are not resolved. An unavailable
                  check never means a clean bill of health.
                </span>
              </div>
              <Panel
                title="Dependency advisory matches"
                hint={
                  isDemo
                    ? "Sample advisory marker — not a live OSV result"
                    : "OSV matches for the indexed repository snapshot"
                }
              >
                <div className="sw-table-scroll">
                  <table className="sw-table">
                    <thead>
                      <tr>
                        <th>PACKAGE</th>
                        <th>REPOSITORY</th>
                        <th>INSTALLED VERSION</th>
                        <th>ADVISORIES</th>
                        <th>NEXT STEP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {risks.map((p, i) => (
                        <tr key={i}>
                          <td>
                            <strong>{p.name}</strong>
                            <small className="sw-block sw-muted">
                              {p.ecosystem}
                            </small>
                          </td>
                          <td>
                            {p.repo.full_name}
                            <small className="sw-block sw-muted">
                              {p.path}
                            </small>
                          </td>
                          <td>
                            <code>{p.version}</code>
                          </td>
                          <td>
                            {p.advisories.map((v) =>
                              v.id.startsWith("DEMO") ? (
                                <Badge key={v.id} tone="medium">
                                  Sample advisory
                                </Badge>
                              ) : (
                                <a
                                  className="sw-advisory"
                                  key={v.id}
                                  href={`https://osv.dev/vulnerability/${encodeURIComponent(v.id)}`}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {v.id}
                                  <ExternalLink size={11} />
                                </a>
                              )
                            )}
                          </td>
                          <td>
                            Verify a compatible update
                            <br />
                            <small className="sw-muted">
                              Review changelog and test
                            </small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!risks.length && (
                    <Empty title="No advisory matches in this view">
                      Inspect the scan coverage below before treating a
                      repository as checked.
                    </Empty>
                  )}
                </div>
              </Panel>
              <Panel title="Scan coverage">
                <div className="sw-repo-list">
                  {repos.map((r) => (
                    <article key={r.id}>
                      <ShieldCheck size={20} />
                      <div className="sw-repo-info">
                        <strong>{r.full_name}</strong>
                        <p>
                          {r.dependencies.packages?.length || 0} exact versions
                          · {r.dependencies.unresolved || 0} unresolved
                          declarations
                        </p>
                        <small>
                          {r.dependencies.note ||
                            `Commit ${r.sha.slice(0, 10) || "not indexed"}`}
                        </small>
                      </div>
                      <Badge
                        tone={
                          r.dependencies.status === "complete"
                            ? "green"
                            : "medium"
                        }
                      >
                        {label(r.dependencies.status || "not_run")}
                      </Badge>
                    </article>
                  ))}
                </div>
              </Panel>
            </>
          )}

          {view === "Reports" && (
            <div className="sw-reports-grid">
              <Panel
                title="Client reports"
                hint="A weekly snapshot, ready to share"
              >
                <div className="sw-report-workspaces">
                  {selectedWorkspaces.map((w) => (
                    <div key={w.id}>
                      <span className="sw-avatar">{w.name[0]}</span>
                      <div>
                        <strong>{w.name}</strong>
                        <small>Risks, resolved findings and next steps</small>
                      </div>
                      <button
                        className="sw-icon-btn"
                        disabled={!canWrite || !!busy}
                        aria-label={`Generate report for ${w.name}`}
                        onClick={() => void generateReport(w.id)}
                      >
                        <Plus size={17} />
                      </button>
                    </div>
                  ))}
                </div>
                {filtered(data.reports).map((r) => (
                  <button
                    className="sw-report-row"
                    key={r.id}
                    onClick={() =>
                      void perform("Opening report…", async () =>
                        setReport(await api<Report>(`reports/${r.id}`))
                      )
                    }
                  >
                    <FileText size={17} />
                    <div>
                      <strong>{r.title}</strong>
                      <small>{relative(r.created)}</small>
                    </div>
                    <ChevronRight size={15} />
                  </button>
                ))}
              </Panel>
              <Panel
                title={report?.title || "A clear update for every client"}
                action={
                  report && (
                    <button
                      className="sw-btn sw-btn-outline sw-btn-small"
                      onClick={() =>
                        download(
                          report.markdown || "",
                          `stackwise-${report.period}.md`
                        )
                      }
                    >
                      <Download size={14} />
                      Download
                    </button>
                  )
                }
              >
                {report ? (
                  <div className="sw-report-body">
                    <ReactMarkdown skipHtml>
                      {report.markdown || ""}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <Empty title="Turn maintenance into a useful update">
                    Choose a workspace on the left to generate a report. It
                    distinguishes open potential issues, reviewer-reported
                    resolutions and checks that were not run.
                  </Empty>
                )}
              </Panel>
            </div>
          )}

          {view === "Settings" && (
            <>
              <Panel
                title="Agency access"
                hint="Access-key sessions for the first version. SSO and billing are not implemented."
              >
                <div className="sw-settings-row">
                  <div>
                    <strong>{isDemo ? "Demo session" : user?.name}</strong>
                    <p>
                      {isDemo
                        ? "Explore sample data without connecting an account."
                        : `${label(user?.role)} · Sessions expire after 8 hours.`}
                    </p>
                  </div>
                  <button
                    className="sw-btn sw-btn-outline sw-btn-small"
                    disabled={!!busy}
                    onClick={() =>
                      void perform("Closing session…", async () => {
                        if (!isDemo) await mutate("logout")
                        setData(EMPTY)
                        setReview(null)
                        setReport(null)
                        setAnswer(null)
                        setSession({ ...session, user: null })
                        setWorkspace("all")
                        setMode("login")
                        window.history.replaceState(null, "", "/dashboard")
                      })
                    }
                  >
                    <LogOut size={14} />
                    {isDemo ? "Leave demo" : "Sign out"}
                  </button>
                </div>
              </Panel>
              {(owner || isDemo) && (
                <Panel
                  title="GitHub connections"
                  hint="Each client workspace stores its own encrypted read-only token. Public repositories can be read without a token."
                  action={
                    <button
                      className="sw-btn sw-btn-outline sw-btn-small"
                      disabled={!data.workspaces.length}
                      onClick={() => openModal("connection")}
                    >
                      Configure connection <ArrowUpRight size={14} />
                    </button>
                  }
                >
                  {data.workspaces.map((w) => (
                    <div className="sw-settings-row" key={w.id}>
                      <div>
                        <strong>{w.name}</strong>
                        <p>
                          {isDemo
                            ? "Sample connection"
                            : w.github_connected
                              ? "Encrypted token saved · Contents, Pull requests and Checks read access required"
                              : "No private repository token saved"}
                        </p>
                        <code className="sw-webhook-path">
                          /api/webhooks/{w.id}
                        </code>
                      </div>
                      <Badge>
                        {w.webhook_configured
                          ? "Webhook configured"
                          : "Manual reviews available"}
                      </Badge>
                    </div>
                  ))}
                </Panel>
              )}
              {(owner || isDemo) && (
                <Panel
                  title="Client access keys"
                  hint="A viewer can read only its assigned workspace. A reviewer can also start reviews and record decisions."
                  action={
                    <div className="sw-heading-actions">
                      {!isDemo && (
                        <button
                          className="sw-btn sw-btn-outline sw-btn-small"
                          onClick={() =>
                            void perform("Loading access keys…", refreshKeys)
                          }
                        >
                          Load keys
                        </button>
                      )}
                      <button
                        className="sw-btn sw-btn-outline sw-btn-small"
                        disabled={!data.workspaces.length}
                        onClick={() => openModal("access")}
                      >
                        <Plus size={14} />
                        Create key
                      </button>
                    </div>
                  }
                >
                  {keys.map((k) => (
                    <div key={k.id} className="sw-settings-row">
                      <div>
                        <strong>{k.name}</strong>
                        <p>
                          {workspaceName(k.workspace_id)} · {k.role}
                        </p>
                      </div>
                      {k.revoked ? (
                        <Badge>Revoked</Badge>
                      ) : (
                        <button
                          className="sw-text-link"
                          disabled={!!busy}
                          onClick={() =>
                            void perform("Revoking access…", async () => {
                              await mutate(`access/${k.id}/revoke`)
                              await refreshKeys()
                            })
                          }
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  ))}
                  {!keys.length && (
                    <p className="sw-panel-copy">
                      Keys are shown once at creation. Store and share them
                      privately; no key values are listed here.
                    </p>
                  )}
                </Panel>
              )}
              <Panel title="Runtime & boundaries">
                <div className="sw-settings-grid">
                  {[
                    {
                      n: "Application",
                      v: "Next.js + Python / FastAPI on Vercel",
                    },
                    {
                      n: "Persistence",
                      v: session.setup.database
                        ? "Managed database configured"
                        : "Postgres connection required for live workspaces",
                    },
                    {
                      n: "Review jobs",
                      v: session.setup.queue
                        ? "Vercel Queues enabled"
                        : "Explicit, resumable job stages",
                    },
                    {
                      n: "AI generation",
                      v: session.setup.ai
                        ? "Groq configured · bounded requests"
                        : "Not configured · static checks remain available",
                    },
                  ].map((x) => (
                    <div key={x.n}>
                      <small>{x.n}</small>
                      <strong>{x.v}</strong>
                    </div>
                  ))}
                </div>
                <p className="sw-panel-copy">
                  Repository content is untrusted. Secret redaction is
                  heuristic; exclude sensitive files before connecting code.
                  Stackwise never executes repository code, applies patches,
                  merges PRs or deploys changes.
                </p>
              </Panel>
              <Panel
                title="Review quality"
                hint="Feedback measures your team’s review decisions, not a benchmark score."
              >
                <div className="sw-settings-grid">
                  <div>
                    <small>Marked useful</small>
                    <strong>
                      {
                        data.findings.filter((f) => f.feedback === "useful")
                          .length
                      }
                    </strong>
                  </div>
                  <div>
                    <small>Flagged false positive</small>
                    <strong>
                      {
                        data.findings.filter(
                          (f) => f.feedback === "false_positive"
                        ).length
                      }
                    </strong>
                  </div>
                  <div>
                    <small>Review latency</small>
                    <strong>
                      {isDemo
                        ? "Not measured in demo"
                        : data.reviews.length
                          ? `${(data.reviews.reduce((s, r) => s + r.elapsed, 0) / data.reviews.length).toFixed(1)}s average analysis stage`
                          : "No completed reviews"}
                    </strong>
                  </div>
                  <div>
                    <small>Retrieval relevance</small>
                    <strong>Inspectable citations; unscored</strong>
                  </div>
                </div>
              </Panel>
            </>
          )}

          {!isDemo &&
            !!filtered(data.jobs).filter((j) => j.status !== "complete")
              .length && (
              <Panel
                title="Saved job progress"
                hint="Each stage is durable. A failed stage is retried only when you request it."
                className="sw-jobs"
              >
                <div className="sw-job-list">
                  {filtered(data.jobs)
                    .filter((j) => j.status !== "complete")
                    .slice(0, 8)
                    .map((j) => (
                      <div key={j.id}>
                        <span className={`sw-job-dot ${j.status}`} />
                        <div>
                          <strong>{repoName(j.repo_id)}</strong>
                          <p>
                            {label(j.kind)} · {label(j.stage)} ·{" "}
                            {label(j.status)}
                          </p>
                          {j.error && (
                            <small className="sw-error">{j.error}</small>
                          )}
                        </div>
                        {canWrite && (
                          <button
                            className="sw-btn sw-btn-outline sw-btn-small"
                            disabled={!!busy || j.status === "running"}
                            onClick={() =>
                              void handleJob(j, j.status === "failed")
                            }
                          >
                            {j.status === "failed"
                              ? "Retry saved stage"
                              : "Run next stage"}
                            <ArrowRight size={13} />
                          </button>
                        )}
                      </div>
                    ))}
                </div>
              </Panel>
            )}
        </main>
        <footer className="sw-workspace-footer">
          <span>
            <StackwiseBrand small />{" "}
            <span>Context for your code. Clarity for your clients.</span>
          </span>
          <span>{isDemo ? "SAMPLE WORKSPACE" : "HUMAN APPROVAL REQUIRED"}</span>
        </footer>
      </div>
      {modal && (
        <Dialog
          title={
            {
              workspace: "Create a client workspace",
              repository: "Connect a repository",
              review: "Review a pull request",
              connection: "Configure GitHub connection",
              access: "Create workspace access key",
            }[modal]
          }
          close={closeModal}
        >
          <form onSubmit={submitModal} className="sw-modal-form">
            {error && (
              <p role="alert" className="sw-error">
                {error}
              </p>
            )}
            {modal !== "workspace" && (
              <label>
                Client workspace
                <select
                  disabled={!!newKey}
                  value={formWorkspace}
                  onChange={(e) => {
                    setFormWorkspace(e.target.value)
                    setFormRepo(
                      data.repositories.find(
                        (r) => r.workspace_id === e.target.value
                      )?.id || ""
                    )
                  }}
                  required
                >
                  {data.workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {["workspace", "repository", "access"].includes(modal) &&
              !newKey && (
                <label>
                  {modal === "repository"
                    ? "GitHub repository"
                    : modal === "access"
                      ? "Key label"
                      : "Workspace name"}
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    maxLength={modal === "repository" ? 250 : 100}
                    placeholder={
                      modal === "repository"
                        ? "owner/repository"
                        : modal === "access"
                          ? "Client Alpha — read only"
                          : "Client Alpha"
                    }
                  />
                </label>
              )}
            {modal === "review" && (
              <>
                <label>
                  Repository
                  <select
                    value={formRepo}
                    onChange={(e) => setFormRepo(e.target.value)}
                    required
                  >
                    {data.repositories
                      .filter((r) => r.workspace_id === formWorkspace)
                      .map((r) => (
                        <option value={r.id} key={r.id}>
                          {r.full_name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Pull request number
                  <input
                    type="number"
                    min={1}
                    max={10000000}
                    value={number}
                    onChange={(e) => setNumber(e.target.value)}
                    required
                    placeholder="128"
                  />
                </label>
                <p>
                  Reads the current PR head and related source. Repository code
                  and tests will not be executed.
                </p>
              </>
            )}
            {modal === "connection" && (
              <>
                <label>
                  Fine-grained GitHub token
                  <input
                    type="password"
                    value={githubToken}
                    onChange={(e) => setGithubToken(e.target.value)}
                    autoComplete="off"
                    placeholder="github_pat_…"
                  />
                </label>
                <p>
                  Select only this client’s repositories. Grant read-only
                  Contents, Pull requests, Checks and Metadata. Leave blank to
                  keep the current token.
                </p>
                <label>
                  Webhook secret
                  <input
                    type="password"
                    value={webhookSecret}
                    minLength={32}
                    onChange={(e) => setWebhookSecret(e.target.value)}
                    autoComplete="off"
                    placeholder="Random secret, at least 32 characters"
                  />
                </label>
                <p>
                  GitHub webhook URL:{" "}
                  <code>
                    {typeof window !== "undefined"
                      ? window.location.origin
                      : ""}
                    /api/webhooks/{formWorkspace}
                  </code>
                  . Content type application/json; subscribe to Pull requests.
                  Add the same secret in GitHub. Leave blank to keep the current
                  webhook secret.
                </p>
                {!isDemo &&
                  data.workspaces.some(
                    (w) =>
                      w.id === formWorkspace &&
                      (w.github_connected || w.webhook_configured)
                  ) && (
                    <button
                      type="button"
                      className="sw-text-link"
                      disabled={!!busy}
                      onClick={() =>
                        void perform(
                          "Removing saved GitHub connection…",
                          async () => {
                            await mutate(
                              `workspaces/${formWorkspace}/connection`,
                              { github_token: "", webhook_secret: "" }
                            )
                            await load()
                            closeModal()
                            setNotice(
                              "Stored GitHub token and webhook secret removed. Existing source snapshots and reviews remain."
                            )
                          }
                        )
                      }
                    >
                      Remove stored GitHub connection
                    </button>
                  )}
              </>
            )}
            {modal === "access" && !newKey && (
              <label>
                Permission
                <select
                  value={accessRole}
                  onChange={(e) => setAccessRole(e.target.value)}
                >
                  <option value="viewer">Viewer — read only</option>
                  <option value="reviewer">
                    Reviewer — reviews and decisions
                  </option>
                </select>
              </label>
            )}
            {newKey ? (
              <div className="sw-one-time-key">
                <LockKeyhole size={20} />
                <strong>Copy this key now</strong>
                <p>
                  It is shown once and gives access only to{" "}
                  {workspaceName(formWorkspace)}. Share it privately.
                </p>
                <code>{newKey}</code>
                <button
                  type="button"
                  className="sw-btn sw-btn-outline"
                  onClick={() =>
                    navigator.clipboard
                      .writeText(newKey)
                      .then(() => setNotice("Access key copied."))
                      .catch(() =>
                        setError(
                          "Clipboard unavailable. Select and copy the key manually."
                        )
                      )
                  }
                >
                  <Copy size={14} />
                  Copy key
                </button>
              </div>
            ) : (
              <>
                <p className="sw-muted">
                  {isDemo
                    ? "Live connections require signing in. This demo does not store credentials."
                    : modal === "repository"
                      ? "First version: GitHub, up to 350 supported files / 3 MB text. Oversized imports fail without replacing an existing index."
                      : "Changes apply only to the selected client workspace."}
                </p>
                <button disabled={!!busy} className="sw-btn sw-btn-green">
                  {busy || (isDemo ? "Got it" : "Save and continue")}
                  <ArrowRight size={15} />
                </button>
              </>
            )}
          </form>
        </Dialog>
      )}
    </div>
  )
}

function EvidenceBlock({ evidence }: { evidence: Evidence }) {
  return (
    <details className="sw-evidence-block">
      <summary>
        <FileCode2 size={14} />
        <span>
          {evidence.path}:{evidence.start}–{evidence.end}
        </span>
        <ChevronDown size={12} />
      </summary>
      <small>
        Symbol {evidence.symbol} · SHA {evidence.sha}
      </small>
      <pre>{evidence.text}</pre>
    </details>
  )
}

function Trend({
  data,
  workspace,
  demo,
  at,
}: {
  data: Portfolio
  workspace: string
  demo: boolean
  at: number
}) {
  const counts = Array.from(
    { length: 7 },
    (_, i) =>
      data.reviews.filter(
        (r) =>
          (workspace === "all" || r.workspace_id === workspace) &&
          Math.floor(r.created / 86400) === Math.floor(at / 86400000) - 6 + i
      ).length
  )
  const values = demo ? [48, 41, 56, 51, 65, 62, 75, 69, 82, 77, 89] : counts
  const max = demo ? 100 : Math.max(1, ...counts)
  const points = values
    .map(
      (v, i) =>
        `${35 + (i * 475) / (values.length - 1)},${174 - (v / max) * 135}`
    )
    .join(" ")
  return (
    <div className="sw-trend">
      <svg
        viewBox="0 0 540 220"
        role="img"
        aria-label={
          demo
            ? "Illustrative rising sample health trend, not measured data"
            : `Review counts, last 7 days: ${counts.join(", ")}`
        }
      >
        <defs>
          <linearGradient id="sw-chart-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#24745c" stopOpacity=".18" />
            <stop offset="100%" stopColor="#24745c" stopOpacity=".02" />
          </linearGradient>
        </defs>
        {[40, 85, 130, 175].map((y, i) => (
          <g key={y}>
            <line
              x1="35"
              x2="510"
              y1={y}
              y2={y}
              stroke="#e8e8df"
              strokeDasharray="3 4"
            />
            <text x="8" y={y + 4}>
              {demo
                ? 90 - i * 20
                : ((max * (3 - i)) / 3).toFixed(max > 3 ? 0 : 1)}
            </text>
          </g>
        ))}
        <polygon
          points={`35,175 ${points} 510,175`}
          fill="url(#sw-chart-fill)"
        />
        <polyline
          points={points}
          fill="none"
          stroke="#24745c"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle
          cx="510"
          cy={174 - (values.at(-1)! / max) * 135}
          r="4"
          fill="#24745c"
        />
        {["6 days ago", "3 days ago", "Today"].map((t, i) => (
          <text
            key={t}
            x={35 + i * 237}
            y="207"
            textAnchor={i === 2 ? "end" : "start"}
          >
            {t}
          </text>
        ))}
      </svg>
    </div>
  )
}

function ReviewDesk({
  review,
  findings,
  repoName,
  workspaceName,
  focus,
  canWrite,
  busy,
  demo,
  onDecision,
  onReviewDecision,
  onRetryAI,
}: {
  review: Review
  findings: Finding[]
  repoName: string
  workspaceName: string
  focus: string
  canWrite: boolean
  busy: boolean
  demo: boolean
  onDecision: (
    f: Finding,
    status: string,
    feedback?: string | null
  ) => Promise<void>
  onReviewDecision: (status: string) => Promise<void>
  onRetryAI: () => void
}) {
  const initial = findings.find((f) => f.id === focus) || findings[0]
  const [findingId, setFindingId] = useState(initial?.id || "")
  const [filePath, setFilePath] = useState(
    initial?.evidence.path || review.files?.[0]?.path || ""
  )
  const [tab, setTab] = useState<"source" | "diff" | "patch">("source")
  const finding = findings.find((f) => f.id === findingId)
  const file = review.files?.find((f) => f.path === filePath)
  const tests = review.checks.tests_changed
  const text =
    tab === "patch"
      ? finding?.patch ||
        "No source-validated patch preview is available. Follow the suggested next step and prepare a patch for human review."
      : tab === "diff"
        ? file?.patch ||
          "GitHub did not provide a textual diff for this file. Source coverage may be incomplete."
        : file?.source ||
          "This file is removed, unsupported or excluded from the indexed snapshot. No source evidence is inferred."
  function selectFinding(f: Finding) {
    setFindingId(f.id)
    setFilePath(f.evidence.path)
    setTab("source")
  }
  return (
    <>
      <div className="sw-review-header">
        <div>
          <span className="sw-eyebrow">
            {workspaceName} / {repoName}
          </span>
          <h2>
            <span>#{review.number}</span> {review.title}
          </h2>
          <p>
            <GitBranch size={13} /> Commit{" "}
            <code>{review.sha.slice(0, 12)}</code>
            <span>•</span>
            {demo
              ? "Authored sample walkthrough"
              : `${review.elapsed.toFixed(1)}s analysis stage`}
          </p>
        </div>
        <div className="sw-review-decision">
          <Badge
            tone={
              review.status === "request_changes"
                ? "high"
                : review.status === "approved"
                  ? "green"
                  : "medium"
            }
          >
            {label(review.status)}
          </Badge>
          {canWrite && (
            <>
              <button
                className="sw-btn sw-btn-outline sw-btn-small"
                disabled={busy}
                onClick={() => void onReviewDecision("request_changes")}
              >
                Request changes
              </button>
              <button
                className="sw-btn sw-btn-green sw-btn-small"
                disabled={busy}
                onClick={() => void onReviewDecision("approved")}
              >
                Approve review
              </button>
            </>
          )}
        </div>
      </div>
      <div className="sw-review-summary">
        <Sparkles size={17} />
        <p>{review.summary}</p>
        <Badge>{label(review.checks.ai)}</Badge>
      </div>
      <div className="sw-review-desk">
        <aside className="sw-changed-files">
          <h3>
            CHANGED FILES <span>{review.files?.length || 0}</span>
          </h3>
          {review.files?.map((f) => (
            <button
              key={f.path}
              className={f.path === filePath ? "active" : ""}
              onClick={() => {
                setFilePath(f.path)
                setTab("source")
              }}
            >
              <FileCode2 size={14} />
              <span>
                {f.path}
                <small>
                  <b>+{f.additions}</b> <i>−{f.deletions}</i>
                </small>
              </span>
            </button>
          ))}
          <div className="sw-tests-note">
            <CircleAlert size={13} />
            <span>
              {tests ? "Test files changed" : "No test files changed"}
              <small>Tests not executed by Stackwise</small>
            </span>
          </div>
          <h3>
            FINDINGS <span>{findings.length}</span>
          </h3>
          {findings.map((f) => (
            <button
              key={f.id}
              className={`sw-finding-nav ${f.id === findingId ? "active" : ""}`}
              onClick={() => selectFinding(f)}
            >
              <span className={`sw-severity-dot ${f.severity}`} />
              <span>
                {f.title}
                <small>{label(f.status)}</small>
              </span>
            </button>
          ))}
          {!findings.length && (
            <p className="sw-muted">
              No actionable finding returned. This is not a guarantee that the
              code is safe.
            </p>
          )}
        </aside>
        <section className="sw-code-panel">
          <div className="sw-code-toolbar">
            <span>
              <FileCode2 size={15} />
              {filePath}
            </span>
            <div>
              {(["source", "diff", "patch"] as const).map((t) => (
                <button
                  key={t}
                  className={tab === t ? "active" : ""}
                  onClick={() => setTab(t)}
                >
                  {t === "patch" ? "Patch preview" : label(t)}
                </button>
              ))}
            </div>
          </div>
          <div
            className="sw-code-lines"
            role="region"
            aria-label={`${tab} of ${filePath}`}
            tabIndex={0}
          >
            {text.split("\n").map((line, i) => (
              <div
                key={i}
                className={`${tab === "source" && finding?.evidence.path === filePath && i + 1 >= finding.evidence.start && i + 1 <= finding.evidence.end ? "highlight" : ""} ${tab !== "source" ? (line.startsWith("+") && !line.startsWith("+++") ? "addition" : line.startsWith("-") && !line.startsWith("---") ? "deletion" : "") : ""}`}
              >
                <span>{i + 1}</span>
                <code>{line || " "}</code>
              </div>
            ))}
          </div>
          {finding && (
            <div className="sw-inline-finding">
              <div>
                <StackwiseBrand small />
                <Badge tone={finding.severity}>
                  {finding.severity.toUpperCase()}
                </Badge>
                <Badge tone="medium">Potential issue</Badge>
              </div>
              <h3>{finding.title}</h3>
              <p>{finding.detail}</p>
              <small>
                Source location checked. Semantic correctness requires human
                validation.
              </small>
            </div>
          )}
        </section>
        <aside className="sw-review-evidence">
          <h3>Evidence</h3>
          {finding ? (
            <>
              <div className="sw-evidence-item">
                <FileCode2 size={15} />
                <div>
                  <strong>{finding.evidence.path}</strong>
                  <span>
                    Lines {finding.evidence.start}–{finding.evidence.end}
                  </span>
                </div>
              </div>
              <div className="sw-evidence-item">
                <GitBranch size={15} />
                <div>
                  <strong>{finding.evidence.symbol}</strong>
                  <span>SHA {finding.evidence.sha.slice(0, 12)}</span>
                </div>
              </div>
              <div className="sw-evidence-item">
                <ShieldCheck size={15} />
                <div>
                  <strong>Location & exact quote checked</strong>
                  <span>Not a confirmed exploit or passing test</span>
                </div>
              </div>
              <details className="sw-quote">
                <summary>Inspect source quote</summary>
                <pre>{finding.evidence.text}</pre>
                <small>Full SHA: {finding.evidence.sha}</small>
              </details>
              <hr />
              <h3>Suggested next step</h3>
              <p>{finding.next_step}</p>
              <button
                className="sw-btn sw-btn-green"
                disabled={!finding.patch}
                onClick={() => setTab("patch")}
              >
                Review patch <Code2 size={15} />
              </button>
              {finding.patch ? (
                <button
                  className="sw-btn sw-btn-outline"
                  onClick={() =>
                    download(
                      finding.patch,
                      `stackwise-pr-${review.number}-${finding.id}.diff`
                    )
                  }
                >
                  <Download size={14} />
                  Download diff
                </button>
              ) : (
                <small className="sw-muted">
                  No validated patch preview. A developer should prepare the
                  fix.
                </small>
              )}
              <div className="sw-decision-actions">
                <button
                  className="sw-btn sw-btn-outline"
                  disabled={busy || !canWrite || finding.status === "resolved"}
                  onClick={() => void onDecision(finding, "resolved")}
                >
                  <CheckCheck size={14} />
                  Mark resolved
                </button>
                <button
                  className="sw-text-link"
                  disabled={busy || !canWrite}
                  onClick={() =>
                    void onDecision(
                      finding,
                      finding.status === "dismissed" ? "open" : "dismissed"
                    )
                  }
                >
                  {finding.status === "dismissed"
                    ? "Reopen finding"
                    : "Dismiss finding"}
                </button>
              </div>
              <Badge tone={finding.status === "open" ? "medium" : "green"}>
                {label(finding.status)}
              </Badge>
              <small className="sw-approval-note">
                Decisions are recorded here. No GitHub code or PR state changes.
                Resolved means reviewer-reported.
              </small>
              <hr />
              <h3>Was this useful?</h3>
              <select
                aria-label="Finding usefulness"
                value={finding.feedback || ""}
                disabled={busy || !canWrite}
                onChange={(e) =>
                  void onDecision(
                    finding,
                    finding.status,
                    e.target.value || null
                  )
                }
              >
                <option value="">Not rated</option>
                <option value="useful">Useful finding</option>
                <option value="false_positive">False positive</option>
                <option value="uncertain">Needs investigation</option>
              </select>
            </>
          ) : (
            <p>
              No finding selected. Inspect the changed source and related
              context.
            </p>
          )}
        </aside>
      </div>
      <Panel
        title="Related repository context"
        hint="Lexical retrieval over this PR’s pinned source snapshot. Python symbols are parsed with AST; other languages use text windows."
      >
        <div className="sw-context-grid">
          {review.context?.map((e, i) => (
            <EvidenceBlock key={i} evidence={e} />
          ))}
        </div>
      </Panel>
      <Panel title="Checks & coverage">
        <div className="sw-settings-grid">
          <div>
            <small>Static checks</small>
            <strong>Focused changed-line patterns</strong>
          </div>
          <div>
            <small>AI review</small>
            <strong>{label(review.checks.ai)}</strong>
            {!demo && canWrite && review.checks.ai !== "complete" && (
              <button
                className="sw-text-link"
                disabled={busy}
                onClick={onRetryAI}
              >
                Retry AI review <RefreshCw size={12} />
              </button>
            )}
          </div>
          <div>
            <small>Test execution</small>
            <strong>Not run</strong>
          </div>
          <div>
            <small>Rejected source references</small>
            <strong>{review.checks.rejected_citations || 0}</strong>
          </div>
        </div>
        <div className="sw-panel-copy">
          <strong>CI observations</strong>
          {review.checks.ci?.runs?.length ? (
            review.checks.ci.runs.map((c, i) => (
              <p key={i}>
                {c.name} · {c.conclusion || c.status}
              </p>
            ))
          ) : (
            <p>
              No readable CI check results for this commit. Stackwise did not
              execute tests.
            </p>
          )}
        </div>
      </Panel>
    </>
  )
}
