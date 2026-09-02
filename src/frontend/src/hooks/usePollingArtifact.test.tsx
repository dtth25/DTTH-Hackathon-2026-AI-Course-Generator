import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiResponseError } from "@/lib/api";
import { usePollingArtifact } from "./usePollingArtifact";

describe("usePollingArtifact", () => {
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

    expect(fetchFn).toHaveBeenCalledWith("course-1", "new");
    expect(result.current.viewedVersion).toBe("new");
    expect(result.current.data).toEqual({ id: "new" });
    expect(result.current.generating).toBe(false);

    unmount();
    vi.useRealTimers();
  });
});
