import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseDashboardPage from "./page";
import {
  apiGetCourseStatus,
  apiGetStudyPack,
  apiRetryDocument,
} from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "course-1" }),
  useRouter: () => ({ push: vi.fn() }),
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
}));

describe("course workspace", () => {
  beforeEach(() => {
    vi.mocked(apiGetCourseStatus).mockResolvedValue({
      course_id: "course-1",
      name: "Sinh thái đô thị",
      status: "ready",
      filenames: ["sinh-thai.pdf", "ghi-chu.txt"],
      file_count: 2,
    });
    vi.mocked(apiGetStudyPack).mockRejectedValue(new Error("Chưa có học liệu"));
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

  it("retries a failed document and resumes course-status polling", async () => {
    const user = userEvent.setup();
    const setIntervalSpy = vi.spyOn(window, "setInterval");
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

    expect(apiRetryDocument).toHaveBeenCalledWith("course-1");
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
    const pollCall = setIntervalSpy.mock.calls.find(([, delay]) => delay === 3000);
    expect(pollCall).toBeDefined();
    await act(async () => {
      await (pollCall?.[0] as () => Promise<void>)();
    });
    expect(apiGetCourseStatus.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Sẵn sàng")).toBeVisible();
    setIntervalSpy.mockRestore();
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
