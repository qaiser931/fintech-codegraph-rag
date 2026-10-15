# Final evaluation

Historical results and the Q01 limited diagnostic are retained without changing
their scores or presenting them as evidence for the current generator.

## Retrieval benchmark

Use the lightweight backend environment and prepared ONNX assets:

```text
python scripts/prepare_vercel.py
python scripts/final_retrieval_benchmark.py
```

The final JSON/Markdown report covers 40 questions, three roles and three modes
(360 retrieval-only checks). Ranking denominators use the gold symbols visible
to each role. Questions with no authorized gold symbols are N/A. Full-context
recall is distinct from Recall@5. Path recall uses the union of returned paths;
path accuracy requires an ordered gold-path subsequence in one returned path.
Zero unauthorized results does not imply physical per-role corpus isolation.
Timings are local, not Vercel performance or PyTorch/ONNX equivalence.

## Actual generated-answer and model-judge benchmark

This is explicit, live work. Use an isolated evaluation environment:

```powershell
py -3.12 -m venv .venv-evaluation
& .\.venv-evaluation\Scripts\python.exe -m pip install -r requirements-evaluation.txt -c requirements-evaluation.lock
$env:CODEGRAPH_SERVERLESS = '1'
& .\.venv-evaluation\Scripts\python.exe scripts/final_answer_evaluation.py
```

Keep GROQ_API_KEY in the ignored root .env.vercel.local or .env, or in the process
environment. The script reads it privately; never paste it into chat or commit it.
The deployed application uses its own server credentials; the local key is only
for judging. No Ollama, Docker, local embedding model, or external backend port is
needed by this evaluation command.

The default selects all 40 gold cases as Security Lead, so the reference can
include all sample security levels. Each answer and exact retrieved context is
saved before judging. Deployed source text is checked against the local corpus.
An answer is not regenerated when resuming a saved snapshot.

Four separate metrics use DeepEval 4.2.8 with a custom Groq model adapter:

| Field | Definition | Direction |
| --- | --- | --- |
| faithfulness | SDK claim support against the retrieved context | Higher is better |
| answer_relevancy | SDK response relevance to the question | Higher is better |
| reference_correctness | G-Eval against the supplied gold answer facts | Higher is better |
| hallucination_free | Raw SDK HallucinationMetric score against supplied contexts | Higher is better |

The installed pinned SDK's hallucination metric uses passing-context agreement,
not the older violation-rate direction. The legacy proxy runner converts its
raw hallucination-free score to a violation rate as 1 minus that score, never
1 minus model faithfulness. The final report retains the raw SDK score.
The separate citation-gold-match proxy measures actual answer citation references,
not semantic grounding of every claim.

Model judging is not human validation. Gold facts can contain assumptions beyond
the executable sample, and a good conservative answer can disagree with them.
Keep failures, low scores and insufficient-evidence answers visible.

Each request has a bounded timeout. The run has a request/time budget checked
before further requests. There are no automatic retries. A quota, timeout,
invalid JSON or truncated response stops the run with null/unscored metrics.
Saved completed stages are reused only after checking protocol/corpus and
snapshot fingerprints. Resume explicitly:

```powershell
& .\.venv-evaluation\Scripts\python.exe scripts/final_answer_evaluation.py --resume
```

Results initially live under ignored telemetry_logs/final-answer-evaluation.
Only a results.json with full_dataset_complete=true establishes a completed
40-case judge run. A one-case run, mock SDK test, working source link, or
1-faithfulness calculation does not establish that result.
After completing the full run, publish the reviewed report as
data/evaluation/final_answer_report.json and .md; preserve its scope and limits.

## Deployment smoke check

```text
python scripts/verify_submission.py
```

This performs contract/security checks and one live documented-latency question.
Use --no-generation for a read-only retrieval/source check. It is not a full
quality benchmark or a guarantee of production latency.
