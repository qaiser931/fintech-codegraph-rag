import { afterEach, beforeEach, expect, test, vi } from "vitest"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import Page from "@/app/dashboard/page"

const citation = {
  doc_id: "fixture-doc",
  symbol_name: "fixture_symbol",
  file_path: "data/sample_codebase/integrations/onelink_client.py",
  start_line: 1,
  end_line: 2,
}
const result = {
  query: "Fixture question",
  answer: "## Fixture heading\n\n- A supported **fixture** fact.",
  status: "SUPPORTED",
  citations: [citation],
  call_path: ["caller → callee"],
  latency_ms: 9000,
}
let fetchMock: ReturnType<typeof vi.fn>
function json(data: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { "content-type": "application/json" },
    })
  )
}
beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal("fetch", fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
function ask() {
  fireEvent.change(screen.getByLabelText("Investigation question"), {
    target: { value: "Fixture question" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Generate answer" }))
}
async function showResult() {
  fetchMock.mockImplementation(() => json(result))
  ask()
  await screen.findByText("Fixture heading")
}

test("Markdown headings and lists render as semantic elements", async () => {
  render(<Page />)
  await showResult()
  expect(screen.getByRole("heading", { name: "Fixture heading" })).toBeTruthy()
  expect(screen.getByRole("listitem").textContent).toContain(
    "supported fixture fact"
  )
})
test("Explore uses source references without an answer confidence badge", async () => {
  fetchMock.mockImplementation(() =>
    json({ sources: [citation], call_path: ["caller → callee"] })
  )
  render(<Page />)
  fireEvent.change(screen.getByLabelText("Investigation question"), {
    target: { value: "Fixture question" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Explore code" }))
  await screen.findByText("CODE EVIDENCE")
  expect(screen.queryByText("SUPPORTED")).toBeNull()
  expect(screen.getByRole("button", { name: /sources \(1\)/i })).toBeTruthy()
})
test("Changing role aborts pending query and prevents its late result from appearing", async () => {
  let finish: (data: Response) => void = () => {}
  fetchMock.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  render(<Page />)
  ask()
  const init = fetchMock.mock.calls[0][1]
  fireEvent.change(screen.getByLabelText("Investigator role"), {
    target: { value: "Junior Dev" },
  })
  expect(init.signal.aborted).toBe(true)
  finish(new Response(JSON.stringify(result)))
  await waitFor(() =>
    expect(screen.getByText("Start with a question")).toBeTruthy()
  )
  expect(screen.queryByText("Fixture heading")).toBeNull()
})
test("Editing the question clears the previous answer and source references", async () => {
  render(<Page />)
  await showResult()
  fireEvent.change(screen.getByLabelText("Investigation question"), {
    target: { value: "A different question" },
  })
  expect(screen.queryByText("Fixture heading")).toBeNull()
  expect(screen.queryByText("fixture_symbol")).toBeNull()
})
test("Editing the stack trace clears evidence from the previous scope", async () => {
  render(<Page />)
  await showResult()
  fireEvent.change(screen.getByLabelText("Stack trace"), {
    target: { value: "New exception" },
  })
  expect(screen.queryByText("Fixture heading")).toBeNull()
})
test("A source response arriving after a role change is discarded", async () => {
  render(<Page />)
  await showResult()
  let finish: (data: Response) => void = () => {}
  fetchMock.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  fireEvent.click(screen.getByRole("button", { name: /fixture_symbol/ }))
  fireEvent.change(screen.getByLabelText("Investigator role"), {
    target: { value: "Security Lead" },
  })
  finish(new Response(JSON.stringify({ code: "private_old_role_source" })))
  await waitFor(() =>
    expect(screen.getByText("Your evidence, one click away")).toBeTruthy()
  )
  expect(screen.queryByText("private_old_role_source")).toBeNull()
})
test("Health checking does not unlock generation while a query is running", async () => {
  fetchMock.mockImplementation((url: string) =>
    url === "/api/health"
      ? json({
          ok: true,
          checked_at: "2026-10-11T15:00:00Z",
          chunks: 64,
          graph_nodes: 64,
        })
      : new Promise(() => {})
  )
  render(<Page />)
  ask()
  fireEvent.click(screen.getByRole("button", { name: "Check connection" }))
  await screen.findByText("Available at last check")
  expect(
    (
      screen.getByRole("button", {
        name: "Generate answer",
      }) as HTMLButtonElement
    ).disabled
  ).toBe(true)
})
test("Permission errors are visible and do not create a result", async () => {
  fetchMock.mockImplementation(() =>
    json({ error: "Access denied for this role." }, 403)
  )
  render(<Page />)
  ask()
  await screen.findByRole("alert")
  expect(screen.getByRole("alert").textContent).toContain("Access denied")
  expect(screen.queryByText("Investigation result")).toBeNull()
})
test("Source code stays literal text and cannot inject HTML into the UI", async () => {
  render(<Page />)
  await showResult()
  fetchMock.mockImplementation(() =>
    json({ code: '<script>danger()</script>\nreturn "ok"' })
  )
  fireEvent.click(screen.getByRole("button", { name: /fixture_symbol/ }))
  await screen.findByText("<script>danger()</script>")
  expect(document.querySelector("script")).toBeNull()
})

test("Cancelling a request aborts it and discards a late response", async () => {
  let finish: (data: Response) => void = () => {}
  fetchMock.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  render(<Page />)
  ask()
  const signal = fetchMock.mock.calls[0][1].signal
  fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }))
  expect(signal.aborted).toBe(true)
  finish(new Response(JSON.stringify(result)))
  await waitFor(() =>
    expect(screen.getByText("Start with a question")).toBeTruthy()
  )
  expect(screen.queryByText("Fixture heading")).toBeNull()
  expect(
    (
      screen.getByRole("button", {
        name: "Generate answer",
      }) as HTMLButtonElement
    ).disabled
  ).toBe(false)
})

test("New investigation clears the question, stack trace and old answer", async () => {
  render(<Page />)
  fireEvent.change(screen.getByLabelText("Stack trace"), {
    target: { value: "Old exception" },
  })
  await showResult()
  fireEvent.click(screen.getByRole("button", { name: "New investigation" }))
  expect(
    (screen.getByLabelText("Investigation question") as HTMLTextAreaElement)
      .value
  ).toBe("")
  expect(
    (screen.getByLabelText("Stack trace") as HTMLTextAreaElement).value
  ).toBe("")
  expect(screen.queryByText("Fixture heading")).toBeNull()
})

test("Execution path count tracks returned paths rather than symbols in each path", async () => {
  fetchMock.mockImplementation(() =>
    json({
      sources: [citation],
      call_path: ["caller → service → database", "callback → verifier"],
    })
  )
  render(<Page />)
  fireEvent.change(screen.getByLabelText("Investigation question"), {
    target: { value: "Fixture question" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Explore code" }))
  await screen.findByText("CODE EVIDENCE")
  fireEvent.click(screen.getByRole("button", { name: "paths (2)" }))
  expect(screen.getByText("caller → service → database")).toBeTruthy()
  expect(screen.getByText("callback → verifier")).toBeTruthy()
  expect(screen.queryByRole("button", { name: "paths (5)" })).toBeNull()
})
