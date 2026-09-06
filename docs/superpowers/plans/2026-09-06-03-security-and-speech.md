# Sessions, Provider Privacy and Azure Speech Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce shared-server access/privacy controls and deliver working Vietnamese narration through Azure speech.

**Architecture:** Replace in-memory revocation and browser-stored credentials with durable sessions and restricted download capabilities. Check policy before every external document-processing call, adapt Azure real-time speech to the local renderer, and make deletion durable and retryable.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PyJWT, Redis, Next.js/React, Azure Speech Python SDK and existing local renderers.

**Spec:** `docs/superpowers/specs/2026-09-06-reliability-and-trust-design.md` (approved).

## Global Constraints

- Planning phase: do not modify product code, execute the implementation plan, commit or push.
- Future execution: preserve pre-existing work; never reset or bulk-stage the dirty worktree.
- Four generation endpoints remain `/api/generate-book`, `/api/generate-slide`, `/api/generate-quiz`, `/api/generate-vid`.
- No independent chat or fifth generation endpoint. Quote, source-health, repair and download-ticket endpoints are support operations.
- Backend-only AI. OpenRouter remains the content/OCR/embedding gateway. Azure real-time Speech is the explicit approved speech exception.
- Next.js 16.2.9 / React 19 / Tailwind 4, FastAPI, SQLAlchemy/Alembic, existing Chroma interfaces. Read installed Next.js documentation before changing its integration.
- SQLite/local inline execution and PostgreSQL 16 / Redis / Celery / private Chroma HTTP must both work.
- Poll processing resources every 3–5 seconds; stop at terminal states. Do not require a reload.
- Preserve three-version limits, readable completed versions, rename/delete controls and Expand/Collapse.
- Slides use the same rendered images in browser, PDF and PPTX.
- Public responses expose clean file labels, page/block locations and excerpts; never raw storage paths, chunk IDs, provider responses, prompts, secrets or debug traces.
- Reuse layout, elevation, motion and stage tokens from `CLAUDE.md`; the intentionally dark slide stage remains dark.
- Source documents, OCR, model output and generated code are untrusted data. Never execute embedded instructions or source/generated code during ordinary generation.
- Future task checkpoints update `progress_new.md`, run the task's relevant checks, and record actual outcomes. If the approved design is wrong, stop and report the mismatch instead of silently redesigning.

Dependencies: Plan01 identities/operations and Plan02 source bindings. Auth can be implemented independently; privacy must precede live extraction/generation/speech. Backend paths and commands below are relative to `src/backend`; frontend paths/commands to `src/frontend`. Every task records actual tests and evidence in progress_new.md. Commit suggestions require Lead authorization. No ordinary test receives live credentials or network access.

## Task P1: Persist and revoke sessions across workers

**Goal:** Persist and revoke sessions across workers.

**Files:** Create backend `app/models/auth_session.py`, `app/services/auth_sessions.py`, `alembic/versions/a6b7c8d9e0f1_durable_auth_sessions.py`, `tests/test_durable_sessions.py`. Modify `app/models/user.py`, `app/models/__init__.py`, `app/core/security.py`, `app/core/deps.py`, `app/routers/auth.py`, `app/schemas/user.py`.

**Interfaces:** `issue_session(db,user,now)->tuple[str,str]` returns JWT/sid; `validate_session(db,payload,now)->User`; `revoke_session(db,sid,now)->None`; `revoke_all_sessions(db,user_id)->None`. Consumes existing hashing, User and JWT settings. Produces durable authentication for every later task.

- [ ] Write red tests using two clients/session factories sharing a file DB: logout invalid across workers/restart; password reset invalidates all sessions; old sid-less JWT denied; wrong audience/issuer/purpose denied; inactive user denied. Use the real register/verify/reset routes with fake OTP delivery and explicit allowed Origin/marker.

```python
def test_reset_revokes_every_session(session_case):
    first, second = session_case.issue(), session_case.issue()
    session_case.reset_password('new-secret-123')
    assert session_case.get_me(first).status_code == 401
    assert session_case.get_me(second).status_code == 401
    assert session_case.login('new-secret-123').status_code == 200
```

Define session_case in this test file with issue() calling the API-client login, reset_password() using actual forgot/reset routes, get_me(token) using bearer and a fresh cookie-free client, login(password) using existing synthetic user. Share a temporary file DB; no direct epoch mutation in the main integration test.

- [ ] Run `uv run --project . --extra dev python -m pytest tests/test_durable_sessions.py -q` and record red. Add the following ORM plus User.auth_epoch Integer NOT NULL server_default0:

```python
class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    auth_epoch = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime)

def issue_session(db, user, now):
    sid = str(uuid4())
    expires = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    db.add(AuthSession(id=sid, user_id=user.id, auth_epoch=user.auth_epoch,
                       created_at=now, expires_at=expires))
    payload = {'sub':user.id, 'sid':sid, 'auth_epoch':user.auth_epoch,
       'purpose':'session', 'iss':'hackagen', 'aud':'hackagen-api',
       'iat':int(now.replace(tzinfo=timezone.utc).timestamp()),
       'exp':int(expires.replace(tzinfo=timezone.utc).timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm='HS256'), sid
```

Migration a6b7c8d9e0f1 follows a5b6c7d8e9f0: batch-add epoch then create sessions; downgrade sessions then epoch. Import SQLAlchemy Column/String/Integer/DateTime/ForeignKey and existing Base; service imports uuid4, datetime/timedelta/timezone, jwt and settings. Keep UTC-naive DB times consistent with existing tables; numeric JWT dates use UTC.

Validate HS256, exact issuer/audience, required claims, purpose=session, active matching user, live session, no revoked_at, expiry and equal user/session/token epoch. Remove memory blacklist as an authority; never store raw JWT. Logout revokes the same selected credential's sid, commits before clearing cookie, and cannot report success when DB revocation fails. Reset atomically changes hash and increments epoch. Login preserves connection release during bcrypt, then re-reads hash/epoch/active/verified state under short transaction before issuance; a concurrent reset invalidates the login snapshot.

- [ ] Add barrier-driven reset/login race, per-session logout leaving another session valid, and cache-cleared restart tests. Run new tests and `tests/test_auth_and_core.py`; expected all pass. Browser covered P2. Acceptance: revocation survives worker/cache/restart and bcrypt does not pin connections. Commit suggestion: `fix: persist authentication session revocation`.

## Task P2: Cookie-based browser auth and request-origin protection

**Goal:** Cookie-based browser auth and request-origin protection.

**Files:** Modify backend `app/core/deps.py`, `main.py`, `app/core/config.py`, `app/routers/auth.py`; create `tests/test_cookie_request_security.py`. Modify frontend `src/lib/auth.ts`, `src/lib/api.ts`, auth pages, AuthGuard/RedirectIfAuthed and login tests; create `src/lib/auth.test.ts`.

**Interfaces:** `require_request_origin(request, *, cookie_authenticated: bool)->None`; frontend `clearLegacyBrowserToken():void`, `clearStoredAuth():void`. Consumes P1. Auth bootstrap has loading/authenticated/unauthenticated states from `/api/auth/me`.

- [ ] Test cross-origin/missing-marker cookie mutations denied, exact allowed local Origin succeeds, no-Origin bearer client succeeds, login unapproved supplied Origin denied and wildcard credential CORS rejected. Run cookie tests red, then implement:

```python
def require_request_origin(request, *, cookie_authenticated):
    if request.method in {'GET','HEAD','OPTIONS'}:
        return
    origin = request.headers.get('origin')
    marker = request.headers.get('x-agy-request')
    if cookie_authenticated and origin not in settings.ALLOWED_ORIGINS:
        raise HTTPException(403, detail={'code':'ORIGIN_REJECTED'})
    if origin is not None and origin not in settings.ALLOWED_ORIGINS:
        raise HTTPException(403, detail={'code':'ORIGIN_REJECTED'})
    if cookie_authenticated and marker != '1':
        raise HTTPException(403, detail={'code':'ORIGIN_REJECTED'})
```

Auth entry routes require marker1 even before authentication and reject supplied unapproved Origin; missing Origin is allowed for explicit header-based CLI clients. Exact CORS origins/credentials/headers only; no suffix/referrer fallback. Production requires secure cookies/HTTPS; loopback development keeps cross-port cookie fetch. Protect admin unsafe routes too.

- [ ] Change frontend fetch to credentials include, add mutation marker, remove bearer-storage helpers/calls, clear old `agy_auth_token` on startup:

```ts
const headers = new Headers(init.headers);
if (!['GET','HEAD','OPTIONS'].includes((init.method ?? 'GET').toUpperCase())) headers.set('X-AGY-Request','1');
const response = await fetch(url, {...init, headers, credentials:'include'});

export function clearLegacyBrowserToken(): void {
  if (typeof window !== 'undefined') localStorage.removeItem('agy_auth_token');
}
```

AuthGuard waits for `/me`, does not use localStorage as proof and clears on401/logout. Browser login/verification rely on Set-Cookie and read user. API-client bearer issuance requires explicit `X-AGY-Client: api`; default browser TokenResponse.access_token is omitted/optional. Update auth tests/client helpers to request API mode only where testing bearer behavior. Do not add a refresh subsystem.

```ts
it('removes legacy token persistence', () => {
  localStorage.setItem('agy_auth_token','legacy-example');
  clearLegacyBrowserToken();
  expect(localStorage.getItem('agy_auth_token')).toBeNull();
});
```

- [ ] Run backend cookie/auth tests and frontend auth/API/login tests, lint/build. Browser: register/verify/login/reload/logout/reset/two tabs/local ports/HTTPS. Acceptance: no persistent browser bearer, no auth redirect loop, cookie mutations protected. Commit suggestion: `feat: use protected cookie authentication in the browser`.

## Task P3: Artifact-specific short-lived download capabilities

**Goal:** Artifact-specific short-lived download capabilities.

**Files:** Create backend `app/services/download_tickets.py`, `app/schemas/download_ticket.py`, `tests/test_download_tickets.py`; modify `app/routers/generation.py`, `app/core/deps.py`, `main.py`. Create frontend `src/hooks/useArtifactUrl.ts` and test; modify API download helpers and Book/Slide/Quiz/Vid readers. Update CLAUDE.md and README's approved download-contract migration.

**Interfaces:** `issue_download_ticket(db,user,session_id,selector,now)->TicketResponse`; `validate_download_ticket(db,token,selector,now,cookie_user_id=None)->User`; `authorize_artifact_download` route dependency. Selector: course_id, artifact, version_id, asset enum(book_pdf,slide_pdf,slide_pptx,slide_image,quiz_key,video_mp4), image_index only for slide_image. TicketResponse has url/expires_at. Frontend `useArtifactUrl(selector)` returns url/loading/error/refresh.

Use zero-based image_index in the new selector and convert exactly once to the existing one-based `/slide-images/{slide_num}` route and `slide_{slide_num}.png` file. Validate index against the actual rendered image array length. Include this conversion in tamper/off-by-one tests; do not change existing file numbering.

- [ ] Red tests: full-session query token denied, ticket cannot access other API/course/version/index, tampered/expired/revoked denied, other-user cookie mismatch denied, valid MP4 Range supported. Run `uv run --project . --extra dev python -m pytest tests/test_download_tickets.py -q`.
- [ ] Implement a separate-purpose signed capability:

```python
def encode_ticket(selector, sid, user, now):
    expires = now + timedelta(seconds=120)
    payload = {**selector.model_dump(mode='json'), 'sub':user.id, 'sid':sid,
       'auth_epoch':user.auth_epoch, 'purpose':'artifact-download',
       'iss':'hackagen', 'aud':'hackagen-download',
       'iat':int(now.replace(tzinfo=timezone.utc).timestamp()),
       'exp':int(expires.replace(tzinfo=timezone.utc).timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm='HS256')
```

POST `/api/courses/{course_id}/download-tickets` owner-checks exact ready artifact/version/asset, maps to fixed existing route, returns a server-constructed encoded URL. Never accept host/path from client. Download validation checks purpose/audience/issuer, exact route-derived selector, live session/epoch/user, current course/version and safe resolved file root. Optional cookie must be same user. Header/cookie auth remains accepted for explicit file clients; general get_current_user stops reading query tokens entirely. Scoped capability query name remains token, but cannot authenticate any general API.

Tickets allow repeated requests within120s for Range. Slide viewer fetches visible/next-image tickets. Hook refreshes15s before expiry while active, aborts stale selection responses; Video saves currentTime/paused, replaces src and restores after loadedmetadata. On expired URL retry refresh once; revoked session requires sign-in. Every download click obtains a fresh ticket. Keep actual FileResponse Range support.

- [ ] Add timer tests for refresh, stale wrong-version responses, playback position and terminal session failure. Set private/no-store on metadata/tickets/files and no-referrer on readers. Test app/proxy logs omit full query strings/Authorization/Cookie. Run backend ticket/auth plus frontend hook/viewer/API tests.
- [ ] Browser: PDFs/PPTX/MP4/images, seek after2min, logout while playing, old-version download after sign-in. Acceptance: links have exact scope and no general auth power. Commit suggestion: `feat: restrict download URLs to artifact capabilities`.

## Task P4: Gate every external path on verified policy

**Goal:** Gate every external path on verified policy.

**Files:** Create backend `app/services/external_policy.py`, `tests/test_external_policy.py`, `scripts/verify_external_policy.py`; modify provider_health.py, llm.py, provider_usage.py, provider_tokens.py, document_processor.py, config.py, `.env.example`, README.

**Interfaces:** `authorize_external_processing(kind,model,*,now)->ProviderAuthorization`; `merge_provider_controls(request,authorization)->dict`. ProviderAuthorization is frozen: policy_id, service, endpoint_slugs tuple, checked_at/expires_at, allowed_models tuple. Consumes existing provider-health metadata and R3 price/capability controls.

- [ ] Test every kind(title,source_plan,ocr,embedding,book,slides,quiz,video_script,speech): missing/stale/false evidence sends zero document bytes; endpoint capability mismatch zero calls; adding price cannot overwrite privacy; no relaxed fallback. Run tests red.
- [ ] Add private evidence schema: policy_id, service(openrouter/azure-speech), exact endpoints/region, allowed kinds, reviewed_at/expires_at(max30days), no_training/no_content_retention, primary URLs, account logging settings digest, reviewer and evidence-file SHA256. Path comes only from administrator config `EXTERNAL_POLICY_EVIDENCE_PATH`; student data cannot select it. A boolean alone cannot constitute verification.

```python
def merge_provider_controls(request, authorization):
    result = deepcopy(request)
    provider = result.setdefault('extra_body',{}).setdefault('provider',{})
    provider.update(data_collection='deny', zdr=True, require_parameters=True)
    requested = set(provider.get('only', authorization.endpoint_slugs))
    allowed = requested & set(authorization.endpoint_slugs)
    if not allowed:
        raise ProviderPolicyUnavailable('No eligible endpoint')
    provider['only'] = sorted(allowed)
    provider['allow_fallbacks'] = False
    return result
```

Normalize slugs against metadata/evidence; apply merge after all request construction and before actual dispatch; preserve price/reasoning/schema controls. Metadata TTL30s; stale/failing metadata never authorizes transfer. Embedding's OpenAI-only path gets the same checks. PolicyUnavailable maps to R5 safe error.

Verifier reads evidence/digests/dates and metadata-only endpoint/voice capabilities; emits safe pass/fail codes and evidence digest, never raw key/account response. Operators must save applicable primary terms and actual account logging review. Azure no-training evidence must apply to real-time prebuilt speech; unrelated custom-voice/OpenAI wording is insufficient. No account-setting mutation or document/speech payload by verifier.

- [ ] Capture the final mocked HTTP body for embeddings/OCR/title/all artifacts and assert controls actually serialized. Run external-policy/health/usage/LLM parsing tests. Browser safe setup error before charges. Acceptance: all external paths covered, no privacy-relaxing fallback. Commit suggestion: `feat: enforce verified external processing policies`.

## Task P5: Azure real-time narration with same-version recovery

**Goal:** Azure real-time narration with same-version recovery.

**Files:** Create backend `app/services/speech.py`, `app/services/video_checkpoint.py`, `app/models/speech_usage.py`, `alembic/versions/a7b8c9d0e1f2_speech_usage.py`, `tests/test_azure_speech.py`, `tests/test_video_checkpoint.py`; modify video_render.py, generator.py, config.py, models/__init__.py, pyproject.toml, uv.lock, Dockerfile and `.env.example`.

**Consumes:** P4 authorization, existing assemble_video/timing dictionaries, R5 logical operations. **Produces:**

```python
@dataclass(frozen=True)
class SpeechCue:
    start: float
    duration: float
    text: str

@dataclass(frozen=True)
class SpeechResult:
    audio_path: str
    cues: tuple[SpeechCue, ...]
    characters: int
    estimated_cost_usd: Decimal | None

class SpeechProvider(Protocol):
    def preflight(self) -> None: ...
    def synthesize(self, text: str, voice: str, output_path: Path,
                   rate: str = '+0%') -> SpeechResult: ...
```

Protocol method ellipses are valid typing definitions. Concrete class: `AzureRealtimeSpeech`, SDK factory injectable. Lazy production import `azure.cognitiveservices.speech`. Pin `azure-cognitiveservices-speech==1.51.2`; [the Microsoft-maintained package release](https://pypi.org/project/azure-cognitiveservices-speech/1.51.2/) lists Python3 Windows AMD64 and Linux x86-64 wheels (verified 2026-09-06). Run `uv add --project . azure-cognitiveservices-speech==1.51.2` during execution and retain the exact lock. Verify actual Windows Python3.13 and Linux container imports; a failure is a reported platform mismatch, not permission to change Python. Remove edge-tts only after no real code path imports it. Do not upgrade unrelated dependencies.

- [ ] Red tests with SDK fake: voice mapping; word-boundary ticks; atomic output; cancellation cleanup; permanent failure no retry; transient failure at most one retry; voice/text mismatch invalidates checkpoint; no Edge import/fallback. Run `uv run --project . --extra dev python -m pytest tests/test_azure_speech.py tests/test_video_checkpoint.py -q`.
- [ ] Configure secret `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, optional Decimal `AZURE_SPEECH_PRICE_PER_MILLION_CHARACTERS`, `SPEECH_PROVIDER='azure-realtime'`. No fake default key/price. Voice map female=vi-VN-HoaiMyNeural, male=vi-VN-NamMinhNeural. Rate allowlist -10%,+0%,+10%; source text cannot choose SSML controls.

```python
config = speechsdk.SpeechConfig(subscription=key, region=region)
voice_name = {'female':'vi-VN-HoaiMyNeural','male':'vi-VN-NamMinhNeural'}[voice]
config.speech_synthesis_voice_name = voice_name
config.set_speech_synthesis_output_format(
    speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3)
audio = speechsdk.audio.AudioOutputConfig(filename=str(temporary_path))
synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=audio)
cues = []
def on_boundary(event):
    cues.append(SpeechCue(start=event.audio_offset / 10_000_000,
                          duration=event.duration.total_seconds(), text=event.text))
synthesizer.synthesis_word_boundary.connect(on_boundary)
ssml = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="vi-VN">'
        f'<voice name="{voice_name}"><prosody rate="{rate}">'
        f'{html.escape(text)}</prosody></voice></speak>')
result = synthesizer.speak_ssml_async(ssml).get()
if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
    raise SpeechSynthesisFailed('Speech service did not complete')
os.replace(temporary_path, output_path)
```

Wrap concrete synthesis in a180s worker-controlled subprocess deadline; terminate/reap on expiry rather than leaving unbounded SDK .get. Pass no unrelated secrets to that subprocess. Classify cancellation by safe code, not raw exception. Check finite nonnegative cues and ordered offsets; map to existing renderer dictionaries. Preflight lists voices for configured region with credentials, verifies both voices/P4 evidence and local ffmpeg before paid script generation. Do not synthesize document text during preflight.

SpeechUsage table: UUID id PK; course_id/user_id/version_id/job_id Strings; scene_index Integer; operation_key String64 unique; attempts Integer default0 CHECK0..2; characters Integer; estimated_cost/actual_cost nullable BigInteger nanodollars; state String24; created_at/completed_at DateTime. FKs to course/user/job for live rows, nullable when detached during purge. Migration a7b8c9d0e1f2 follows a6b7c8d9e0f1. Record dispatched before synthesis and completed afterward; a timeout after dispatch is unknown and cannot be blindly resent. Retry once only for a proven pre-dispatch/transient no-generation failure; uncertain billing needs reconciliation. Never mix Azure estimates into measured OpenRouter cost totals.

Checkpoint API in video_checkpoint.py: `video_script_key(binding,version_id,script,voice,rate,policy_id)->str`, `save_script(identity,script,work)->None`, `load_script(identity)->dict|None`, `save_scene(identity,index,result,work)->None`, `load_scene(identity,index)->SpeechResult|None`. Define frozen `VideoCheckpointIdentity` containing binding, version_id, script_digest, voice, rate, speech_policy_id, schema_revision='video-checkpoint-v1'; key is canonical_digest of JSON. Store under private course/version checkpoint directory. Use existing Book checkpoint temporary-write/fsync/replace and live job fence pattern, with separate Video schema. Validate content/audio/cue hashes and every identity field before reuse. Persist validated script before speech; completed scene before next scene. No cross-version cache.

Replace `_synthesize_narration` with injected SpeechProvider. Remove ambient pytest/environment-based silence success from the real adapter; use explicit fake provider only in tests. Keep renderer/MP4 contract. A retry resumes completed script/scenes and regenerates only failed uncached work while respecting operation limits.

- [ ] Add fake integration: scene1 complete, scene2 fails before dispatch, retry uses saved script/scene1, generates scene2 and assembles. Test deletion/cancellation prevents audio promotion, changed script invalidates identity and unknown scene charge blocks retry. Run speech/checkpoint/job/video tests and SDK container/import check. Browser/live audible output in Plan04 requires Azure authorization, never synthetic silence. Acceptance: narrated Video supported with bounded recoverable stages and private accounting. Commit suggestion: `feat: add Azure narration and recoverable Video stages`.

## Task P6: Bound uploads and shared authentication abuse

**Goal:** Bound uploads and shared authentication abuse.

**Files:** Create backend `app/services/upload_validation.py`, `app/services/parser_worker.py`, `app/services/auth_limits.py`, `tests/test_upload_boundaries.py`, `tests/test_auth_limits.py`, root `docs/deployment/reliability-operations.md`; modify backend `app/routers/upload.py`, `app/routers/auth.py`, `app/services/document_processor.py`, `app/core/config.py`, `main.py`, `Dockerfile`, root `docker-compose.production.yml`.

**Interfaces:** `stage_upload(upload,directory)->StagedUpload`; `validate_staged_upload(staged)->None`; `parse_in_subprocess(staged)->ManifestCandidate`; `enforce_auth_limit(action,ip,account_hash)->None`. StagedUpload is frozen path/display_name/extension/size/sha256. ManifestCandidate contains S1 Manifest plus private parsed blocks. UploadRejected carries an allowlisted public code.

- [ ] Red tests: 50MiB+1 streamed file rejected before full read, sixth file rejected, invalid final batch member leaves no promoted file/course, wrong signature/encrypted PDF/ZIP bomb/external relationship rejected, parser deadline kills child, spoofed proxy IP rejected. Run `uv run --project . --extra dev python -m pytest tests/test_upload_boundaries.py tests/test_auth_limits.py -q`.
- [ ] Implement bounded staging:

```python
MAX_FILE_BYTES = 50 * 1024 * 1024
async def copy_bounded(upload, target):
    size = 0
    while True:
        block = await upload.read(1024 * 1024)
        if not block:
            break
        size += len(block)
        if size > MAX_FILE_BYTES:
            raise UploadRejected('FILE_TOO_LARGE')
        target.write(block)
    if size == 0:
        raise UploadRejected('EMPTY_FILE')
    return size
```

ASGI ingress in main.py counts total body bytes and rejects over256MiB before multipart consumes the whole body. The repository has no identified ingress-proxy configuration; document required operator settings in docs/deployment/reliability-operations.md (256MiB request limit, HTTPS, exact forwarded-proxy trust, no query logging) and verify the actual deployment in V2/V6. Do not invent or silently install a new proxy. Stage UUID-named files in one verified task directory; sanitize display names separately. Validate all files before DB course creation/promotion; finally clean only that verified directory on failure.

PDF: header/parser validation, no encrypted files, <=1000pages, <=25million raster pixels/page. DOCX: <=10000entries, <=200MiB expanded declared AND streamed, <=100:1 ratio per-entry/aggregate, required [Content_Types].xml and word/document.xml, reject traversal/symlink entries and remote relationships, no external XML entities. Text rejects binary/NUL and uses documented supported decoding; no remote imports.

Parser subprocess receives only staged path/type, never provider key. It parses locally to bounded result file; parent timeout60s terminates/reaps. Linux limit512MiB address space; Windows structural/byte/deadline checks with documented absent OS memory cap. No shell=True, macro execution or source code execution. OCR runs separately through P4 after local parse.

Redis limiter atomically checks/increments IP and HMAC(account-normalized-email) windows. Exact defaults: login IP10/account5 per600s; registration/reset/verification-mail IP5/account3 per3600s, plus current OTP limits. Implement one Lua transaction, set TTL on first count, return Retry-After seconds. Shared Redis failure is503, limit exceeded429; never fall back to per-process memory in shared mode. Local memory uses lock/monotonic clock with identical semantics. Trust forwarded IP only when immediate peer is in configured trusted-proxy CIDRs. Never store/log clear email as limiter key.

- [ ] Test concurrent clients cannot exceed combined limits, outage fail-closed, generic account messages and windows expiring. Run new tests plus existing upload/auth/CORS suites and Ruff. Browser: bad upload useful error/no partial course; throttled login safe countdown; valid flow works. Acceptance: limits apply before expensive processing and across workers. Commit suggestion: `fix: bound document parsing and shared auth abuse`.

## Task P7: Durable deletion and private diagnostics

**Goal:** Durable deletion and private diagnostics.

**Files:** Create backend `app/models/purge_job.py`, `app/services/purge_service.py`, `alembic/versions/a8b9c0d1e2f3_durable_purge_jobs.py`, `tests/test_purge_lifecycle.py`; modify `app/routers/courses.py`, `app/routers/auth.py`, `app/routers/admin.py`, `app/services/document_processor.py`, `app/services/embedding_cache.py`, `app/jobs/tasks.py`, `app/jobs/celery_app.py`, `app/models/__init__.py`, `main.py`, root `docs/deployment/reliability-operations.md`.

**Interfaces:** `request_course_purge(db,course,now)->str`; `run_purge(purge_id,*,factory,storage,vector_store,now)->None`. Admin support endpoints `GET /api/admin/purges`, `POST /api/admin/purges/{id}/retry` return opaque IDs/states/timestamps/codes, no source names/paths.

PurgeJob: UUID PK; course_id String (no cascading FK); owner_digest String64; state String24; attempts Integer default0; next_attempt_at/requested_at/completed_at DateTime; last_error_code String80; private targets_json. Migration a8b9c0d1e2f3 follows a7b8c9d0e1f2. Targets contain owned relative namespaces, not content. Tombstones survive removal of user/course rows.

- [ ] Red tests: vector outage retains pending purge, restart resumes, duplicate purge safe, stale worker cannot recreate, plans/cache/speech/checkpoints removed, cross-owner denied, outside-root path denied, content-free detached accounting retained only as specified. Run `uv run --project . --extra dev python -m pytest tests/test_purge_lifecycle.py -q`.
- [ ] Deletion transaction tombstones course, cancels jobs, invalidates claims, creates purge record and commits before cleanup dispatch. Account deletion revokes sessions/epoch first and creates purge records before removing identifying rows. Stop treating best-effort filesystem cleanup as completed deletion.

Purge order: partial/checkpoints/speech; artifact versions; source revision content; vectors for all revisions; exact embedding-cache namespaces; originals; then private manifests/plans/build rows and identifier detachment. Missing file is idempotent success; service/permission error remains pending. Backoff1min,5min,30min,2h,then2h until resolved. After24h show overdue admin state and keep retrying. Content-free accounting/security retained30days; deletion tombstones retained through backup horizon. Backup maximum30days and replay tombstones before restored traffic.

Define `purge_due_courses()` in jobs/tasks.py and register a60-second Celery beat schedule in celery_app.py, selecting due pending jobs with short claim/update and dispatching opaque purge IDs. Local mode starts a60-second stoppable lifespan task in main.py calling the same selector/executor; no long-held DB session. Define `expire_retained_records()` scheduled daily to delete detached content-free records older than30days, while retaining deletion tombstones until the backup horizon has elapsed. Include ProviderReconciliation reviewer/source-reference scrubbing and SpeechUsage detachment. Return deletion-request accepted immediately after access revocation; do not report physical cleanup complete until purge succeeds.

Modify root docker-compose.production.yml to add one `scheduler` service using the backend image/production environment, command `["uv","run","--project",".","celery","-A","app.jobs.celery_app:celery_app","beat","--schedule","/app/backend/cache/celerybeat-schedule","--loglevel=INFO"]`. Route `hackagen.purge_due_courses` and `hackagen.expire_retained_records` to the existing ingestion queue; explicitly decorate tasks with those names. Only one scheduler replica; DB claims still make duplicate delivery safe. Add the corresponding loadtest environment override to docker-compose.loadtest.yml. Test scheduled purge actually reaches a worker, rather than merely testing that a beat_schedule dictionary exists.

```python
def owned_path(root, relative):
    base = Path(root).resolve()
    candidate = (base / relative).resolve()
    if candidate == base or not candidate.is_relative_to(base):
        raise ValueError('Unsafe purge target')
    return candidate
```

Validate separately under configured upload/output/cache roots. Never shell-compose deletion. Cache namespace is course:revision:model:dimensions:normalization; persist its hash in purge targets. Inventory old orphan cache scopes and clean within the approved retention target without touching another owner's namespace. Detach ProviderCall/BookBudget/SpeechUsage identifying FKs before deleting parent rows; do not leave PII in JSON metadata.

Health public endpoints return only coarse status. Admin diagnostics list safe dependency states, no course IDs/paths/raw errors. Disable access-query strings at Uvicorn/proxy and redact credential fields; no request/provider document bodies in logs. Captured-log tests use synthetic sentinel secrets/text and assert absence.

- [ ] Run purge/ownership/job/health/log suites. Browser: immediate access removal, safe admin pending/overdue status, retry eventual completion. Acceptance: deletion remains tracked across failures/restarts and cannot falsely complete. Commit suggestion: `fix: make document deletion durable and diagnostics private`.

## Task P8: Integrated security/provider checkpoint

**Goal:** Integrated security/provider checkpoint.

**Files:** Add backend `tests/test_security_release_contract.py`, frontend `e2e/session-and-downloads.spec.ts`; update README/CLAUDE.md/.env.example/progress_new.md.

- [ ] Parameterize other-owner probes over every new/existing source, quote, artifact, job, repair, ticket and purge route. Assert denial plus zero provider/job/file side effects. Include source prompt injection, generated Markdown XSS, remote document references and ticket purpose separation.
- [ ] Run P1–P7 tests, existing auth/course/job/provider suites, frontend auth/download tests and `npm run test:e2e -- e2e/session-and-downloads.spec.ts --project=chromium`. Run affected Ruff and frontend lint/build. Expected all required tests pass; no live speech required for offline checkpoint.
- [ ] Document Azure setup/evidence, cookie/CORS/session migration, download contract, parsing bounds, limiter settings, purge/backup/restore commands. Pin SDK after official compatibility verification and record Windows/Linux imports. Example secrets are symbolic. No Edge fallback.
- [ ] Acceptance: durable access, scoped downloads, guarded transfers/uploads and retryable deletion work offline/integration. Plan04 still must prove actual eligible endpoints, audible Video, real outputs and security review. Commit suggestion: `test: cover shared server security and speech boundaries`.

## Security review handoff

Additional executable regression examples belong in the named P-task test files:

```python
# P3, tests/test_download_tickets.py
def test_ticket_cannot_change_version(ticket_case):
    token = ticket_case.issue(asset='book_pdf', version='v1')
    assert ticket_case.download(token, asset='book_pdf', version='v1').status_code == 200
    assert ticket_case.download(token, asset='book_pdf', version='v2').status_code in (401,403,404)
    ticket_case.logout()
    assert ticket_case.download(token, asset='book_pdf', version='v1').status_code == 401

# P4, tests/test_external_policy.py
def test_price_merge_keeps_privacy_and_does_not_mutate_input():
    from types import SimpleNamespace
    request = {'extra_body':{'provider':{'max_price':{'prompt':0.3},'data_collection':'allow'}}}
    auth = SimpleNamespace(endpoint_slugs=('eligible-provider',))
    result = merge_provider_controls(request, auth)
    actual = result['extra_body']['provider']
    assert actual['max_price'] == {'prompt':0.3}
    assert actual['data_collection'] == 'deny' and actual['zdr'] is True
    assert actual['only'] == ['eligible-provider'] and actual['allow_fallbacks'] is False
    assert request['extra_body']['provider']['data_collection'] == 'allow'

# P6, tests/test_upload_boundaries.py
@pytest.mark.asyncio
async def test_stream_rejects_before_consuming_remaining_input(monkeypatch):
    import io
    from app.services import upload_validation as validation
    monkeypatch.setattr(validation,'MAX_FILE_BYTES',3)
    class Upload:
        calls = 0
        async def read(self, size):
            self.calls += 1
            return b'xx' if self.calls < 100 else b''
    upload = Upload()
    with pytest.raises(validation.UploadRejected):
        await validation.copy_bounded(upload, io.BytesIO())
    assert upload.calls == 2

# P7, tests/test_purge_lifecycle.py
def test_purge_never_accepts_storage_root_or_parent(tmp_path):
    from app.services.purge_service import owned_path
    for relative in ('.','../other-student'):
        with pytest.raises(ValueError):
            owned_path(tmp_path, relative)
    assert owned_path(tmp_path, 'course-a/version-a').is_relative_to(tmp_path.resolve())

# P8, tests/test_security_release_contract.py
def test_foreign_owner_denial_has_no_side_effect(owned_endpoint_case):
    assert owned_endpoint_case.request_as_owner().status_code in (200,201,202)
    before = owned_endpoint_case.side_effect_counts()
    response = owned_endpoint_case.request_as_other_user()
    assert response.status_code == 404
    assert owned_endpoint_case.side_effect_counts() == before
```

ticket_case creates a real P1 session and owned course with two real fixture PDF versions; issue() calls the ticket route and returns only its token in memory; download() calls existing asset route with selected version; logout() calls real logout. It uses separate cookie-free clients for capability requests so bearer/cookie auth cannot mask ticket validation. owned_endpoint_case parameterizes the ordinary owner-scoped source/quote/job/artifact/repair routes with valid positive-control inputs; side_effect_counts reads actual job/ledger rows and private fixture file count. Admin routes get separate role403 tests. Both fixtures use temporary owned storage and fake providers, never production state.

For P5 define the constructor exactly as `AzureRealtimeSpeech(*, config, authorize, sdk_module=None)`: config supplies the declared settings, authorize is P4-compatible callable, sdk_module is injected only by tests. The production default lazily imports SDK1.51.2. SDK fake implements SpeechConfig, output-format enum, AudioOutputConfig, SpeechSynthesizer with word-boundary callback collection and a completed/cancelled async result object; write a small fixture MP3 to the supplied temporary filename when completing. Test a cancellation then assert output absent and no second SDK call on a permanent failure. Test word-boundary event with audio_offset=15000000, duration=timedelta(milliseconds=200), text='học' yields start1.5/duration0.2. These are exact fake event values, not a live sound-quality assertion.

Plan04 requests a separate security-focused review and records both deployment modes. Missing Azure credentials/applicable policy evidence blocks release; never silently disable Video acceptance, restore Edge or weaken policy. The user authorized design and planning; this session does not provision Azure or send narration.
