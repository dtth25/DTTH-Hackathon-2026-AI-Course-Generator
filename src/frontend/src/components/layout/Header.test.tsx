import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Header } from "./Header"

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("@/components/layout/ThemeToggle", () => ({
  ThemeToggle: () => null,
}))

vi.mock("@/lib/auth", () => ({
  isAuthenticated: () => false,
  removeToken: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  apiLogout: vi.fn(),
}))

describe("Header", () => {
  it("exposes the mobile navigation state and controlled panel", () => {
    render(<Header />)

    const trigger = screen.getByRole("button", { name: "Mở trình đơn" })
    expect(trigger).toHaveAttribute("aria-expanded", "false")
    expect(trigger).toHaveAttribute("aria-controls", "mobile-navigation")
    expect(document.getElementById("mobile-navigation")).not.toBeInTheDocument()

    fireEvent.click(trigger)

    expect(screen.getByRole("button", { name: "Đóng trình đơn" })).toHaveAttribute(
      "aria-expanded",
      "true"
    )
    expect(document.getElementById("mobile-navigation")).toBeInTheDocument()
  })
})
