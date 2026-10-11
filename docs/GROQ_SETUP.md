# Groq generation profile

The laptop demo can use Groq-hosted `openai/gpt-oss-120b` instead of local Ollama
inference. Groq listed this as a production model on 2026-10-11. Its current free
plan lists 8,000 tokens/minute; actual account quotas and model permissions apply.
Official references:
https://console.groq.com/docs/models
https://console.groq.com/docs/rate-limits
https://console.groq.com/docs/reasoning

Keep the real key in the ignored `.env` only:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=
```

The last line must contain your own locally saved key. The deployment helper
retains the key, role-token mapping, Ollama settings and other environment entries;
it changes only the provider/model values in .env. The API container explicitly
selects the same Groq provider/model while reading its key from the existing
read-only .env mount. Original source and container backups are retained.

Requests go to Groq's fixed official HTTPS endpoint with a 5-second connect
wait, a 90-second read wait, 2048 completion tokens, low reasoning effort and
final-answer output only. No automatic cloud retry occurs. If output stops for
length, the generator returns its conservative evidence assessment instead of
accepting a partial answer. HTTP 429 indicates quota; HTTP 503 with the specific
cloud-credentials message indicates provider authentication/permission failure;
HTTP 504 indicates a generation timeout. Error logs contain no request text or key.

The question and retrieved code context are sent to Groq. The demonstration
corpus is synthetic. Local embeddings, reranking, graph traversal and API/UI
still consume laptop resources. Cloud generation requires internet access.
Estimated cost uses published list prices ($0.15 per million input tokens and
$0.60 per million output tokens, checked 2026-10-11); it is not an invoice and
does not establish whether your account's request was billed or used free quota.

After installing, launch Streamlit with `CODEGRAPH_QUERY_READ_TIMEOUT=240`.
The helper submits one live webhook question using the existing Junior Dev
role credentials and records its actual status/latency without copying the
answer or source into publication files. A successful response does not establish
complete answer correctness. The earlier Ollama/DeepEval Q01 diagnostic remains
historical evidence for that saved answer, not a benchmark for the Groq model.

The generator needs no running Ollama model. After verifying the switch,
`ollama stop qwen2.5:1.5b` unloads only that demo model, if loaded. Existing
Ollama installations and saved judge results can be retained.
