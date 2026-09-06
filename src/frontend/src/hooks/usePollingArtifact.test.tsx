import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiRequestError, ApiResponseError } from "@/lib/api";
import { usePollingArtifact } from "./usePollingArtifact";

describe("usePollingArtifact", () => {
  it("retries initial discovery after an outage and recovers the active job", async () => {
    const random = vi.spyOn(Math, "random").mockReturnValue(0);
    const fetchFn = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue({ status: "processing", job_id: "recovered-job", version_id: "v2", progress: 0 });
    const { result } = renderHook(() => usePollingArtifact({
      courseId: "course-1", fetchFn, isReady: () => false, timeoutMs: 60_000,
      timeoutMessage: "Delayed", defaultErrorMessage: "Failed", pollMs: 1,
    }));
    await waitFor(() => expect(result.current.activeJob).toEqual({ jobId: "recovered-job", versionId: "v2" }));
    expect(fetchFn).toHaveBeenCalledTimes(2);
    random.mockRestore();
  });

  it("clears a transient discovery error when retry recovers ready content", async () => {
    const random = vi.spyOn(Math, "random").mockReturnValue(0);
    const fetchFn = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue({ status: "ready", version_id: "v1", data: { id: "ready" } });
    const { result } = renderHook(() => usePollingArtifact({
      courseId: "course-1", fetchFn, isReady: (value) => Boolean(value.id),
      timeoutMs: 60_000, timeoutMessage: "Delayed", defaultErrorMessage: "Failed", pollMs: 1,
    }));
    await waitFor(() => expect(result.current.data).toEqual({ id: "ready" }));
    expect(result.current.error).toBeNull();
    random.mockRestore();
  });

  it("clears a discovery outage while legacy processing recovers to ready", async () => {
    const random = vi.spyOn(Math, "random").mockReturnValue(0);
    const fetchFn = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ status: "processing", version_id: "legacy", progress: 20, data: null })
      .mockResolvedValue({ status: "ready", version_id: "legacy", progress: 100, data: { id: "legacy-ready" } });
    const { result } = renderHook(() => usePollingArtifact({
      courseId: "course-1", fetchFn, isReady: (value) => Boolean(value.id),
      timeoutMs: 60_000, timeoutMessage: "Delayed", defaultErrorMessage: "Failed", pollMs: 1,
    }));
    await waitFor(() => expect(result.current.data).toEqual({ id: "legacy-ready" }));
    expect(result.current.error).toBeNull();
    random.mockRestore();
  });

  it("ignores an uncached version response after switching back to cached content", async () => {
    let resolveOld!: (value: { status: string; version_id: string; data: { id: string } }) => void;
    const oldResponse = new Promise<{ status: string; version_id: string; data: { id: string } }>((resolve) => { resolveOld = resolve; });
    const fetchFn = vi.fn((_course: string, version?: string | null) => {
      if (version === "v0") return oldResponse;
      return Promise.resolve({ status: "ready", version_id: "v1", data: { id: "v1" } });
    });
    const { result } = renderHook(() => usePollingArtifact({
      courseId: "course-1", fetchFn, isReady: (value) => Boolean(value.id),
      timeoutMs: 60_000, timeoutMessage: "Delayed", defaultErrorMessage: "Failed",
    }));
    await waitFor(() => expect(result.current.data).toEqual({ id: "v1" }));
    act(() => result.current.switchVersion("v0"));
    await waitFor(() => expect(fetchFn).toHaveBeenCalledWith("course-1", "v0", expect.any(Object)));
    act(() => result.current.switchVersion("v1"));
    await act(async () => resolveOld({ status: "ready", version_id: "v0", data: { id: "v0" } }));
    expect(result.current.viewedVersion).toBe("v1");
    expect(result.current.data).toEqual({ id: "v1" });
  });

  it("stops legacy artifact observation after a forbidden response", async () => {
    const fetchFn = vi.fn()
      .mockResolvedValueOnce({ status: "ready", version_id: "v1", data: { id: "v1" } })
      .mockRejectedValue(new ApiRequestError("Forbidden", 403));
    const { result } = renderHook(() => usePollingArtifact({
      courseId: "course-1", fetchFn, isReady: (value) => Boolean(value.id),
      timeoutMs: 60_000, timeoutMessage: "Delayed", defaultErrorMessage: "Failed", pollMs: 10,
    }));
    await waitFor(() => expect(result.current.hasFetched).toBe(true));
    vi.useFakeTimers();
    act(() => result.current.startPolling(Date.now(), "legacy-v2"));
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(result.current.generating).toBe(false);
    window.dispatchEvent(new Event("online"));
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(fetchFn).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
  it("recovers an initial processing job and keeps its selected version identity", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      status: "processing", job_id: "j1", version_id: "v1", progress: 0, data: null,
    });
    const { result } = renderHook(() => usePollingArtifact({
      courseId: "course-1", fetchFn, isReady: () => false,
      timeoutMs: 6 * 60_000, timeoutMessage: "Delayed", defaultErrorMessage: "Failed",
    }));
    await waitFor(() => expect(result.current.activeJob).toEqual({ jobId: "j1", versionId: "v1" }));
    expect(result.current.generating).toBe(true);
    expect(result.current.progress).toBe(0);
  });
  it("sanitizes a raw successful error envelope", async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      status: "error",
      error: "Failed to fetch",
      error_code: "UNKNOWN_BACKEND_ERROR",
    });

    const { result } = renderHook(() =>
      usePollingArtifact({
        courseId: "course-1",
        fetchFn,
        isReady: () => false,
        timeoutMs: 60_000,
        timeoutMessage: "Timed out",
        defaultErrorMessage: "Tạo học liệu thất bại.",
      })
    );

    await waitFor(() => expect(result.current.error).toBe("Tạo học liệu thất bại."));
    expect(result.current.error).not.toContain("Failed to fetch");
  });

  it("never exposes invalid artifact response diagnostics", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new ApiResponseError());

    const { result } = renderHook(() =>
      usePollingArtifact({
        courseId: "course-1",
        fetchFn,
        isReady: () => false,
        timeoutMs: 60_000,
        timeoutMessage: "Timed out",
        defaultErrorMessage: "Tạo học liệu thất bại.",
      })
    );

    await waitFor(() =>
      expect(result.current.error).toBe(
        "Máy chủ trả về dữ liệu không hợp lệ. Vui lòng thử lại."
      )
    );
    expect(result.current.error).not.toMatch(/SyntaxError|provider_trace|Unexpected end/u);
  });

  it("keeps polling the generated version after the user switches views", async () => {
    const fetchFn = vi.fn(async (_courseId: string, version?: string | null) => {
      if (version === "new") {
        return { status: "ready", data: { id: "new" }, version_id: "new" };
      }
      return { status: "ready", data: { id: version ?? "active" }, version_id: version ?? "active" };
    });

    const { result, unmount } = renderHook(() =>
      usePollingArtifact({
        courseId: "course-1",
        fetchFn,
        isReady: (data) => Boolean(data.id),
        timeoutMs: 60_000,
        timeoutMessage: "Timed out",
        defaultErrorMessage: "Failed",
        pollMs: 10,
      })
    );

    await waitFor(() => expect(result.current.hasFetched).toBe(true));
    vi.useFakeTimers();
    act(() => result.current.startPolling(Date.now(), "new"));
    act(() => result.current.switchVersion("old"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(fetchFn).toHaveBeenCalledWith(
      "course-1",
      "new",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(result.current.viewedVersion).toBe("new");
    expect(result.current.data).toEqual({ id: "new" });
    expect(result.current.generating).toBe(false);

    unmount();
    vi.useRealTimers();
  });

  it("stores a queued job beside its version then resumes artifact polling on success", async () => {
    const fetchFn = vi.fn(async (_courseId: string, version?: string | null) => ({
      status: "ready",
      data: { id: version ?? "active" },
      version_id: version ?? "active",
    }));
    const { result, unmount } = renderHook(() =>
      usePollingArtifact({
        courseId: "course-1",
        fetchFn,
        isReady: (data) => Boolean(data.id),
        timeoutMs: 60_000,
        timeoutMessage: "Timed out",
        defaultErrorMessage: "Failed",
        pollMs: 10,
      })
    );
    await waitFor(() => expect(result.current.hasFetched).toBe(true));

    act(() => result.current.startJob("job-2", "version-2"));
    expect(result.current.activeJob).toEqual({ jobId: "job-2", versionId: "version-2" });
    expect(result.current.generating).toBe(true);

    vi.useFakeTimers();
    act(() => result.current.resumeArtifactPolling());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(fetchFn).toHaveBeenLastCalledWith(
      "course-1",
      "version-2",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(result.current.activeJob).toBeNull();
    expect(result.current.data).toEqual({ id: "version-2" });
    expect(result.current.generating).toBe(false);
    unmount();
    vi.useRealTimers();
  });

  it("retains a terminal job version for exactly one retry and can clear it for fresh work", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ status: "ready", data: { id: "old" }, version_id: "old" });
    const { result } = renderHook(() =>
      usePollingArtifact({
        courseId: "course-1",
        fetchFn,
        isReady: (data) => Boolean(data.id),
        timeoutMs: 60_000,
        timeoutMessage: "Timed out",
        defaultErrorMessage: "Failed",
      })
    );
    await waitFor(() => expect(result.current.hasFetched).toBe(true));

    act(() => result.current.startJob("job-1", "reserved-v3"));
    act(() => result.current.prepareActiveJobRetry());
    expect(result.current.consumeJobRetryVersion()).toBe("reserved-v3");
    expect(result.current.consumeJobRetryVersion()).toBeNull();

    act(() => result.current.startJob("job-2", "reserved-v4"));
    act(() => result.current.prepareActiveJobRetry());
    act(() => result.current.clearJobRetryVersion());
    expect(result.current.consumeJobRetryVersion()).toBeNull();
  });
});
