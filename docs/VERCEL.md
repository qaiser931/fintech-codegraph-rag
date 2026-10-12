# One-project Vercel deployment

The frontend and Python backend run under one Vercel domain. No external backend
URL, Docker container, tunnel, fixed public port or Oracle VM is used.

## Existing project settings

1. Open the existing Vercel project connected to `qaiser931/fintech-codegraph-rag`.
2. In Settings → Build and Deployment, change Root Directory from `frontend` to
   the repository root (clear the field). Framework: **Next.js**.
3. Clear custom install/build/output-directory overrides; use the default pnpm
   install and `pnpm build`. Do not set a custom install command: the Python builder
   must run the repository's `tool.vercel.scripts.vercel-install` hook.
4. Enable **Fluid compute**. `api/index.py` requests a 300-second maximum duration.
5. Set `GROQ_API_KEY`, `API_ROLE_TOKENS`, `LLM_PROVIDER=groq` and
   `LLM_MODEL=openai/gpt-oss-120b` for the deployment environment. Use the existing
   private values; the Groq key and role JSON must never be shared in chat or Git.
6. Remove the obsolete `CODEGRAPH_API_URL`; redeploy the new commit.

The migration installer writes an ignored `.env.vercel.local` with these four
settings for private import/copying. It never prints the values or commits the file.
Vercel's Production/Preview variables are independent; configure both if preview
queries should work. No cross-project self-fetch or protection bypass secret is needed.

## Build and runtime

The Python install hook uses the locked requirements, verifies pinned ONNX model
hashes and prepares 64 symbol chunks, 64 graph nodes and dense embeddings. Models
and indices enter the private function bundle, never the public static directory.
The hook runs in the Python builder itself, so it does not depend on Next's build
finishing first. Runtime does not download models, index code or write a database.

`vercel.json` maps the existing browser API paths to one Python function. The API
facade dispatches to the core FastAPI app inside the same process, without HTTP to
another host. Generation stays on Groq. Cold-start inference uses single-threaded
ONNX sessions and small batches to bound memory.

The root Python dependencies omit PyTorch, Chroma, Streamlit and evaluation SDKs.
The function excludes Node/UI files, tests, local logs and private env files. The
build checks a conservative 480 MB combined asset/dependency budget against Vercel's
500 MB Python limit; the actual deployment's reported bundle remains authoritative.

## Verification before retiring the old backend

After Ready, open `/api/health`: expect `ok: true`, 64 chunks and 64 graph nodes.
In `/dashboard`, select Junior Dev and Explore the 1LINK peak-latency question.
Open its source citation. Generate one answer: the documented sample range is
2.0–6.0 seconds, with a citation, subject to evidence validation.

Verify a confidential source is denied to Junior Dev and allowed to an authorized
role. Check the Vercel function logs if initialization fails; share the error type
and status, not environment-variable values. Verify once with the laptop API/tunnel
stopped. Only then retire the old project containers/Oracle deployment. Do not
uninstall Docker or remove unrelated applications' volumes as part of this migration.

## Free-plan scope

This configuration is designed for Vercel Hobby's current Python bundle and Fluid
function limits. Cold starts, monthly usage quotas and Groq free-account quotas can
interrupt the demo. A passed local build is not a verified cloud deployment, and
no permanent free uptime is promised. The GitHub push triggers deployment; the
final cloud routing/build checks must pass in the user's Vercel project.

Primary references:
- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/functions/limitations
- https://vercel.com/kb/guide/how-to-use-python-and-javascript-in-the-same-application
- https://github.com/vercel/vercel/tree/main/packages/python
