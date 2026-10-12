import { afterEach, expect, test, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import HomePage from "@/app/page"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test("The landing page remains usable without a backend and opens the real workspace", () => {
  const fetch = vi.fn()
  vi.stubGlobal("fetch", fetch)
  render(<HomePage />)
  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
    "Find the evidence"
  )
  const links = screen.getAllByRole("link", { name: "Open dashboard" })
  expect(links.length).toBeGreaterThan(0)
  for (const link of links) expect(link.getAttribute("href")).toBe("/dashboard")
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByText("Illustrative preview")).toBeTruthy()
  expect(screen.queryByText("SUPPORTED")).toBeNull()
})

test("Project links point to the actual repository and documentation", () => {
  render(<HomePage />)
  expect(
    screen.getByRole("link", { name: "View source" }).getAttribute("href")
  ).toBe("https://github.com/qaiser931/fintech-codegraph-rag")
  expect(
    screen
      .getByRole("link", { name: /Explore the project documentation/ })
      .getAttribute("href")
  ).toContain("/docs/PROJECT10_REQUIREMENTS.md")
  expect(
    screen.getByText(/Individual successful requests are diagnostics/)
  ).toBeTruthy()
})
