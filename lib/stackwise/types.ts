export type Evidence = {
  path: string
  start: number
  end: number
  sha: string
  symbol: string
  text: string
  id?: string
  verified?: string
}
export type Finding = {
  id: string
  workspace_id: string
  review_id: string
  severity: string
  title: string
  detail: string
  next_step: string
  evidence: Evidence
  patch: string
  origin: string
  status: string
  feedback: string | null
  created?: number
  updated?: number
}
export type Workspace = {
  id: string
  name: string
  color: string
  github_connected?: boolean
  webhook_configured?: boolean
}
export type Dependency = {
  name: string
  version: string
  ecosystem: string
  path: string
  advisories: { id: string }[]
}
export type Repository = {
  id: string
  workspace_id: string
  full_name: string
  status: string
  sha: string
  branch: string
  file_count: number
  indexed: number | null
  dependencies: {
    status?: string
    packages?: Dependency[]
    unresolved?: number
    note?: string
    checked_at?: number
  }
  ci: {
    status?: string
    runs?: { name: string; status: string; conclusion: string | null }[]
  }
  prs: { number: number; title: string; sha: string; draft: boolean }[]
}
export type ChangedFile = {
  path: string
  patch: string
  source: string
  additions: number
  deletions: number
  patch_available: boolean
  status: string
}
export type Review = {
  id: string
  workspace_id: string
  repo_id: string
  number: number
  title: string
  sha: string
  base_sha: string
  status: string
  summary: string
  created: number
  elapsed: number
  checks: {
    ai?: string
    static?: string
    test_execution?: string
    tests_changed?: boolean
    rejected_citations?: number
    evidence?: string
    ci?: Repository["ci"]
  }
  files?: ChangedFile[]
  context?: Evidence[]
  findings?: Finding[]
}
export type Job = {
  id: string
  workspace_id: string
  repo_id: string
  kind: string
  stage: string
  status: string
  error: string
  result_id: string
  created: number
  updated: number
}
export type Report = {
  id: string
  workspace_id: string
  period: string
  title: string
  created: number
  markdown?: string
}
export type Portfolio = {
  demo: boolean
  workspaces: Workspace[]
  repositories: Repository[]
  reviews: Review[]
  findings: Finding[]
  jobs: Job[]
  reports: Report[]
  audit: {
    id: string
    workspace_id: string
    actor: string
    action: string
    subject: string
    created: number
  }[]
  truncated?: string
}
export type User = {
  name: string
  role: "owner" | "reviewer" | "viewer"
  workspace_id: string | null
  csrf: string
  auth_method?: "github" | "owner_key" | "workspace_key"
}
export type Session = { user: User | null; setup: Record<string, boolean> }
