import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8")

describe("brand tokens", () => {
  it("uses the approved light palette and no colored shadow", () => {
    expect(css).toContain("--background: #F7F3EA")
    expect(css).toContain("--primary: #244A3A")
    expect(css).toContain("--accent-strong: #C5563C")
    expect(css).not.toMatch(/box-shadow:[^;]*(purple|violet|blue|primary)/i)
  })
})
