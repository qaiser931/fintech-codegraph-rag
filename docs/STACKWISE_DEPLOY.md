# Deploy Stackwise on the existing Vercel project

The source is prepared for one Next.js frontend and Python backend on Vercel.
A successful local build does not verify Vercel deployment, Postgres or live provider access.

## 1. Preserve and publish the migration

The delivery helper checks each changed file against the known production/reviewed baselines,
backs up affected source, checks out no unrelated branch, validates the app, then commits only
reviewed paths. It does not remove telemetry, evaluation results, private environment files,
Docker containers or cloud resources. It never force-pushes.

If GitHub main has advanced or an affected source file has an unexpected edit, reconcile that
source before retrying. Do not run `git reset --hard` or delete the existing project.

## 2. Vercel project settings

Keep the existing repository and project. Root Directory: repository root (empty / `.`).
Framework: Next.js. Node: 22 or 24. Python: 3.12, as pinned in `.python-version`.
Enable Fluid compute. Keep normal install/build defaults; do not run the historical
`scripts/prepare_vercel.py` hook. The new Python install hook downloads no models.

## 3. Durable storage

Vercel → Storage / Marketplace → connect **Neon Postgres** (or a compatible Postgres provider).
Select the provider's free allowance if suitable and attach it to the project. Confirm that
`DATABASE_URL` is injected into the intended environment. Use the pooled TLS connection URL.
Never paste that connection string in chat or commit it.

The app creates only its `sw_*` tables; it does not drop existing tables. Use a dedicated database
or branch for this app. Preview and production should have separate databases and access keys.
SQLite is local/test-only and is rejected when `VERCEL` is set. In-memory or function-local disk
storage is not used for real client workspaces.

## 4. Private project variables

Retain the real existing `GROQ_API_KEY` and `LLM_MODEL` (default `openai/gpt-oss-120b`).
The migration helper generates new private settings in ignored `.env.stackwise.vercel`:

| Key | Value / purpose |
| --- | --- |
| `STACKWISE_APP_URL` | Exact canonical HTTPS application URL, with no trailing slash |
| `STACKWISE_ADMIN_TOKEN` | New random agency owner access key, at least 32 characters |
| `STACKWISE_ENCRYPTION_KEY` | New Fernet key; encrypts workspace GitHub tokens/secrets |
| `CRON_SECRET` | New random secret, at least 32 characters; Vercel sends it to the cron |
| `STACKWISE_QUEUE_ENABLED` | `1` to publish durable job stages to Vercel Queues |
| `STACKWISE_QUEUE_REGION` | `iad1`, consistently for all publishers |
| `DATABASE_URL` | Injected by the managed Postgres integration |
| `GROQ_API_KEY` | Existing server-only Groq key |
| `LLM_MODEL` | Existing Groq model or default shown above |

Privately import the generated settings in Vercel for **Production**. Do not create duplicate
keys; edit existing values. No key uses a `NEXT_PUBLIC_` prefix. Do not send the file in chat.
Changing the owner key invalidates owner sessions. Replacing the encryption key without
re-encrypting stored connections makes those connections unreadable; keep a private backup.
The old `API_ROLE_TOKENS`, `CODEGRAPH_API_URL` and Ollama settings are unused by Stackwise.

## 5. Redeploy and smoke-test

Redeploy the new commit. Check Vercel logs for the Python function and the private
`src.stackwise.worker` queue subscriber. The subscriber is declared in `pyproject.toml`;
it is not an exposed public processing endpoint. Its module imports without database credentials.

- Open `/` for the Stackwise landing and `/dashboard?demo=1` for the sample review.
- Open `/api/health` to check the deployed service name is `stackwise`.
  Configuration booleans are not a database-connectivity test.
- Open `/dashboard`, sign in privately with `STACKWISE_ADMIN_TOKEN`, and create a workspace.
  A successful portfolio load validates real database connectivity.
- Connect one small public repository. Its two saved stages are snapshot and maintenance.
- If a queue delivery is unavailable, use **Run next stage**. A failed stage requires explicit
  **Retry saved stage**; no infinite provider retry loop exists.
- Review a PR number. Verify its SHA and exact line evidence. Inspect/download a patch if available.
- Create a viewer key in Settings, then test in a separate private browser window: that key
  must see only its assigned workspace and cannot record decisions or start AI requests.
- Generate and download a client report. Reload to confirm that real decisions persist.

The source has bounded network calls and per-workspace job/question budgets. Very large
repositories and PRs are rejected rather than silently presented as complete analyses.
Vercel Queues is a beta service; account availability and provider quotas must be verified
on the actual project. The database job record survives an unavailable queue.

## 6. Private GitHub repositories and PR events

Create a GitHub **fine-grained personal access token** limited to the intended client repositories.
Grant **read-only Contents, Pull requests, Checks and Metadata**. In Stackwise Settings,
configure that token for the correct workspace. It is encrypted before database storage and
is never returned by list endpoints. This first version uses explicit token setup, not OAuth.
The app contains no GitHub write API calls.

For automatic PR events, generate a different random webhook secret of at least 32 characters.
Save it in that workspace connection. In the GitHub repository's Webhooks settings, use:

- Payload URL: `https://YOUR-APP/api/webhooks/WORKSPACE_ID` (shown in Settings)
- Content type: `application/json`
- Secret: the same private webhook secret
- Events: Pull requests

Delivery signatures are HMAC-SHA256 verified. A repository must already belong to that workspace.
Repeated delivery of the same PR head maps to one saved job. Changed heads create a new review;
old reviews keep their earlier commit evidence. The daily cron saves a weekly report snapshot
and refreshes up to five least-recently indexed repositories. It does not promise minute-level
monitoring or send email. Reports can be refreshed manually.

## 7. Local development (optional)

Activate a Python 3.12 environment with the new requirements and run `vercel dev` from the
repository root for the combined application. Put local settings in an ignored environment
file, using `STACKWISE_LOCAL=1` and the exact local `STACKWISE_APP_URL`. A local SQLite
`DATABASE_URL=sqlite:///./stackwise-local.db` is acceptable only outside Vercel. The combined
Vercel dev command provides one application origin; no production laptop server is required.

## Reference documentation

- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/functions/limitations
- https://vercel.com/docs/postgres
- https://vercel.com/docs/queues/python-sdk
- https://vercel.com/docs/cron-jobs/usage-and-pricing
- https://docs.github.com/en/rest/repos/contents
- https://docs.github.com/en/rest/pulls/pulls
- https://google.github.io/osv.dev/post-v1-querybatch/
