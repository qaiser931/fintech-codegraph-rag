# Project 10 delivery status

Reviewed 2026-10-13. Scope: finish the existing synthetic fintech CodeGraph RAG
project. The user excludes the video from this work. Stackwise, repository upload
and PR review are separate future work.

- Public source: https://github.com/qaiser931/fintech-codegraph-rag
- Production demo: https://fintech-codegraph-rag.vercel.app/
- Landing: / ; investigation workspace: /dashboard
- Deployment: one Vercel Next.js/Python project, Groq generation, immutable ONNX
  retrieval assets. No laptop, Ollama, Docker, Oracle VM or tunnel is required.

## Verified evidence

| Item | Evidence | Scope |
| --- | --- | --- |
| Frontend lint/typecheck/build | Passed against unchanged frontend source | Local checks, not every browser/device |
| UI regression tests | 14 passed | Landing, request state, source rendering and role changes |
| Backend/graph/generation/evaluation tests | 142 passed in the lightweight serverless profile | Provider calls mocked in generation unit tests |
| DeepEval adapter/runner contract tests | 9 passed with real pinned SDK and mocked transport | Not actual model-judge scores |
| Deployed readiness/pages | final_live_checks.json | Actual production checks at recorded timestamps |
| Authorization/source containment | final_live_checks.json and serverless tests | Public demo roles, not real user login |
| One live Groq answer | Q11, supported, one citation; reference match proxy 1.0 | Synthetic documented latency, not measured production latency |
| Gold questions | gold_dataset.json, 40 cases | Reference expectations, not a human-validated causal benchmark |
| Final retrieval modes/roles | final_retrieval_report.json and .md | 40 cases x 3 roles x 3 modes; no generated answers |

Reports are in data/evaluation. Historical PyTorch results and the limited Q01
local-judge diagnostic remain separately labelled and unchanged.

## Remaining answer-quality evidence

The current generator still needs its full 40-case model-judge run. The saved
Q01 diagnostic applies to an earlier answer/local judge, not current Groq
correctness. No missing score is replaced with a proxy, relevance score,
fabricated success, or a 1-faithfulness hallucination claim.

Run the isolated workflow in EVALUATION.md using the existing private Groq key.
After results.json reports full_dataset_complete=true, publish its reviewed JSON
and Markdown as data/evaluation/final_answer_report.json and .md and update this
section with observed scores and limits. Completing all cases does not imply
all scores meet their thresholds.

## Submission limits

- Only the bundled Python sample is indexed, using symbol chunks.
- Role/tenant filtering applies to returned evidence; no physical per-role
  corpus/model isolation. Demo visitors can select sample roles.
- Source fixtures and authority labels are synthetic, not actual provider code
  or proof of regulatory approval.
- Cache, traces and aggregate telemetry are bounded process-local state.
- Model-judge results are not human validation; low/incomplete scores stay visible.
- Video is intentionally excluded, not marked submitted.
- Full rubric compliance is not claimed while judge evidence is incomplete.

## Final handoff

Keep private env files out of Git. Commit only reviewed code, documents and
reports; never model binaries, local SDK state, credentials or logs. Use the
existing D repository and authenticated origin, without force-pushing. GitHub
push triggers the existing Vercel deployment. Confirm its final commit is Ready;
repeat smoke checks if runtime source/configuration changes.
