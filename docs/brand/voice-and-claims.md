# HackaGen brand voice and claim policy

HackaGen presents itself as a Vietnamese learning workshop built around the learner's own documents. Product copy should explain the source, the learning action, and the artifact a person can inspect. AI may be part of the mechanism, but it is not the headline or the proof.

## Voice rules

Prefer direct Vietnamese verbs and named product facts:

| Avoid | Use instead |
| --- | --- |
| `Học thông minh hơn với AI` | `Từ tài liệu đang đọc dở đến một buổi học có cấu trúc.` |
| `Đăng ký để bắt đầu tạo khóa học với AI` | `Tạo tài khoản để mở không gian học đầu tiên.` |
| `Tải lên tài liệu để AI phân tích và tạo bộ học liệu hoàn chỉnh.` | `Tải tài liệu. Sau khi tệp được đọc, bạn chọn loại học liệu cần tạo.` |
| `Xuất sắc! Bạn đạt 90% — đã nắm vững nội dung.` | `Bạn trả lời đúng 90%. Xem lại phần giải thích trước khi làm lượt tiếp theo.` |

Do not use `seamless`, `unlock`, `transform`, `empower`, `robust`, `revolutionize`, `supercharge`, `đột phá`, `nâng tầm`, `thông minh hơn`, `bộ học liệu hoàn chỉnh`, or `slide chuyên nghiệp` in public copy. Avoid em dashes, emoji decoration, three-beat slogans, `Không chỉ là X, mà còn là Y`, mechanically equal sentence rhythm, and repeated broad promises. Use Lucide icons or the HackaGen brand mark instead of emoji. Do not publish testimonials without a real name, role or organization, approved quotation, approval date, and usage permission.

Run the semantic and source audit from `src/frontend`:

```powershell
npm run audit:brand
```

The source audit parses TypeScript/JSX, ignores comments and internal identifiers, safely joins statically knowable `+` fragments without executing application code, and checks banned language in user-facing literals. Landing collections use named copy fields so their rendered prose participates in rhythm checks. Operational controls such as repeated authentication actions remain outside the marketing-rhythm corpus.

## Claim types

Every public landing claim is defined in `src/frontend/src/content/brand.vi.ts` with an ID, exact text, status, evidence path, and verification date.

| Status | Meaning | Required evidence | Public rendering |
| --- | --- | --- | --- |
| `target` | A product, quality, capacity, or performance goal that has not passed its gate. | Approved plan or specification describing the target. | Never. |
| `shipped` | Behavior available in the current product. | An implemented route or UI surface plus an automated acceptance test that demonstrates the exact statement. | Yes, after review. |
| `measured` | A numeric result observed under a defined test. | A committed benchmark artifact with workload, environment, method, timestamp, raw result, and pass/fail threshold. | Yes, only with the same scope and conditions. |

The current renderable registry entries point to these evidence sources:

| Claim ID | Exact claim text | Status | Evidence | Last verified |
| --- | --- | --- | --- | --- |
| `formats` | `Tải PDF, DOCX hoặc TXT.` | `shipped` | `src/frontend/src/components/course/UploadZone.tsx` | `2026-09-02` |
| `outputs` | `Study Guide, slide, quiz và video` | `shipped` | `src/frontend/src/app/course/[id]/page.tsx` | `2026-09-02` |
| `course-source` | `Mỗi khóa học được tạo từ tệp bạn tải lên.` | `shipped` | `src/backend/tests/test_course_and_upload.py` | `2026-09-02` |
| `document-source` | `HackaGen giữ nội dung trong tài liệu làm nguồn` | `shipped` | `src/backend/tests/test_vector_store_and_processor.py` | `2026-09-02` |
| `course-files` | `PDF, DOCX hoặc TXT được giữ theo từng khóa học.` | `shipped` | `src/backend/tests/test_course_and_upload.py` | `2026-09-02` |
| `indexing` | `Trang, đoạn và tệp nguồn được chuẩn bị để truy xuất.` | `shipped` | `src/backend/tests/test_vector_store_and_processor.py` | `2026-09-02` |
| `process-details` | `Mỗi bước giữ lại một chi tiết có thể kiểm tra: tệp nào đã vào, học liệu nào được tạo và định dạng nào có thể dùng tiếp.` | `shipped` | `src/frontend/src/components/landing/ProcessLedger.tsx` | `2026-09-02` |
| `output-selection` | `Tạo riêng Study Guide, slide, quiz hoặc video khi bạn cần.` | `shipped` | `src/frontend/src/app/course/[id]/page.tsx` | `2026-09-02` |
| `delivery` | `Đọc trên web hoặc tải định dạng có sẵn của từng học liệu.` | `shipped` | `src/backend/tests/test_generation_service.py` | `2026-09-02` |
| `fixture-evidence` | `Những hình dưới đây được chụp từ dữ liệu minh họa cố định của chính ứng dụng.` | `shipped` | `src/frontend/e2e/capture-product-screenshots.spec.ts` | `2026-09-02` |
| `book-evidence` | `Study Guide chia phần đọc theo mục lục, có điều hướng trước và sau cùng nút tải PDF.` | `shipped` | `src/frontend/src/components/dashboard/BookTab.tsx` | `2026-09-02` |
| `video-evidence` | `Không gian video cho chọn định dạng, giọng đọc và theo dõi phần trăm của lượt dựng đang chạy.` | `shipped` | `src/frontend/src/components/dashboard/VidOptionsPanel.tsx` | `2026-09-02` |
| `capability-scope` | `Bảng này đặt đầu vào, cách dùng và định dạng tải xuống cạnh nhau để dễ đối chiếu.` | `shipped` | `src/frontend/src/components/landing/CapabilityTable.tsx` | `2026-09-02` |
| `course-upload` | `Tải tệp lên theo từng khóa học.` | `shipped` | `src/backend/tests/test_course_and_upload.py` | `2026-09-02` |
| `book-delivery` | `Đọc từng phần trong trình duyệt; tải bản PDF khi cần.` | `shipped` | `src/frontend/src/components/dashboard/BookTab.tsx` | `2026-09-02` |
| `slide-formats` | `Trình chiếu tại chỗ; lấy bản PPTX hoặc PDF.` | `shipped` | `src/frontend/src/components/dashboard/SlideTab.tsx` | `2026-09-02` |
| `quiz-delivery` | `Làm câu hỏi trong khóa học; đáp án có bản PDF.` | `shipped` | `src/frontend/src/components/dashboard/QuizTab.tsx` | `2026-09-02` |
| `video-delivery` | `Phát trong khóa học; tải MP4 sau khi dựng xong.` | `shipped` | `src/frontend/src/components/dashboard/VidTab.tsx` | `2026-09-02` |
| `start-upload` | `Tải tài liệu lên để mở không gian học mới.` | `shipped` | `src/frontend/src/components/course/UploadZone.tsx` | `2026-09-02` |

The `capacity` and `source-only` entries remain `target`. They must not be rendered as shipped behavior until their separate runtime and PDF-only RAG acceptance gates pass.

## Claim promotion workflow

1. The feature owner proposes the exact public sentence and adds or updates its registry entry as `target`.
2. For `shipped`, the feature owner links the smallest route or UI implementation and the acceptance test that proves the full sentence. For `measured`, they commit the reproducible benchmark artifact and environment details.
3. An independent code reviewer checks that the claim is no broader than the evidence, that the evidence file exists, and that the verification date reflects the latest run.
4. The release owner may approve the status change from `target` to `shipped` or `measured` only after that independent review. Authors must not self-promote a claim directly to public copy.
5. The landing page renders claims through `getRenderableClaims` and identifies them with `data-marketing-claim-id`. Run `npm run audit:brand`, unit tests, visual/accessibility tests, lint, and build after a promotion.
6. If the behavior, benchmark environment, or source surface changes, return the claim to `target` until its evidence is rerun and reviewed.

No customer count, institution, speed, quality percentage, capacity, safety, source-grounding, quotation, or logo may be invented to fill a marketing section.

## Product screenshot privacy

Product evidence is captured only from `src/frontend/e2e/fixtures/demo-data.ts` and `visual-app.ts`. Fixture data must be visibly synthetic and neutral; use reserved domains such as `example.invalid`, not a real email. Before replacing an asset:

1. Inspect every fixture for names, email addresses, filenames, document excerpts, tokens, and IDs.
2. Run `npm run capture:product`.
3. Open all three PNG files in `src/frontend/public/product`, confirm that no personal or confidential data appears, and record file hashes in the visual review.
4. Keep nonempty Vietnamese alt text, fixed intrinsic dimensions, and the visible `Minh họa giao diện` caption on the landing page.

Capture assets are updated only after this privacy inspection. Visual baselines are updated only for an intentional, approved design change and are reviewed as images before acceptance.
