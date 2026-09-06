# Reliable Long-Video Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long videos resumable, bounded, cancellable, and materially faster while keeping output quality and the existing Vid endpoint.

**Architecture:** Run video only in the durable `video` worker queue. Persist a hash-validated checkpoint per immutable version, synthesize independent audio concurrently, render scenes with bounded FFmpeg processes, stream-copy the final concatenation, validate output, then publish atomically.

**Tech Stack:** Python 3.11+, Celery 5.6, SQLAlchemy, edge-tts, Pillow, FFmpeg/imageio-ffmpeg, Pydantic 2, Next.js 16, React 19, pytest, Vitest

**Spec:** [Reliable Long-Video Generation Design](../specs/2026-09-01-reliable-long-video-design.md)

## Global Constraints

- Complete the runtime/durable-jobs plan through its worker and API tasks first.
- Keep `POST /generate/vid` as the only Vid generation endpoint.
- Do not introduce external media, web knowledge, frontend provider calls, placeholder clips, or silent success.
- Production video workers run in Linux containers. Validate process-tree cancellation there.
- Default output remains 720p/30fps for standard/overview and the current vertical Shorts dimensions.
- Do not commit unless the Lead explicitly authorizes it; commit commands below are checkpoints only.
- Before Task 6, complete Tasks 1-4 of [Distinctive Product Appearance and Brand Voice](2026-09-01-distinctive-product-appearance-and-brand-voice.md). Video queue/progress UI must inherit that plan's editorial tokens and evidence-qualified copy, with no neon/glow treatment or unsupported speed claim. After Task 6, regenerate `video-progress.png` and rerun the brand/visual gates when those commands exist.

## File Structure

### Create

- `src/backend/app/services/video_checkpoint.py` — checkpoint schema, hashes, atomic manifest, resume/cleanup.
- `src/backend/app/services/subprocess_runner.py` — bounded FFmpeg execution and process-tree termination.
- `src/backend/tests/test_video_checkpoint.py`
- `src/backend/tests/test_subprocess_runner.py`
- `src/backend/tests/fixtures/video_long_script.json` — deterministic eight-scene offline script.
- `src/backend/tests/performance/test_video_benchmark.py` — opt-in reference benchmark.

### Modify

- `src/backend/app/core/config.py` — TTS/FFmpeg/concurrency/retention settings.
- `src/backend/app/services/video_render.py` — concurrent TTS, checkpointed scene render, stream-copy assembly, validation.
- `src/backend/app/services/generator.py` — durable video staging/publish and job stages.
- `src/backend/app/workers/tasks.py` — cancellation and recovery integration.
- `src/backend/tests/test_pdf_book_and_video_concat.py` — new assembly behavior and duration assertions.
- `src/backend/tests/test_generation_service.py` — resume and terminal outcome behavior.
- `src/frontend/src/components/dashboard/VidTab.tsx`
- `src/frontend/src/components/dashboard/VidOptionsPanel.tsx`
- `src/frontend/src/hooks/usePollingArtifact.ts`
- `src/frontend/src/lib/types.ts`
- `README.md` — worker sizing and recovery operations.

---

## Task 1: Define a versioned, atomic checkpoint contract

**Files:**

- Create: `src/backend/app/services/video_checkpoint.py`
- Create: `src/backend/tests/test_video_checkpoint.py`

- [ ] Write failing tests for new manifest creation, atomic save, hash match, changed narration invalidation, changed renderer invalidation, corrupt/missing file invalidation, successful resume, and terminal cleanup.

```python
def test_changed_narration_invalidates_only_affected_scene(tmp_path, valid_checkpoint) -> None:
    valid_checkpoint.scenes[1].narration_hash = sha256_text("changed")
    resumed = VideoCheckpoint.load(tmp_path, request=original_request_with_changed_scene_2)
    assert resumed.scenes[0].clip_ready is True
    assert resumed.scenes[1].audio_ready is False
    assert resumed.scenes[1].clip_ready is False
```

- [ ] Implement strict Pydantic models. Never trust a JSON manifest without validating schema and ensuring every resolved child path stays under the version work directory:

```python
class SceneCheckpoint(BaseModel):
    scene_number: int = Field(ge=1)
    narration_hash: str
    visual_hash: str
    audio_ready: bool = False
    clip_ready: bool = False
    audio_duration: float | None = Field(default=None, gt=0)
    audio_size: int | None = Field(default=None, gt=0)
    clip_size: int | None = Field(default=None, gt=0)


class VideoCheckpointData(BaseModel):
    schema_version: Literal[1] = 1
    renderer_version: str
    request_hash: str
    script_hash: str
    scenes: list[SceneCheckpoint]
```

- [ ] Use canonical JSON plus SHA-256 for request/script/scene hashes. Include format, voice, dimensions, frame rate, renderer version, narration, and normalized visual data in the relevant hash.
- [ ] Write manifests as `checkpoint.json.tmp`, flush and `os.fsync`, then `os.replace`. Do the same temporary-write/replace sequence for generated audio and clips.
- [ ] Validate a claimed audio/clip with bounded media probing before reuse; size alone is insufficient.
- [ ] Provide `mark_audio_ready`, `mark_clip_ready`, `invalidate_scene`, `completed_scene_count`, and `cleanup_terminal(older_than)` methods. Do not remove a live work directory.
- [ ] Run `uv run pytest tests/test_video_checkpoint.py -q` and `uv run ruff check app/services/video_checkpoint.py tests/test_video_checkpoint.py`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/video_checkpoint.py src/backend/tests/test_video_checkpoint.py; git commit -m "feat: add resumable video checkpoints"`.

## Task 2: Bound and cancel every media subprocess

**Files:**

- Create: `src/backend/app/services/subprocess_runner.py`
- Create: `src/backend/tests/test_subprocess_runner.py`
- Modify: `src/backend/app/core/config.py`
- Modify: `src/backend/app/services/video_render.py`

- [ ] Write cross-platform unit tests using the current Python executable as the child process. Cover success, nonzero exit with only the last 2,000 stderr characters, timeout, cancellation, and no orphaned grandchild on the Linux test path.

```python
def test_timeout_terminates_child(tmp_path) -> None:
    with pytest.raises(MediaProcessTimeout) as exc:
        run_media_process([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.1)
    assert exc.value.code == "ffmpeg_timeout"
```

- [ ] Add validated settings:

```python
VIDEO_FFMPEG_THREADS: int = Field(default=2, ge=1, le=8)
VIDEO_FFMPEG_SCENE_TIMEOUT_SECONDS: int = Field(default=180, ge=30)
VIDEO_FFMPEG_ASSEMBLY_TIMEOUT_SECONDS: int = Field(default=600, ge=60)
VIDEO_MEDIA_PROBE_TIMEOUT_SECONDS: int = Field(default=30, ge=5)
VIDEO_TTS_TIMEOUT_SECONDS: int = Field(default=60, ge=10)
VIDEO_TTS_CONCURRENCY: int = Field(default=3, ge=1, le=8)
VIDEO_WORK_RETENTION_HOURS: int = Field(default=24, ge=1)
```

- [ ] Implement `run_media_process(command, *, timeout, cancellation_check, error_code)`. Start a new process group/session, poll cancellation, use `communicate` without unbounded output, and terminate then kill the process tree after a grace period.
- [ ] Return a typed result on exit zero. Raise sanitized `MediaProcessFailed`, `MediaProcessTimeout`, or `MediaProcessCancelled`; log the command executable and bounded stderr, never secrets or complete narration.
- [ ] Replace both raw `subprocess.run` calls in `_run_ffmpeg` and `_probe_duration`. Pass scene, assembly, and probe timeouts explicitly rather than choosing by command-string inspection.
- [ ] Add `-threads str(settings.VIDEO_FFMPEG_THREADS)` to all libx264 commands.
- [ ] Run `uv run pytest tests/test_subprocess_runner.py tests/test_pdf_book_and_video_concat.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/core/config.py src/backend/app/services/subprocess_runner.py src/backend/app/services/video_render.py src/backend/tests; git commit -m "fix: bound video media processes"`.

## Task 3: Synthesize scene audio concurrently and safely

**Files:**

- Modify: `src/backend/app/services/video_render.py`
- Modify: `src/backend/tests/test_pdf_book_and_video_concat.py`

- [ ] Add failing async tests with a fake edge-tts stream for concurrency capped at 3, per-attempt timeout, two backoffs then success, invalid voice without retry, cancellation, temp-file cleanup, and checkpoint reuse.

```python
@pytest.mark.asyncio
async def test_tts_concurrency_is_bounded(fake_tts, tmp_path) -> None:
    await synthesize_scene_audio(scenes(8), tmp_path, semaphore_size=3)
    assert fake_tts.max_active == 3
```

- [ ] Extract an async `synthesize_one_scene` that wraps the edge-tts stream with `asyncio.timeout(settings.VIDEO_TTS_TIMEOUT_SECONDS)`, writes a `.part` file, validates duration, replaces the target, then saves its checkpoint.
- [ ] Implement an async batch using `asyncio.TaskGroup` and `Semaphore`. On cancellation or a nonretryable failure, cancel siblings and await them before returning; never leave file handles or `.part` files.
- [ ] Retry only declared transient network/handshake/timeouts. Back off 1.5 then 3 seconds plus bounded jitter. Convert invalid voice, empty narration, and cancellation into stable terminal codes.
- [ ] Keep the existing offline pytest silence path, but route it through the same validation/checkpoint contract. Tests must never call the network.
- [ ] Replace `asyncio.run` per scene with one event-loop entry per video. The worker is synchronous, so expose a single synchronous wrapper that calls the async batch once.
- [ ] Run `uv run pytest tests/test_pdf_book_and_video_concat.py -k "tts or narration" -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/video_render.py src/backend/tests/test_pdf_book_and_video_concat.py; git commit -m "perf: synthesize video scenes concurrently"`.

## Task 4: Resume scene rendering and remove the default whole-video re-encode

**Files:**

- Modify: `src/backend/app/services/video_render.py`
- Modify: `src/backend/app/services/video_checkpoint.py`
- Modify: `src/backend/tests/test_pdf_book_and_video_concat.py`
- Create: `src/backend/tests/fixtures/video_long_script.json`

- [ ] Add failing tests proving completed audio/clip reuse, resume after scene four, fade filters inside each scene encode, default concat stream copy, xfade only when explicitly selected, final validation, and no work-directory deletion after failure.

```python
def test_default_assembly_uses_stream_copy(monkeypatch, checkpointed_scenes) -> None:
    commands = capture_media_commands(monkeypatch)
    assemble_checkpointed_video(checkpointed_scenes, transition="fade-cut")
    final = commands[-1]
    assert ["-c", "copy"] == final[final.index("-c"):final.index("-c") + 2]
    assert "xfade" not in " ".join(final)
```

- [ ] Change `build_scene_clip` to include subtle video fade-in/fade-out during its existing encode. Keep audio complete; do not trim narration tails.
- [ ] Make `concat_clips` strict in production: stream-copy identical clips and raise `invalid_scene_encoding` instead of silently hiding an invariant violation with a second full encode. Unit-test the compatibility fallback separately if retained.
- [ ] Add `transition="fade-cut" | "xfade"` to the internal renderer only. Default to `fade-cut`; retain `concat_clips_xfade` for old-output comparisons, never as the default call.
- [ ] Replace `_vid_scenes` with `{course}/_work/vid/{version_id}` supplied by the caller. Before each TTS/render, validate the checkpoint; after each successful artifact, atomically update it.
- [ ] Add final validation: file exists/nonzero, expected dimensions and frame rate, audio and video streams present, playable duration within 1 second of summed scene durations.
- [ ] Remove unconditional `shutil.rmtree` from `assemble_video`. Cleanup only after atomic publication or cooperative cancellation as defined by the spec.
- [ ] Run the full offline renderer tests: `uv run pytest tests/test_pdf_book_and_video_concat.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services/video_render.py src/backend/app/services/video_checkpoint.py src/backend/tests; git commit -m "perf: checkpoint and stream-copy long videos"`.

## Task 5: Integrate job stages, cancellation, atomic publish, and cleanup

**Files:**

- Modify: `src/backend/app/services/generator.py`
- Modify: `src/backend/app/workers/tasks.py`
- Modify: `src/backend/app/services/job_service.py`
- Modify: `src/backend/tests/test_generation_service.py`
- Modify: `src/backend/tests/test_worker_tasks.py`

- [ ] Add failing service/worker tests for exact stages, scene progress, cancellation before each costly stage, worker retry using checkpoints, duplicate delivery of ready output, validation failure without publish, and success cleanup.

```python
def test_retry_resumes_existing_video_work(worker, checkpoint_after_scene_four, renderer) -> None:
    worker.run_video(checkpoint_after_scene_four.job_id)
    assert renderer.rendered_scene_numbers == [5, 6, 7, 8]
    assert checkpoint_after_scene_four.job.state == "succeeded"
```

- [ ] Have `GeneratorService.generate_vid` allocate its work directory from `(course_id, version_id)`, not a mutable current-version path. Generate and checkpoint `script.json` before media work.
- [ ] Emit stable stages: `generating_script`, `preparing_scenes`, `synthesizing_audio`, `rendering_scene`, `assembling_video`, `validating_output`, `publishing_version`. Include `current_scene` and `total_scenes` in owner-safe job metadata, not arbitrary JSON from the model.
- [ ] Check `JobReporter.raise_if_cancelled()` before/after the LLM call, TTS batch, each scene render, assembly, and publish. Pass cancellation checks into media subprocess execution.
- [ ] Publish `vid.json` and `vid.mp4` through `AtomicArtifactDirectory` only after final validation. Mark the job succeeded only after the atomic directory swap and database version metadata commit.
- [ ] On cancellation, stop child processes, mark cancelled, then remove work. On retryable failure retain work. On final failure retain work for 24 hours and schedule the terminal cleanup task.
- [ ] Make a daily Celery maintenance task remove only work directories whose database job is terminal and older than the configured retention. Resolve and verify every path under the course `_work/vid` root before deletion.
- [ ] Run `uv run pytest tests/test_generation_service.py tests/test_worker_tasks.py tests/test_pdf_book_and_video_concat.py -q`.
- [ ] Commit checkpoint if authorized: `git add src/backend/app/services src/backend/app/workers src/backend/tests; git commit -m "feat: resume and cancel long video jobs"`.

## Task 6: Replace browser timeout with backend-owned video lifecycle UI

**Files:**

- Modify: `src/frontend/src/components/dashboard/VidTab.tsx`
- Modify: `src/frontend/src/components/dashboard/VidOptionsPanel.tsx`
- Modify: `src/frontend/src/hooks/usePollingArtifact.ts`
- Modify: `src/frontend/src/hooks/usePollingArtifact.test.tsx`
- Modify: `src/frontend/src/lib/types.ts`
- Test: existing dashboard component test location or create `src/frontend/src/components/dashboard/VidTab.test.tsx`

- [ ] Read `src/frontend/AGENTS.md` and installed Next.js 16 documentation it names.
- [ ] Add failing UI tests for queue position, all stable stage labels, scene X/Y, attempt 2, cancel pending, cancelled terminal state, failed ingestion disables generation, and continued polling beyond eight minutes.
- [ ] Consume the shared `JobProgress` contract from the runtime plan. Map stable codes/stages to Vietnamese user labels locally; never render a raw exception string.
- [ ] Remove the eight-minute overall Vid timeout. Use per-request abort and backend terminal state as specified in the runtime plan.
- [ ] Disable Vid generation unless the course is `ready`. On ingestion/source failure, show the course failure with an upload-again action.
- [ ] Keep all current player/download/version behavior for ready versions.
- [ ] Run `npm test -- --run`, `npm run lint`, and `npm run build` from `src/frontend`.
- [ ] Commit checkpoint if authorized: `git add src/frontend/src; git commit -m "feat: show resumable video generation progress"`.

## Task 7: Prove recovery, speed, and isolation on the reference deployment

**Files:**

- Create: `src/backend/tests/performance/test_video_benchmark.py`
- Modify: `src/backend/tests/load/README.md`
- Modify: `README.md`

- [ ] Implement an opt-in benchmark marked `performance` that loads the fixed eight-scene JSON, uses deterministic silence audio, records wall time/output duration/file probe data, and writes a JSON result. Normal pytest must skip it.
- [ ] Add an assertion helper for the agreed same-host gate: `wall_seconds <= 283.30 * 0.75`, duration error <=1 second, 1280x720, 30fps, and audio/video streams present.
- [ ] Run the benchmark three times after a warmup. Record median and worst run; the gate uses the median, but report both.
- [ ] Start six Vid jobs with video concurrency 3. Capture queued/start/finish timestamps and assert jobs 4-6 start within 10 minutes at p95.
- [ ] Kill `worker-video` after scene four, restart it, and verify logs/checkpoint show scenes 1-4 reused. Repeat with cooperative cancellation and verify no child FFmpeg remains.
- [ ] While three jobs render, run the runtime plan's 100-user authenticated profile and verify API p95 <500 ms and failure rate <1%.
- [ ] Document CPU, memory, disk, Docker resource limits, FFmpeg path/version, fixture hash, and exact commands beside results.
- [ ] Run final regression:

```powershell
cd src/backend
uv run ruff check app tests
uv run pytest -q
uv run pytest -m performance tests/performance/test_video_benchmark.py -q
cd ..\frontend
npm test -- --run
npm run lint
npm run build
```

- [ ] Commit checkpoint if authorized: `git add README.md src/backend/tests/performance src/backend/tests/load/README.md; git commit -m "test: prove long video reliability and performance"`.

## Final Verification

- [ ] Search `src/backend/app/services/video_render.py` for raw `subprocess.run`, unconditional work cleanup, and default `concat_clips_xfade`; none may remain.
- [ ] Search for `_vid_scenes`; only migration/compatibility comments may remain.
- [ ] Inspect one cancelled, one recovered, and one successful database job and filesystem work directory against the retention contract.
- [ ] Play all three output formats and inspect audio tails, scene transitions, text layout, dimensions, and downloads.
- [ ] Review the diff for command injection, path traversal, unbounded stderr, unbounded child lifetime, raw narration logging, and API-thread media work.
