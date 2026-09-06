# Frontend regression checks — 2026-09-06

Working directory: `D:\HackaGen-appearance-worktree\src\frontend`.
Scope: existing tests, lint, build, and requested mocked Playwright checks; no product edits, snapshot updates, or paid calls. Build and Playwright were run only after the parent stopped the review frontend dev process to free `.next`.

## Commands and outcomes

| Command | Environment | Exit | Result |
| --- | --- | --- | --- |
| `npm test -- --run` | Default sandbox | 1 | Vitest could not load config because Vite's `externalize-deps` plugin encountered `Error: spawn EPERM` in Windows realpath handling. No tests executed. |
| `npm test -- --run` | Authorized escalation after sandbox failure | 0 | 18 test files passed, 108 tests passed. Start 13:31:09 local; duration 14.53 seconds. |
| `npm run lint` | Default sandbox | 0 | 0 errors, 5 warnings. |
| `npm run build` | Default sandbox | 0 | Next.js 16.2.9 production build compiled, TypeScript passed, all 12 static pages generated. Compile 3.7s; TypeScript 6.4s. |
| `npx playwright test e2e/live-progress.spec.ts e2e/visual-brand.spec.ts --project=chromium --update-snapshots=none` | Default sandbox | 1 | `Error: spawn EPERM`; no test execution. |
| `npx playwright test e2e/live-progress.spec.ts e2e/visual-brand.spec.ts --project=chromium --update-snapshots=none` | Authorized escalation after sandbox failure | 1 | 24 passed, 2 failed in 1.5 minutes; 26 tests, 2 workers. |

Successful test output also contained two `Not implemented: navigation to another Document` messages from jsdom. These did not fail the suite and do not establish real browser navigation correctness.

Lint warnings:

- `scripts/rich-text-renderer.mjs:20:7`: unused `ROOT` variable.
- `scripts/rich-text-renderer.mjs:135:12`: unused `error` variable.
- `src/components/dashboard/SlideTab.tsx:341:11`, `478:17`, and `494:13`: Next.js `no-img-element` advice. The project's image-based slide invariant makes these warnings a performance review item, not proof of broken rendering.

## Coverage inspected

- `ArtifactJobRetry.test.tsx` mocks the API and covers failed reserved-version retry identity across Book, Slide, Quiz, and Video; empty first-generation failure/cancellation; and dismissing a Book retry before fresh work.
- `usePollingArtifact.test.tsx` covers discovery outages, forbidden responses, stale version responses, error sanitization, active-job identity, ready completion, and one-shot retry state.
- `JobProgress.test.tsx` covers queues, progress stages, retry schedules, capacity continuation, terminal polling, cancellation races, unmount aborts, and public error sanitization.
- `api.test.ts` covers network/XHR/JSON/auth error mapping and encoded paths; `VersionSwitcher.test.tsx` checks accessible version selection.
- `e2e/live-progress.spec.ts` uses route mocks, fixture authentication, synthetic artifact data, and a controlled clock. It covers all artifact tabs through long jobs/offline recovery and navigation races, but does not call real generation services.
- `e2e/visual-brand.spec.ts` contains fixture-based Book workspace, landing/courses, video progress/cancellation, and ingestion error/retry checks.

## Limits and gaps relevant to this review

The successful unit suite does not validate the generated handbook's factual accuracy, mathematical/code fidelity, major-topic coverage, export pagination, real slide images/PPTX/PDF parity, or quiz answer/explanation correctness. It does not establish cross-user server ownership or measured provider costs. Those require the separate real UI, generated-artifact, backend, and architecture evidence requested in the review.

Vitest explicitly excludes `e2e/**`. There are no dedicated Book content/export, slide image/export parity, or quiz scoring/answer-key correctness test files in the discovered frontend test inventory. Artifact tab coverage concentrates on retry and polling behavior using minimal mocked content. This is a coverage observation, not a claim that those product features are broken.

Playwright configuration currently has `reuseExistingServer: false` and starts another Next dev server with the same frontend build directory. Its output directory is `.next/playwright-test-results`. The parent stopped the real review frontend before these later checks. The real review browser session was not touched. No visual baselines were changed.

## Playwright failures and retained evidence

All eight `live-progress.spec.ts` tests passed, including all four artifact tabs' long-job recovery and stale-response navigation scenarios. Of the 18 `visual-brand.spec.ts` tests, 16 passed and two Book workspace snapshots failed:

- Desktop dark (`visual-brand.spec.ts:211:7`): expected 1440 by 1061, received 1440 by 1067; 30,987 pixels differ (reported ratio 0.03).
- Mobile light (`visual-brand.spec.ts:211:7`): expected 390 by 1322, received 390 by 1360; 22,069 pixels differ (reported ratio 0.05).

Both failed at `expectVisualSnapshot`, line 86, before the helper's following axe accessibility assertion. Therefore those two cases do not establish the absence of high-impact accessibility violations. A stable screenshot was captured in each case. The differences are confirmed; their cause and whether they represent intended design changes remain unverified. No repeated reproduction or baseline update was performed.

Sanitized error-only text and six PNG files (actual, expected, diff for each viewport) are retained under `dogfood-output/review-new-20260906/frontend-visual/`. Raw Playwright traces and page snapshots remain in ignored build artifacts and were not copied into review evidence, because they include fixture authenticated URLs.

The server log also emitted one `Internal Next.js error: Router action dispatched before initialization.` browser message and an LCP loading advisory for `/product/video-progress.png`. Neither became an additional failed test; the router diagnostic is an observed development-runtime issue whose relationship to customer behavior is unverified. Other output consisted of repeated Node `NO_COLOR`/`FORCE_COLOR` warnings.
