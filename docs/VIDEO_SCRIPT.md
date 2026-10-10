# Project 10 video: 2 minutes 45 seconds

Record the actual UI and repository. Hide credentials and personal terminal content.
Prepare the UI first. Any cut that shortens generation waiting should be labeled
"waiting shortened"; do not change or invent answers, timings or scores.

| Time | Screen | Narration/action |
| --- | --- | --- |
| 00:00-00:20 | README architecture diagram | "Our Project 10 is Cursor-Style Fintech Codebase Graph RAG. It helps a developer connect isolated code snippets to the payment execution path in a Pakistani fintech sample codebase." |
| 00:20-00:40 | Diagram and metadata | "Python AST symbols become chunks with file and line metadata. BGE vector search and BM25 are fused using RRF, then reranked. The graph adds caller and callee context after role filtering." |
| 00:40-01:20 | Senior Dev, JazzCash question | Select Senior Dev. Show Explore code matches, call paths and Open source. "For this question, graph context recovered all five expected Senior symbols. The source references make the retrieved evidence inspectable." |
| 01:20-01:50 | Generate answer result | Show a real completed answer from the UI. Explain citations, typed evidence status and telemetry. If it says INSUFFICIENT_EVIDENCE, say "The engine reports insufficient evidence rather than claiming a verified root cause." Do not relabel it as supported. |
| 01:50-02:10 | Junior Dev role switch | Show that previous output/source clear; run authorized retrieval. "Results and source access are restricted by the token-bound role. Changing a body field cannot elevate that role." |
| 02:10-02:30 | Metrics/report | Show four-combination demo table or historical baseline report. "These JazzCash timings are one-question retrieval observations. The 40-case report is historical. Judge-based answer quality is not yet verified." |
| 02:30-02:45 | README/repo URL | "FastAPI exposes the service and Streamlit provides the UI. Tests cover authentication, paths and failure handling. The README records setup and known limitations, including CPU generation delays." Show the actual public repo URL. |

For explicit failure handling, show an actual generated INSUFFICIENT_EVIDENCE result,
not just an Explore empty match. If no completed generation result is available,
record one deliberate UI Generate answer request, wait for it to finish, and preserve
its actual status. Do not launch evaluation batches or repeatedly click after a timeout.

This file is a recording script. It is not a finished video presentation.
