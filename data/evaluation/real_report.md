# Codebase Graph RAG Evaluation

| Metric | vector_only | hybrid | hybrid_graph |
| --- | ---: | ---: | ---: |
| recall_at_k | 0.6954 | 0.6925 | 0.6925 |
| precision_at_k | 0.2350 | 0.2350 | 0.2350 |
| mrr | 0.7112 | 0.6654 | 0.6690 |
| ndcg_at_k | 0.6158 | 0.5922 | 0.5922 |
| code_symbol_resolution_precision | 0.2042 | 0.2083 | 0.1458 |
| call_path_recall_at_k | 0.0000 | 0.0000 | 0.5596 |
| execution_path_accuracy | 0.0000 | 0.0000 | 0.8500 |
| citation_groundedness | 0.0000 | 0.0000 | 0.0000 |

## Evaluation modes

- **vector_only**: dense/vector retrieval without hybrid lexical retrieval or graph expansion.
- **hybrid**: dense + BM25 retrieval combined through the existing hybrid pipeline.
- **hybrid_graph**: hybrid retrieval followed by code dependency graph expansion.

These metrics are deterministic retrieval/graph metrics. LLM-based faithfulness and answer-correctness evaluation should be reported separately.