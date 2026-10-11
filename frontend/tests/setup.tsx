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
// Rendering-only providers: the real investigation page remains under test.
vi.mock("@/components/ui/sidebar", () => {
  const box = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  )
  return {
    Sidebar: box,
    SidebarContent: box,
    SidebarGroup: box,
    SidebarGroupContent: box,
    SidebarGroupLabel: box,
    SidebarMenu: box,
    SidebarMenuItem: box,
    SidebarProvider: box,
    SidebarMenuButton: ({
      children,
      isActive: _active,
      ...props
    }: React.ComponentProps<"button"> & { isActive?: boolean }) => (
      <button data-active={_active ? "true" : undefined} {...props}>
        {children}
      </button>
    ),
    SidebarTrigger: () => <button aria-label="Toggle sidebar" />,
  }
})
