import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CourseDashboardPage from "./page";
import {
  ApiNetworkError,
  ApiRequestError,
  apiGetCourseStatus,
  apiGetStudyPack,
  apiRetryDocument,
} from "@/lib/api";

const navigation = vi.hoisted(() => ({ courseId: "course-1", push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: navigation.courseId }),
  useRouter: () => ({ push: navigation.push }),
}));

vi.mock("@/components/auth/AuthGuard", () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("@/components/dashboard/BookTab", () => ({
  BookTab: () => <div>Nội dung Study Guide</div>,
}));

vi.mock("@/components/dashboard/SlideTab", () => ({
  SlideTab: () => <div>Nội dung slide</div>,
}));

vi.mock("@/components/dashboard/QuizTab", () => ({
  QuizTab: () => <div>Nội dung quiz</div>,
}));

vi.mock("@/components/dashboard/VidTab", () => ({
  VidTab: () => <div>Nội dung video</div>,
}));

vi.mock("@/lib/api", () => ({
  apiGetCourseStatus: vi.fn(),
  apiGetStudyPack: vi.fn(),
  apiRetryDocument: vi.fn(),
  NETWORK_UNAVAILABLE_MESSAGE:
    "Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.",
  ApiNetworkError: class ApiNetworkError extends Error {
    code = "NETWORK_UNAVAILABLE" as const;
    constructor() {
      super("Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.");
    }
  },
  ApiRequestError: class ApiRequestError extends Error {
    status: number;
    detail: unknown;
    constructor(message: string, status: number, detail?: unknown) {
      super(message);
      this.status = status;
      this.detail = detail;
    }
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe("course workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.courseId = "course-1";
    navigation.push.mockReset();
    vi.mocked(apiGetCourseStatus).mockResolvedValue({
      course_id: "course-1",
      name: "Sinh thái đô thị",
      status: "ready",
      filenames: ["sinh-thai.pdf", "ghi-chu.txt"],
      file_count: 2,
    });
    vi.mocked(apiGetStudyPack).mockRejectedValue(new Error("Chưa có học liệu"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("marks the resolved dashboard as a semantic course workspace", async () => {
    const { container } = render(<CourseDashboardPage />);

    await screen.findByRole("heading", { name: "Sinh thái đô thị" });
    await waitFor(() => {
      expect(
        container.querySelector('[data-visual-state="course-workspace"]')
      ).toBeInTheDocument();
    });
    const workspacePanel = container.querySelector(
      '[data-visual-state="course-workspace"] section'
    );
    expect(workspacePanel).toBeInTheDocument();
    expect(workspacePanel?.tagName).toBe("SECTION");
    expect(workspacePanel).toHaveClass(
      "border-t-[3px]",
      "border-[var(--accent-strong)]"
    );
    expect(workspacePanel).not.toHaveClass("rounded-xl");
    expect(workspacePanel).not.toHaveClass("bg-card");
    expect(workspacePanel).not.toHaveClass("p-6");
  });

  it("explains provider quota failure without blaming the PDF", async () => {
    vi.mocked(apiGetCourseStatus).mockResolvedValue({
      course_id: "course-1",
      status: "paused_due_to_quota",
      error: "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
      error_code: "OPENROUTER_KEY_LIMIT_EXCEEDED",
      can_retry: true,
      recommended_action: "restore_provider_quota",
    });

    render(<CourseDashboardPage />);

    expect(
      await screen.findByText("Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.")
    ).toBeVisible();
    expect(screen.queryByText(/PDF.*scan/u)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lập chỉ mục lại" })).toBeEnabled();
    expect(
      screen.getByText(/Tệp đã tải lên vẫn được giữ nguyên/u)
    ).toBeVisible();
  });

  it("renders a network failure with the stable public message", async () => {
    vi.mocked(apiGetCourseStatus).mockResolvedValue({
      course_id: "course-1",
      status: "error",
      error: "Failed to fetch",
      error_code: "NETWORK_UNAVAILABLE",
    });

    render(<CourseDashboardPage />);

    expect(
      await screen.findByText(
        "Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại."
      )
    ).toBeVisible();
    expect(screen.queryByText("Failed to fetch")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lập chỉ mục lại" })).toBeEnabled();
  });

  it("uses a connection-specific page-load recovery state", async () => {
    vi.mocked(apiGetCourseStatus).mockRejectedValue(new ApiNetworkError());

    render(<CourseDashboardPage />);

    expect(
      await screen.findByRole("heading", { name: "Không thể kết nối đến máy chủ" })
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Thử kết nối lại" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Không tìm thấy khóa học" })).not.toBeInTheDocument();
  });

  it("keeps the missing-course heading for an actual 404", async () => {
    vi.mocked(apiGetCourseStatus).mockRejectedValue(
      new ApiRequestError("Không tìm thấy khóa học.", 404)
    );

    render(<CourseDashboardPage />);

    expect(await screen.findByRole("heading", { name: "Không tìm thấy khóa học" })).toBeVisible();
  });

  it("asks for a replacement file instead of retrying unreadable PDF extraction", async () => {
    const user = userEvent.setup();
    vi.mocked(apiGetCourseStatus).mockResolvedValue({
      course_id: "course-1",
      status: "error",
      error: "Không thể đọc văn bản trong tệp.",
      error_code: "DOCUMENT_TEXT_EXTRACTION_FAILED",
      can_retry: true,
      recommended_action: "upload_clearer_pdf",
    });

    render(<CourseDashboardPage />);

    expect(
      await screen.findByText(/Thử lại cùng tệp này sẽ không giúp/u)
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Tải tệp thay thế" }));
    expect(apiRetryDocument).not.toHaveBeenCalled();
    expect(navigation.push).toHaveBeenCalledWith("/courses/create?replace=course-1");
  });

  it("falls back safely when the backend sends an unknown recommended action", async () => {
    vi.mocked(apiGetCourseStatus).mockResolvedValue({
      course_id: "course-1",
      status: "error",
      error: "Cần kiểm tra lại tài liệu.",
      can_retry: true,
      recommended_action: "unknown_backend_action" as never,
    });

    render(<CourseDashboardPage />);

    expect(await screen.findByText("Cần kiểm tra lại tài liệu.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Thử lập chỉ mục lại" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tải tệp thay thế" })).not.toBeInTheDocument();
  });

  it("does not overlap slow polls and stops after ready", async () => {
    vi.useFakeTimers();
    const slowPoll = deferred<{ course_id: string; status: string }>();
    vi.mocked(apiGetCourseStatus)
      .mockResolvedValueOnce({ course_id: "course-1", status: "processing" })
      .mockReturnValueOnce(slowPoll.promise)
      .mockResolvedValue({ course_id: "course-1", status: "ready" });

    render(<CourseDashboardPage />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Đang xử lý")).toBeVisible();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    expect(apiGetCourseStatus).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });
    expect(apiGetCourseStatus).toHaveBeenCalledTimes(2);

    slowPoll.resolve({ course_id: "course-1", status: "ready" });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Sẵn sàng")).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9_000);
    });
    expect(apiGetCourseStatus).toHaveBeenCalledTimes(2);
  });

  it("ignores an out-of-order poll after the course id changes", async () => {
    vi.useFakeTimers();
    const slowOldPoll = deferred<{ course_id: string; name: string; status: string }>();
    vi.mocked(apiGetCourseStatus).mockImplementation((courseId) => {
      if (courseId === "course-2") {
        return Promise.resolve({ course_id: "course-2", name: "Khóa 2", status: "ready" });
      }
      if (vi.mocked(apiGetCourseStatus).mock.calls.length === 1) {
        return Promise.resolve({ course_id: "course-1", name: "Khóa 1", status: "processing" });
      }
      return slowOldPoll.promise;
    });

    const { rerender } = render(<CourseDashboardPage />);
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(3_000);
    });
    navigation.courseId = "course-2";
    rerender(<CourseDashboardPage />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByRole("heading", { name: "Khóa 2" })).toBeVisible();

    slowOldPoll.resolve({ course_id: "course-1", name: "Khóa 1", status: "processing" });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByRole("heading", { name: "Khóa 2" })).toBeVisible();
  });

  it("retries a failed document and resumes course-status polling", async () => {
    const user = userEvent.setup();
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    let resolveRetry: (value: {
      document_id: string;
      status: "processing";
      stage: "extracting";
      progress: number;
      message: string;
      job_id: string;
    }) => void = () => undefined;
    vi.mocked(apiGetCourseStatus)
      .mockResolvedValueOnce({
        course_id: "course-1",
        status: "paused_due_to_quota",
        error: "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
        error_code: "OPENROUTER_KEY_LIMIT_EXCEEDED",
        can_retry: true,
        recommended_action: "restore_provider_quota",
      })
      .mockResolvedValueOnce({ course_id: "course-1", status: "processing" })
      .mockResolvedValueOnce({ course_id: "course-1", status: "ready" });
    vi.mocked(apiRetryDocument).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRetry = resolve;
        })
    );

    render(<CourseDashboardPage />);
    await user.click(
      await screen.findByRole("button", { name: "Thử lập chỉ mục lại" })
    );

    expect(apiRetryDocument).toHaveBeenCalledWith("course-1", expect.any(Object));
    expect(screen.getByRole("button", { name: "Đang thử lại" })).toBeDisabled();

    resolveRetry({
      document_id: "course-1",
      status: "processing",
      stage: "extracting",
      progress: 0,
      message: "Đang thử lại xử lý tài liệu từ tệp đã tải lên.",
      job_id: "job-1",
    });
    await waitFor(() => {
      expect(screen.getByText("Đang xử lý")).toBeVisible();
    });
    const pollCall = setTimeoutSpy.mock.calls.find(([, delay]) => delay === 3000);
    expect(pollCall).toBeDefined();
    await act(async () => {
      await (pollCall?.[0] as () => Promise<void>)();
    });
    expect(apiGetCourseStatus.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Sẵn sàng")).toBeVisible();
    setTimeoutSpy.mockRestore();
  });

  it("keeps an AbortError silent after the course page unmounts", async () => {
    let rejectStatus: (reason: unknown) => void = () => undefined;
    vi.mocked(apiGetCourseStatus).mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectStatus = reject;
        })
    );
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { unmount } = render(<CourseDashboardPage />);

    unmount();
    rejectStatus(new DOMException("The operation was aborted.", "AbortError"));
    await Promise.resolve();

    expect(screen.queryByText("The operation was aborted.")).not.toBeInTheDocument();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
