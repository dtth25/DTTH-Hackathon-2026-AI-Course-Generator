import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCancelJob, apiGetJob } from "@/lib/api";
import type { JobStatusResponse } from "@/lib/types";
import { JobProgress } from "./JobProgress";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    apiGetJob: vi.fn(),
    apiCancelJob: vi.fn(),
  };
});

const storageValues = new Map<string, string>();
const testStorage: Storage = {
  get length() { return storageValues.size; },
  clear: () => storageValues.clear(),
  getItem: (key) => storageValues.get(key) ?? null,
  key: (index) => Array.from(storageValues.keys())[index] ?? null,
  removeItem: (key) => { storageValues.delete(key); },
  setItem: (key, value) => { storageValues.set(key, value); },
};

const baseJob: JobStatusResponse = {
  id: "job-1",
  document_id: "course-1",
  job_type: "video",
  status: "queued",
  queue_position: 2,
  progress: 0,
  message: "raw worker message must stay private",
  created_at: "2026-09-05T00:00:00Z",
  updated_at: "2026-09-05T00:00:00Z",
};

function job(overrides: Partial<JobStatusResponse>): JobStatusResponse {
  return { ...baseJob, ...overrides };
}

describe("JobProgress", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", testStorage);
    vi.mocked(apiGetJob).mockReset();
    vi.mocked(apiCancelJob).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
  });

  it("shows a queued state with a safe queue name and position", async () => {
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "queued" }));

    render(<JobProgress jobId="job-1" allowCancel />);

    expect(await screen.findByText("Đang chờ")).toBeInTheDocument();
    expect(screen.getByText("Hàng chờ dựng video · vị trí 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yêu cầu hủy" })).toBeInTheDocument();
  });

  it("shows backend progress for a running job", async () => {
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "running", progress: 64 }));

    render(<JobProgress jobId="job-1" allowCancel />);

    expect(await screen.findByText("Đang dựng video (64%)…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "64");
  });

  it("shows live generation stages from the backend instead of a generic reload-only status", async () => {
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "running", progress: 7, stage: "capacity_wait" }));

    render(<JobProgress jobId="job-1" />);

    expect(await screen.findByText("Đang chờ lượt xử lý AI · đã chạy 0 giây")).toBeInTheDocument();
  });

  it("renders the worker retry schedule returned by the server", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-05T00:00:00Z"));
    vi.mocked(apiGetJob).mockResolvedValue(job({
      status: "retry_scheduled",
      progress: 31,
      next_attempt_at: "2026-09-05T00:02:00Z",
    }));

    render(<JobProgress jobId="job-1" allowCancel />);
    await act(async () => Promise.resolve());
    expect(screen.getByText(/Dự kiến thử lại lúc/u)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Yêu cầu hủy" })).not.toBeInTheDocument();

    expect(screen.queryByText(/Thử lại sau 3 giây/u)).not.toBeInTheDocument();
  });

  it("shows capacity wait copy for a retry-scheduled capacity continuation", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-05T00:00:00Z"));
    vi.mocked(apiGetJob).mockResolvedValue(job({
      status: "retry_scheduled",
      progress: 57,
      stage: "capacity_wait",
      next_attempt_at: "2026-09-05T00:00:04Z",
    }));

    render(<JobProgress jobId="job-1" />);
    await act(async () => Promise.resolve());

    expect(screen.getByText("Đang chờ lượt xử lý AI")).toBeInTheDocument();
    expect(screen.getByText(/Hệ thống sẽ tự tiếp tục khi có lượt/u)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "57");
  });

  it("streams progress observations and reaches success", async () => {
    vi.useFakeTimers();
    const onSucceeded = vi.fn();
    const onUpdate = vi.fn();
    vi.mocked(apiGetJob)
      .mockResolvedValueOnce(job({ status: "running", progress: 15 }))
      .mockResolvedValueOnce(job({ status: "running", progress: 52 }))
      .mockResolvedValueOnce(job({ status: "succeeded", progress: 100 }));

    render(<JobProgress jobId="job-1" onSucceeded={onSucceeded} onUpdate={onUpdate} />);
    await act(async () => Promise.resolve());
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "52");
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    expect(onSucceeded).toHaveBeenCalledOnce();
    expect(onUpdate).toHaveBeenLastCalledWith(expect.objectContaining({ progress: 100 }));
  });

  it("does not revive terminal observation on online or visibility events", async () => {
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "succeeded", progress: 100 }));
    render(<JobProgress jobId="job-1" />);
    await waitFor(() => expect(apiGetJob).toHaveBeenCalledOnce());
    window.dispatchEvent(new Event("online"));
    document.dispatchEvent(new Event("visibilitychange"));
    await act(async () => Promise.resolve());
    expect(apiGetJob).toHaveBeenCalledOnce();
  });

  it("supersedes an aborted recheck without scheduling a concurrent third read", async () => {
    vi.useFakeTimers();
    let secondResolve!: (value: JobStatusResponse) => void;
    vi.mocked(apiGetJob)
      .mockImplementationOnce((_id, init) => new Promise((_, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))))
      .mockImplementationOnce(() => new Promise((resolve) => { secondResolve = resolve; }));
    render(<JobProgress jobId="job-1" />);
    await act(async () => Promise.resolve());
    window.dispatchEvent(new Event("online"));
    await act(async () => Promise.resolve());
    expect(apiGetJob).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(apiGetJob).toHaveBeenCalledTimes(2);
    await act(async () => secondResolve(job({ status: "succeeded", progress: 100 })));
  });

  it("stops polling after cancellation", async () => {
    vi.useFakeTimers();
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "cancelled" }));

    const onRetry = vi.fn();
    render(<JobProgress jobId="job-1" onRetry={onRetry} />);
    await act(async () => Promise.resolve());
    expect(screen.getByText("Đã hủy")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });
    expect(apiGetJob).toHaveBeenCalledTimes(1);
    act(() => screen.getByRole("button", { name: "Tạo lại" }).click());
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows a safe failure and a retry action", async () => {
    const onRetry = vi.fn();
    vi.mocked(apiGetJob).mockResolvedValue(
      job({
        status: "failed",
        error_code: "VIDEO_GENERATION_FAILED",
        error: "provider response: secret stack trace",
        message: "worker-17 exhausted raw payload",
      })
    );

    render(<JobProgress jobId="job-1" onRetry={onRetry} />);

    expect(await screen.findByText("Không thể tạo video. Vui lòng thử lại.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("hands succeeded jobs back to artifact polling and never polls again", async () => {
    vi.useFakeTimers();
    const onSucceeded = vi.fn();
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "succeeded", progress: 100 }));

    render(<JobProgress jobId="job-1" onSucceeded={onSucceeded} />);
    await act(async () => Promise.resolve());

    expect(onSucceeded).toHaveBeenCalledOnce();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });
    expect(apiGetJob).toHaveBeenCalledTimes(1);
  });

  it("requests cooperative cancellation only for active video jobs", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(apiGetJob).mockResolvedValue(job({ status: "running", progress: 12 }));
    vi.mocked(apiCancelJob).mockResolvedValue(job({ status: "cancelled", progress: 12 }));

    render(<JobProgress jobId="job-1" allowCancel />);
    await screen.findByText("Đang dựng video (12%)…");
    await userEvent.click(screen.getByRole("button", { name: "Yêu cầu hủy" }));

    expect(apiCancelJob).toHaveBeenCalledWith("job-1", expect.any(Object));
    expect(
      screen.getByText("Đã gửi yêu cầu hủy. Video sẽ dừng ở điểm an toàn gần nhất.")
    ).toBeInTheDocument();
    expect(screen.getByText("Đã hủy")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(apiGetJob).toHaveBeenCalledTimes(1);
  });

  it("cancellation supersedes a pending status read and ignores later events", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let resolvePending!: (value: JobStatusResponse) => void;
    vi.mocked(apiGetJob)
      .mockResolvedValueOnce(job({ status: "queued" }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolvePending = resolve; }));
    vi.mocked(apiCancelJob).mockResolvedValue(job({ status: "cancelled" }));
    render(<JobProgress jobId="job-1" allowCancel />);
    await screen.findByText("Đang chờ");
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    await userEvent.click(screen.getByRole("button", { name: "Yêu cầu hủy" }));
    expect(screen.getByText("Đã hủy")).toBeInTheDocument();
    await act(async () => resolvePending(job({ status: "running", progress: 80 })));
    window.dispatchEvent(new Event("online"));
    document.dispatchEvent(new Event("visibilitychange"));
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(screen.getByText("Đã hủy")).toBeInTheDocument();
    expect(apiGetJob).toHaveBeenCalledTimes(2);
  });

  it("aborts an in-flight status request when unmounted", () => {
    let signal: AbortSignal | undefined;
    vi.mocked(apiGetJob).mockImplementation((_jobId, init) => {
      signal = init?.signal ?? undefined;
      return new Promise(() => undefined);
    });

    const { unmount } = render(<JobProgress jobId="job-1" />);
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("never renders raw payload, worker, provider, or technical diagnostics", async () => {
    vi.mocked(apiGetJob).mockResolvedValue(
      job({
        status: "failed",
        error_code: "UNKNOWN_TECHNICAL_FAILURE",
        error: "provider_response={api_key: hidden}",
        message: "worker_id=celery-4 payload_json={secret:true}",
      })
    );

    const { container } = render(<JobProgress jobId="job-1" />);
    await waitFor(() => expect(screen.getByText("Không thể hoàn tất tác vụ. Vui lòng thử lại.")).toBeInTheDocument());
    expect(container).not.toHaveTextContent(/payload|worker|provider|api_key|technical|secret/iu);
  });

  it("uses authenticated encoded-id clients for reading and cancellation", async () => {
    const originalFetch = globalThis.fetch;
    const actualApi = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    const responseBody = JSON.stringify(job({ status: "cancelled" }));
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(responseBody, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
    );
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("agy_auth_token", "test-token");

    await actualApi.apiGetJob("job/with space");
    await actualApi.apiCancelJob("job/with space");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringMatching(/\/api\/jobs\/job%2Fwith%20space$/u),
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer test-token" }),
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringMatching(/\/api\/jobs\/job%2Fwith%20space$/u),
      expect.objectContaining({
        method: "DELETE",
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer test-token" }),
      })
    );
    vi.stubGlobal("fetch", originalFetch);
  });
});
