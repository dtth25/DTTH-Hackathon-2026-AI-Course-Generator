import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { existsSync } from "node:fs"
import path from "node:path"

import WelcomePage from "@/app/page"
import { LANDING_COPY, MARKETING_CLAIMS } from "@/content/brand.vi"

vi.mock("@/components/auth/RedirectIfAuthed", () => ({
  RedirectIfAuthed: ({ children }: { children: React.ReactNode }) => children,
}))

describe("landing page", () => {
  it("leads with the document workflow and real product evidence", () => {
    const { container } = render(<WelcomePage />)

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Từ tài liệu đang đọc dở"
    )
    expect(screen.getAllByText("Minh họa giao diện").length).toBeGreaterThanOrEqual(2)
    expect(container.querySelectorAll('[data-marketing-claim-id="capacity"]')).toHaveLength(0)
    expect(container.innerHTML).not.toMatch(/bg-gradient|backdrop-blur|✨|🚀|💡|—/u)
  })

  it("keeps the workflow and capability details semantic", () => {
    const { container } = render(<WelcomePage />)

    for (const id of ["workspace", "process", "evidence", "capabilities", "start"]) {
      expect(container.querySelector(`#${id}`)).toBeInTheDocument()
    }

    expect(screen.getByRole("table", { name: "Định dạng và học liệu hiện có" })).toBeInTheDocument()
    expect(
      screen.getAllByRole("region", { name: "Định dạng đi vào và học liệu đi ra" })
    ).toHaveLength(1)
    expect(screen.getByRole("group", { name: "Cuộn ngang bảng định dạng" })).toHaveAttribute(
      "tabindex",
      "0"
    )
    expect(screen.getByRole("link", { name: "Xem cách một tài liệu được xử lý" })).toHaveAttribute(
      "href",
      "#process"
    )
  })

  it("renders the approved public workflow composition", () => {
    const { container } = render(<WelcomePage />)

    const hero = container.querySelector("#workspace")
    expect(hero).toHaveTextContent(LANDING_COPY.body)

    for (const statement of [
      "PDF, DOCX hoặc TXT được giữ theo từng khóa học.",
      "Trang, đoạn và tệp nguồn được chuẩn bị để truy xuất.",
      "Tạo riêng Study Guide, slide, quiz hoặc video khi bạn cần.",
      "Đọc trên web hoặc tải định dạng có sẵn của từng học liệu.",
    ]) {
      expect(screen.getByText(statement)).toBeInTheDocument()
    }
  })

  it("maps every leaf claim marker exactly to shipped evidence", () => {
    const { container } = render(<WelcomePage />)
    const normalize = (value: string | null) => value?.replace(/\s+/gu, " ").trim() ?? ""
    const registry = new Map(MARKETING_CLAIMS.map((claim) => [claim.id, claim]))
    const repoRoot = path.resolve(process.cwd(), "../..")
    const markedElements = container.querySelectorAll<HTMLElement>("[data-marketing-claim-id]")

    expect(markedElements.length).toBeGreaterThan(0)
    for (const element of markedElements) {
      const claimId = element.dataset.marketingClaimId
      const claim = claimId ? registry.get(claimId) : undefined

      expect(claim, `Missing registry entry for ${claimId ?? "an empty claim id"}`).toBeDefined()
      expect(claim?.status, `Public claim ${claimId} must not be a target`).not.toBe("target")
      expect(normalize(element.textContent), `Rendered text differs for ${claimId}`).toBe(
        normalize(claim?.text ?? null)
      )
      expect(element.children, `Claim ${claimId} must be attached to a leaf text element`).toHaveLength(0)
      expect(
        existsSync(path.resolve(repoRoot, claim?.evidence ?? "")),
        `Evidence path does not exist for ${claimId}`
      ).toBe(true)
    }

    for (const claim of MARKETING_CLAIMS.filter((entry) => entry.status === "target")) {
      expect(container.querySelectorAll(`[data-marketing-claim-id="${claim.id}"]`)).toHaveLength(0)
    }
  })

  it("uses an AA-safe brand token for small accent labels", () => {
    const { container } = render(<WelcomePage />)

    for (const label of ["Ghi chú nguồn", "Từ tệp đến buổi học", "Sản phẩm đang chạy"]) {
      expect(screen.getByText(label)).toHaveClass("text-ring")
    }

    const evidenceLabels = container.querySelectorAll(
      "#evidence figcaption > span:first-child"
    )
    expect(evidenceLabels).toHaveLength(2)
    for (const label of evidenceLabels) {
      expect(label).toHaveClass("text-ring")
    }
  })

  it("renders fixed-size Vietnamese-labelled product screenshots", () => {
    render(<WelcomePage />)

    const images = screen.getAllByRole("img")
    expect(images).toHaveLength(3)
    for (const image of images) {
      expect(image).toHaveAttribute("width")
      expect(image).toHaveAttribute("height")
      expect(image.getAttribute("alt")).toMatch(/[À-ỹ]/u)
    }

    expect(
      screen.getByRole("img", {
        name: "Không gian khóa học minh họa với Study Guide, slide, quiz và video",
      })
    ).toHaveAttribute("width", "1200")
  })
})
