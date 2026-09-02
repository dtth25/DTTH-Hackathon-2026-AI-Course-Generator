import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CourseCard } from "./CourseCard";
import { apiDeleteCourse, apiRenameCourse } from "@/lib/api";
import { toast } from "sonner";
import type { CourseListItem } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  apiDeleteCourse: vi.fn(),
  apiRenameCourse: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const course: CourseListItem = {
  course_id: "abc123def456",
  name: "Giáo trình Kiểm thử",
  status: "ready",
  filenames: ["tailieu.pdf"],
  file_count: 1,
  created_at: "2026-07-01T10:00:00",
};

const readyCourse: CourseListItem = {
  ...course,
  filenames: ["de-cuong.pdf", "ghi-chu.txt"],
  file_count: 2,
};

describe("CourseCard document treatment", () => {
  it("renders a course as a document object without promotional hover lift", () => {
    const { container } = render(<CourseCard course={readyCourse} />);

    expect(container.firstChild).toHaveAttribute("data-course-document");
    expect(container.innerHTML).not.toContain("-translate-y");
    expect(container.innerHTML).not.toMatch(/hover:shadow-/);
    expect(screen.getByText("2 tệp nguồn")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Xóa khóa học" })
    ).toBeInTheDocument();
  });
});

describe("CourseCard delete", () => {
  beforeEach(() => {
    vi.mocked(apiDeleteCourse).mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it("calls onDeleted and shows no error toast when delete succeeds", async () => {
    vi.mocked(apiDeleteCourse).mockResolvedValueOnce(undefined);
    const onDeleted = vi.fn();
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<CourseCard course={course} onDeleted={onDeleted} />);

    await user.click(
      screen.getByRole("button", { name: "Xóa khóa học" })
    );

    const confirmButton = await screen.findByRole("button", { name: "Xóa" });
    await user.click(confirmButton);

    await waitFor(() => expect(apiDeleteCourse).toHaveBeenCalledWith("abc123def456"));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("shows an error toast and does NOT call onDeleted when delete fails (regression guard for the silent-catch bug)", async () => {
    vi.mocked(apiDeleteCourse).mockRejectedValueOnce(new Error("Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau."));
    const onDeleted = vi.fn();
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<CourseCard course={course} onDeleted={onDeleted} />);

    await user.click(
      screen.getByRole("button", { name: "Xóa khóa học" })
    );

    const confirmButton = await screen.findByRole("button", { name: "Xóa" });
    await user.click(confirmButton);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau.")
    );
    expect(onDeleted).not.toHaveBeenCalled();
  });
});

describe("CourseCard rename", () => {
  beforeEach(() => {
    vi.mocked(apiRenameCourse).mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it("shows an error toast when rename fails instead of failing silently", async () => {
    vi.mocked(apiRenameCourse).mockRejectedValueOnce(new Error("Tên khóa học không được để trống."));
    const onRenamed = vi.fn();
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<CourseCard course={course} onRenamed={onRenamed} />);

    await user.click(screen.getByTitle("Đổi tên khóa học"));
    const input = await screen.findByPlaceholderText("Tên khóa học");
    await user.clear(input);
    await user.type(input, "Tên mới");
    await user.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Tên khóa học không được để trống.")
    );
    expect(onRenamed).not.toHaveBeenCalled();
  });
});
