# HackaGen combined-signal visual review

This record reviews the uncommitted implementation based on Git base revision `23a8144` in `D:/HackaGen-appearance-worktree`. Product images come from deterministic demo fixtures, not customer data. Release fails when three or more signals below are present.

## Combined-signal checklist

- [ ] AI is the subject of the main headline.
- [ ] Purple/blue gradient or colored glow is a dominant visual.
- [ ] Three or more equal promotional cards have matched copy height.
- [ ] Generic emoji replace the icon system.
- [ ] No real product evidence appears above the final CTA.
- [ ] Unsupported testimonial or numerical claim appears.
- [ ] Copy repeats one broad promise without explaining input, action, and output.
- [ ] Most sections are centered, equally spaced, and visually interchangeable.

## Evidence packet for independent reviewers

1. **What feels uniquely HackaGen rather than generically AI?** The `Xưởng học liệu` framing, warm paper-and-ink system, document-rule motif, uneven process ledger, and Vietnamese workflow copy make the learner's own source file the organizing idea.
2. **Which product fact is proved visually?** Deterministic captures show one course workspace with two source files, a Study Guide with chapter navigation and PDF download, and a video configuration surface reporting 64% generation progress.
3. **Which phrase would only make sense for this product?** `Từ tài liệu đang đọc dở đến một buổi học có cấu trúc.` describes the product's document-to-study-workspace transition rather than a generic AI benefit.
4. **Is any claim broader than its evidence?** The public registry is limited to shipped formats, artifact surfaces, course/file retention, indexing, delivery, and slide downloads. `capacity` and `source-only` remain non-rendering targets; they require separate runtime and PDF-only RAG gates.

## Screenshot privacy and integrity evidence

- Fixture identity: `Người học mẫu`, `demo@example.invalid`, course `Nhập môn sinh thái đô thị`, neutral filenames `chuong-1.pdf` and `ghi-chu.txt`.
- No real name, reachable email, customer filename, uploaded document, institution, quotation, or customer metric is present.
- All three PNG assets were opened and inspected at original resolution on 2026-09-02.
- Final-capture SHA-256 values:
  - `course-workspace.png`: `B7AC018B4D5D133ECDE440722C35F4DBC3DCC521D05303A8BC6E19AFB922320A`
  - `book-reading.png`: `2C603D7B31EAB6846C81A19D50FC2A87BA806D2864D4831982DEE092B4C329A7`
  - `video-progress.png`: `859C1EEFF82BCFA156EE9CB2E951677F7BDB01968ECDB27AF991976807094CCF`

## Implementation verification evidence

- `npm run audit:brand`: passed; 393 user-facing literals were checked for banned language and 36 marketing prose nodes passed rhythm checks; the semantic registry suite passed 4/4 tests. Permanent parser self-tests cover static concatenation, named landing data, and safe operational labels. Controlled negative probes also confirmed that `"unlock " + dynamicValue` and a three-beat named availability value fail with source locations.
- `npm run capture:product`: passed 1/1; all three assets exceeded 20 KB, retained the hashes above, and were opened after capture for privacy review.
- `npm run test:visual`: passed 12/12 Win32 Chromium snapshots and the zero-serious/critical Axe gate at the planned viewports. The three landing baselines were visually inspected and intentionally regenerated after the capability descriptions were varied; a normal replay then passed 12/12.
- `npm test -- --run`: passed 27/27 tests across 12 files. The focused landing/brand run passed 10/10 tests across 2 files (6 landing + 4 brand).
- `npm run lint`: passed with 0 errors and the three existing `@next/next/no-img-element` warnings in functional slide media rendering.
- `npm run build`: passed with all expected App Router pages generated.
- Manual scans found no rendered marketing violation. Their only matches were the banned-pattern guard itself, its regression test, and internal CSS `transform` identifiers.
- Implementation-author precheck: 0 of 8 combined signals observed. This precheck does not replace either independent reviewer decision below.

## Reviewer 1

- Approval status: Current Task 8 approval.
- Reviewer name/role: Codex independent Task 8 reviewer (`task8_reviewer`)
- Review date: 2026-09-02
- Base revision: `23a814485bd045fe37d5ed6cc678081e397a9870`
- Review scope/hash: 65 files from the sorted union of `git diff --name-only 23a814485bd045fe37d5ed6cc678081e397a9870` and `git ls-files --others --exclude-standard`, excluding `docs/brand/visual-review.md` and `.superpowers/**`; SHA-256 over UTF-8 normalized-slash path + NUL + raw bytes + NUL = `A62763996DBC75DE70F645B701B267C1BB61C8AA032E128D5BB9D24558ABF419`.
- Regenerated landing-baseline approval: Reviewer 1 inspected and approved desktop `806EBF8F501A209F19606103DD6031C06C50E73DA99F708CD738A47C36CEC843`, mobile `D478CC77060AD4F91B77F8D07BB394E2F6EB43EE14FF90F2349B153B05E11998`, and tablet `9410D4D3711F9602681CFA4DC4B3FCB4E411B4DC4FD8B741CAED4F2BF12B5657`.
- Present signal count: 0 of 8
- Decision: PASS / APPROVED
- Claim broader than evidence: No.
- Q1: The Vietnamese `Xưởng học liệu` identity, warm paper/ink typography, source-note annotation, asymmetrical process ledger, and learner-document-first workflow feel specific to HackaGen rather than a generic AI template.
- Q2: The deterministic captures prove that one course exposes its source-file count, a navigable Study Guide with chapter structure and PDF download, and a Video workspace with format, voice, and in-progress controls. The displayed 64% is fixture state, not a production metric.
- Q3: `Một tài liệu đi qua HackaGen như thế nào` only makes sense for HackaGen’s document-to-study-workspace flow.
- Q4: No rendered claim is broader than its evidence. All 19 rendered markers are leaf text nodes exactly equal to shipped registry entries with existing evidence; output selection, reader/player/download, fixture, and process wording stay within those surfaces, while `capacity` and `source-only` remain non-rendering targets.
- Prior review (historical and superseded): the 2026-09-02 review of base `23a814485bd045fe37d5ed6cc678081e397a9870` recorded uncommitted implementation content SHA-256 `1D593CD233083AC08085AC6C42A829F6B3D7C4FC52FDB703FF99EA4DA4F6993C` across 65 changed/untracked implementation files, excluding the mutable reviewer record. It is not the current release approval.

## Reviewer 2

- Reviewer name/role: Codex independent whole-plan reviewer (`whole_plan_reviewer_final`)
- Review date: 2026-09-02
- Base revision: `23a814485bd045fe37d5ed6cc678081e397a9870`
- Review scope/hash: 65 files from the sorted union of `git diff --name-only 23a814485bd045fe37d5ed6cc678081e397a9870` and `git ls-files --others --exclude-standard`, excluding `docs/brand/visual-review.md` and `.superpowers/**`; SHA-256 over UTF-8 normalized-slash path + NUL + raw bytes + NUL = `A62763996DBC75DE70F645B701B267C1BB61C8AA032E128D5BB9D24558ABF419`.
- Present signal count: 0 of 8
- Decision: PASS / APPROVED
- Claim broader than evidence: No.
- Q1: The Vietnamese `Xưởng học liệu` identity, warm paper/ink system, document-rule motif, uneven process ledger, and document-first workflow make it specific to HackaGen.
- Q2: The deterministic captures show a course workspace with two source files, a navigable Study Guide with PDF download, and a Video workspace with format, voice, and in-progress controls.
- Q3: `Một tài liệu đi qua HackaGen như thế nào` only makes sense for this document-to-study-workspace flow.
- Q4: No rendered claim is broader than its evidence; source-only and capacity remain non-rendering targets.

Both reviewer sections must contain a date, the reviewed revision or diff, the signal count, answers to the four questions above, and an explicit pass/fail decision before release. Pending fields are intentionally not approval evidence.
