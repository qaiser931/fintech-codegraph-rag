# Fintech CodeGraph RAG

A Next.js investigation workspace and FastAPI API deployed together on Vercel.
Open the landing page at `/` and the workspace at `/dashboard`. The browser uses
same-origin `/api/*` routes. Docker, Cloudflare tunnels, an Oracle VM and a running
laptop are not required by this deployment.

## Deploy from GitHub

See [Vercel deployment](docs/VERCEL.md). Select **Next.js**, set **Root Directory**
to the repository root (empty), and enable Fluid compute. Use the default Next.js
install/build settings. Set these server-only environment variables:

- `GROQ_API_KEY`: your existing Groq key.
- `API_ROLE_TOKENS`: the existing JSON token-to-role mapping, preserving all three roles.
- `LLM_PROVIDER=groq`
- `LLM_MODEL=openai/gpt-oss-120b`

Remove the old `CODEGRAPH_API_URL` setting. It is no longer used. Keep credentials
out of Git and never prefix them with `NEXT_PUBLIC_`.

Vercel's Python install hook installs locked lightweight dependencies, downloads
pinned float32 ONNX models with SHA-256 verification, and builds immutable symbol,
graph and dense indices before bundling the function. Models are not committed to
GitHub and are not downloaded during requests. Build failure stops publication.

## Retrieval and generation

The API retains BGE semantic embeddings, BM25, RRF fusion, the MiniLM cross-encoder,
and role-filtered NetworkX call-graph expansion. ONNX Runtime replaces PyTorch for
inference. Exact cosine search over the small, immutable sample corpus replaces
Chroma's persistent database. Dense candidates are filtered by clearance and tenant
before scoring/ranking; graph expansion retains the existing role checks.

Groq generates answers using the existing citation and numeric-grounding validation.
Questions and selected synthetic code snippets are sent to Groq. Its account quotas
can return 429. No automatic generation retries or fabricated answer scores are used.
A documented sample-code latency is not a measurement of production latency.

## API and roles

- `GET /api/health`: readiness, index counts and the UI `ok` flag.
- `POST /api/retrieve`: authorized code evidence and call paths, without generation.
- `POST /api/query`: grounded answer, status, citations and query telemetry.
- `GET /api/source/{file_path}?role=...`: authorized source as literal JSON text.

Request bodies contain `query`, `role` and optional `stack_trace`. The public demo
retains its role selector; it is not a production login system. The server binds the
selected demo role to its private token internally. Explicit bearer credentials,
when supplied, still undergo the core API's 401 and role-mismatch 403 checks.
Source requests cannot leave `data/sample_codebase` or elevate the selected role.

Function files are read-only at runtime. Indices are rebuilt on deployment when
sample sources change. Runtime cache and telemetry are bounded, per-process memory;
they are neither durable nor shared between function instances. Cold starts and
free-plan quotas remain possible; this is not an unlimited or guaranteed-uptime service.

## Local development and checks

Use Node 22/24 and Python 3.12. Install the root pnpm package and the lightweight
Python requirements. Prepare the assets with `python scripts/prepare_vercel.py`.
Install the Vercel CLI (`npm install -g vercel`). For the unified app, use `vercel dev`: one browser-facing development URL, with
Vercel managing the internal runtimes. Do not start Docker or a tunnel.

```text
pnpm install --frozen-lockfile
python -m pip install -r requirements.txt -c requirements-vercel.lock
python scripts/prepare_vercel.py
vercel dev
```

Frontend checks: `pnpm lint`, `pnpm typecheck`, `pnpm build`, `pnpm test`.
The serverless tests in `tests/test_serverless.py` use real bundled models but no
live LLM request. They require prepared assets and pytest. The older native Python/
Streamlit workflow is retained for reference in [the archive](docs/LOCAL_WORKFLOW_ARCHIVE.md);
its optional dependencies are in `requirements-local.txt`, not in the Vercel bundle.

## Evaluation evidence

The original gold dataset and saved evaluation remain in `data/evaluation`.
The [fresh ONNX retrieval report](data/evaluation/vercel_retrieval_report.json) covers
40 questions for each of the three roles (120 checks), with zero unauthorized
results. Mean authorized expected-symbol context recall was 0.9423 for Junior Dev
and 0.8854 for Senior Dev/Security Lead. These are full-context retrieval metrics,
not answer correctness or equivalence to a newly rerun PyTorch benchmark.

### Assignment evidence and limits

The gold dataset contains 40 questions with expected symbol document IDs, source
files, execution paths and answer facts. Symbol document IDs are the stable citation
references; numbered citation labels depend on each request's context ordering.
Historical retrieval metrics are in `data/evaluation/real_report.md`. The successful
2026-10-10 four-combination JazzCash demo achieved full expected-symbol context
coverage after graph expansion for both authorized role sets. It is a one-question
demo, not a newly completed 40-case benchmark or proof of generated-answer correctness.

The evaluation utilities include code-symbol precision, call-path recall, execution
path accuracy and a gold file/symbol citation-match proxy. The stored historical
citation score is zero; source-link accessibility does not establish claim grounding.
Answer-quality proxy scoring in `src/evaluation/llm_evaluation.py` is not a verified
Ragas/DeepEval judge run. Its optional legacy DeepEval branch maps answer relevancy
to answer correctness; that branch must not be cited as a valid correctness benchmark.
A separate Q01 DeepEval 4.2.8 diagnostic completed on 2026-10-11 using
the local `llama3.2:3b` judge: Faithfulness 1.0000, Answer Relevancy 0.3333,
and Reference Correctness 0.6000 (threshold 0.70).
Faithfulness uses a custom extraction prompt and schema capped at 20 facts
**total** across the unchanged retrieved context. It is a limited-evidence
single-case diagnostic; the earlier per-document extraction failed from
timeouts/output truncation. Only Faithfulness passed. The local judge has
not been human validated; this does not establish complete answer
correctness or a newly completed 40-question benchmark. Metric evidence:
[Q01 diagnostic](data/evaluation/q01_deepeval_diagnostic.json).
No model-based hallucination score is claimed.

The historical Chroma deployment applied role clearance inside its query. BM25 returns only authorized
candidates but retains a shared server-side corpus in memory; physical per-role
corpus isolation is not implemented. Telemetry and cache are bounded process-local
stores. The earlier CPU-laptop timing results do not characterize this serverless deployment.

The required 2-3 minute assignment video is a separate submission item. See `docs/PROJECT10_REQUIREMENTS.md` and
`docs/VIDEO_SCRIPT.md` for the requirement mapping and recording sequence.
