import { vi } from "vitest"
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }),
})
HTMLElement.prototype.scrollIntoView = vi.fn()
