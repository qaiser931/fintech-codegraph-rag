# Stackwise

**Know which repository needs you next.**

An evidence-led maintenance desk for software agencies: separate client workspaces,
commit-pinned pull request reviews, direct dependency advisory checks and client reports.
The interface follows the supplied *Stackwise Product Concept*. This checkout contains
only Stackwise application source, tests and relevant documentation. See
[repository layout and archive](docs/REPOSITORY_LAYOUT.md) for the retained historical version.

## One application on Vercel

- **Frontend:** Next.js / React, agency overview and a three-column PR review workspace.
- **Backend:** Python / FastAPI in `api/index.py`; same-origin `/api/*` routes.
- **Data:** managed Postgres connected through the Vercel Marketplace. No runtime disk persistence.
- **Jobs:** Python Vercel Queues subscriber, with saved, explicitly runnable stages as a fallback.
- **AI:** Groq, using the existing server-side API key. No local model downloads or Ollama.
- No Docker, VM, tunnel, laptop server or separate production ports.

## What works in this first version

1. An owner creates client workspaces and connects GitHub repositories. Public repositories
   work without a token. Private repositories use a separately encrypted, repository-scoped
   read-only token for each workspace.
2. Import pins the default branch to a SHA and reads supported UTF-8 source files without
   executing code. A successful refresh replaces only that repository's current snapshot;
   earlier reviews retain their own source evidence. Failed imports retain the previous snapshot.
3. A review reads the PR head, diff, related source and earlier Stackwise review summaries.
   Focused static patterns and optional Groq suggestions are checked against the head's exact
   source quote, file, line and SHA. Invalid source references are rejected.
4. A reviewer inspects findings, previews/downloads diffs, records useful/false-positive feedback,
   dismisses or marks findings resolved, and records request-changes/approval decisions.
   **These decisions never modify code or GitHub PR state.**
5. Dependency checks query OSV for exact direct npm/PyPI versions. CI check runs are read from
   GitHub; client tests are never executed by Stackwise.
6. Workspace-scoped weekly Markdown reports summarize open risks, recent reviews, reported
   resolutions and next steps. A daily Vercel cron creates weekly snapshots and queues a bounded
   round of repository refreshes.
7. Repository Q&A returns source citations from the selected workspace's indexed commit.

`/dashboard?demo=1` is an interactive, clearly labeled sample portfolio. Its decisions are
session-local and do not change connected client data. `/dashboard` requires a real access key.

## Setup and verification

See [docs/STACKWISE_DEPLOY.md](docs/STACKWISE_DEPLOY.md) for Vercel settings, Postgres,
private environment variables, first sign-in and GitHub webhooks.
See [docs/STACKWISE_SCOPE.md](docs/STACKWISE_SCOPE.md) for the concept mapping and explicit limits.
The dated [live verification record](docs/STACKWISE_LIVE_VERIFICATION.md) distinguishes
observed production workflows, local regression checks and remaining coverage limits.
Zero findings do not approve a review: both review screens display the recorded human decision.

```sh
python -m venv .venv-stackwise
# Activate this environment, then:
python -m pip install -r requirements.txt -r requirements-test.txt -c requirements-vercel.lock
python -m pytest -q
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test --maxWorkers=1
pnpm build
```

Use `vercel dev` for the combined local app. The optional `pnpm dev:ui` command serves only
Next.js and does not start Python; do not mistake that for a verified backend deployment.

## Boundaries

Findings remain **potential issues** until a human validates them. Source-location validation
is not proof that a finding is semantically correct. A downloadable patch is not a tested fix.
Repository text is untrusted data, not agent instructions. Credentials are heuristically
redacted before storage/AI; remove sensitive material before importing a repository.

The starter supports GitHub snapshots of **350 supported files / 3 MB source / 100 KB per file**,
PRs with at most **60 changed files**, 20 workspaces and 10 repositories per workspace.
Python gets AST symbols; other languages use lexical text windows. There is no dense embedding
model, test sandbox, transitive dependency solver, automatic fix branch, autonomous merge,
GitHub App OAuth, billing or SSO in this version. The concept's pricing is a hypothesis,
not an implemented paid plan. Provider and hosting quotas still apply.

Historical CodeGraph results remain in Git history and the separate old local project.
They are not a Stackwise benchmark. See the archive reference in the repository-layout guide.

This repository is used to test the Stackwise pull request review workflow.
