# Stackwise live verification — 16 October 2026

Application: https://fintech-codegraph-rag.vercel.app/
Repository: https://github.com/qaiser931/fintech-codegraph-rag

This records the controlled owner-assisted checks shown in production and the local
regressions used while preparing the changes. It is not an AI-accuracy benchmark or
a guarantee about arbitrary repositories. No client source code was executed.

## Observed production evidence

| Workflow | Observation | Scope |
| --- | --- | --- |
| Hosting | Vercel reports successful deployment of `a71f424bb727e44c0c2f1eaeba01a485723503e7`; Python health returns HTTP 200 | Next.js frontend and Python API on one Vercel project, Neon Postgres and Groq; no laptop service hop |
| Durable workspace | Owner created a workspace, connected/indexed the repository and loaded saved review/report records | Live database reads and writes, not just configuration booleans |
| Source Q&A | Repository question returned a citation to `tests/stackwise/test_boundaries.py:113–131` | One inspected answer; not general answer-correctness evidence |
| Viewer role | Separate client viewer sign-in exposed its workspace and read-only review details | Cross-workspace and mutation boundaries also have automated regression coverage; this record does not claim a complete live tenant-isolation audit |
| Dependency coverage | Refreshed snapshot `cd16d48a86` displayed 30 exact direct versions, 39 unresolved declarations and no advisory matches | Snapshot/provider-specific observation; unresolved ranges and transitives were not cleared |
| Actionable evidence | PR #3, `c9edbe05de4dd1dc4c051857e2dabb5a06d45198`, produced one TLS finding at line 8 for `verify=False` | Earlier PR #2 review retains its original duplicate findings as historical evidence |
| Patch preview | Downloaded PR #2 diff changes only `verify=False` to `verify=True`; `git apply --check` passes against that exact head, and the resulting Python parses | Application/syntax check only; no runtime test or proof of a deployed fix |
| Queue publication and execution | After explicit consumer deployment, production `/api/queue_worker` logs show three saved jobs at `stage=complete status=complete`, with HTTP 204, without manual stage execution in the controlled check | Earlier `delivery: queued` responses alone were not treated as completion |
| Private callback | Unauthenticated public GET and POST to `/api/queue_worker` both return HTTP 404 | An explicit private queue trigger is required; request metadata alone is not authentication |
| Signed webhook | Repository owner configured the same private secret in Stackwise and GitHub; GitHub ping delivery displayed a green success tick | Secret values and request cookies are excluded from this record |
| Automatic PR review | Opening PR #4 automatically created a review at `22e91f1d9fd08fa65d049e2096d4dfc22cba586e`, without the Review a PR/Run next stage buttons; the detail screen shows `verify=True`, zero findings and a pending human decision | Verifies the PR-opened webhook → queue → saved review path. The PR-synchronize event was not independently exercised in this live check |
| Client report | A workspace-scoped weekly Markdown report was generated/downloaded and inspected | Historical snapshots describe the time they were created; they are not silently replaced with later results |

The PR #4 list originally said “Reviewed” merely because it had zero open findings,
while its detail correctly said “needs review”. The UI correction derives both badges
from the saved decision: **Needs review**, **Approved**, or **Changes requested**.
Approval is an internal human record; it never merges or approves a GitHub PR.
The correction was published as `5ad3951334d13a6ac4cfffd4cf733ba8f6ed7ed1`;
deployment success and public API checks were confirmed. This record does not claim
an additional authenticated visual check of every decision badge after deployment.

## Local verification

- Private queue callback change: 72 Python tests passed. Real Queue SDK tests exercise
  publish → HTTP callback → durable snapshot stage → next-stage publication → completion
  and acknowledgement using an embedded queue, with network providers stubbed. Failed
  stages remain failed for explicit retry; a live lease requests redelivery.
- The exact callback consumer matches Vercel's function-key encoding. The function
  configuration matches the official schema, and Next's route parser verifies the
  main-API rewrite excludes the callback while retaining normal API routes.
- Delivery helpers were tested in isolated Git repositories for known source hashes,
  backup preservation, validation failure, unrelated staged edits, fast-forward safety,
  scoped commits, publication resume and remote verification. Their simulated Git remotes
  are not represented as real GitHub deployments.
- Human-decision UI regression cases cover pending reviews with zero findings,
  approved reviews with findings, and request-changes decisions with zero findings.
  List and detail must agree. Frontend lint, typecheck, test and build results belong
  to the accompanying update run, rather than to client-repository test execution.

## Boundaries retained

On 16 October, the owner manually called the authenticated cron endpoint and received
HTTP 200 with `reports=weekly_snapshots_saved`, `maintenance_jobs=1` and
`queue_deliveries=1`. This proves the handler and one publication, not the job's
completion or an automatic scheduled invocation. The latter remains unobserved.
GitHub private-token permissions, large repositories, hosting
quotas and broader model accuracy require their own checks. There is no test sandbox,
automatic fix branch, merge, billing or SSO. Historical CodeGraph judge results remain
historical, including incomplete runs and low scores.

Test PRs #2, #3 and #4 were verified closed without merging. Closing a test PR does not
retroactively change its saved review
or turn its old findings into a demonstrated production resolution.
