"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ArtifactVersion } from "@/lib/types";
import { normalizePublicError } from "@/lib/types";

/** Shared poll cadence — was a `3000` literal duplicated independently across 6 call
 * sites (the 4 tabs below, plus the simpler list/status pollers in courses/page.tsx and
 * course/[id]/page.tsx, which poll a plain status field rather than an artifact-generation
 * state machine and so don't fit this hook's shape). */
export const DEFAULT_POLL_MS = 3000;

/** Common shape of the 4 artifact status responses (Book/Slide/Quiz/Vid). */
export interface ArtifactStatusLike<T> {
  status?: string;
  data?: T | null;
  progress?: number | null;
  error?: string | null;
  error_code?: unknown;
  version_id?: string | null;
  active_version?: string | null;
  versions?: ArtifactVersion[];
}

export interface ActiveArtifactJob {
  jobId: string;
  versionId: string | null;
}

interface UsePollingArtifactOptions<T> {
  courseId: string;
  fetchFn: (courseId: string, version?: string | null) => Promise<ArtifactStatusLike<T>>;
  /** True once `data` actually has renderable content (e.g. chapters.length > 0) — a
   * "ready" status with an empty payload is treated as not-ready-yet. */
  isReady: (data: T) => boolean;
  timeoutMs: number;
  timeoutMessage: string;
  defaultErrorMessage: string;
  pollMs?: number;
  /** Fires once, right when data first becomes ready — for feature-specific side effects
   * like resetting the active chapter/slide index or quiz-taking state. */
  onReady?: (data: T) => void;
}

/**
 * Shared "generate → poll until ready/error/timeout" state machine for Book/Slide/Quiz/
 * Vid tabs — was 4 independent copies with divergent timeouts and no shared error
 * handling before this hook.
 */
export function usePollingArtifact<T>({
  courseId,
  fetchFn,
  isReady,
  timeoutMs,
  timeoutMessage,
  defaultErrorMessage,
  pollMs = DEFAULT_POLL_MS,
  onReady,
}: UsePollingArtifactOptions<T>) {
  const [data, setData] = useState<T | null>(null);
  const [hasFetched, setHasFetched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dataByVersion, setDataByVersion] = useState<Record<string, T>>({});
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [activeVersion, setActiveVersion] = useState<string | null>(null);
  const [viewedVersion, setViewedVersion] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<ActiveArtifactJob | null>(null);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingVersionRef = useRef<string | null>(null);
  const viewedVersionRef = useRef<string | null>(null);

  // Keep the latest callbacks in refs so `startPolling`'s recursive closure always calls
  // the current version without needing to be recreated (and without going in the
  // initial-fetch effect's dependency array, which would restart in-flight polling on
  // every render). Synced in an effect, not during render, per react-hooks/refs.
  const fetchFnRef = useRef(fetchFn);
  const isReadyRef = useRef(isReady);
  const onReadyRef = useRef(onReady);
  useEffect(() => {
    fetchFnRef.current = fetchFn;
    isReadyRef.current = isReady;
    onReadyRef.current = onReady;
    viewedVersionRef.current = viewedVersion;
  });

  const startPolling = useCallback(
    (startedAt: number, versionId?: string | null) => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      pollingVersionRef.current = versionId ?? viewedVersion;
      if (pollingVersionRef.current) {
        const invalidated = pollingVersionRef.current;
        setDataByVersion((cache) => {
          const next = { ...cache };
          delete next[invalidated];
          return next;
        });
      }
      const poll = async () => {
        const pollingVersion = pollingVersionRef.current;
        try {
          const res = await fetchFnRef.current(courseId, pollingVersion);
          if (res.versions) setVersions(res.versions);
          if (res.active_version !== undefined) setActiveVersion(res.active_version ?? null);
          if (res.status === "ready" && res.data && isReadyRef.current(res.data)) {
            const completedVersion = res.version_id ?? pollingVersion;
            if (completedVersion) setDataByVersion((cache) => ({ ...cache, [completedVersion]: res.data as T }));
            // A generation the user kicked off always surfaces when it finishes, even if
            // they switched to look at a different existing version meanwhile — like
            // NotebookLM notifying "your new version is ready" instead of silently caching
            // it until the user happens to click back.
            if (completedVersion) setViewedVersion(completedVersion);
            setData(res.data);
            setHasFetched(true);
            onReadyRef.current?.(res.data);
            setGenerating(false);
            setProgress(100);
            pollingVersionRef.current = null;
            return;
          }
          if (res.status === "error") {
            if (!viewedVersionRef.current || viewedVersionRef.current === pollingVersion) {
              setError(normalizePublicError(res.error_code, defaultErrorMessage));
            }
            setGenerating(false);
            pollingVersionRef.current = null;
            return;
          }
          if (typeof res.progress === "number") setProgress(res.progress);
        } catch {
          // Ignore transient errors while the background job is still running.
        }
        if (pollingVersionRef.current !== pollingVersion) return;
        if (Date.now() - startedAt > timeoutMs) {
          if (!viewedVersionRef.current || viewedVersionRef.current === pollingVersion) {
            setError(timeoutMessage);
          }
          setGenerating(false);
          pollingVersionRef.current = null;
          return;
        }
        pollTimer.current = setTimeout(poll, pollMs);
      };
      pollTimer.current = setTimeout(poll, pollMs);
    },
    [courseId, timeoutMs, timeoutMessage, defaultErrorMessage, pollMs, viewedVersion]
  );

  const startJob = useCallback((jobId: string | null | undefined, versionId: string | null | undefined) => {
    if (!jobId) {
      startPolling(Date.now(), versionId);
      return;
    }
    if (pollTimer.current) clearTimeout(pollTimer.current);
    pollingVersionRef.current = null;
    setError(null);
    setGenerating(true);
    setProgress(0);
    setActiveJob({ jobId, versionId: versionId ?? null });
  }, [startPolling]);

  const finishJob = useCallback(() => {
    setGenerating(false);
  }, []);

  const dismissJob = useCallback(() => {
    setActiveJob(null);
    setGenerating(false);
  }, []);

  const resumeArtifactPolling = useCallback(() => {
    if (!activeJob) return;
    const { versionId } = activeJob;
    setActiveJob(null);
    setGenerating(true);
    setProgress(5);
    startPolling(Date.now(), versionId);
  }, [activeJob, startPolling]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      pollingVersionRef.current = null;
    };
  }, [courseId]);

  useEffect(() => {
    if (hasFetched) return;
    fetchFnRef
      .current(courseId, viewedVersion)
      .then((res) => {
        if (res.versions) setVersions(res.versions);
        if (res.active_version !== undefined) setActiveVersion(res.active_version ?? null);
        if (res.version_id && !viewedVersion) setViewedVersion(res.version_id);
        if (res.status === "ready" && res.data && isReadyRef.current(res.data)) {
          setData(res.data);
          if (res.version_id) setDataByVersion((cache) => ({ ...cache, [res.version_id as string]: res.data as T }));
          onReadyRef.current?.(res.data);
        } else if (res.status === "processing") {
          setGenerating(true);
          setProgress(res.progress ?? 5);
          startPolling(Date.now(), res.version_id ?? viewedVersion);
        } else if (res.status === "error") {
          setError(normalizePublicError(res.error_code, defaultErrorMessage));
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : defaultErrorMessage))
      .finally(() => setHasFetched(true));

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, hasFetched, viewedVersion]);

  const switchVersion = useCallback((versionId: string) => {
    if (versionId === viewedVersion) return;
    setViewedVersion(versionId);
    const cached = dataByVersion[versionId];
    setData(cached ?? null);
    setError(null);
    setHasFetched(Boolean(cached));
  }, [dataByVersion, viewedVersion]);

  const refresh = useCallback(() => {
    setHasFetched(false);
    setError(null);
  }, []);

  return {
    data,
    setData,
    hasFetched,
    error,
    setError,
    generating,
    setGenerating,
    progress,
    setProgress,
    dataByVersion,
    startPolling,
    activeJob,
    startJob,
    finishJob,
    dismissJob,
    resumeArtifactPolling,
    versions,
    activeVersion,
    viewedVersion,
    switchVersion,
    refresh,
  };
}
