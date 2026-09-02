import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CoursesPage from "./page";
import { apiGetCourses } from "@/lib/api";

vi.mock("@/components/auth/AuthGuard", () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("@/components/course/CourseCard", () => ({
  CourseCard: ({ course }: { course: { name?: string } }) => (
    <article>{course.name}</article>
  ),
}));

vi.mock("@/lib/api", () => ({
  apiGetCourses: vi.fn(),
}));

describe("courses visual states", () => {
  beforeEach(() => {
    vi.mocked(apiGetCourses).mockReset();
  });

  it("marks the resolved empty shelf for deterministic visual capture", async () => {
    vi.mocked(apiGetCourses).mockResolvedValue({ courses: [], total: 0 });
    const { container } = render(<CoursesPage />);

    await waitFor(() => {
      expect(
        container.querySelector('[data-visual-state="courses-empty"]')
      ).toBeInTheDocument();
    });
    expect(
      container.querySelector('[data-visual-state="courses-populated"]')
    ).not.toBeInTheDocument();
  });

  it("marks the resolved populated shelf for deterministic visual capture", async () => {
    vi.mocked(apiGetCourses).mockResolvedValue({
      courses: [
        {
          course_id: "course-1",
          name: "Sinh thái đô thị",
          status: "ready",
          filenames: ["sinh-thai.pdf"],
          file_count: 1,
        },
      ],
      total: 1,
    });
    const { container } = render(<CoursesPage />);

    await waitFor(() => {
      expect(
        container.querySelector('[data-visual-state="courses-populated"]')
      ).toBeInTheDocument();
    });
    expect(
      container.querySelector('[data-visual-state="courses-empty"]')
    ).not.toBeInTheDocument();
  });
});
