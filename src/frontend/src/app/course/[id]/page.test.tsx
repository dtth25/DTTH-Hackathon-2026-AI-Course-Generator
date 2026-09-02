import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseDashboardPage from "./page";
import { apiGetCourseStatus, apiGetStudyPack } from "@/lib/api";

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
});
