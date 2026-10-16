# Stackwise concept → first implementation

The supplied five-page Stackwise Product Concept is the product reference. Its first-version
rule is respected: source-backed suggestions and downloadable patch previews, with human
approval. The example portfolio numbers and pricing are illustrative hypotheses.

| Concept | Implemented behavior | Limits / follow-up |
| --- | --- | --- |
| Agency overview | Client filter, loaded-record KPIs, priority actions, workspace drill-down | Sample health trend is labeled illustrative; live chart counts completed review records, not invented health scores |
| Client isolation | Separate workspace IDs; server-side membership checks on reads, mutations, retrieval, jobs, reports and patches | Access-key sessions; not enterprise SSO or independently audited SaaS |
| GitHub repository context | Commit-pinned archive import, redacted source, Python AST symbols and lexical BM25 retrieval | GitHub only; no filesystem-path access to a visitor's laptop, no ZIP import yet |
| Related code | Callers/tests/contracts can be found through symbol/name overlap; earlier Stackwise review summaries feed PR review | Lexical retrieval is not full program analysis or a complete historical GitHub PR index |
| PR review | Head source + diff, focused static checks, optional Groq review, source evidence validation | 60 changed files; unsupported/binary/omitted diffs visibly lack coverage |
| Evidence | File, symbol, line range, exact quote and commit SHA retained | Location validation does not prove the bug; all findings remain potential |
| Suggested fix | Validated exact-source replacement, unified diff preview/download; Python syntax checked | No fix branches, repository writes, test execution, auto-merge or deploy |
| Human decisions | Request changes / approve review; dismiss / reopen / mark resolved; usefulness feedback | Decisions are internal records; they do not submit a GitHub review or prove a fix landed |
| Dependencies | OSV exact direct npm/PyPI advisory lookups; explicit unavailable/unresolved state | No dependency resolution, lockfile/transitive audit, license checking or guaranteed fixed-version recommendation |
| CI | Read check runs for a pinned commit | Requires GitHub read permission; no test runner or sandbox |
| PR events | Signed, repository-scoped webhook and idempotent head-SHA jobs | Requires owner-configured token/webhook and Vercel queue delivery for unattended progress |
| Maintenance | Durable stages and bounded daily refresh round | Five least-recently indexed repos per daily cron; not continuous real-time monitoring |
| Client reports | Stored weekly Markdown snapshot, manual refresh and download | No emails, scheduled delivery, PDF renderer or share-link bypass of workspace auth |
| Evaluation | Security/flow tests, actionable-finding fixtures, rejected-evidence tests, latency metadata, reviewer feedback | No fabricated benchmark; live provider quality and false-positive rates need real labeled reviews |
| Commercial plans | No pretend checkout or plan limits sold as subscriptions | Billing, SSO, custom retention and fix branches remain future work |

## Supported repository files

UTF-8 `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.go`, `.java`, `.rb`, `.php`,
`.rs`, `.cs`, `.c`, `.h`, `.cpp`, `.kt`, `.swift`, `.sql`, `.md`, `.json`, `.toml`,
`.yaml`, `.yml`, `.txt`, `.html`, `.css`, `.scss`, `.vue`, `.svelte`, `.sh`, `.bash`, `.xml`,
and files named `Dockerfile`. These are read as data, never executed.

Python symbols are parsed with the standard-library AST. Other languages are text windows,
not language-specific call graphs. Lockfiles, generated/minified code, binary or non-UTF-8
files, credential/secret filenames, `.env*`, vendor folders, dependencies and symlinks are excluded.
Heuristic redaction preserves line numbers but cannot guarantee removal of every secret.

An archive may contain at most 350 accepted files, 3 MB accepted text and 100 KB per file.
Compressed downloads are capped at 20 MB; expanded entries at 80 MB. Individual oversized
or excluded files are counted as skipped. Exceeding the total source/file limits fails the
import with no partial index replacing the previous successful one. Always inspect coverage.

## Re-indexing and history

Each repository has a workspace-scoped current snapshot. A successful refresh replaces that
snapshot only. It does not delete another repository or old review source references. Earlier
findings/reports remain records of their earlier SHA. A failed import retains the old index.
A later-started completed index wins over an older concurrent job. GitHub PR source is pinned
to the PR head, independently of the default-branch snapshot used for repository Q&A.

## Job stages and retries

Index: snapshot → maintenance → complete. Review: snapshot → analysis → complete.
The database stores payload/stage before publishing the next message. Queue messages contain
only job IDs. Failed stages are acknowledged and require an explicit retry; interrupted stages
can be resumed after their processing lease expires. At-least-once delivery can repeat a network
call if a process dies before its database commit; it is not an exactly-once billing guarantee.
No in-process background task is trusted to survive a Vercel response.

## Historical CodeGraph evidence

Earlier source, reports and partial 40-case judge runs are retained in Git history and the
separate old local project (see [repository layout](REPOSITORY_LAYOUT.md)). They describe the previous
fintech sample and are not a Stackwise acceptance score. In particular, completed cases with low
correctness/hallucination scores must not be described as passing tests. The migration does not
restart that judge run or substitute missing scores.

PR evidence responses are capped at 3.5 MB; an unusually large review may require splitting the
PR even when its repository snapshot fits the index limits. Portfolio list records omit patch
and source bodies; the authorized detail endpoint loads them only when a review is opened.

The controlled fixture report at `data/evaluation/stackwise_fixture_report.json` records nine
small Python pattern cases and three lexical-retrieval questions. All nine fixture labels
matched (zero false-positive cases in these authored examples); all three expected files were
retrieved in the top three. This is a narrowly scoped regression evaluation, not measured live
AI accuracy. Python call patterns use AST to avoid turning quoted examples into findings.

Unavailable AI review can be retried explicitly from Checks & coverage. It must still match
the same PR head; completed AI reviews are cached. An explicit retry preserves existing human
finding decisions and deduplicates matching findings. Provider quality scores are not fabricated.
