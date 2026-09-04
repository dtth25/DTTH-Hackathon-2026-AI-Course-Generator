import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiGenerateBook,
  apiGenerateQuiz,
  apiGenerateSlide,
  apiGenerateVid,
  apiGetBook,
  apiGetJob,
  apiGetQuiz,
  apiGetSlide,
  apiGetVid,
} from "@/lib/api";
import { BookTab } from "./BookTab";
import { QuizTab } from "./QuizTab";
import { SlideTab } from "./SlideTab";
import { VidTab } from "./VidTab";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

vi.mock("@/lib/api", () => ({
  ApiRequestError: class ApiRequestError extends Error {
    status: number;
    detail: unknown;
    constructor(message: string, status: number, detail?: unknown) {
      super(message);
      this.status = status;
      this.detail = detail;
    }
  },
  apiCancelJob: vi.fn(),
  apiDeleteArtifactVersion: vi.fn(),
  apiGenerateBook: vi.fn(),
  apiGenerateQuiz: vi.fn(),
  apiGenerateSlide: vi.fn(),
  apiGenerateVid: vi.fn(),
  apiGetBook: vi.fn(),
  apiGetJob: vi.fn(),
  apiGetQuiz: vi.fn(),
  apiGetSlide: vi.fn(),
  apiGetVid: vi.fn(),
  apiRenameArtifactVersion: vi.fn(),
  getDownloadBookUrl: vi.fn(() => "/book.pdf"),
  getDownloadQuizKeyUrl: vi.fn(() => "/quiz.pdf"),
  getDownloadSlidePdfUrl: vi.fn(() => "/slides.pdf"),
  getDownloadSlideUrl: vi.fn(() => "/slides.pptx"),
  getDownloadVidMp4Url: vi.fn(() => "/video.mp4"),
  getSlideImageUrl: vi.fn(() => "/slide.png"),
}));

const versions = [
  { version_id: "old-v1", label: "Bản cũ 1", options: {}, status: "ready" as const, progress: 100 },
  { version_id: "old-v2", label: "Bản cũ 2", options: {}, status: "ready" as const, progress: 100 },
  { version_id: "reserved-v3", label: "Bản đang thử", options: {}, status: "error" as const, progress: 23 },
];

const failedJob = {
  id: "failed-job",
  document_id: "course-1",
  job_type: "book" as const,
  status: "failed" as const,
  progress: 23,
  message: "private worker failure",
  error_code: "BOOK_GENERATION_FAILED",
  created_at: "2026-09-05T00:00:00Z",
  updated_at: "2026-09-05T00:00:03Z",
};

type Case = {
  name: string;
  component: React.ReactElement;
  createButton: string;
  initialSubmit: string;
  getArtifact: ReturnType<typeof vi.fn>;
  generate: ReturnType<typeof vi.fn>;
  data: unknown;
  jobType: "book" | "slides" | "quiz" | "video";
};

const cases: Case[] = [
  {
    name: "Book",
    component: <BookTab courseId="course-1" />,
    createButton: "Tạo mới sách ôn tập",
    initialSubmit: "Tạo sách ôn tập",
    getArtifact: vi.mocked(apiGetBook),
    generate: vi.mocked(apiGenerateBook),
    data: { title: "Sách", summary: "Tóm tắt", chapters: [{ chapter_title: "Chương", sections: [] }] },
    jobType: "book",
  },
  {
    name: "Slide",
    component: <SlideTab courseId="course-1" />,
    createButton: "Tạo mới bộ slide",
    initialSubmit: "Tạo slide bài giảng",
    getArtifact: vi.mocked(apiGetSlide),
    generate: vi.mocked(apiGenerateSlide),
    data: { title: "Slide", slides: [{ title: "Trang 1" }] },
    jobType: "slides",
  },
  {
    name: "Quiz",
    component: <QuizTab courseId="course-1" />,
    createButton: "Tạo mới bộ câu hỏi",
    initialSubmit: "Tạo trắc nghiệm",
    getArtifact: vi.mocked(apiGetQuiz),
    generate: vi.mocked(apiGenerateQuiz),
    data: [{ question: "Câu hỏi?", options: ["A", "B"], correct: "A" }],
    jobType: "quiz",
  },
  {
    name: "Vid",
    component: <VidTab courseId="course-1" />,
    createButton: "Tạo mới video",
    initialSubmit: "Tạo video bài giảng",
    getArtifact: vi.mocked(apiGetVid),
    generate: vi.mocked(apiGenerateVid),
    data: { title: "Video", scenes: [{ scene_number: 1, title: "Cảnh", narration: "Lời", duration_seconds: 1 }] },
    jobType: "video",
  },
];

describe("artifact terminal-job retry identity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiGetJob).mockImplementation(async () => failedJob);
  });

  for (const testCase of cases) {
    it(`${testCase.name} retries the reserved failed version while another version is viewed`, async () => {
      const user = userEvent.setup();
      testCase.getArtifact.mockImplementation(async (_courseId: string, version?: string | null) => ({
        status: "ready",
        progress: 100,
        version_id: version ?? "old-v1",
        active_version: "old-v1",
        versions,
        data: testCase.data,
      }));
      testCase.generate.mockResolvedValue({
        course_id: "course-1",
        version_id: "reserved-v3",
        job_id: "failed-job",
      });
      vi.mocked(apiGetJob).mockResolvedValue({ ...failedJob, job_type: testCase.jobType });

      render(testCase.component);
      await user.click(await screen.findByRole("button", { name: testCase.createButton }));
      await user.click(screen.getByRole("button", { name: "Tạo phiên bản mới" }));
      await screen.findByRole("button", { name: "Thử lại" });
      await user.click(screen.getByRole("button", { name: /Bản cũ 2/u }));
      await user.click(await screen.findByRole("button", { name: "Thử lại" }));
      await user.click(screen.getByRole("button", { name: "Tạo phiên bản mới" }));

      await waitFor(() => expect(testCase.generate).toHaveBeenCalledTimes(2));
      expect(testCase.generate.mock.calls[1]?.[1]).toEqual(
        expect.objectContaining({ retry_version_id: "reserved-v3" })
      );
      expect(testCase.generate.mock.calls[1]?.[1]).not.toEqual(
        expect.objectContaining({ retry_version_id: "old-v2" })
      );
    });
  }

  it("Book clears a dismissed terminal retry before a fresh create", async () => {
    const user = userEvent.setup();
    vi.mocked(apiGetBook).mockResolvedValue({
      status: "ready",
      progress: 100,
      version_id: "old-v1",
      active_version: "old-v1",
      versions,
      data: cases[0].data as never,
    });
    vi.mocked(apiGenerateBook).mockResolvedValue({
      course_id: "course-1",
      version_id: "reserved-v3",
      job_id: "failed-job",
    });

    render(<BookTab courseId="course-1" />);
    await user.click(await screen.findByRole("button", { name: "Tạo mới sách ôn tập" }));
    await user.click(screen.getByRole("button", { name: "Tạo phiên bản mới" }));
    await user.click(await screen.findByRole("button", { name: "Thử lại" }));
    await user.click(screen.getByRole("button", { name: "Hủy" }));
    await user.click(screen.getByRole("button", { name: "Tạo mới sách ôn tập" }));
    await user.click(screen.getByRole("button", { name: "Tạo phiên bản mới" }));

    await waitFor(() => expect(apiGenerateBook).toHaveBeenCalledTimes(2));
    expect(vi.mocked(apiGenerateBook).mock.calls[1]?.[1]).not.toHaveProperty("retry_version_id");
  });
});

describe("empty artifact terminal-job retry identity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  for (const testCase of cases) {
    const terminalStatus = testCase.name === "Vid" ? "cancelled" as const : "failed" as const;
    const retryButton = terminalStatus === "cancelled" ? "Tạo lại" : "Thử lại";

    it(`${testCase.name} reuses the first reserved version after a ${terminalStatus} job`, async () => {
      const user = userEvent.setup();
      testCase.getArtifact.mockResolvedValue({
        status: "empty",
        progress: 0,
        version_id: null,
        active_version: null,
        versions: [],
        data: null,
      });
      testCase.generate.mockResolvedValue({
        course_id: "course-1",
        version_id: "first-reserved-v1",
        job_id: "first-terminal-job",
      });
      vi.mocked(apiGetJob).mockResolvedValue({
        ...failedJob,
        id: "first-terminal-job",
        job_type: testCase.jobType,
        status: terminalStatus,
      });

      render(testCase.component);
      await user.click(await screen.findByRole("button", { name: testCase.initialSubmit }));
      await waitFor(() => expect(testCase.generate).toHaveBeenCalledTimes(1));
      expect(testCase.generate.mock.calls[0]?.[1]).not.toHaveProperty("retry_version_id");

      await user.click(await screen.findByRole("button", { name: retryButton }));
      await user.click(await screen.findByRole("button", { name: testCase.initialSubmit }));

      await waitFor(() => expect(testCase.generate).toHaveBeenCalledTimes(2));
      expect(testCase.generate.mock.calls[1]?.[1]).toEqual(
        expect.objectContaining({ retry_version_id: "first-reserved-v1" })
      );
    });
  }
});
