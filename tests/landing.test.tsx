import { afterEach, expect, test, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import HomePage from "@/app/page"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
test("The Stackwise landing works without a backend and opens both live and demo workspaces", () => {
  const fetch = vi.fn()
  vi.stubGlobal("fetch", fetch)
  render(<HomePage />)
  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
    "Know whichrepository needsyou next."
  )
  expect(
    screen
      .getByRole("link", { name: "Open your workspace" })
      .getAttribute("href")
  ).toBe("/dashboard")
  expect(
    screen.getByRole("link", { name: "Explore the demo" }).getAttribute("href")
  ).toBe("/dashboard?demo=1")
  expect(screen.getByText("Illustrative sample · no client data")).toBeTruthy()
  expect(fetch).not.toHaveBeenCalled()
})
test("Human approval and truthful limits are visible on the landing", () => {
  render(<HomePage />)
  expect(screen.getByText(/No autonomous merges/)).toBeTruthy()
  expect(screen.getByText("Clear coverage limits")).toBeTruthy()
  expect(
    screen.getByRole("link", { name: /View source/ }).getAttribute("href")
  ).toBe("https://github.com/qaiser931/fintech-codegraph-rag")
})

test("Landing page provides GitHub sign in buttons, target audience and working features", () => {
  render(<HomePage />)
  const githubLinks = screen.getAllByRole("link", { name: /GitHub/i })
  expect(githubLinks.length).toBeGreaterThanOrEqual(2)
  expect(githubLinks[0].getAttribute("href")).toBe("/api/auth/github")

  expect(screen.getByText("Software agencies")).toBeTruthy()
  expect(screen.getByText("Small software startups")).toBeTruthy()
  expect(screen.getByText("Software development teams")).toBeTruthy()
  expect(screen.getByText("Engineering & product managers")).toBeTruthy()

  expect(screen.getByText("AI code review & reports")).toBeTruthy()
  expect(screen.getByText("Workspace management")).toBeTruthy()
  expect(screen.getByText("Multiple repository analysis")).toBeTruthy()
  expect(screen.getByText("Ask Your Code")).toBeTruthy()
})

