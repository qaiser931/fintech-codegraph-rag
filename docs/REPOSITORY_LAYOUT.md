# Stackwise source and historical archive

The current branch contains Stackwise only. Git history is intentionally retained;
this change does not rewrite history, delete saved database records, or rotate keys.

| Path | Purpose |
| --- | --- |
| `app/` | Next.js landing, dashboard, styles and metadata |
| `components/stackwise-*.tsx` | Current application interface and brand |
| `lib/stackwise/` | Same-origin API client and TypeScript types |
| `api/` | Python API and private queue callback |
| `src/stackwise/` | Workspace security, repository import/review, jobs and storage |
| `tests/` | Stackwise Python/UI regressions and labeled demo fixture |
| `scripts/` | Lightweight install hook, private-settings setup and fixture evaluation |
| `data/evaluation/stackwise_*.json` | Small, explicitly scoped Stackwise evidence |
| `docs/` | Stackwise deployment, scope, fixes and verification notes |
| Root manifests/configuration | Reproducible build, runtime and test configuration |

Unused CodeGraph API, graph/vector ingestion/retrieval, Streamlit UI, fintech sample
code, old tests and evaluation tooling, and unused template UI components were removed
from the current checkout after tracing Stackwise imports. Package versions and the
production API/queue/cron configuration are unchanged. Not every installed transitive
package is an application source file; dependencies are managed by the lockfile.

The exact previous version is preserved at commit
`5ad3951334d13a6ac4cfffd4cf733ba8f6ed7ed1`:

- [Historical source and CodeGraph records](https://github.com/qaiser931/fintech-codegraph-rag/tree/5ad3951334d13a6ac4cfffd4cf733ba8f6ed7ed1)
- [Historical CodeGraph README](https://github.com/qaiser931/fintech-codegraph-rag/blob/5ad3951334d13a6ac4cfffd4cf733ba8f6ed7ed1/docs/archive/CODEGRAPH_README.md)

The local delivery creates a separate `D:\Personal\Stackwise` working repository.
It retains `D:\Personal\fintech-codegraph-rag` unchanged as the old local project,
including ignored local results, tools and environments. An additional Git bundle
and committed-source ZIP are saved outside the new project before publication.
GitHub's `main` file tree becomes Stackwise-only; historical commits/branches remain
available. The repository URL and production domain are not renamed by this change.

The new private-settings file copies only existing Stackwise-related key names from
the old ignored settings files. It does not generate replacement keys or write to
Vercel. Managed Postgres records and Vercel-only values are not exported. The saved
encryption key must be preserved to read existing encrypted connections.

Use the new folder for future edits and pushes. Editing/pushing from the old folder
after migration can cause conflicts with the cleaned branch; keep it as an archive.
Local build folders, dependencies and a Python environment may be regenerated and
are ignored by Git. They are not part of the published source.
