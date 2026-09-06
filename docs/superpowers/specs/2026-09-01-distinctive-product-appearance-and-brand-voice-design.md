# Distinctive Product Appearance and Brand Voice Design

**Date:** 2026-09-01  
**Status:** Approved planning baseline  
**Scope:** Public landing/authentication pages and authenticated product shell; no backend behavior change

## Problem

HackaGen is technically coherent, but parts of the current frontend use a familiar AI-product template:

- The landing page opens with a centered gradient hero and the generic headline `Học thông minh hơn với AI`.
- Four capabilities are presented as four equal rounded cards with equal spacing and copy length.
- Inter is the only typeface, blue is the dominant brand color, and the primary visual is a generic `BookOpen` icon.
- The page contains no real product screenshot, artifact example, measured result, or source-grounding evidence.
- Copy repeats broad phrases such as `bộ học liệu hoàn chỉnh`, `chuyên nghiệp`, and `với AI` without showing how the product behaves.

None of those traits alone proves that a site was made by AI. Together they make the product look interchangeable with many AI landing pages and conceal HackaGen's strongest distinction: it turns a user's own source material into a concrete, inspectable study workspace.

## Brand Position

HackaGen is a Vietnamese **learning workshop**, not an AI spectacle.

**Promise:** Turn source documents into a structured place to read, teach, practise, and explain.

**Personality:** Clear, practical, editorial, grounded, quietly capable, and recognizably Vietnamese.

**AI's role:** A mechanism inside the workflow. Headlines lead with the document and the learning task, not with AI.

**Primary audience:** Learners and educators who already have material but need a usable structure for studying or teaching it.

## Voice Rules

### Use

- Concrete Vietnamese verbs: `tải lên`, `đọc`, `đối chiếu`, `tạo`, `ôn`, `trình bày`, `tải xuống`.
- Specific inputs and outputs: PDF/DOCX/TXT, Study Guide, slide, quiz, video, PDF/PPTX/MP4.
- Short direct sentences mixed with longer explanatory sentences.
- Honest limits and source rules near the related claim.
- Product facts only when the feature is shipped and visible.

### Avoid

- Generic English AI words: `seamless`, `unlock`, `transform`, `empower`, `robust`, `revolutionize`, `supercharge`.
- Generic Vietnamese equivalents in marketing copy: `đột phá`, `nâng tầm`, `thông minh hơn`, `hoàn chỉnh`, `chuyên nghiệp` unless a nearby sentence defines the measurable meaning.
- Em dashes in user-facing marketing copy.
- Emoji used as icons or decoration. Use the existing Lucide icon system or the custom brand mark.
- Three-beat slogan formulas such as `Nhanh. Thông minh. Mạnh mẽ.`
- `Không chỉ là X, mà còn là Y` and `It's not just X, it's Y` constructions.
- Four or more consecutive marketing sentences whose word counts differ by no more than two words; vary rhythm deliberately instead of padding every sentence to the same size.
- Exact repeated marketing sentences or the same four-word phrase appearing more than twice outside product names and required format lists.
- Claims about speed, scale, grounding quality, safety, or user satisfaction without a recorded source.
- Testimonials until there is a real name, role/organization, quote approval, date, and permission record. Do not create synthetic or anonymous testimonials.

### Approved Landing Copy

Use these lines as the initial implementation baseline:

- Eyebrow: `XƯỞNG HỌC LIỆU TỪ TÀI LIỆU CỦA BẠN`
- H1: `Từ tài liệu đang đọc dở đến một buổi học có cấu trúc.`
- Body: `Tải PDF, DOCX hoặc TXT. HackaGen giữ nội dung trong tài liệu làm nguồn, rồi dựng Study Guide, slide, quiz và video để bạn học tiếp.`
- Primary CTA: `Tạo bộ học liệu từ tài liệu`
- Secondary CTA: `Xem cách một tài liệu được xử lý`
- Source note: `Nội dung học liệu bám theo tệp bạn tải lên. Khi tài liệu không nói rõ, HackaGen không tự bổ sung kiến thức từ web.`

Do not render the final source note until the corresponding source-only behavior has passed the relevant backend acceptance tests. Until then, render the narrower shipped claim: `Mỗi khóa học được tạo từ tệp bạn tải lên.`

## Claim Registry

All landing claims live in one typed registry. A claim has:

```ts
type ClaimStatus = "shipped" | "measured" | "target"

type MarketingClaim = {
  id: string
  text: string
  status: ClaimStatus
  evidence: string
  lastVerified: `${number}-${number}-${number}`
}
```

- `shipped` points to a route, UI surface, or automated acceptance test.
- `measured` points to a committed benchmark result and its environment.
- `target` is internal planning language and cannot render on the public site.
- Runtime goals such as 100 active users and p95 below 500 ms remain `target` until the load gate passes.
- Source-only/grounding claims become `shipped` only after the Book RAG and relevant artifact tests pass.

## Visual Direction: The Learning Workshop

The visual metaphor is an annotated study desk: warm paper, ink, marginal notes, page edges, file labels, and restrained editorial typography. It must not use robots, brains, sparkles, magic wands, neon glows, purple-blue gradients, or floating glass cards.

### Color

Light mode is the first-visit default:

| Token | Value | Use |
|---|---|---|
| `background` | `#F7F3EA` | warm paper canvas |
| `foreground` | `#18211D` | ink text |
| `card` | `#FFFCF6` | raised paper only where needed |
| `primary` | `#244A3A` | forest ink, primary actions |
| `primary-foreground` | `#FFFDF7` | action text |
| `accent-strong` | `#C5563C` | terracotta annotations and active markers |
| `secondary` | `#E8E0D2` | quiet controls and bands |
| `muted` | `#EFE8DC` | recessed regions |
| `muted-foreground` | `#6C675E` | secondary text |
| `border` | `#D5CBBB` | rules and paper edges |
| `ring` | `#9D3E2B` | accessible focus |

Dark mode remains available manually, but uses charcoal and parchment rather than blue-black neon:

| Token | Value |
|---|---|
| `background` | `#171A18` |
| `foreground` | `#F1EBDD` |
| `card` | `#20241F` |
| `primary` | `#8EC4A6` |
| `primary-foreground` | `#101713` |
| `accent-strong` | `#E17A5F` |
| `secondary` / `muted` | `#2A302A` |
| `muted-foreground` | `#B8B0A2` |
| `border` | `#3A4039` |
| `ring` | `#F09A80` |

The video/slide presenter stage retains its dedicated dark tokens because it is functional media chrome, not brand decoration.

### Typography

- Body/interface: `Be Vietnam Pro`, weights 400, 500, 600, 700, Vietnamese subset.
- Editorial/display headings: `Newsreader`, weights 500, 600, 700, Vietnamese subset.
- Data, file metadata, timestamps, and queue positions may use the existing monospace system stack.
- Landing H1 is left-aligned and capped at 64 px desktop/42 px mobile. Do not center every heading.
- Body measure is 55-72 characters. Sections deliberately vary density; copy blocks are not padded to equal heights.

Both selected fonts are present in the installed Next.js 16 font type declarations with a Vietnamese subset.

### Shape and Effects

- Base radius 6 px; paper panels maximum 10 px.
- Pills only for status, tags, filters, or compact metadata.
- Shadows are subtle paper separation, never colored glow.
- No CSS gradients on public marketing surfaces.
- No `backdrop-blur`, glassmorphism, floating-orb decoration, or hover lift on marketing cards.
- Motion is functional and under 200 ms; respect `prefers-reduced-motion`.

## Brand Mark

Replace the generic standalone `BookOpen` logo with a small custom SVG mark: two offset document sheets, a folded corner, and three uneven source lines. Use forest ink plus one terracotta line. It must remain legible at 20 px and include an accessible text label when used without the wordmark. Do not use sparkles, an AI brain, a chat bubble, or a robot.

## Page Composition

### Landing

Do not use `Hero → equal feature cards → testimonials → CTA`.

Use this sequence:

1. An asymmetrical 12-column opening: direct copy at left, a real HackaGen course-workspace screenshot at right, and a small source-rule annotation crossing the grid.
2. A vertical `Một tài liệu đi qua HackaGen như thế nào` ledger with four unequal rows. Each row shows a real input/output detail rather than a promotional benefit.
3. Two real product evidence panels: the Book reading/source-quality view and the video workspace/progress view. Screenshots must be captured from the application, not generated artwork. Regenerate them after the later grounding/job-progress plans change those surfaces.
4. A compact capability table with formats, downloadable artifacts, and current availability. It is not a grid of four identical cards.
5. A restrained final action beside a sample document label. No testimonial section until verified customer evidence exists.

Every screenshot has Vietnamese alt text, fixed intrinsic dimensions, a visible `Minh họa giao diện` caption when its data is deterministic demo data, and no real user name, email, filename, or document content.

### Authentication

Replace the solid primary branding slab with an editorial source excerpt: brand mark, one concrete sentence, a thin document-rule motif, and a small list of accepted formats. Forms remain visually dominant and familiar.

### Authenticated Product

- Prefer document rows, dividers, tabs, and workspace regions over nesting every section in a rounded card.
- Course cards may remain cards because they represent discrete objects, but vary metadata naturally and remove hover lift.
- Empty/error/loading states use Lucide icons and direct recovery language; no emoji or celebratory AI language.
- Job progress and grounding metrics from the other plans use the same editorial tokens, typographic hierarchy, and claim rules.

## Real Evidence Rules

- Product screenshots are generated from deterministic demo fixtures through Playwright.
- Screenshot fixtures contain obviously synthetic neutral data and are labelled `Minh họa giao diện` on the landing page.
- Real product evidence satisfies the need for visual specificity. People photography is optional and may appear only when it is original, consented, relevant to the product story, and recorded with usage permission; never add anonymous stock people merely to look less AI-generated.
- Do not fabricate customer counts, latency, quality percentages, institutions, quotes, or logos.
- A measured claim links internally to the committed benchmark artifact used to approve it.
- Product screenshots must be regenerated when their surface changes; the capture script is the source of truth.

## Acceptance Gates

### Automated

- Landing source contains zero CSS gradient utilities, zero glow/blur decoration, zero emoji, and zero em dash characters in rendered marketing copy.
- Landing copy contains none of the banned generic terms or formula patterns.
- Landing/auth copy contains no three-beat slogan, exact repeated sentence, overused four-word phrase, or run of four uniformly sized sentences as defined above.
- Every rendered marketing claim is `shipped` or `measured`; no `target` claim renders.
- At least two real product screenshots render with nonempty Vietnamese alt text and fixed dimensions.
- No testimonial component or customer quote renders without the complete verification fields.
- Playwright screenshot baselines pass at 390×844, 768×1024, and 1440×1000 for the landing page plus key authenticated states.
- Automated accessibility scan has zero serious or critical violations; manual keyboard/focus/contrast checks meet WCAG 2.2 AA.

### Manual Combined-Signal Review

Reviewers judge the page as a whole, not by one isolated trait. Release fails when three or more of these are present:

- AI is the subject of the main headline.
- Purple/blue gradient or colored glow is a dominant visual.
- Three or more equal promotional cards have matched copy height.
- Generic emoji replace the icon system.
- No real product evidence appears above the final CTA.
- Unsupported testimonial or numerical claim appears.
- Copy repeats one broad promise without explaining input, action, and output.
- Most sections are centered, equally spaced, and visually interchangeable.

At least two reviewers must answer these questions in the pull request:

1. What feels uniquely HackaGen rather than generically AI?
2. Which product fact is proved visually?
3. Which phrase would only make sense for this product?
4. Is any claim broader than its evidence?

## Out of Scope

- Inventing customer testimonials, logos, people photography, or benchmark results.
- Redesigning generated Book PDFs, Slides, or rendered video frames in this release.
- Changing backend generation behavior.
- Removing the user-selectable dark theme.
