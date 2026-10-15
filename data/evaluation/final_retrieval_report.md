# Final ONNX retrieval benchmark

40 questions x 3 roles x 3 retrieval modes; no generated-answer or judge scores

| Role / Mode | Recall@5 | Precision@5 | MRR | NDCG@5 | Context recall | Symbol precision | Path recall | Path accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Junior Dev / vector_only | 0.7094 | 0.2308 | 0.7060 | 0.6250 | 0.7479 | 0.2009 | 0.0000 | 0.0000 |
| Junior Dev / hybrid | 0.7051 | 0.2308 | 0.6846 | 0.6123 | 0.7350 | 0.2051 | 0.0000 | 0.0000 |
| Junior Dev / hybrid_graph | 0.7051 | 0.2308 | 0.6904 | 0.6123 | 0.9423 | 0.1453 | 0.8438 | 0.8000 |
| Senior Dev / vector_only | 0.6954 | 0.2350 | 0.7113 | 0.6158 | 0.7329 | 0.2042 | 0.0000 | 0.0000 |
| Senior Dev / hybrid | 0.6925 | 0.2350 | 0.6654 | 0.5922 | 0.7108 | 0.2083 | 0.0000 | 0.0000 |
| Senior Dev / hybrid_graph | 0.6925 | 0.2350 | 0.6690 | 0.5922 | 0.8854 | 0.1458 | 0.8187 | 0.7750 |
| Security Lead / vector_only | 0.6954 | 0.2350 | 0.6904 | 0.6016 | 0.7329 | 0.2042 | 0.0000 | 0.0000 |
| Security Lead / hybrid | 0.6925 | 0.2350 | 0.6654 | 0.5916 | 0.7108 | 0.2083 | 0.0000 | 0.0000 |
| Security Lead / hybrid_graph | 0.6925 | 0.2350 | 0.6685 | 0.5916 | 0.8854 | 0.1458 | 0.8187 | 0.7750 |

All returned chunks were authorized. See JSON for per-case denominators, paths, timings and provenance.

## Interpretation

- Recall/precision/NDCG@5 and MRR use authorized gold symbol IDs; unavailable gold sets are N/A.
- Share of returned symbols in the authorized gold set; full context.
- Coverage of authorized expected-path symbols in the union of returned paths; no order credit.
- One returned path must contain the authorized gold path in order, allowing intermediate calls.
- Not measured by retrieval; actual answer citations and semantic claim grounding require answer evaluation.
- Local benchmark on this machine, including one cold first query; not Vercel p50/p95 or PyTorch equivalence.
