export type ClaimStatus = "shipped" | "measured" | "target"

export type MarketingClaim = {
  id: string
  text: string
  status: ClaimStatus
  evidence: string
  lastVerified: `${number}-${number}-${number}`
}

export type LandingCopy = {
  eyebrow: string
  headline: string
  body: string
  primaryCta: string
  secondaryCta: string
  sourceNote: string
}

export const LANDING_COPY: LandingCopy = {
  eyebrow: "XƯỞNG HỌC LIỆU TỪ TÀI LIỆU CỦA BẠN",
  headline: "Từ tài liệu đang đọc dở đến một buổi học có cấu trúc.",
  body: "Tải PDF, DOCX hoặc TXT. HackaGen giữ nội dung trong tài liệu làm nguồn, rồi dựng Study Guide, slide, quiz và video để bạn học tiếp.",
  primaryCta: "Tạo bộ học liệu từ tài liệu",
  secondaryCta: "Xem cách một tài liệu được xử lý",
  sourceNote: "Mỗi khóa học được tạo từ tệp bạn tải lên.",
}

export const MARKETING_CLAIMS: readonly MarketingClaim[] = [
  {
    id: "formats",
    text: "Tải PDF, DOCX hoặc TXT.",
    status: "shipped",
    evidence: "src/frontend/src/components/course/UploadZone.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "outputs",
    text: "Study Guide, slide, quiz và video",
    status: "shipped",
    evidence: "src/frontend/src/app/course/[id]/page.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "course-source",
    text: LANDING_COPY.sourceNote,
    status: "shipped",
    evidence: "src/backend/tests/test_course_and_upload.py",
    lastVerified: "2026-09-02",
  },
  {
    id: "document-source",
    text: "HackaGen giữ nội dung trong tài liệu làm nguồn",
    status: "shipped",
    evidence: "src/backend/tests/test_vector_store_and_processor.py",
    lastVerified: "2026-09-02",
  },
  {
    id: "course-files",
    text: "PDF, DOCX hoặc TXT được giữ theo từng khóa học.",
    status: "shipped",
    evidence: "src/backend/tests/test_course_and_upload.py",
    lastVerified: "2026-09-02",
  },
  {
    id: "indexing",
    text: "Trang, đoạn và tệp nguồn được chuẩn bị để truy xuất.",
    status: "shipped",
    evidence: "src/backend/tests/test_vector_store_and_processor.py",
    lastVerified: "2026-09-02",
  },
  {
    id: "process-details",
    text: "Mỗi bước giữ lại một chi tiết có thể kiểm tra: tệp nào đã vào, học liệu nào được tạo và định dạng nào có thể dùng tiếp.",
    status: "shipped",
    evidence: "src/frontend/src/components/landing/ProcessLedger.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "output-selection",
    text: "Tạo riêng Study Guide, slide, quiz hoặc video khi bạn cần.",
    status: "shipped",
    evidence: "src/frontend/src/app/course/[id]/page.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "delivery",
    text: "Đọc trên web hoặc tải định dạng có sẵn của từng học liệu.",
    status: "shipped",
    evidence: "src/backend/tests/test_generation_service.py",
    lastVerified: "2026-09-02",
  },
  {
    id: "fixture-evidence",
    text: "Những hình dưới đây được chụp từ dữ liệu minh họa cố định của chính ứng dụng.",
    status: "shipped",
    evidence: "src/frontend/e2e/capture-product-screenshots.spec.ts",
    lastVerified: "2026-09-02",
  },
  {
    id: "book-evidence",
    text: "Study Guide chia phần đọc theo mục lục, có điều hướng trước và sau cùng nút tải PDF.",
    status: "shipped",
    evidence: "src/frontend/src/components/dashboard/BookTab.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "video-evidence",
    text: "Không gian video cho chọn định dạng, giọng đọc và theo dõi phần trăm của lượt dựng đang chạy.",
    status: "shipped",
    evidence: "src/frontend/src/components/dashboard/VidOptionsPanel.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "capability-scope",
    text: "Bảng này đặt đầu vào, cách dùng và định dạng tải xuống cạnh nhau để dễ đối chiếu.",
    status: "shipped",
    evidence: "src/frontend/src/components/landing/CapabilityTable.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "course-upload",
    text: "Tải tệp lên theo từng khóa học.",
    status: "shipped",
    evidence: "src/backend/tests/test_course_and_upload.py",
    lastVerified: "2026-09-02",
  },
  {
    id: "book-delivery",
    text: "Đọc từng phần trong trình duyệt; tải bản PDF khi cần.",
    status: "shipped",
    evidence: "src/frontend/src/components/dashboard/BookTab.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "slide-formats",
    text: "Trình chiếu tại chỗ; lấy bản PPTX hoặc PDF.",
    status: "shipped",
    evidence: "src/frontend/src/components/dashboard/SlideTab.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "quiz-delivery",
    text: "Làm câu hỏi trong khóa học; đáp án có bản PDF.",
    status: "shipped",
    evidence: "src/frontend/src/components/dashboard/QuizTab.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "video-delivery",
    text: "Phát trong khóa học; tải MP4 sau khi dựng xong.",
    status: "shipped",
    evidence: "src/frontend/src/components/dashboard/VidTab.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "start-upload",
    text: "Tải tài liệu lên để mở không gian học mới.",
    status: "shipped",
    evidence: "src/frontend/src/components/course/UploadZone.tsx",
    lastVerified: "2026-09-02",
  },
  {
    id: "capacity",
    text: "Phục vụ 100 người dùng hoạt động",
    status: "target",
    evidence: "docs/superpowers/specs/2026-09-01-runtime-capacity-and-durable-jobs-design.md",
    lastVerified: "2026-09-01",
  },
  {
    id: "source-only",
    text: "Không bổ sung kiến thức từ web",
    status: "target",
    evidence: "docs/superpowers/specs/2026-09-01-pdf-only-book-rag-design.md",
    lastVerified: "2026-09-01",
  },
] as const

export function getRenderableClaims(claims: readonly MarketingClaim[]): MarketingClaim[] {
  return claims.filter((claim) => claim.status === "shipped" || claim.status === "measured")
}

const BANNED = [
  /seamless|unlock|transform|empower|robust|revolutionize|supercharge/iu,
  /đột phá|nâng tầm|thông minh hơn|bộ học liệu hoàn chỉnh|slide chuyên nghiệp/iu,
  /không chỉ (?:là )?.+mà (?:còn )?là/iu,
  /it's not just .+it's/iu,
  /[✨🚀💡🪄🤖]/u,
  /—/u,
]

export function assertBrandLanguage(text: string): void {
  const match = BANNED.find((pattern) => pattern.test(text))
  if (match) throw new Error(`Brand language violation: ${match.source}`)
}

const THREE_BEAT = /(?:^|\s)(?:[\p{L}\p{M}]+(?:\s+[\p{L}\p{M}]+){0,2}\.\s*){3}/u

function normalizedSentences(text: string): string[] {
  return text
    .split(/[.!?]+/u)
    .map((sentence) => sentence.trim().toLocaleLowerCase("vi"))
    .filter(Boolean)
}

export function assertBrandRhythm(text: string): void {
  if (THREE_BEAT.test(text)) throw new Error("Brand rhythm violation: three-beat slogan")

  const sentences = normalizedSentences(text)
  if (new Set(sentences).size !== sentences.length) {
    throw new Error("Brand rhythm violation: repeated sentence")
  }

  const counts = sentences.map((sentence) => sentence.split(/\s+/u).length)
  for (let index = 0; index <= counts.length - 4; index += 1) {
    const window = counts.slice(index, index + 4)
    if (Math.max(...window) - Math.min(...window) <= 2) {
      throw new Error("Brand rhythm violation: uniform sentence length")
    }
  }

  const words = text.toLocaleLowerCase("vi").match(/[\p{L}\p{M}\d]+/gu) ?? []
  const phraseCounts = new Map<string, number>()
  const allowedProductPhrases = new Set([
    "study guide slide quiz",
    "guide slide quiz video",
    "pdf docx txt study",
  ])
  for (let index = 0; index <= words.length - 4; index += 1) {
    const phrase = words.slice(index, index + 4).join(" ")
    if (allowedProductPhrases.has(phrase)) continue
    phraseCounts.set(phrase, (phraseCounts.get(phrase) ?? 0) + 1)
  }
  if ([...phraseCounts.values()].some((count) => count > 2)) {
    throw new Error("Brand rhythm violation: repeated four-word phrase")
  }
}
