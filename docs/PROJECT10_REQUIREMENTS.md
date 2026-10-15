# Edversity Project 10: requirement-to-evidence map

Source: RAG-IdeaList-EdversityLab.pdf, Project 10 page 13, production standards
page 2, delivery rules page 1. Updated 2026-10-13 for Vercel. This update retains
the original requirement interpretation and does not mark missing scores complete.

| Requirement | Current evidence | Status / limits |
| --- | --- | --- |
| AST parser and symbols | ast_parser.py, chunker.py | Implemented/tested; Python .py only |
| Dependency graph/call expansion | graph_builder.py, graph_expand.py | Implemented/tested, including real retrieval |
| Dense/sparse, RRF, cross-encoder | ONNX BGE/exact cosine, BM25, RRF, ONNX MiniLM | Implemented; three modes and three roles benchmarked |
| Query and optional stack trace | /api/query, /api/retrieve, Next.js dashboard | Implemented/tested |
| Call paths, file/line references | Typed responses and source viewer | Implemented; live source/access checks passed |
| Failure impact/technical answers | Grounded generator, graph evidence, typed statuses | Implemented; full quality benchmark remains separate |
| Code-symbol precision | final_retrieval_report.json | Fresh full-context symbol precision, distinct from Precision@5 |
| Call-path recall | final_retrieval_report.json | Authorized reference-path symbol coverage in returned paths |
| Execution-path accuracy | final_retrieval_report.json | Ordered authorized gold path in one returned path |
| Citation groundedness | Q11 live check; final answer runner | One actual-answer reference-match proxy; full citation evaluation pending, not semantic grounding proof |
| 25-50 gold questions | gold_dataset.json: 40 cases | Present; retrieval references filtered by role |
| Recall/precision/MRR/NDCG baselines | Final ONNX report; historical real_results.json | Fresh ONNX three-mode benchmark; PyTorch history retained without equivalence claim |
| Ragas/DeepEval faithfulness/correctness/hallucination | Explicit Groq/DeepEval final answer runner | SDK contract tested; full current judge run pending private-key execution |
| Metadata governance | CodeChunk metadata/source references | Implemented; jurisdiction/authority/version values are fixtures |
| Pre-retrieval authorization | Dense/BM25 candidates, graph/source checks | Implemented; no physical per-role corpus isolation; public sample selector is not login |
| p50/p95, tokens, cost, cache | telemetry.py and query telemetry | Implemented; bounded process-local state, not durable/shared analytics |
| Typed failures and traces | API models, error handling, tests | Implemented; live 400/401/403 passed; provider errors tested offline |
| FastAPI and functional web UI | Root Next.js app, api/index.py | Deployed; live landing/dashboard checks passed |
| README and architecture | README.md, VERCEL.md | Included with current setup and limits |
| Public GitHub | github.com/qaiser931/fintech-codegraph-rag | Public main verified; final update push needs its own confirmation |
| 2-3 minute video | VIDEO_SCRIPT.md | Excluded at user's request; not claimed complete |

Detailed status: SUBMISSION.md. Evaluation commands/definitions: EVALUATION.md.
Reports are in data/evaluation. The Vercel profile uses build-time immutable
indices and a read-only runtime. Chroma/Streamlit/native indexing is optional
historical source, not the deployed backend. Arbitrary upload/runtime re-indexing
is not implemented in this submission.

The earlier Q01 DeepEval diagnostic is one limited-evidence local-judge case
with below-threshold relevance/correctness. It is not current 40-case Groq
quality evidence. Failed cases and missing scores must remain visible.
