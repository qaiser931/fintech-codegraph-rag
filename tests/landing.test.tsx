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
