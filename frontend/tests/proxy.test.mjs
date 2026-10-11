import { test, before, after } from "node:test"
import assert from "node:assert/strict"
import http from "node:http"
import { spawn } from "node:child_process"
import { readdir, readFile } from "node:fs/promises"
import path from "node:path"

// Contract fixture only: no real model, index, or credentials are used.
const tokens = {
  "fixture-junior-token-00000": "Junior Dev",
  "fixture-senior-token-00000": "Senior Dev",
  "fixture-security-token-000": "Security Lead",
}
const citation = {
  doc_id: "fixture-doc",
  symbol_name: "verify_switch_transaction",
  file_path: "data/sample_codebase/integrations/onelink_client.py",
  start_line: 2,
  end_line: 3,
}
const sourceCode = 'first <tag> & value\n\nreturn "ok"'
let base,
  api,
  app,
  child,
  healthIndexed = true
let seen = []
async function listen(server) {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve))
  return server.address().port
}
function send(res, data, status = 200) {
  res.writeHead(status, { "content-type": "application/json" })
  res.end(JSON.stringify(data))
}
before(async () => {
  api = http.createServer(async (req, res) => {
    let text = ""
    for await (const chunk of req) text += chunk
    const body = text ? JSON.parse(text) : null
    seen.push({ path: req.url, auth: req.headers.authorization, body })
    if (req.url === "/health")
      return send(res, {
        status: "healthy",
        indexed: healthIndexed,
        chunks: 64,
        graph_nodes: 64,
        graph_edges: 264,
      })
    const token = req.headers.authorization?.replace("Bearer ", "")
    if (!tokens[token])
      return send(res, { detail: "PRIVATE_SERVER_SECRET" }, 401)
    if (body && tokens[token] !== body.role)
      return send(res, { detail: "PRIVATE_SERVER_SECRET" }, 403)
    if (body?.query.startsWith("error "))
      return send(
        res,
        { detail: "PRIVATE_SERVER_SECRET" },
        Number(body.query.split(" ")[1])
      )
    if (body?.query === "invalid json") {
      res.writeHead(200)
      return res.end("invalid")
    }
    if (body?.query === "wrong contract")
      return send(res, { answer: "old API" })
    if (body?.query === "redirect test") {
      res.writeHead(302, { location: "/credential-leak" })
      return res.end()
    }
    if (req.url.startsWith("/source/")) {
      const role = new URL(req.url, "http://fixture").searchParams.get("role")
      if (tokens[token] !== role || role === "Security Lead")
        return send(res, { detail: "PRIVATE_SERVER_SECRET" }, 403)
      res.writeHead(200, { "content-type": "text/html" })
      return res.end(
        '<html><title>NOT_SOURCE</title><h1>NOT_SOURCE</h1><pre><code><span id="L1">first &lt;tag&gt; &amp; value</span>\n<span id="L2">&nbsp;</span>\n<span id="L3">return &quot;ok&quot;</span></code></pre></html>'
      )
    }
    const common = {
      query: body.query,
      role: body.role,
      call_path: ["caller → callee"],
      retrieved_items: [],
      latency_ms: 120,
    }
    return send(
      res,
      req.url === "/retrieve"
        ? { ...common, sources: [citation] }
        : {
            ...common,
            answer: "Fixture answer",
            status: "SUPPORTED",
            citations: [citation],
          }
    )
  })
  const backendPort = await listen(api)
  const reservation = http.createServer()
  const appPort = await listen(reservation)
  await new Promise((resolve) => reservation.close(resolve))
  base = `http://127.0.0.1:${appPort}`
  child = spawn(
    process.execPath,
    [
      "node_modules/next/dist/bin/next",
      "start",
      "-H",
      "127.0.0.1",
      "-p",
      String(appPort),
    ],
    {
      env: {
        ...process.env,
        CODEGRAPH_API_URL: `http://127.0.0.1:${backendPort}`,
        API_ROLE_TOKENS: JSON.stringify(tokens),
        NEXT_TELEMETRY_DISABLED: "1",
      },
      stdio: "pipe",
    }
  )
  let logs = ""
  child.stdout.on("data", (chunk) => {
    logs += chunk
  })
  child.stderr.on("data", (chunk) => {
    logs += chunk
  })
  for (let i = 0; i < 150; i++) {
    if (child.exitCode !== null) throw new Error(`Next failed: ${logs}`)
    try {
      app = await fetch(base)
      if (app.ok) break
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  assert.ok(app?.ok, "Production app starts")
})
after(async () => {
  child?.kill()
  api?.closeAllConnections()
  if (api) await new Promise((resolve) => api.close(resolve))
})
async function post(
  query = "fixture question",
  role = "Junior Dev",
  extra = {},
  endpoint = "query"
) {
  return fetch(`${base}/api/${endpoint}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, role, ...extra }),
  })
}
test("Manual health works without sending a role credential and reports actual index counts", async () => {
  const response = await fetch(`${base}/api/health`)
  const data = await response.json()
  assert.equal(response.status, 200)
  assert.equal(data.ok, true)
  assert.equal(data.chunks, 64)
  assert.equal(seen.at(-1).auth, undefined)
  assert.equal(response.headers.get("cache-control"), "no-store")
})
test("Unindexed backend is not labelled ready", async () => {
  healthIndexed = false
  assert.equal((await (await fetch(`${base}/api/health`)).json()).ok, false)
  healthIndexed = true
})
for (const role of Object.values(tokens))
  test(`Query binds the canonical ${role} to its server credential`, async () => {
    const response = await post(" fixture question ", role, {
      stack_trace: " trace ",
    })
    assert.equal(response.status, 200)
    assert.equal((await response.json()).status, "SUPPORTED")
    const request = seen.at(-1)
    assert.equal(tokens[request.auth.replace("Bearer ", "")], role)
    assert.equal(request.body.query, "fixture question")
    assert.equal(request.body.stack_trace, "trace")
  })
test("Explore returns source references and a single path without an invented answer status", async () => {
  const response = await post("fixture question", "Senior Dev", {}, "retrieve")
  const data = await response.json()
  assert.equal(response.status, 200)
  assert.equal(data.sources.length, 1)
  assert.equal(data.call_path.length, 1)
  assert.equal(data.status, undefined)
  assert.equal(data.answer, undefined)
})
for (const status of [401, 403, 404, 422, 429, 500, 503, 504])
  test(`HTTP ${status} survives the proxy with no private error details`, async () => {
    const response = await post(`error ${status}`)
    const data = await response.text()
    assert.equal(response.status, status)
    assert.ok(!data.includes("PRIVATE_SERVER_SECRET"))
  })
for (const args of [
  ["ab"],
  ["x".repeat(2001)],
  ["question", "junior_dev"],
  ["question", "Junior Dev", { stack_trace: "x".repeat(8001) }],
  ["question", "Junior Dev", { stack_trace: 1 }],
]) {
  test(`Invalid input is rejected before the backend (${args[0].length} chars / ${args[1] || "default"})`, async () => {
    const count = seen.length
    assert.equal((await post(...args)).status, 400)
    assert.equal(seen.length, count)
  })
}
test("Malformed JSON is an HTTP 400", async () => {
  assert.equal(
    (await fetch(`${base}/api/query`, { method: "POST", body: "{bad" })).status,
    400
  )
})
test("Source HTML becomes only decoded, numbered code lines", async () => {
  const response = await fetch(
    `${base}/api/source/${citation.file_path}?role=Senior%20Dev`
  )
  assert.equal(response.status, 200)
  assert.equal((await response.json()).code, sourceCode)
  assert.ok(seen.at(-1).path.includes("role=Senior%20Dev"))
})
test("Source permission failure retains HTTP 403", async () => {
  assert.equal(
    (
      await fetch(
        `${base}/api/source/${citation.file_path}?role=Security%20Lead`
      )
    ).status,
    403
  )
})
test("Source outside sample codebase is rejected before the backend", async () => {
  const count = seen.length
  assert.equal(
    (await fetch(`${base}/api/source/src/config.py?role=Junior%20Dev`)).status,
    400
  )
  assert.equal(seen.length, count)
})
for (const query of ["invalid json", "wrong contract", "redirect test"])
  test(`${query} is HTTP 502`, async () => {
    assert.equal((await post(query)).status, 502)
    assert.ok(!seen.some((request) => request.path === "/credential-leak"))
  })
test("Build includes the real dashboard and excludes fixture credentials from browser chunks", async () => {
  const html = await (await fetch(base)).text()
  assert.ok(html.includes("What do you want to investigate?"))
  assert.ok(html.includes("CodeGraph"))
  async function scan(dir) {
    for (const item of await readdir(dir, { withFileTypes: true })) {
      const name = path.join(dir, item.name)
      if (item.isDirectory()) await scan(name)
      else if (name.endsWith(".js")) {
        const content = await readFile(name, "utf8")
        for (const token of Object.keys(tokens))
          assert.ok(!content.includes(token))
        assert.ok(!content.includes("process.env.API_ROLE_TOKENS"))
      }
    }
  }
  await scan(".next/static")
})
