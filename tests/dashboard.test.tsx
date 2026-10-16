import { afterEach, expect, test, vi } from "vitest"
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import StackwiseApp from "@/components/stackwise-app"
import fixture from "./stackwise-demo.json"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState(null, "", "/")
})
function mockDemo(data: typeof fixture = fixture) {
  window.history.replaceState(null, "", "/dashboard?demo=1")
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    void options
    return new Response(
      JSON.stringify(
        url.endsWith("session") ? { user: null, setup: {} } : data
      ),
      { status: 200, headers: { "Content-Type": "application/json" } }
    )
  })
  vi.stubGlobal("fetch", fetch)
  return fetch
}
async function navigate(name: string) {
  await userEvent.click(
    within(
      screen.getByRole("navigation", { name: "Workspace navigation" })
    ).getByRole("button", { name: new RegExp(name) })
  )
}

test.each([
  ["needs_review", "Needs review", false],
  ["approved", "Approved", true],
  ["request_changes", "Changes requested", false],
] as const)(
  "Review list and detail keep the human decision %s independent of finding count",
  async (status, expected, keepFindings) => {
    mockDemo({
      ...fixture,
      reviews: fixture.reviews.map((review) => ({ ...review, status })),
      findings: keepFindings ? fixture.findings : [],
    })
    render(<StackwiseApp />)
    await screen.findByRole("heading", { name: "Agency overview" })
    await navigate("Code reviews")
    const row = screen.getByRole("button", { name: /#128/ })
    expect(within(row).getByText(expected)).toBeTruthy()
    expect(within(row).queryByText("Reviewed")).toBeNull()
    await userEvent.click(row)
    await screen.findByRole("heading", {
      name: /#128 Add client account endpoint/,
    })
    expect(screen.getByText(expected)).toBeTruthy()
  }
)

test("Demo is clearly labeled and portfolio filters do not mix client findings", async () => {
  mockDemo()
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  expect(
    screen.getByText(/All metrics and findings are illustrative/)
  ).toBeTruthy()
  await userEvent.selectOptions(
    screen.getByLabelText("Filter workspace"),
    "demo-beta"
  )
  expect(screen.queryByText("Account ownership needs a check")).toBeNull()
  expect(screen.queryByRole("button", { name: "Open Client Alpha" })).toBeNull()
})

test("A sample PR exposes exact source, patch preview and local review decisions", async () => {
  const fetch = mockDemo()
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  await navigate("Code reviews")
  await userEvent.click(screen.getByRole("button", { name: /#128/ }))
  await screen.findByRole("heading", {
    name: /#128 Add client account endpoint/,
  })
  expect(
    screen.getByText(
      "Source location checked. Semantic correctness requires human validation."
    )
  ).toBeTruthy()
  await userEvent.click(
    screen.getByRole("button", {
      name: /TLS certificate verification is disabled/,
    })
  )
  await userEvent.click(screen.getByRole("button", { name: "Review patch" }))
  expect(
    screen.getByRole("region", { name: /patch of auth\/routes.py/ }).textContent
  ).toContain("+        verify=True")
  await userEvent.click(screen.getByRole("button", { name: "Mark resolved" }))
  expect(screen.getByText(/Demo decision updated/)).toBeTruthy()
  expect(
    fetch.mock.calls.every(
      ([, options]) => !options || (options as RequestInit).method !== "POST"
    )
  ).toBeTruthy()
})

test("Repository source stays literal and cannot inject HTML", async () => {
  mockDemo()
  const original = fixture.reviews[0].files[0].source
  fixture.reviews[0].files[0].source = '<img src=x onerror="window.hacked=1">'
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  await navigate("Code reviews")
  await userEvent.click(screen.getByRole("button", { name: /#128/ }))
  const region = await screen.findByRole("region", { name: /source of/ })
  expect(region.textContent).toContain("<img src=x")
  expect(region.querySelector("img")).toBeNull()
  fixture.reviews[0].files[0].source = original
})

test("Switching clients clears a code answer and its source references", async () => {
  mockDemo()
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  await navigate("Workspaces")
  await userEvent.type(
    screen.getByLabelText("Codebase question"),
    "How does ownership work?"
  )
  await userEvent.click(screen.getByRole("button", { name: "Ask code" }))
  await screen.findByText(/In the sample account route/)
  await userEvent.selectOptions(
    screen.getByLabelText("Filter workspace"),
    "demo-beta"
  )
  expect(screen.queryByText(/In the sample account route/)).toBeNull()
})

test("A report states sample status, source limitations and actual review decisions", async () => {
  mockDemo()
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  await navigate("Reports")
  await userEvent.click(
    screen.getByRole("button", { name: "Generate report for Client Alpha" })
  )
  await screen.findByText("Illustrative demo. No live client measurements.")
  expect(screen.getByText(/Tests were not executed/)).toBeTruthy()
  expect(screen.getByRole("button", { name: "Download" })).toBeTruthy()
})

test("Live unauthenticated sessions show sign-in, never a client portfolio", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ user: null, setup: { database: false } }))
    )
  )
  render(<StackwiseApp />)
  await screen.findByLabelText("Access key")
  expect(screen.queryByRole("heading", { name: "Agency overview" })).toBeNull()
  expect(screen.getByText("Deployment setup required")).toBeTruthy()
})

test("Out-of-order review responses are discarded after changing navigation", async () => {
  window.history.replaceState(null, "", "/dashboard")
  let resolveReview: (value: Response) => void = () => {}
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("session"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              user: {
                name: "Client",
                role: "reviewer",
                csrf: "test",
                workspace_id: "demo-alpha",
              },
              setup: {},
            })
          )
        )
      if (url.endsWith("portfolio"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...fixture,
              demo: false,
              reviews: fixture.reviews.map((r) => ({
                ...r,
                created: Date.now() / 1000,
              })),
            })
          )
        )
      return new Promise<Response>((resolve) => {
        resolveReview = resolve
      })
    })
  )
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  await navigate("Code reviews")
  await userEvent.click(screen.getByRole("button", { name: /#128/ }))
  await navigate("Workspaces")
  resolveReview(new Response(JSON.stringify(fixture.reviews[0])))
  await waitFor(() =>
    expect(screen.queryByRole("region", { name: /source of/ })).toBeNull()
  )
  expect(
    screen.getByRole("heading", { name: "Connected repositories" })
  ).toBeTruthy()
})

test("A live answer arriving after a workspace switch is discarded", async () => {
  window.history.replaceState(null, "", "/dashboard")
  let resolveAnswer: (value: Response) => void = () => {}
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      if (url.endsWith("session"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              user: {
                name: "Agency",
                role: "owner",
                csrf: "test",
                workspace_id: null,
              },
              setup: {},
            })
          )
        )
      if (url.endsWith("portfolio"))
        return Promise.resolve(
          new Response(JSON.stringify({ ...fixture, demo: false }))
        )
      return new Promise<Response>((resolve) => {
        resolveAnswer = resolve
      })
    })
  )
  render(<StackwiseApp />)
  await screen.findByRole("heading", { name: "Agency overview" })
  await navigate("Workspaces")
  await userEvent.type(
    screen.getByLabelText("Codebase question"),
    "Explain the caller"
  )
  await userEvent.click(screen.getByRole("button", { name: "Ask code" }))
  await userEvent.selectOptions(
    screen.getByLabelText("Filter workspace"),
    "demo-beta"
  )
  resolveAnswer(
    new Response(
      JSON.stringify({
        answer: "OUTDATED CLIENT ALPHA ANSWER",
        status: "cited",
        citations: fixture.findings.map((f) => f.evidence),
      })
    )
  )
  await waitFor(() =>
    expect(screen.queryByText("OUTDATED CLIENT ALPHA ANSWER")).toBeNull()
  )
})
