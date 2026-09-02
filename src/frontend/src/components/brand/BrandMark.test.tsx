import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BrandMark } from "./BrandMark"

describe("BrandMark", () => {
  it("has a name when rendered without the wordmark", () => {
    render(<BrandMark labelled />)

    expect(screen.getByRole("img", { name: "HackaGen" })).toBeInTheDocument()
  })

  it("is decorative by default when rendered beside the wordmark", () => {
    render(<BrandMark />)

    expect(screen.queryByRole("img")).not.toBeInTheDocument()
  })
})
