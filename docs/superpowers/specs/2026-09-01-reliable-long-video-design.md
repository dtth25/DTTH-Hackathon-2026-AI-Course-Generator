# Reliable Long-Video Generation Design

**Date:** 2026-09-01  
**Status:** Approved planning baseline  
**Depends on:** Runtime Capacity and Durable Jobs Design

## Problem

Long video generation is a serial, failure-sensitive pipeline. Each scene is synthesized and encoded in order, FFmpeg has no command timeout, failed attempts delete all scene work, and the final crossfade performs another full-video encode. A measured eight-scene fixture produced 416 seconds of video in 283.30 seconds before adding real LLM and network TTS latency. The browser stops waiting after eight minutes even if the backend is still working.

## User Outcome

- An accepted long video continues safely if the browser closes or the API restarts.
- Users see queue position, stage, scene progress, and a cancel action.
- A worker restart reuses valid completed scenes rather than beginning from scene one.
- One video cannot monopolize API threads or make health/read endpoints unresponsive.
- The default assembly removes the avoidable final whole-video crossfade encode.

## Pipeline

```text
queued
  -> generating_script
  -> preparing_scenes
  -> synthesizing_audio (scene checkpoints)
  -> rendering_scenes (scene checkpoints)
  -> assembling_video
  -> validating_output
  -> publishing_version
  -> ready
```

The worker owns a staging directory for the immutable `version_id`:

```text
{course_dir}/_work/vid/{version_id}/
  checkpoint.json
  script.json
  scenes/000/audio.mp3
  scenes/000/clip.mp4
  scenes/001/...
  assembled.mp4
```

`checkpoint.json` contains the normalized request hash, script hash, renderer version, voice, format, per-scene source hash, audio duration, file size, output probe metadata, and state. A checkpoint is reused only when all identifying hashes match and `ffprobe` validates the file. Atomic replacement writes the manifest after the artifact file is durable.

Failed and retried jobs retain valid staging data. Success publishes through the existing `AtomicArtifactDirectory`, then removes staging data. Cancellation removes the staging directory only after the worker stops its active child process. A daily recovery task removes terminal staging directories older than 24 hours.

## TTS

- Synthesize up to 3 independent scenes concurrently with an `asyncio.Semaphore(3)`.
- Apply a 60-second timeout per scene attempt.
- Retry transient Edge TTS failures at most 3 times with 1.5-second and 3-second backoff plus jitter.
- Do not retry invalid voice, empty narration, or cancellation.
- Write to a temporary filename, validate nonzero audio duration, then atomically rename.
- Record progress after each completed scene, throttled to one database write per 2 seconds.

## FFmpeg

- Every subprocess has an explicit timeout and captures a bounded stderr tail for diagnostics.
- Scene render timeout: 180 seconds. Assembly timeout: 600 seconds. Probe timeout: 30 seconds.
- Set `-threads` from `VIDEO_FFMPEG_THREADS`, default 2.
- On timeout or cancellation, terminate the whole subprocess tree and wait for exit before returning.
- Render scenes sequentially within one video job. Deployment concurrency provides parallel videos; per-video FFmpeg parallelism would oversubscribe the host.
- Give every scene its own short fade-in/fade-out during its single encode, then use concat stream copy for the default transition. Preserve the old xfade helper only as an explicit compatibility mode, not the production default.
- Validate final codec, dimensions, nonzero audio/video streams, and expected duration within 1 second before publish.

## Recovery and Idempotency

- The script is generated once per version and reused if its request hash matches.
- The worker checks durable cancellation before/after script generation, each TTS completion, each scene render, and assembly.
- A redelivery for a ready version returns without rendering.
- A redelivery for a partial version resumes at the first invalid or incomplete checkpoint.
- A changed renderer version or input hash invalidates only affected scene clips; a changed narration invalidates its audio and clip.
- User-visible errors use stable codes such as `tts_timeout`, `ffmpeg_timeout`, `invalid_video_output`, `video_cancelled`, and `video_worker_lost`.

## Frontend

The browser does not own the job timeout. `usePollingArtifact` continues until the backend reports a terminal state or the component unmounts. It polls active work every 3 seconds and queued work every 10 seconds, with a 30-second request timeout. The video panel displays:

- `Waiting — position N`
- current stage label
- `Scene X of Y`
- percentage
- retry attempt when greater than one
- cancel button while the backend says `can_cancel`

The page disables generation unless the course is `ready`. A failed document-processing course shows the server's sanitized failure and a retry-upload action instead of enabling video generation.

## Performance Gate

On the same reference machine and fixture used for the 283.30-second baseline:

- Wall time must improve by at least 25% without reducing 720p/30fps output quality.
- Final duration must match the sum of scene durations within 1 second.
- No intermediate full-video re-encode occurs in the default path.
- Killing the video worker after scene 4 and restarting it must reuse scenes 1-4.
- With 6 videos accepted and 3 workers, the second batch begins within 10 minutes at p95 on the reference machine.
- While three videos render, the 100-user authenticated API test continues to meet the runtime p95 and error-rate gate.

## Out of Scope

- GPU encoding requirements.
- Distributed object storage.
- Changing the video generation endpoint or adding a fifth generation type.
- External stock media or web-derived information.
