import { describe, expect, it } from "vitest"

import {
  LANDING_COPY,
  MARKETING_CLAIMS,
  assertBrandLanguage,
  assertBrandRhythm,
  getRenderableClaims,
} from "./brand.vi"

describe("HackaGen brand copy", () => {
  it("never renders target claims", () => {
    expect(getRenderableClaims(MARKETING_CLAIMS).every((claim) => claim.status !== "target")).toBe(true)
  })

  it("records shipped evidence for each public landing workflow statement", () => {
    const claims = new Map(MARKETING_CLAIMS.map((claim) => [claim.id, claim]))

    expect(claims.get("course-source")).toMatchObject({
      text: LANDING_COPY.sourceNote,
      status: "shipped",
      evidence: "src/backend/tests/test_course_and_upload.py",
    })
    expect(claims.get("document-source")).toMatchObject({
      text: "HackaGen giữ nội dung trong tài liệu làm nguồn",
      status: "shipped",
      evidence: "src/backend/tests/test_vector_store_and_processor.py",
    })
    expect(claims.get("course-files")).toMatchObject({
      text: "PDF, DOCX hoặc TXT được giữ theo từng khóa học.",
      status: "shipped",
      evidence: "src/backend/tests/test_course_and_upload.py",
    })
    expect(claims.get("indexing")).toMatchObject({
      text: "Trang, đoạn và tệp nguồn được chuẩn bị để truy xuất.",
      status: "shipped",
      evidence: "src/backend/tests/test_vector_store_and_processor.py",
    })
    expect(claims.get("delivery")).toMatchObject({
      text: "Đọc trên web hoặc tải định dạng có sẵn của từng học liệu.",
      status: "shipped",
      evidence: "src/backend/tests/test_generation_service.py",
    })
    expect(claims.get("slide-formats")).toMatchObject({
      text: "Trình chiếu tại chỗ; lấy bản PPTX hoặc PDF.",
      status: "shipped",
      evidence: "src/frontend/src/components/dashboard/SlideTab.tsx",
    })
  })

  it("contains no generic AI patterns", () => {
    const copy = Object.values(LANDING_COPY).join(" ")
    expect(() => assertBrandLanguage(copy)).not.toThrow()
    expect(() => assertBrandRhythm(copy)).not.toThrow()
  })

  it("rejects repeated and mechanically uniform marketing rhythm", () => {
    expect(() => assertBrandRhythm("Nhanh. Thông minh. Mạnh mẽ.")).toThrow("three-beat")
    expect(() => assertBrandRhythm("Đọc tài liệu rõ hơn. Đọc tài liệu rõ hơn.")).toThrow("repeated sentence")
    expect(() =>
      assertBrandRhythm(
        "Một câu có bốn từ. Câu này cũng bốn từ. Câu kia vẫn bốn từ. Nhịp này luôn bốn từ.",
      ),
    ).toThrow("uniform sentence length")
  })
})
