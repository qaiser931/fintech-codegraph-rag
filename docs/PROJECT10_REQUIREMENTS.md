# Edversity Project 10: requirement-to-evidence map

Source: RAG-IdeaList-EdversityLab.pdf, page 13 (Project 10), page 2 (mandatory
production standards) and page 1 (delivery rules). Reviewed 2026-10-10.

| Requirement | Implementation/evidence | Delivery status |
| --- | --- | --- |
| AST code parser and symbol extraction | src/ingestion/ast_parser.py, chunker.py | Implemented; offline parser tests passed |
| Dependency graph and call expansion | graph_builder.py, retrieval/graph_expand.py | Implemented; real retrieval demo completed on laptop |
| Dense + sparse search, RRF and cross-encoder reranking | retrieval/dense.py, bm25.py, rrf.py, reranker.py, hybrid.py | Implemented; three-mode real-model demo available |
| Payment code query and optional stack trace | POST /query and /retrieve; Streamlit inputs | Implemented; deployment of Explore patch requires finish helper success |
| Call paths and code line/file references | Query and retrieval response models; authenticated source viewer | Implemented; prior source fetch checks passed; manual visual check pending |
| Failure impact analysis and technical answer | generator.py with code/path grounding and role prompts | Implemented engine; earlier live answer was INSUFFICIENT_EVIDENCE, not independently audited causal analysis |
| Required four Project 10 metrics | evaluation/metrics.py and historical real_report.md | Historical symbol precision, path recall, path accuracy, citation-match proxy retained; historical citation score 0 |
| 25-50 question gold benchmark | data/evaluation/gold_dataset.json contains 40 cases with document IDs, paths and answer facts | Available; no fresh full benchmark for final delivery |
| Recall/precision/MRR/NDCG baselines | runner.py, run_real_evaluation.py, historical results JSON | Available; historical provenance/limits documented |
| Faithfulness/correctness/hallucination via Ragas or DeepEval judge | llm_evaluation.py has deterministic proxies and optional legacy judge code | NOT verified; proxy output does not satisfy verified LLM-as-judge results. Relevancy must not be reported as correctness |
| Metadata governance | CodeChunk doc/tenant/version/time/security/jurisdiction/source authority fields | Implemented; values are sample metadata |
| Pre-retrieval authorization | Token-bound role, Chroma query filter, candidate/path filtering, source containment | Returned user results are filtered; BM25 uses a shared loaded corpus, not physical per-role memory isolation |
| p50/p95, tokens, cost, cache | telemetry.py, GET /metrics, query response/UI | Implemented; process-local memory and cache reset on restart |
| Typed failure statuses and structured traces | API models, generation evidence fallback, trace store | Implemented; authentication 401/403 verified historically |
| FastAPI + functional web UI | src/api, ui; offline AppTest cases | 201 offline review tests passed; actual new laptop deployment/visual check pending helper/user |
| Comprehensive README with architecture diagram | README.md Mermaid architecture and setup | Included in final bundle and patch |
| Public GitHub repository | Clean project folder, credential-free template, ignore rules | Publication not verified; user must provide or publish repository URL |
| 2-3 minute video | docs/VIDEO_SCRIPT.md | Recording plan provided; actual video not yet recorded |

## Recorded real-model demo (one question)

| Retrieval mode | Role | Recall@5 | Expected context coverage | Items | Time |
| --- | --- | ---: | ---: | ---: | ---: |
| vector | Senior Dev | 0.40 | 0.40 | 6 | 0.43 s |
| hybrid | Senior Dev | 0.40 | 0.60 | 6 | 2.80 s |
| hybrid_graph | Senior Dev | 0.40 | 1.00 | 12 | 4.38 s |
| hybrid_graph | Junior Dev | 0.50 | 1.00 | 12 | 4.01 s |

Coverage denominators differ: five Senior expected symbols, four Junior authorized
symbols. Appended graph context can increase full-context coverage without changing
Recall@5. Do not describe these results as a 40-case benchmark or universal accuracy.

## Deadline submission

1. Finish local deployment; confirm the site opens and the feature displays.
2. Publish this project's clean source to a public GitHub repository and retain its URL.
3. Record the 2-3 minute video with actual query/result, source links, role filtering,
   typed failure behavior and accurately labeled metrics.
4. Submit the repo and video links. State evaluation/isolation limits honestly.

Full rubric compliance is not claimed until the pending delivery items and verified
judge evaluation are completed. Do not manufacture scores to fill the gaps.

Online demo update: the final offline run passed **204 tests** in 5.54 seconds, including public API-target isolation. Four focused helper checks passed for UI ownership and stale-listener rejection. The actual Windows tunnel and external browser result remain unverified until the laptop helper is run.
