import type {
  BookArtifactStatus,
  CoursesResponse,
  CourseStatusResponse,
  StudyPackResponse,
  VidArtifactStatus,
} from "@/lib/types";

export const DEMO_COURSE_LIST = {
  courses: [
    {
      course_id: "demo-course",
      name: "Nhập môn sinh thái đô thị",
      status: "ready",
      filenames: ["chuong-1.pdf", "ghi-chu.txt"],
      file_count: 2,
      created_at: "2026-08-30T08:00:00Z",
    },
  ],
  total: 1,
} satisfies CoursesResponse;

export const DEMO_STATUS = {
  course_id: "demo-course",
  name: "Nhập môn sinh thái đô thị",
  status: "ready",
  progress: 100,
  filenames: ["chuong-1.pdf", "ghi-chu.txt"],
  file_count: 2,
  has_book: true,
  has_slide: true,
  has_quiz: true,
  has_vid: true,
} satisfies CourseStatusResponse;

export const DEMO_BOOK_STATUS = {
  status: "ready",
  progress: 100,
  version_id: "book-v1",
  active_version: "book-v1",
  versions: [
    {
      version_id: "book-v1",
      label: "Bản đọc đầu tiên",
      options: {},
      status: "ready",
      progress: 100,
    },
  ],
  data: {
    title: "Nhập môn sinh thái đô thị",
    summary: "Cách hệ sinh thái vận hành trong không gian đô thị.",
    chapters: [
      {
        chapter_title: "Dòng năng lượng",
        sections: [
          {
            title: "Nguồn và dòng",
            content:
              "Năng lượng đi qua các bậc dinh dưỡng trong hệ sinh thái.",
          },
        ],
      },
      {
        chapter_title: "Đa dạng sinh học",
        sections: [
          {
            title: "Sinh cảnh",
            content:
              "Mỗi sinh cảnh đô thị tạo điều kiện sống khác nhau.",
          },
        ],
      },
    ],
  },
} satisfies BookArtifactStatus;

export const DEMO_VID_STATUS = {
  status: "processing",
  progress: 64,
  version_id: "vid-v1",
  active_version: "vid-v1",
  data: null,
  versions: [
    {
      version_id: "vid-v1",
      label: "Video tổng quan",
      options: {},
      status: "processing",
      progress: 64,
    },
  ],
} satisfies VidArtifactStatus;

export const DEMO_STUDY_PACK = {
  course_id: "demo-course",
  stats: {
    course_id: "demo-course",
    status: "ready",
    has_book: true,
    has_book_pdf: true,
    has_slide: true,
    has_slide_pptx: true,
    has_quiz: true,
    has_quiz_answer_key: true,
    has_vid: true,
    num_chunks: 42,
  },
  study_pack: {
    title: "Nhập môn sinh thái đô thị",
    book: DEMO_BOOK_STATUS.data ?? undefined,
    readiness: { book: true, slide: true, quiz: true, vid: true },
  },
} satisfies StudyPackResponse;
