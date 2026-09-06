# Distinctive Product Appearance and Brand Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give HackaGen a distinctive Vietnamese learning-workshop identity and remove the combined visual/copy patterns that make the product feel like a generic AI-generated website.

**Architecture:** Centralize verified marketing copy and claims, replace generic visual tokens with an editorial study-desk system, apply it to shared shell and key product surfaces, then rebuild the landing page around real product screenshots and concrete workflow evidence. Automated language audits, Playwright visual baselines, accessibility scans, and a two-reviewer combined-signal gate prevent regression.

**Tech Stack:** Next.js 16.2.9, React 19.2.4, Tailwind CSS 4, next/font, Lucide React, Vitest 4, Testing Library, Playwright, axe-core

**Spec:** [Distinctive Product Appearance and Brand Voice Design](../specs/2026-09-01-distinctive-product-appearance-and-brand-voice-design.md)

## Global Constraints

- Brand direction is `The Learning Workshop`: warm paper, ink, marginal annotation, and real product evidence.
- First-visit theme is light; dark theme remains a manual choice.
- Body font is `Be Vietnam Pro`; display font is `Newsreader`; both load the Vietnamese subset through `next/font/google`.
- No marketing gradients, colored glow, glassmorphism, floating orbs, emoji icons, synthetic testimonials, or fabricated metrics.
- Marketing copy contains no em dash and none of the banned generic/formula phrases from the spec.
- Marketing copy contains no three-beat slogan, repeated sentence, overused four-word phrase, or run of four mechanically uniform sentence lengths.
- AI is a workflow mechanism, not the main headline subject.
- Only `shipped` and `measured` claims can render. A `target` claim never renders publicly.
- Product screenshots come from deterministic HackaGen UI fixtures, carry a `Minh họa giao diện` caption, and contain no real user data.
- Keep presenter-stage dark tokens and generated artifact rendering unchanged.
- Meet WCAG 2.2 AA and respect `prefers-reduced-motion`.
- Read `src/frontend/AGENTS.md` plus these installed Next.js 16 references before implementation:
  - `src/frontend/node_modules/next/dist/docs/01-app/01-getting-started/11-css.md`
  - `src/frontend/node_modules/next/dist/docs/01-app/01-getting-started/12-images.md`
  - `src/frontend/node_modules/next/dist/docs/01-app/01-getting-started/13-fonts.md`
  - `src/frontend/node_modules/next/dist/docs/01-app/02-guides/testing/playwright.md`
  - `src/frontend/node_modules/next/dist/docs/03-architecture/accessibility.md`
- Do not commit unless the Lead explicitly authorizes it. Commit commands below are execution checkpoints only.

## File Structure

### Create

- `src/frontend/src/content/brand.vi.ts` — approved copy, typed claim registry, banned-pattern policy.
- `src/frontend/src/content/brand.vi.test.ts` — claim/copy contract tests.
- `src/frontend/scripts/audit-brand-language.mjs` — Task 8 source audit for banned language, emoji, and em dash after copy migration.
- `src/frontend/src/components/brand/BrandMark.tsx` — custom accessible document/source SVG.
- `src/frontend/src/components/brand/BrandMark.test.tsx`
- `src/frontend/src/components/landing/LandingIntro.tsx` — asymmetrical opening and first product image.
- `src/frontend/src/components/landing/ProcessLedger.tsx` — unequal document-to-artifact workflow rows.
- `src/frontend/src/components/landing/ProductEvidence.tsx` — real screenshots and captions.
- `src/frontend/src/components/landing/CapabilityTable.tsx` — concrete format/output availability.
- `src/frontend/src/components/landing/LandingPage.test.tsx`
- `src/frontend/src/app/brand-tokens.test.ts`
- `src/frontend/src/app/course/[id]/page.test.tsx`
- `src/frontend/e2e/fixtures/demo-data.ts` — deterministic neutral course/study-pack responses.
- `src/frontend/e2e/fixtures/visual-app.ts` — auth priming and API route interception.
- `src/frontend/e2e/capture-product-screenshots.spec.ts` — reproducible marketing screenshot capture.
- `src/frontend/e2e/visual-brand.spec.ts` — responsive screenshot and accessibility gates.
- `src/frontend/playwright.config.ts`
- `src/frontend/public/product/course-workspace.png`
- `src/frontend/public/product/book-reading.png`
- `src/frontend/public/product/video-progress.png`
- `docs/brand/voice-and-claims.md` — human editing rules and verified-claim process.
- `docs/brand/visual-review.md` — combined-signal review record template.

### Modify

- `src/frontend/src/app/layout.tsx` — two-font setup, revised metadata, and light first-visit theme.
- `src/frontend/src/app/globals.css` — paper/ink tokens, radii, shadows, reduced motion.
- `src/frontend/src/components/ui/button.tsx`, `card.tsx`, `badge.tsx`, `empty-state.tsx` — restrained shared styling.
- `src/frontend/src/components/layout/Header.tsx`, `Footer.tsx` — brand mark and editorial shell.
- `src/frontend/src/app/(auth)/layout.tsx` — source-excerpt authentication composition.
- `src/frontend/src/app/page.tsx` — evidence-led landing composition.
- `src/frontend/src/app/courses/page.tsx`, `src/frontend/src/components/course/CourseCard.tsx` — document shelf/list treatment.
- `src/frontend/src/app/course/[id]/page.tsx` — workspace dividers and reduced card nesting.
- `src/frontend/src/app/courses/create/page.tsx` — approved direct upload voice.
- `src/frontend/src/app/(auth)/login/page.tsx`, `register/page.tsx`, `forgot-password/page.tsx`, `reset-password/page.tsx`, `verify-email/page.tsx` — approved direct authentication voice.
- `src/frontend/src/components/dashboard/BookTab.tsx`, `SlideTab.tsx`, `QuizTab.tsx`, `VidTab.tsx` — direct empty/error/success language.
- `src/frontend/src/components/dashboard/BookOptionsPanel.tsx`, `SlideOptionsPanel.tsx`, `QuizOptionsPanel.tsx`, `VidOptionsPanel.tsx` — direct option labels and descriptions.
- `src/frontend/package.json`, `src/frontend/package-lock.json` — brand audit and Playwright dependencies/scripts.
- `README.md` — visual test and screenshot regeneration commands.
- `docs/superpowers/plans/2026-09-01-runtime-capacity-and-durable-jobs.md`
- `docs/superpowers/plans/2026-09-01-reliable-long-video-generation.md`
- `docs/superpowers/plans/2026-09-01-pdf-only-grounded-book-rag.md`

---

## Task 1: Centralize brand copy and evidence-qualified claims

**Files:**

- Create: `src/frontend/src/content/brand.vi.ts`
- Create: `src/frontend/src/content/brand.vi.test.ts`
- Modify: `src/frontend/package.json`

**Interfaces:**

- Consumes: no application interface; policy values come directly from the design spec.
- Produces: `ClaimStatus`, `MarketingClaim`, `LandingCopy`, `LANDING_COPY`, `MARKETING_CLAIMS`, `getRenderableClaims()`, `assertBrandLanguage()`, and `assertBrandRhythm()`.

- [ ] **Step 1: Write failing claim-registry tests**

```ts
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

  it("contains no generic AI patterns", () => {
    const copy = Object.values(LANDING_COPY).join(" ")
    expect(() => assertBrandLanguage(copy)).not.toThrow()
    expect(() => assertBrandRhythm(copy)).not.toThrow()
  })

  it("rejects repeated and mechanically uniform marketing rhythm", () => {
    expect(() => assertBrandRhythm("Nhanh. Thông minh. Mạnh mẽ.")).toThrow("three-beat")
    expect(() => assertBrandRhythm("Đọc tài liệu rõ hơn. Đọc tài liệu rõ hơn.")).toThrow("repeated sentence")
    expect(() => assertBrandRhythm("Một câu có bốn từ. Câu này cũng bốn từ. Câu kia vẫn bốn từ. Nhịp này luôn bốn từ.")).toThrow("uniform sentence length")
  })
})
```

- [ ] **Step 2: Run the test and verify the missing-module failure**

Run: `cd src/frontend; npm test -- --run src/content/brand.vi.test.ts`  
Expected: FAIL because `src/content/brand.vi.ts` does not exist.

- [ ] **Step 3: Create exact public copy and claim types**

```ts
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
```

- [ ] **Step 4: Add shipped claims and keep performance/grounding as non-renderable targets until their gates pass**

```ts
export const MARKETING_CLAIMS: readonly MarketingClaim[] = [
  { id: "formats", text: "Nhận PDF, DOCX và TXT", status: "shipped", evidence: "src/frontend/src/components/course/UploadZone.tsx", lastVerified: "2026-09-01" },
  { id: "outputs", text: "Tạo Study Guide, slide, quiz và video", status: "shipped", evidence: "src/frontend/src/app/course/[id]/page.tsx", lastVerified: "2026-09-01" },
  { id: "capacity", text: "Phục vụ 100 người dùng hoạt động", status: "target", evidence: "docs/superpowers/specs/2026-09-01-runtime-capacity-and-durable-jobs-design.md", lastVerified: "2026-09-01" },
  { id: "source-only", text: "Không bổ sung kiến thức từ web", status: "target", evidence: "docs/superpowers/specs/2026-09-01-pdf-only-book-rag-design.md", lastVerified: "2026-09-01" },
] as const

export function getRenderableClaims(claims: readonly MarketingClaim[]): MarketingClaim[] {
  return claims.filter((claim) => claim.status === "shipped" || claim.status === "measured")
}
```

- [ ] **Step 5: Implement the reusable language assertion**

```ts
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
```

- [ ] **Step 6: Add the semantic brand audit command**

Keep the first audit semantic and green while legacy application copy is being migrated. Task 8 adds the source scanner and expands this command.

Add scripts:

```json
{
  "audit:brand": "vitest run src/content/brand.vi.test.ts"
}
```

- [ ] **Step 7: Run tests and the audit**

Run: `cd src/frontend; npm test -- --run src/content/brand.vi.test.ts; npm run audit:brand`  
Expected: the unit test and semantic brand audit pass.

- [ ] **Step 8: Commit checkpoint if authorized**

```powershell
git add src/frontend/src/content src/frontend/package.json
git commit -m "feat: define HackaGen brand voice and claims"
```

## Task 2: Install the paper-and-ink token and typography foundation

**Files:**

- Modify: `src/frontend/src/app/layout.tsx`
- Modify: `src/frontend/src/app/globals.css`
- Modify: `src/frontend/src/components/ui/button.tsx`
- Modify: `src/frontend/src/components/ui/card.tsx`
- Modify: `src/frontend/src/components/ui/badge.tsx`
- Create: `src/frontend/src/app/brand-tokens.test.ts`

**Interfaces:**

- Consumes: exact palette/type/radius values from the design spec.
- Produces: CSS variables `--font-body`, `--font-display`, `--accent-strong`, `--radius`, shared Tailwind token mappings, and `font-display` utility use through `var(--font-display)`.

- [ ] **Step 1: Write a failing token-source test**

```ts
import { readFileSync } from "node:fs"
import { describe, expect, it } from "vitest"

const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8")

describe("brand tokens", () => {
  it("uses the approved light palette and no colored shadow", () => {
    expect(css).toContain("--background: #F7F3EA")
    expect(css).toContain("--primary: #244A3A")
    expect(css).toContain("--accent-strong: #C5563C")
    expect(css).not.toMatch(/box-shadow:[^;]*(purple|violet|blue|primary)/i)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails on the old blue/white tokens**

Run: `cd src/frontend; npm test -- --run src/app/brand-tokens.test.ts`  
Expected: FAIL because the approved token values are absent.

- [ ] **Step 3: Replace the single Inter import with the verified Vietnamese font pair**

```tsx
import { Be_Vietnam_Pro, Newsreader } from "next/font/google"

const bodyFont = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
})

const displayFont = Newsreader({
  subsets: ["latin", "vietnamese"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
})
```

Apply both variables to `<html>`, set the title template to `%s | HackaGen`, and set metadata description to `Tạo Study Guide, slide, quiz và video từ tài liệu của bạn.`

- [ ] **Step 4: Apply the exact spec tokens in `globals.css`**

Map `--font-sans: var(--font-body)`, add `--font-display`, set light/dark token values from the spec verbatim, set `--radius: 0.375rem`, cap `--radius-xl` at `0.625rem`, keep neutral shadows, and leave `--stage-*` unchanged.

- [ ] **Step 5: Make light mode the first-visit default**

At the `ThemeProvider` call site use:

```tsx
<ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
```

The toggle must still switch and persist explicit light/dark choices.

- [ ] **Step 6: Restrain shared primitives**

Use 6 px button/card radii, remove general hover lift/scale, reserve fully rounded badges for status/tag semantics, and keep visible focus rings. Do not change component props or variants.

- [ ] **Step 7: Add reduced-motion behavior**

```css
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 8: Run token tests, existing component tests, lint, and build**

Run: `cd src/frontend; npm test -- --run src/app/brand-tokens.test.ts; npm test -- --run; npm run lint; npm run build`  
Expected: all commands pass with no font/subset build error.

- [ ] **Step 9: Commit checkpoint if authorized**

```powershell
git add src/frontend/src/app src/frontend/src/components/ui
git commit -m "style: establish HackaGen paper and ink system"
```

## Task 3: Replace the generic book icon with a distinctive brand shell

**Files:**

- Create: `src/frontend/src/components/brand/BrandMark.tsx`
- Create: `src/frontend/src/components/brand/BrandMark.test.tsx`
- Modify: `src/frontend/src/components/layout/Header.tsx`
- Modify: `src/frontend/src/components/layout/Footer.tsx`
- Modify: `src/frontend/src/app/(auth)/layout.tsx`

**Interfaces:**

- Consumes: `--primary`, `--accent-strong`, `--font-display` from Task 2.
- Produces: `BrandMark({ size, labelled, className }: BrandMarkProps)` used by Header, Footer, and auth layout.

- [ ] **Step 1: Write the failing brand-mark accessibility test**

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { BrandMark } from "./BrandMark"

describe("BrandMark", () => {
  it("has a name when rendered without the wordmark", () => {
    render(<BrandMark labelled />)
    expect(screen.getByRole("img", { name: "HackaGen" })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test and verify the missing-component failure**

Run: `cd src/frontend; npm test -- --run src/components/brand/BrandMark.test.tsx`  
Expected: FAIL because `BrandMark.tsx` is missing.

- [ ] **Step 3: Implement the exact custom SVG interface**

```tsx
import { cn } from "@/lib/utils"

export type BrandMarkProps = {
  size?: number
  labelled?: boolean
  className?: string
}

export function BrandMark({ size = 28, labelled = false, className }: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 40 40"
      width={size}
      height={size}
      role={labelled ? "img" : undefined}
      aria-label={labelled ? "HackaGen" : undefined}
      aria-hidden={labelled ? undefined : true}
      className={cn("shrink-0", className)}
    >
      <path d="M5 10v26h24" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path d="M10 4h18l7 7v24H10z" fill="var(--card)" stroke="currentColor" strokeWidth="2.5" />
      <path d="M28 4v8h7" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path d="M16 19h13M16 25h9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M16 31h12" stroke="var(--accent-strong)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
```

- [ ] **Step 4: Replace shell logo usage**

Use `<BrandMark />` beside a `font-display` HackaGen wordmark in Header/auth; use `<BrandMark labelled />` only where no visible wordmark exists. Remove `BookOpen` imports used only as a logo.

- [ ] **Step 5: Recompose authentication branding**

Replace the solid primary slab with a warm paper/secondary panel, a left-aligned wordmark, the sentence `Mang theo tài liệu. HackaGen giúp bạn sắp lại thành một buổi học có thể dùng tiếp.`, a thin rule motif, and `PDF · DOCX · TXT` metadata. Keep the form side unchanged except token/typography inheritance.

- [ ] **Step 6: Make Header and Footer evidence-oriented**

Remove translucent `backdrop-blur` from Header. Use an opaque paper background and 1 px rule. Footer shows the wordmark, `Học liệu bắt đầu từ tài liệu của bạn.`, and the existing copyright; no generic navigation sections are added.

- [ ] **Step 7: Run targeted and full frontend tests**

Run: `cd src/frontend; npm test -- --run src/components/brand/BrandMark.test.tsx; npm test -- --run; npm run lint; npm run build`  
Expected: all pass and `rg "BookOpen" src/components/layout src/app/\(auth\)/layout.tsx` returns no logo usage.

- [ ] **Step 8: Commit checkpoint if authorized**

```powershell
git add src/frontend/src/components/brand src/frontend/src/components/layout "src/frontend/src/app/(auth)/layout.tsx"
git commit -m "feat: add the HackaGen document mark"
```

## Task 4: Apply the editorial system to authenticated product surfaces

**Files:**

- Modify: `src/frontend/src/app/courses/page.tsx`
- Modify: `src/frontend/src/components/course/CourseCard.tsx`
- Modify: `src/frontend/src/components/ui/empty-state.tsx`
- Modify: `src/frontend/src/app/course/[id]/page.tsx`
- Modify: `src/frontend/src/app/courses/create/page.tsx`
- Modify: `src/frontend/src/components/course/CourseCard.test.tsx`
- Create: `src/frontend/src/app/course/[id]/page.test.tsx`

**Interfaces:**

- Consumes: shared tokens/primitives from Task 2, BrandMark shell from Task 3, existing API/types unchanged.
- Produces: stable `data-visual-state` values (`courses-empty`, `courses-populated`, `course-workspace`) consumed by the Playwright fixture in Task 5.

- [ ] **Step 1: Add failing structural tests**

```tsx
it("renders a course as a document object without promotional hover lift", () => {
  const { container } = render(<CourseCard course={readyCourse} />)
  expect(container.firstChild).toHaveAttribute("data-course-document")
  expect(container.innerHTML).not.toContain("-translate-y")
  expect(screen.getByText("2 tệp nguồn")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run focused tests and confirm the new semantics fail**

Run: `cd src/frontend; npm test -- --run src/components/course/CourseCard.test.tsx src/app/course/[id]/page.test.tsx`  
Expected: FAIL on missing `data-course-document`, updated metadata, and workspace marker.

- [ ] **Step 3: Rework the course list into a document shelf**

Keep a responsive grid because courses are discrete objects, but remove hover elevation, use a 3 px terracotta top rule for the selected/ready state, left-align all metadata, vary height naturally, label file counts as `1 tệp nguồn`/`N tệp nguồn`, and place status beside timestamps rather than as a floating promotional badge.

- [ ] **Step 4: Make empty/loading/error states direct**

Replace `Tải lên tài liệu để AI tạo bộ học liệu hoàn chỉnh cho bạn.` with `Tải tệp đầu tiên để mở một không gian học mới.` Keep Lucide icons, remove oversized rounded icon wells, and make the recovery action the strongest element.

- [ ] **Step 5: Reduce card nesting in the course workspace**

In `course/[id]/page.tsx`, keep the header on the paper canvas, render tabs as a ruled navigation strip, and change the tab body from `rounded-xl border bg-card p-6` to a semantic `<section>` with a top rule and responsive padding. Add `data-visual-state="course-workspace"` to the main workspace root. Add `data-visual-state="courses-empty"` or `data-visual-state="courses-populated"` to the course-list root after loading resolves.

- [ ] **Step 6: Update create-course copy**

Use title `Mở một không gian học từ tài liệu` and body `Tải PDF, DOCX hoặc TXT. Bạn có thể tạo từng loại học liệu sau khi tệp được đọc và lập chỉ mục.` Do not promise speed or complete output.

- [ ] **Step 7: Run product-surface regression**

Run: `cd src/frontend; npm test -- --run; npm run audit:brand; npm run lint; npm run build`  
Expected: tests, the scoped brand-source audit, lint, and build pass.

- [ ] **Step 8: Commit checkpoint if authorized**

```powershell
git add src/frontend/src/app/courses src/frontend/src/app/course src/frontend/src/components/course src/frontend/src/components/ui/empty-state.tsx
git commit -m "style: make the product feel like a learning workspace"
```

## Task 5: Create deterministic real-product screenshot fixtures

**Files:**

- Create: `src/frontend/playwright.config.ts`
- Create: `src/frontend/e2e/fixtures/demo-data.ts`
- Create: `src/frontend/e2e/fixtures/visual-app.ts`
- Create: `src/frontend/e2e/capture-product-screenshots.spec.ts`
- Create: `src/frontend/public/product/course-workspace.png`
- Create: `src/frontend/public/product/book-reading.png`
- Create: `src/frontend/public/product/video-progress.png`
- Modify: `src/frontend/package.json`
- Modify: `src/frontend/package-lock.json`

**Interfaces:**

- Consumes: `data-visual-state` hooks from Task 4 and current frontend API paths/types.
- Produces: `DEMO_COURSE_LIST`, `DEMO_STATUS`, `DEMO_STUDY_PACK`, `DEMO_BOOK_STATUS`, `DEMO_VID_STATUS`, `primeVisualAuth(page)`, `installVisualDemoRoutes(page)`, and three fixed screenshot assets consumed by Task 6.

- [ ] **Step 1: Install and pin browser-test dependencies**

Run:

```powershell
cd src/frontend
npm install --save-dev @playwright/test @axe-core/playwright
npx playwright install chromium
```

Expected: `package.json` and lockfile update; Chromium installs without changing application dependencies.

- [ ] **Step 2: Add Playwright configuration**

```ts
import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: { command: "npm run dev", url: "http://127.0.0.1:3000", reuseExistingServer: true },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
```

- [ ] **Step 3: Define neutral deterministic demo data**

Use course id `demo-course`, title `Nhập môn sinh thái đô thị`, filenames `chuong-1.pdf` and `ghi-chu.txt`, no personal name/email, ready status, and four artifact versions. `DEMO_BOOK_STATUS` is a ready Book with two chapters. `DEMO_VID_STATUS` is processing at 64% with `data: null`. Export the exact constants named in the Interfaces block.

```ts
import type {
  BookArtifactStatus,
  CoursesResponse,
  CourseStatusResponse,
  StudyPackResponse,
  VidArtifactStatus,
} from "@/lib/types"

export const DEMO_COURSE_LIST = {
  courses: [{ course_id: "demo-course", name: "Nhập môn sinh thái đô thị", status: "ready", filenames: ["chuong-1.pdf", "ghi-chu.txt"], file_count: 2, created_at: "2026-08-30T08:00:00Z" }],
  total: 1,
} satisfies CoursesResponse

export const DEMO_STATUS = {
  course_id: "demo-course", name: "Nhập môn sinh thái đô thị", status: "ready", progress: 100,
  filenames: ["chuong-1.pdf", "ghi-chu.txt"], file_count: 2, quality_score: 88,
  has_book: true, has_slide: true, has_quiz: true, has_vid: true,
} satisfies CourseStatusResponse

export const DEMO_BOOK_STATUS = {
  status: "ready", progress: 100, version_id: "book-v1", active_version: "book-v1",
  versions: [{ version_id: "book-v1", label: "Bản đọc đầu tiên", options: {}, status: "ready", progress: 100 }],
  data: {
    title: "Nhập môn sinh thái đô thị", summary: "Cách hệ sinh thái vận hành trong không gian đô thị.",
    chapters: [
      { chapter_title: "Dòng năng lượng", sections: [{ title: "Nguồn và dòng", content: "Năng lượng đi qua các bậc dinh dưỡng trong hệ sinh thái." }] },
      { chapter_title: "Đa dạng sinh học", sections: [{ title: "Sinh cảnh", content: "Mỗi sinh cảnh đô thị tạo điều kiện sống khác nhau." }] },
    ],
  },
} satisfies BookArtifactStatus

export const DEMO_VID_STATUS = {
  status: "processing", progress: 64, version_id: "vid-v1", active_version: "vid-v1", data: null,
  versions: [{ version_id: "vid-v1", label: "Video tổng quan", options: {}, status: "processing", progress: 64 }],
} satisfies VidArtifactStatus

export const DEMO_STUDY_PACK = {
  course_id: "demo-course",
  stats: { course_id: "demo-course", status: "ready", has_book: true, has_book_pdf: true, has_slide: true, has_slide_pptx: true, has_quiz: true, has_quiz_answer_key: true, has_vid: true, quality_score: 88, num_chunks: 42 },
  study_pack: { title: "Nhập môn sinh thái đô thị", book: DEMO_BOOK_STATUS.data ?? undefined, readiness: { book: true, slide: true, quiz: true, vid: true }, quality_scores: { book: 88 }, grounding: { num_chunks: 42, quality_score: 88, warnings: [] } },
} satisfies StudyPackResponse
```

- [ ] **Step 4: Implement auth and API interception helpers**

```ts
import type { Page } from "@playwright/test"
import {
  DEMO_BOOK_STATUS,
  DEMO_COURSE_LIST,
  DEMO_STATUS,
  DEMO_STUDY_PACK,
  DEMO_VID_STATUS,
} from "./demo-data"

export async function primeVisualAuth(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("agy_auth_token", "visual-fixture-token")
    localStorage.setItem("agy_auth_user", JSON.stringify({ email: "demo@example.invalid", full_name: "Người học mẫu" }))
  })
}

export async function installVisualDemoRoutes(page: Page): Promise<void> {
  await page.route("**/api/courses/all", (route) => route.fulfill({ json: DEMO_COURSE_LIST }))
  await page.route("**/api/course/demo-course/status", (route) => route.fulfill({ json: DEMO_STATUS }))
  await page.route("**/api/course/demo-course/study-pack", (route) => route.fulfill({ json: DEMO_STUDY_PACK }))
  await page.route("**/api/course/demo-course/book*", (route) => route.fulfill({ json: DEMO_BOOK_STATUS }))
  await page.route("**/api/course/demo-course/vid*", (route) => route.fulfill({ json: DEMO_VID_STATUS }))
}
```

The five fixtures use `satisfies CoursesResponse`, `CourseStatusResponse`, `StudyPackResponse`, `BookArtifactStatus`, and `VidArtifactStatus` from `src/frontend/src/lib/types.ts`, so later API-contract changes fail compilation instead of producing stale screenshots.

- [ ] **Step 5: Write the capture test**

```ts
import { expect, test } from "@playwright/test"
import { installVisualDemoRoutes, primeVisualAuth } from "./fixtures/visual-app"

test("capture product evidence", async ({ page }) => {
  await primeVisualAuth(page)
  await installVisualDemoRoutes(page)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/course/demo-course")
  await expect(page.locator('[data-visual-state="course-workspace"]')).toBeVisible()
  await page.locator('[data-visual-state="course-workspace"]').screenshot({
    path: "public/product/course-workspace.png",
    animations: "disabled",
  })
})
```

Capture the ready Book panel as `book-reading.png` and the 64%-processing video panel as `video-progress.png` after selecting their tabs; crop to stable panel/workspace locators, not browser chrome. Regenerate both when the Book grounding or durable video-progress plans later change those surfaces.

- [ ] **Step 6: Add reproducible scripts and generate assets**

```json
{
  "test:e2e": "playwright test",
  "capture:product": "playwright test e2e/capture-product-screenshots.spec.ts --project=chromium"
}
```

Run: `cd src/frontend; npm run capture:product`  
Expected: three PNG files exist, are larger than 20 KB, contain only fixture data, and render the real HackaGen UI.

- [ ] **Step 7: Inspect screenshots manually for private data and stale generic styling**

Open all three PNGs. Reject if any real email/name/file text appears, if a loading skeleton remains, if the viewport clips a primary control, or if gradients/glows/equal marketing cards appear.

- [ ] **Step 8: Commit checkpoint if authorized**

```powershell
git add src/frontend/playwright.config.ts src/frontend/e2e src/frontend/public/product src/frontend/package.json src/frontend/package-lock.json
git commit -m "test: capture deterministic HackaGen product evidence"
```

## Task 6: Rebuild the landing page around product evidence

**Files:**

- Create: `src/frontend/src/components/landing/LandingIntro.tsx`
- Create: `src/frontend/src/components/landing/ProcessLedger.tsx`
- Create: `src/frontend/src/components/landing/ProductEvidence.tsx`
- Create: `src/frontend/src/components/landing/CapabilityTable.tsx`
- Create: `src/frontend/src/components/landing/LandingPage.test.tsx`
- Modify: `src/frontend/src/app/page.tsx`

**Interfaces:**

- Consumes: `LANDING_COPY`, `getRenderableClaims()`, `BrandMark`, and three screenshot paths from Tasks 1, 3, and 5.
- Produces: server-rendered landing sections with ids `workspace`, `process`, `evidence`, `capabilities`, and `start`, plus `data-marketing-claim-id` on every public claim.

- [ ] **Step 1: Write failing landing-composition tests**

```tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import WelcomePage from "@/app/page"

describe("landing page", () => {
  it("leads with the document workflow and real product evidence", () => {
    const { container } = render(<WelcomePage />)
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Từ tài liệu đang đọc dở")
    expect(screen.getAllByText("Minh họa giao diện").length).toBeGreaterThanOrEqual(2)
    expect(container.querySelectorAll('[data-marketing-claim-id="capacity"]')).toHaveLength(0)
    expect(container.innerHTML).not.toMatch(/bg-gradient|backdrop-blur|✨|🚀|💡|—/u)
  })
})
```

- [ ] **Step 2: Run the test and verify it fails against the old centered hero**

Run: `cd src/frontend; npm test -- --run src/components/landing/LandingPage.test.tsx`  
Expected: FAIL on headline, evidence captions, and gradient utility.

- [ ] **Step 3: Implement `LandingIntro` as an asymmetrical 12-column opening**

Use left-aligned copy in columns 1-6, `course-workspace.png` in columns 7-12, one terracotta source annotation crossing the image edge, and CTA labels from `LANDING_COPY`. The secondary CTA links to `#process`; the screenshot uses `next/image`, explicit `width={1200}`, `height={760}`, `priority`, and Vietnamese alt text.

- [ ] **Step 4: Implement the unequal process ledger**

Render four rows with sequence numbers `01`-`04`, varied column spans, and concrete text:

1. `Tệp nguồn` / `PDF, DOCX hoặc TXT được giữ theo từng khóa học.`
2. `Đọc và lập chỉ mục` / `Trang, đoạn và tệp nguồn được chuẩn bị để truy xuất.`
3. `Chọn học liệu` / `Tạo riêng Study Guide, slide, quiz hoặc video khi bạn cần.`
4. `Học và tải xuống` / `Đọc trên web hoặc tải định dạng có sẵn của từng học liệu.`

Use rules and source labels, not cards.

- [ ] **Step 5: Implement two real evidence panels**

Render `book-reading.png` and `video-progress.png` at different aspect/column widths with `Minh họa giao diện` captions. Describe visible behaviors only. Do not state grounding percentages, speed, or scale unless their claim status is renderable.

- [ ] **Step 6: Implement the capability table**

Use semantic `<table>` rows for `Đầu vào`, `Study Guide`, `Slide`, `Quiz`, and `Video`, with current shipped formats/availability. On mobile, retain table semantics with horizontal scroll rather than converting to equal cards.

- [ ] **Step 7: Replace `app/page.tsx` and metadata**

Compose `LandingIntro`, `ProcessLedger`, `ProductEvidence`, and `CapabilityTable`; set page title to `HackaGen | Học liệu từ tài liệu của bạn`; add a restrained final `<section id="start">` with a sample document label and primary CTA. Remove the old `features` array and all gradient/equal-card markup. Do not add testimonials.

- [ ] **Step 8: Run landing tests, brand audit, lint, and build**

Run: `cd src/frontend; npm test -- --run src/components/landing/LandingPage.test.tsx; npm run audit:brand; npm run lint; npm run build`  
Expected: all pass; no banned marketing pattern is reported.

- [ ] **Step 9: Commit checkpoint if authorized**

```powershell
git add src/frontend/src/app/page.tsx src/frontend/src/components/landing
git commit -m "feat: rebuild landing around real product evidence"
```

## Task 7: Add responsive visual and accessibility regression gates

**Files:**

- Create: `src/frontend/e2e/visual-brand.spec.ts`
- Modify: `src/frontend/playwright.config.ts`
- Modify: `src/frontend/package.json`
- Create: `src/frontend/e2e/visual-brand.spec.ts-snapshots/` — Playwright-generated baseline images for the named viewport/state cases

**Interfaces:**

- Consumes: `primeVisualAuth`, `installVisualDemoRoutes`, stable section/state locators, and completed landing/product styling.
- Produces: `npm run test:visual` and committed baseline screenshots for three viewports in light mode plus critical dark-mode product states.

- [ ] **Step 1: Write the failing visual/accessibility test**

```ts
import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import { installVisualDemoRoutes, primeVisualAuth } from "./fixtures/visual-app"

for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 1000 },
]) {
  test(`landing ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto("/")
    await expect(page).toHaveScreenshot(`landing-${viewport.name}.png`, { fullPage: true, animations: "disabled" })
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([])
  })
}
```

- [ ] **Step 2: Run the test without baselines and confirm expected failure**

Run: `cd src/frontend; npx playwright test e2e/visual-brand.spec.ts`  
Expected: FAIL because baseline screenshots do not exist.

- [ ] **Step 3: Add authenticated-state cases**

Test populated courses, course workspace Book, queued video progress, and ingestion error at desktop/mobile. Call both visual fixture helpers before navigation. Set theme through the same persisted key used by `next-themes`; include one dark workspace and one dark auth-form baseline, not a dark-first landing variant.

- [ ] **Step 4: Add semantic visual assertions before snapshots**

Assert the H1 is left-aligned on desktop, at least two evidence images are visible before the final CTA, every evidence image has nonempty alt text, no testimonial region exists, no `[class*="gradient"]`/`[class*="blur"]` marketing element exists, and primary focus order follows Header → H1 actions → process → evidence → final action.

- [ ] **Step 5: Generate and inspect baselines**

Run: `cd src/frontend; npx playwright test e2e/visual-brand.spec.ts --update-snapshots`  
Expected: baseline PNGs are created. Inspect every image at native size before accepting it; do not approve screenshots solely because the command passes.

- [ ] **Step 6: Add the stable script and verify clean replay**

```json
{
  "test:visual": "playwright test e2e/visual-brand.spec.ts --project=chromium"
}
```

Run: `cd src/frontend; npm run test:visual`  
Expected: PASS without updating snapshots and with zero serious/critical axe violations.

- [ ] **Step 7: Perform manual keyboard and reduced-motion checks**

At 200% zoom and 390 px width, tab through landing, auth, courses, and workspace. Verify visible focus, no hidden action, no horizontal page scroll except the labelled capability table, and no nonessential animation when reduced motion is enabled.

- [ ] **Step 8: Commit checkpoint if authorized**

```powershell
git add src/frontend/e2e/visual-brand.spec.ts src/frontend/e2e/visual-brand.spec.ts-snapshots src/frontend/playwright.config.ts src/frontend/package.json
git commit -m "test: gate HackaGen visual identity and accessibility"
```

## Task 8: Complete copy migration, documentation, and two-reviewer release gate

**Files:**

- Modify: `src/frontend/src/app/(auth)/login/page.tsx`
- Modify: `src/frontend/src/app/(auth)/register/page.tsx`
- Modify: `src/frontend/src/app/(auth)/forgot-password/page.tsx`
- Modify: `src/frontend/src/app/(auth)/reset-password/page.tsx`
- Modify: `src/frontend/src/app/(auth)/verify-email/page.tsx`
- Modify: `src/frontend/src/components/dashboard/BookTab.tsx`
- Modify: `src/frontend/src/components/dashboard/SlideTab.tsx`
- Modify: `src/frontend/src/components/dashboard/QuizTab.tsx`
- Modify: `src/frontend/src/components/dashboard/VidTab.tsx`
- Modify: `src/frontend/src/components/dashboard/BookOptionsPanel.tsx`
- Modify: `src/frontend/src/components/dashboard/SlideOptionsPanel.tsx`
- Modify: `src/frontend/src/components/dashboard/QuizOptionsPanel.tsx`
- Modify: `src/frontend/src/components/dashboard/VidOptionsPanel.tsx`
- Create: `src/frontend/scripts/audit-brand-language.mjs`
- Create: `docs/brand/voice-and-claims.md`
- Create: `docs/brand/visual-review.md`
- Modify: `README.md`

**Interfaces:**

- Consumes: `assertBrandLanguage`, claim registry workflow, screenshot/a11y commands, combined-signal checklist.
- Produces: a clean full-frontend language audit and a completed reviewer record required before release.

- [ ] **Step 1: Expand the audit to user-facing roots and capture every remaining violation**

Change the script's root list to:

```js
const AUDIT_ROOTS = ["src/app", "src/components", "src/content"]
const EXCLUDED = [/\.test\.[jt]sx?$/, /\/e2e\//, /\/node_modules\//, /\/\.next\//]
```

Scan JSX text and quoted user-facing values, excluding comments and internal-only technical error constants. Keep semantic claim validation in Vitest.

Use the installed TypeScript parser rather than raw regex over whole files:

```js
import ts from "typescript"

const COPY_KEYS = new Set([
  "alt", "aria-label", "description", "headline", "label", "message",
  "placeholder", "subtitle", "text", "title",
])

function propertyName(node) {
  const parent = node.parent
  if (ts.isJsxAttribute(parent)) return parent.name.getText()
  if (ts.isPropertyAssignment(parent)) return parent.name.getText().replace(/["']/g, "")
  if (ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) return parent.name.text
  return ""
}

function userFacingText(node) {
  if (ts.isJsxText(node)) return node.getText()
  if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && COPY_KEYS.has(propertyName(node))) {
    return node.text
  }
  if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && ts.isJsxExpression(node.parent)) {
    return node.text
  }
  return ""
}
```

Walk each source-file AST, run the banned patterns over nonempty returned text, and report file plus one-based line/column. Accumulate extracted public copy and apply the same three-beat, repeated-sentence, repeated-four-word-phrase, and four-sentence uniformity checks from `assertBrandRhythm`. This avoids flagging comments, CSS class names, and internal identifiers while checking rendered literals and named copy fields.

Expand the package command:

```json
{
  "audit:brand": "node scripts/audit-brand-language.mjs && vitest run src/content/brand.vi.test.ts"
}
```

Run: `cd src/frontend; npm run audit:brand`  
Expected: any remaining phrases such as `bộ học liệu hoàn chỉnh`, `Học thông minh hơn`, or em-dash marketing copy are reported with file and line.

- [ ] **Step 2: Replace each reported user-facing phrase with direct task language**

Use these exact replacements where the context matches:

- `Đăng ký để bắt đầu tạo khóa học với AI` → `Tạo tài khoản để mở không gian học đầu tiên.`
- `Tải lên tài liệu để AI phân tích và tạo bộ học liệu hoàn chỉnh.` → `Tải tài liệu. Sau khi tệp được đọc, bạn chọn loại học liệu cần tạo.`
- `Xuất sắc! Bạn đạt N% — đã nắm vững nội dung.` → `Bạn trả lời đúng N%. Xem lại phần giải thích trước khi làm lượt tiếp theo.`

Do not mechanically alter internal comments or valid punctuation inside generated document content.

- [ ] **Step 3: Document the claim promotion workflow**

`docs/brand/voice-and-claims.md` records: prohibited/approved voice examples, claim type definitions, required evidence, who may change `target` to `measured`/`shipped`, screenshot privacy rules, and the command `npm run audit:brand`.

- [ ] **Step 4: Create and complete the manual combined-signal review**

`docs/brand/visual-review.md` contains the eight signals and four questions verbatim from the spec, fields for reviewer name/date/revision, and one concrete answer per question. Release requires two independent reviewers and fails when three or more signals are present.

- [ ] **Step 5: Document exact developer commands**

Add to `README.md`:

```powershell
cd src/frontend
npm run audit:brand
npm run capture:product
npm run test:visual
npm test -- --run
npm run lint
npm run build
```

Explain that capture assets update only after inspecting fixture privacy and that visual baselines update only after an intentional approved design change.

- [ ] **Step 6: Run the final frontend gate**

Run all six commands above.  
Expected: brand audit clean; three product screenshots regenerated; visual/a11y suite clean; unit tests, lint, and build pass.

- [ ] **Step 7: Review the source manually**

Run:

```powershell
rg -n "bg-gradient|backdrop-blur|shadow-.*(primary|violet|purple)|✨|🚀|💡|—" src/frontend/src/app/page.tsx src/frontend/src/components/landing src/frontend/src/content
rg -n -i "seamless|unlock|transform|empower|robust|đột phá|nâng tầm|thông minh hơn|không chỉ.*mà" src/frontend/src/app src/frontend/src/components src/frontend/src/content
```

Expected: no rendered marketing match. Any internal/test match is reviewed and documented rather than blindly deleted.

- [ ] **Step 8: Commit checkpoint if authorized**

```powershell
git add src/frontend/src src/frontend/scripts/audit-brand-language.mjs src/frontend/package.json src/frontend/package-lock.json docs/brand README.md
git commit -m "docs: enforce HackaGen visual and voice review"
```

## Final Verification

- [ ] Landing composition follows opening workspace → process ledger → real evidence → capability table → final action; no testimonial section exists.
- [ ] At least two reviewers completed `docs/brand/visual-review.md`, and fewer than three combined AI-vibe signals remain.
- [ ] Every public numerical/source/scale claim can be traced from `data-marketing-claim-id` to a non-target registry entry and its evidence file.
- [ ] Three product screenshots contain only deterministic fixture data and match current authenticated UI.
- [ ] No generic `BookOpen` logo, emoji icon, landing gradient, colored glow, glass blur, or equal promotional feature-card grid remains.
- [ ] Light is the first-visit theme; manual dark mode remains readable and retains functional presenter-stage styling.
- [ ] Vietnamese diacritics render correctly in both fonts and no layout shift/font build error appears.
- [ ] Unit, brand audit, Playwright visual/accessibility, lint, and production build commands all pass.
- [ ] Review the final diff for fabricated claims, synthetic testimonials, personal screenshot data, accessibility regressions, and unintended generated-artifact changes.
