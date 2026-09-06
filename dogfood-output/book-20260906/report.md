# HackaGen real-user PDF test

Tested on 6 September 2026 against the existing application at http://localhost:3000.

**Result: all four generators completed, but the highest available settings did not produce dependable technical study material.** The principal problems are missing source coverage, damaged code/math in exports, contradictory quiz explanations, and misleading progress during video retries.

Course: http://localhost:3000/course/4d653d9c14f0

Input: Competitive Programmer's Handbook, Antti Laaksonen, draft 3 July 2018; 296 PDF pages, 30 chapters, 1,099,959 bytes. The PDF was treated as source material, not as instructions to the tester.

## OpenRouter spending

Amounts are USD, measured directly using the API key from the running backend. No credentials are included in these artifacts.

| Measure | Before | After | Change |
|---|---:|---:|---:|
| Account cumulative spending | $499.911309499 | $501.294669859 | **+$1.383360360** |
| This API key's cumulative spending | $0.978296380 | $2.361656740 | **+$1.383360360** |
| Account remaining credit | $520.088690501 | $518.705330141 | -$1.383360360 |
| Key allowance remaining | $9.021703620 | $7.638343260 | -$1.383360360 |

Baseline: 05:24:32 UTC, immediately before upload. Final generation snapshot: 05:47:53 UTC, after all jobs succeeded. The account and key deltas agree. The same totals were already visible at 05:41:52 UTC, before video rendering finished.

The observed increase includes document processing, all four generations and automatic retries. These are shared counters; unrelated concurrent use of the same key would also be included. No separate per-feature billing attribution was obtained. Provider counters lagged during the run, so early intermediate readings should not be used as exact feature costs.

Evidence: usage-before-upload.json, usage-after-generation.json, cost-summary.json, final-job-statuses.json.

## Generated outputs and timings

| Feature | Highest available setting used | Result | Server job duration |
|---|---|---|---:|
| Upload/indexing | Full book.pdf | Succeeded | 37 seconds |
| Study guide | Advanced; requested English and all 30 source chapters | 39-page PDF, 8 chapters | 14m 04s |
| Slides | Advanced, 22 slides; requested English and broad coverage | 23-slide PPTX/PDF; viewer exposes 22 | 58 seconds |
| Quiz | 15 questions, hard | Interactive quiz and 11-page question/answer PDF | 6m 33s |
| Video | Standard, 16:9, 5-7 minutes; Vietnamese female voice | 9 scenes, 5m 13s, 1280x720 MP4 | 18m 32s |

Jobs overlapped. Upload-to-last-job completion took about 21m 35s. Exactly one generation was manually submitted for each feature; video recovery used the application's automatic retries.

Downloads:

- [Study guide PDF](downloads/study-guide.pdf)
- [Slides PPTX](downloads/slides.pptx)
- [Slides PDF](downloads/slides.pdf)
- [Quiz and answer-key PDF](downloads/quiz-key.pdf)
- [Video MP4](downloads/video.mp4)

## Findings

Six issues: five high severity, one medium. These are observations of the running application and generated files; application source code was not changed.

### ISSUE-001: Advanced slide requests do not control language or coverage

**High — content quality.** Despite the explicit English request, the whole deck is in Vietnamese. Most slides cover the preface, introductory C++ and basic containers. There is one edit-distance slide, but no substantive graph, geometry or number-theory coverage matching the requested advanced overview. The design is readable but predominantly bullet lists rather than worked algorithm illustrations.

Reproduce: upload this PDF, select Slide > Advanced 22 slides, request an English advanced lecture spanning complexity, data structures, dynamic programming, graphs, mathematics, strings and geometry, then inspect the output.

Evidence: [settings](screenshots/slide-settings.png), [output](screenshots/slides-full-view.png), slides-content.json and the exported PDF. No additional paid regeneration was performed merely to reproduce a content defect.

### ISSUE-002: Code and mathematical notation are damaged across generated exports

**High — technical correctness/export fidelity.** Slide PDF page 9 mangles `ios::sync_with_stdio(0)` and replaces the newline escape with empty quotes. Page 13 displays `v.pushback(5)` instead of `v.push_back(5)`. Other examples corrupt `unordered_set`, braces and include directives.

The study guide's web reader shows intact C++ in Chapter 1, but PDF page 6 loses syntax. Guide PDF page 22 contains literal `ext extbackslash` and `otin` fragments in the subset-DP recurrence. The quiz PDF also mangles identifiers. The video's scene-five text contains a malformed `unordered_set` identifier.

Original PDF page 15 contains the correct `ios::sync_with_stdio` and newline escape. This is not a defect in the uploaded book.

Evidence: [slide page 9](screenshots/slide-export-9.png), [slide page 13](screenshots/slide-export-13.png), [guide page 6](screenshots/book-export-6.png), [guide page 22](screenshots/book-export-22.png), source-code-comparison.json and video-content.json.

### ISSUE-003: The slide viewer makes the final slide inaccessible

**Medium — viewer/export consistency.** The website reports 22 slides. Both PPTX and PDF have 23. Selecting thumbnail 22 shows references and disables Next, making the summary slide present in the exports inaccessible in the viewer.

Reproduce: open the generated deck and select the last thumbnail. Compare it with the last page of either export.

Evidence: [viewer stops at 22](screenshots/slides-last-visible.png), [exported slide 23](screenshots/slide-export-23.png). PPTX ZIP integrity verified: 23 slide XML files and 23 embedded images.

### ISSUE-004: Quiz explanations contradict the marked answer

**High — assessment correctness.** Question 1 marks D correct, but the explanation says A is correct and D is unsupported. Question 2 marks C correct (Python), while its explanation refers to C as the alternative choice that appears under B (Java). The contradictions also appear in the answer-key PDF. This is consistent with shuffled options retaining old letter references, although the implementation cause was not inspected.

Reproduce: select D for question 1; compare the marked answer and score with the explanation. Select C on question 2 and compare its letter references. The question-1 mismatch was confirmed again after signing back in.

Evidence: [unanswered question](screenshots/quiz-unanswered.png), [confirmed contradiction](screenshots/quiz-q1-mismatch-confirmed.png), [question 2 feedback](screenshots/quiz-q2-feedback.png), quiz-content.json.

### ISSUE-005: Video error state hides ongoing retry progress

**High — generation/status reliability.** Speech synthesis repeatedly failed with `No audio was received`. The website showed a terminal-looking error and offered a new-generation dialog while the original job continued retrying. Later the artifact endpoint reported 78% processing, yet the existing tab still showed failure. Refreshing the page revealed 85%; the original job eventually succeeded.

Reproduce on this run: after the TTS failure, leave the error tab open or switch away and back; compare with the recovered state after refresh. No new video generation was manually submitted. The failure occurrence depends on the speech service, so a fresh generation may not reproduce it.

Long-running guide progress was also inconsistent: the job route reported 0% / waiting while the artifact UI showed 61-80%.

Evidence: [stale error](screenshots/video-stale-error-before-refresh.png), [after refresh](screenshots/video-after-refresh.png), [playable result](screenshots/video-playing.png), runtime-errors-redacted.json and final-job-statuses.json.

### ISSUE-006: Advanced guide omits supplied topics and incorrectly describes missing evidence

**High — grounding/completeness.** The guide is in Vietnamese despite the English request. Its 8 chapters contain useful explanations and review questions, but do not cover all 30 source chapters as requested. There is no treatment under Dijkstra, Bellman-Ford, Kruskal, segment trees, Fenwick trees, tries or the Z-algorithm in the exported text.

More decisively, guide page 20 says the provided material does not contain detailed information about bit-counting builtins. Source PDF page 108 explicitly explains `__builtin_clz`, `__builtin_ctz`, `__builtin_popcount` and `__builtin_parity`, with working examples. The generated chapter lacks relevant source coverage.

Reproduce: generate the advanced guide with the saved all-30-chapters request; compare its Chapter 4 with the source's Bit manipulation section.

Evidence: [guide overview](screenshots/book-ready.png), [page 20](screenshots/book-export-20.png), coverage-comparison.json, book-coverage-audit.json and the original PDF.

## What worked

- Login, upload, background generation and saved artifacts.
- Study-guide chapter navigation, expand/hide contents and restore contents.
- Slide thumbnails, Next/Previous and presentation mode, within the exposed 22 slides.
- Quiz answer selection, scoring and explanations appearing after answering. Answers survive switching tabs. The observed questions are mostly about introductory material and container choices; one includes a concrete Prufer-code exercise.
- All five authenticated download endpoints returned HTTP 200 with appropriate content types. PDF files opened successfully; PPTX structure is valid.
- Video playback advanced normally with no media error, 1280x720 decoded video and decoded audio bytes while unmuted. The MP4 is 6,621,532 bytes and 313.216 seconds long. The scene script was reviewed; playback was sampled rather than a full subjective listening review.

## Testing limits and environment notes

This tested the already-running Docker application, not a rebuild of the worktree's many pre-existing edits. No code changes, commits or deployments were made. The supplied user account owns the new course.

The browser automation's direct download command canceled twice, but retrieving the same visible signed links succeeded. This is an automation limitation, not a proven website download bug. Screen recording failed because the local automation encoder lacked ffmpeg and reset its browser context; screenshots and generated files are the valid evidence. The session was restored by logging in again. The two quiz-mismatch-step screenshots belong to that failed recording attempt and are not used as issue evidence.

Before the user supplied a login, one unverified QA signup was created with an example.com email. It has no uploaded documents. Credentials were not saved in the report or helper files.

## Priority for improvement

Preserve code/math end to end; keep quiz explanations aligned with displayed answers; verify source coverage before labeling material advanced or high quality; respect the requested language; reconcile viewer counts and export counts; and keep retry/progress states synchronized. The current high quality badge (100/100 initially, 90/100 later) does not establish correctness of these outputs.

Final playback check: the browser was left playing to completion. See playback-verification.json and screenshots/video-playback-complete.png for the final media state. This verifies continuous playback, not a subjective human listening assessment of pronunciation or instructional delivery.
