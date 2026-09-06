# HackaGen: real-user book.pdf generation test

Date: 2026-09-06 (Asia/Saigon)
Target: http://localhost:3000, existing running Docker application.
Input: user's book.pdf, Competitive Programmer's Handbook by Antti Laaksonen, 296 pages, 1,099,959 bytes.
Scope: upload, highest available generation settings, study guide, slides, quiz, video, output/download checks, OpenRouter cost before and after.

## Cost baseline

Live backend key queried directly via OpenRouter, 2026-09-06T05:20:58Z. Credentials were not printed or saved in report artifacts.

- Account total credits purchased: $1,020.00.
- Account cumulative usage: $499.911309499.
- Account remaining credit (credits minus usage): $520.088690501.
- API key cumulative usage: $0.97829638.
- API key spending limit: $10.00; allowance remaining: $9.02170362.
- Snapshot: usage-before.json.

Account usage delta can include unrelated activity. Key usage delta will also include concurrent users sharing this backend key. No generation cost should be inferred from listed model prices.

## Progress

- Landing page loaded successfully.
- Created a dedicated test signup, Book PDF QA (book-qa-20260906@example.com); redirected to email verification, as expected. It is unverified and has no uploaded documents.
- Configured demo login was rejected. Requested a working test account or a receivable signup email from the user.
- No PDF upload or generation has been triggered yet.
- Source text extraction works locally, allowing later checks against the original textbook.

## Findings

No product defects asserted yet. Required email verification and rejection of invalid credentials are expected behaviors, not defects.

## Remaining checks

Upload and indexing; highest settings exposed by the website; guide completeness and source coverage; slide navigation/export; interactive quiz answer/review; video playback/audio/export; final usage measurement. These depend on signing into a verified account.

## Generation started

Signed in successfully using the account supplied by the user. Created course http://localhost:3000/course/4d653d9c14f0.

- Upload submitted around 05:24:40Z; ready by 05:25:40Z. UI source quality indicator: 100/100.
- Study guide: Chuyen sau (advanced), requested English, all 30 chapters, accurate math/C++, worked examples, pitfalls and exercises. Started around 05:26Z.
- Slides: Chuyen sau, 22 slides, English, broad handbook coverage, examples and formulas. Started around 05:26Z.
- Quiz: 15 questions, Kho (hard). Started around 05:27Z. No language or topic override exposed in this form.
- Video: longest available, Tieu chuan 16:9 5-7 minutes, default female voice, Vietnamese narration, core algorithms with examples. Started around 05:28Z.
- All generation was triggered through visible browser controls, with screenshots of chosen settings.
- Post-ingestion OpenRouter account usage: $499.926398899, delta $0.0150894. Key usage still unchanged, so provider counter updates may lag.

### ISSUE-001: Advanced slides ignore language and most requested coverage

Severity: high. Category: content. Static generated-output defect; no additional paid retry performed.

The saved 22-slide advanced deck is Vietnamese despite the explicit English request. Most content covers the preface, Chapter 1, and elementary C++ containers; there is one edit-distance slide but no substantive graph, geometry, or number-theory coverage. This falls well short of an advanced overview of the supplied 30-chapter book.

Evidence: screenshots/slide-settings.png (request and advanced selection), screenshots/slides-full-view.png (Vietnamese output), slides-content.json (complete exported text), downloads/slides.pdf.

Reproduction: upload book.pdf; select Slide > Chuyen sau 22 slides; enter the saved English broad-coverage request; generate; inspect the resulting deck.

### ISSUE-002: Generated C++ examples are corrupted

Severity: high. Category: content/rendering. Static generated-output defect.

Slide PDF shows `v.pushback(5)` instead of `v.push_back(5)`, `ios::syncwith` followed by a subscript-like character instead of `ios::sync_with_stdio`, malformed `unordered_set` / `unordered_map`, and an empty quoted string where the newline escape should be. The introductory C++ template omits `#` before include and braces around main. Learners cannot safely copy the code.

Evidence: downloads/slides.pdf, pages 6, 9, 13-15; slides-content.json. Visual verification of individual examples is in progress.

### ISSUE-003: Slide PDF and viewer disagree on the number of pages

Severity: medium. Category: export consistency. Static generated-output defect.

The website reports 22 slides, while the downloaded PDF contains 23 pages, with its final page labeled Slide 23. The PDF needs comparison with the PPTX and viewer before attributing the cause.

Evidence: screenshots/slides-full-view.png; downloads/slides.pdf; slides-content.json.

## Export verification note

The browser automation download command reported cancellation twice for PPTX. Fetching the exact visible authenticated download link from the same browser succeeded (HTTP 200, correct PPTX MIME type, 1,311,626 bytes); the PDF link also returned HTTP 200 (48,141 bytes). Files were saved using this workaround. This is recorded as an automation limitation rather than a proven website download failure.

### ISSUE-004: Quiz explanations reference the wrong answer letters

Severity: high. Category: learning-content correctness.

Question 1 marks D correct and increments the score, but its explanation says A is the accurate analysis and D is unsupported. Question 2 marks C correct (Python), but its explanation refers to C as the alternative choice (the displayed Java answer is B). This is consistent with option labels being shuffled without updating prose, although the implementation cause was not inspected.

Reproduction: open the 15-question hard quiz; choose D on question 1; observe score/green answer versus the explanation. Navigate to question 2, choose C, and compare the explanation's letter references. Returning to question 1 preserves the mismatch.

Evidence: screenshots/quiz-unanswered.png, screenshots/quiz-answered.png, screenshots/quiz-q2-feedback.png, screenshots/quiz-mismatch-step-1.png, screenshots/quiz-mismatch-step-2.png; videos/quiz-explanation-mismatch.webm.

Additional export verification: PPTX is a valid ZIP containing 23 slides and 23 embedded images. Both export formats have 23 slides; viewer offers 22.

Visual inspection of slide PDF pages 9 and 13 confirms the malformed C++ seen in extracted text, rather than a text-extraction artifact. Evidence: screenshots/slide-export-9.png and screenshots/slide-export-13.png.

Evidence correction: recording could not be produced because the browser recording command reset the automation context and its encoder reported missing ffmpeg. The two quiz-mismatch-step screenshots show that failed recording attempt, not the quiz; use the earlier quiz-unanswered, quiz-answered and quiz-q2-feedback screenshots as the valid evidence. No video exists for this issue. This is a tooling limitation, not a site authentication defect. Signing back into the same user account to continue.

### ISSUE-005: Video generation fails in speech synthesis and UI offers a new run while retries continue

Severity: high. Category: generation reliability and status UX.

The longest video option showed 'Cannot create video. Please try again' after repeated TTS failures. The public job endpoint simultaneously still reported running / waiting to retry. Clicking the UI recovery button opens a new-generation dialog even while the original job is retrying. The dialog was canceled, so no second manual paid video generation was submitted.

Evidence: screenshots/video-failed-first.png, runtime-errors-redacted.json. Logs show repeated edge-tts NoAudioReceived failures at 05:32 and 05:35; a later internal attempt also hit invalid video JSON before retrying. Failure persists across tab navigation. Final terminal result pending.

Quiz verification: answers and score survive switching to Video and back. Answer-key PDF download endpoint succeeds (HTTP 200), producing an 11-page PDF. The answer-letter contradiction is present in the exported PDF as well.

Slide-count impact confirmed in the browser: selecting the last thumbnail stops at references (Slide 22) with Next disabled. The summary slide (Slide 23), present in both downloads, cannot be reached in the viewer. Evidence: screenshots/slides-last-visible.png and screenshots/slide-export-23.png.

Original-source comparison confirms underscores and newline escapes exist correctly in the supplied PDF. For example, source PDF page 15 contains `ios::sync_with_stdio(0)` and `"\n"`. This rules out blaming the uploaded book for the malformed generated examples. See source-code-comparison.json.

Guide progress is now 80% in its artifact UI, while the public job progress still says 0% / waiting to process. Earlier tab switching showed only the 0% job progress. This is inconsistent feedback for a long-running generation.

### ISSUE-006: Study guide loses source coverage and incorrectly claims supplied material is absent

Severity: high. Category: grounding / completeness.

The advanced guide has 8 chapters and 39 pages. It ignores the explicit English request. It covers selected topics in detail, but does not provide the requested comprehensive coverage of all 30 source chapters. The exported text contains no Dijkstra, Bellman-Ford, Kruskal, segment-tree, Fenwick-tree, trie, or Z-algorithm treatment.

More concretely, guide page 20 states the supplied materials do not contain detailed information about compiler bit-counting builtins. Original PDF page 108 explicitly explains __builtin_clz, __builtin_ctz, __builtin_popcount and __builtin_parity and supplies working code. This is a source retrieval/coverage failure visible in the result, not simply a short summary.

Evidence: screenshots/book-ready.png, screenshots/book-export-20.png, coverage-comparison.json, book-coverage-audit.json and the original PDF. Repro: generate the advanced guide with the saved all-30-chapters request; inspect Chapter 4 and compare it with the source's Bit manipulation section.

ISSUE-002 also affects study-guide export fidelity: browser Chapter 1 shows intact `#include`, braces and `ios::sync_with_stdio`, but PDF page 6 removes or mangles them. PDF page 22 contains literal fragments such as `ext extbackslash` and `otin` in recurrence notation. Evidence: screenshots/book-export-6.png, screenshots/book-export-22.png, screenshots/book-chapter5.png. Formula/code preservation must be checked across both the web renderer and export renderer.

Guide navigation, chapter selection, PDF endpoint, expand/hide table-of-contents and restore table-of-contents worked. Completed job time: 05:40:20Z, duration 14 minutes 4 seconds. It was visibly ready at 05:41:52Z.

Video recovery update: at approximately 05:45-05:46Z the authenticated artifact endpoint reported processing at 78%, despite the existing tab still showing failure. Refreshing the page and reopening Video revealed 85% progress. No new generation was submitted. ISSUE-005 should be understood as a transient speech-synthesis failure plus a stale error state that hides automatic recovery; final MP4 verification is still pending. Before/after evidence: screenshots/video-stale-error-before-refresh.png and screenshots/video-after-refresh.png.
