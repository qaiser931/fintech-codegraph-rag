# CodeGraph frontend

A Next.js 16 / React 19 investigation dashboard adapted from the supplied v0 application shell. This frontend lives in `frontend/` of the existing Fintech CodeGraph RAG repository; the Python backend stays separate.

## Local configuration

Use Node.js 24 LTS and pnpm 11.25.0. Copy `.env.example` to `.env.local`, then set:

- `CODEGRAPH_API_URL`: `http://127.0.0.1:8001` locally, or the reachable HTTPS backend base URL on Vercel.
- `API_ROLE_TOKENS`: the existing backend JSON map from **token to canonical role**: `Junior Dev`, `Senior Dev`, `Security Lead`.

Both variables remain on the Next.js server. Never use `NEXT_PUBLIC_` for credentials. The frontend does not need a Groq API key.

```powershell
npm exec --yes --package=pnpm@11.25.0 -- pnpm install --frozen-lockfile
npm exec --yes --package=pnpm@11.25.0 -- pnpm build
npm exec --yes --package=pnpm@11.25.0 -- pnpm start
```

Open the printed localhost URL. The local `.env.local` and `.env.vercel.local` files are ignored by Git.

## API contract

The browser calls same-origin Next.js routes. These select the backend bearer credential for the requested demo role and forward the canonical role name. The destination comes exclusively from server configuration. Requests do not follow redirects.

| Next.js endpoint | Existing FastAPI endpoint | Result |
| --- | --- | --- |
| POST `/api/query` | POST `/query` | Answer, evidence status, citations, paths, telemetry |
| POST `/api/retrieve` | POST `/retrieve` | Source references and paths; no invented answer status |
| GET `/api/health` | GET `/health` | Manual health/readiness check and real index counts |
| GET `/api/source/{path}?role=...` | GET `/source/{path}?role=...` | Role-authorized HTML source converted to code lines |

Question length: 3–2000 characters. Optional stack trace: at most 8000 characters. Query timeout: 240 seconds; retrieval: 120 seconds; source/health: 30 seconds. There are no automatic generation retries. Non-success HTTP statuses remain errors. Backend secrets and private error bodies are not forwarded to the browser.

The source viewer decodes only the backend's `pre/code` content, preserves numbered lines, highlights the citation range, and renders literal text. Role, question, or stack-trace edits clear previous evidence and abort/discard stale requests. Markdown supports headings, lists, tables, and code; raw HTML is disabled.

## Validation

```powershell
npm exec --yes --package=pnpm@11.25.0 -- pnpm lint
npm exec --yes --package=pnpm@11.25.0 -- pnpm build
npm exec --yes --package=pnpm@11.25.0 -- pnpm test
```

The 27 production-proxy checks use an isolated contract fixture. Nine DOM tests cover markdown, exploration, permissions, stale role/source results, question/stack-trace changes, concurrent health checks, and literal source rendering. Sidebar providers are simplified only in DOM tests. These checks do not call a model or prove answer correctness. The remote review browser could not reach the local test server, so real browser appearance and mobile layout still need a local check.

## Vercel deployment

Import `qaiser931/fintech-codegraph-rag` from GitHub. Select **Next.js**, **Root Directory `frontend`**, and **Node.js 24.x**. Keep pnpm lockfile detection and the default Next.js output directory. Set the two server variables above for Production and Preview, then deploy. The Node route handlers declare maximum durations of 300 seconds for investigations and 60 seconds for source/health; use Fluid compute.

A Vercel frontend cannot reach your laptop's `127.0.0.1`. For a temporary demo, use the package's authenticated backend tunnel launcher and its ignored `.env.vercel.local`. The laptop, Docker API and tunnel must remain running. Restarting a Quick Tunnel creates a new URL; update `CODEGRAPH_API_URL` in Vercel and redeploy. Permanent operation while the laptop is off requires separately hosted backend services and indices.

This is a public synthetic-code demo with selectable roles, not a production user login. The existing backend still enforces role-bound credentials and source access. Documented sample-code latency is not a production performance measurement.

Official references:
- https://vercel.com/docs/monorepos
- https://vercel.com/docs/functions/configuring-functions/duration
- https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
