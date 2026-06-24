/**
 * API configuration and endpoints for backend communication.
 */

export const API_BASE_URL = "http://localhost:8001";

export const ENDPOINTS = {
  upload: `${API_BASE_URL}/api/upload`,
  courseStatus: (courseId: string) =>
    `${API_BASE_URL}/api/course/${courseId}/status`,
  generateCourse: `${API_BASE_URL}/api/generate-course`,
  generateSummary: `${API_BASE_URL}/api/generate-summary`,
  generateFlashcards: `${API_BASE_URL}/api/generate-flashcards`,
  generateQuiz: `${API_BASE_URL}/api/generate-quiz`,
  generateSlides: `${API_BASE_URL}/api/generate-slides`,
  generateMindmap: `${API_BASE_URL}/api/generate-mindmap`,
  customPrompt: `${API_BASE_URL}/api/custom-prompt`,
  getCoursesAll: `${API_BASE_URL}/api/courses/all`,
  getCourse: (id: string) => `${API_BASE_URL}/api/course/${id}/course`,
  getCourseStatus: (id: string) => `${API_BASE_URL}/api/course/${id}/status`,
} as const;

export type Citation = {
  page?: number | string;
  source?: string;
  chunk_id?: number | string;
};

/* ── Types ─────────────────────────────────────────────── */

/** Một bài học trong chapter */
export interface Lesson {
  title: string;
}

/** Một chapter trong course */
export interface Chapter {
  title: string;
  lessons: Lesson[];
}

/** Course detail trả về từ GET /api/course/{course_id}/course */
export interface CourseDetail {
  title: string;
  description?: string;
  chapters: Chapter[];
}

/** Response từ GET /api/course/{course_id}/course */
export interface CourseResponse {
  course_id: string;
  course: CourseDetail;
  citations?: Array<{ page: number; source: string; chunk_id: string }>;
}

/** Một item trong danh sách courses (GET /api/courses/all) */
export interface CourseListItem {
  course_id: string;
  status: string;
  pdf_path?: string;
  created_at?: string;
}

/** Response từ GET /api/courses/all */
export interface CourseListResponse {
  courses: CourseListItem[];
  total: number;
}

/* ── Course Generation Types ───────────────────────────── */

/** Request body cho POST /api/generate-course */
export interface GenerateCourseRequest {
  file_id: string;
  user_prompt?: string;
}

/** Response từ POST /api/generate-course */
export interface GenerateCourseResponse {
  course_title: string;
  chapters: Array<{ id: number; title: string; lessons: string[] }>;
  total_slides: number;
  citations: Array<{ page: number; source: string; chunk_id: string }>;
}

/* ── Slides Types ──────────────────────────────────────── */

/** Một slide trong response */
export interface SlideItem {
  title: string;
  content: string;
  layout_hint?: string;
  image_suggestion?: string;
  citation?: {
    page: number | string;
    source: string;
    chunk_id: string;
  };
}

/** Response từ POST /api/generate-slides */
export interface SlidesResponse {
  course_id: string;
  topic: string;
  total_slides: number;
  slides: SlideItem[];
  citations: Array<{ page: number; source: string; chunk_id: string }>;
}

/**
 * Generate slides from course.
 * POST /api/generate-slides
 */
export async function generateSlides(
  courseId: string,
  topic: string = "tổng quan",
  numSlides: number = 10
): Promise<SlidesResponse> {
  const response = await fetch(ENDPOINTS.generateSlides, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      course_id: courseId,
      topic,
      num_slides: numSlides,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.message || `Lỗi tạo slides: ${response.statusText}`);
  }

  return response.json();
}

/* ── Flashcards Types ──────────────────────────────────── */

/** Một flashcard */
export interface FlashcardItem {
  question: string;
  answer: string;
  citation?: {
    page: number | string;
    source: string;
    chunk_id: string;
  };
}

/** Response từ POST /api/generate-flashcards */
export interface FlashcardsResponse {
  course_id: string;
  total: number;
  flashcards: FlashcardItem[];
  citations: Array<{ page: number | string; source: string; chunk_id: string }>;
}

/**
 * Generate flashcards from course.
 * POST /api/generate-flashcards
 */
export async function generateFlashcards(
  courseId: string,
  count: number = 12
): Promise<FlashcardsResponse> {
  const response = await fetch(ENDPOINTS.generateFlashcards, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      course_id: courseId,
      count,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.message || `Lỗi tạo flashcards: ${response.statusText}`);
  }

  return response.json();
}

/* ── Mindmap Types ─────────────────────────────────────── */

export interface MindmapNode {
  title: string;
  children?: (MindmapNode | string)[];
}

export interface MindmapData {
  central_topic: string;
  branches: MindmapNode[];
}

/** Response từ POST /api/generate-mindmap */
export interface MindmapResponse {
  course_id: string;
  mindmap: MindmapData;
  citations: Array<{ page: number | string; source: string; chunk_id: string }>;
}

/**
 * Generate mindmap from course.
 * POST /api/generate-mindmap
 */
export async function generateMindmap(
  courseId: string,
  maxDepth: number = 3
): Promise<MindmapResponse> {
  const response = await fetch(ENDPOINTS.generateMindmap, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      course_id: courseId,
      max_depth: maxDepth,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.message || `Lỗi tạo mindmap: ${response.statusText}`);
  }

  return response.json();
}

/* ── Quiz Types ────────────────────────────────────────── */

/** Một câu hỏi trong quiz */
export interface QuizQuestion {
  question: string;
  options: string[];
  correct: number;
  explanation: string;
}

/** Response từ POST /api/generate-quiz */
export interface QuizResponse {
  course_id: string;
  topic: string;
  difficulty: string;
  questions: QuizQuestion[];
  total_questions: number;
  citations?: Array<{ page: number; source: string; chunk_id: string }>;
}

/** Generic response parser with error handling */
async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(
      err?.detail || err?.message || `HTTP ${response.status}: ${response.statusText}`
    );
  }
  return response.json();
}

/* ── Fetch helpers ─────────────────────────────────────── */

/**
 * Fetch danh sách tất cả courses.
 * GET /api/courses/all
 */
export async function getCoursesAll(): Promise<CourseListResponse> {
  const response = await fetch(ENDPOINTS.getCoursesAll);
  if (!response.ok) {
    throw new Error(`Không thể lấy danh sách khóa học: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch chi tiết một course (chapters + lessons).
 * GET /api/course/{course_id}/course
 */
export async function getCourse(id: string): Promise<CourseResponse> {
  const response = await fetch(ENDPOINTS.getCourse(id));
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("NOT_FOUND");
    }
    throw new Error(`Lỗi lấy khóa học: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Generate course từ file đã upload.
 * POST /api/generate-course
 */
export async function generateCourse(
  fileId: string,
  userPrompt?: string
): Promise<GenerateCourseResponse> {
  const response = await fetch(ENDPOINTS.generateCourse, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      user_prompt: userPrompt,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(
      err?.message || `Lỗi tạo khóa học: ${response.statusText}`
    );
  }

  return response.json();
}

/**
 * Generate quiz từ course.
 * POST /api/generate-quiz
 */
export async function generateQuiz(
  courseId: string,
  topic: string = "Kiến thức tổng quát",
  quantity: number = 10,
  difficulty: string = "medium"
): Promise<QuizResponse> {
  const response = await fetch(ENDPOINTS.generateQuiz, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      course_id: courseId,
      topic,
      quantity,
      difficulty,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => null);
    throw new Error(err?.message || `Lỗi tạo quiz: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Upload files to backend.
 * POST /api/upload
 * Response: { file_id: string, pages: number, status: string }
 */
/** Response từ POST /api/upload */
export interface UploadResponse {
  course_id: string;
  filename: string;
  status: string;
  message: string;
}

/** Response từ GET /api/course/{course_id}/status */
export interface CourseStatusResponse {
  course_id: string;
  status: string;
  error?: string;
}

/** Response type cho generate content */
export type GenerateResponse = Record<string, unknown>;

/** Feature types for generateContent */
export type GenerateFeature = "course" | "summary" | "flashcards" | "quiz" | "slides" | "mindmap" | "custom";

/**
 * Upload a single file to backend.
 * POST /api/upload
 */
export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(ENDPOINTS.upload, {
    method: "POST",
    body: formData,
  });

  return parseResponse<UploadResponse>(response);
}

/**
 * Upload multiple files (uses first file only, matching backend's single-file API).
 * POST /api/upload
 */
export async function uploadFiles(files: File[]): Promise<UploadResponse> {
  if (files.length === 0) {
    throw new Error("Không có file để tải lên.");
  }
  return uploadFile(files[0]);
}

export async function getCourseStatus(
  courseId: string
): Promise<CourseStatusResponse> {
  const response = await fetch(ENDPOINTS.courseStatus(courseId), {
    cache: "no-store",
  });

  return parseResponse<CourseStatusResponse>(response);
}

export async function generateContent(
  feature: GenerateFeature,
  courseId: string,
  prompt: string
): Promise<GenerateResponse> {
  const topic = prompt || "tổng quan";

  const config: Record<
    GenerateFeature,
    { endpoint: string; body: Record<string, unknown> }
  > = {
    course: {
      endpoint: ENDPOINTS.generateCourse,
      body: {
        course_id: courseId,
        user_prompt: prompt,
        target_audience: "sinh viên",
      },
    },
    summary: {
      endpoint: ENDPOINTS.generateSummary,
      body: { course_id: courseId, type: "detailed" },
    },
    flashcards: {
      endpoint: ENDPOINTS.generateFlashcards,
      body: { course_id: courseId, count: 8 },
    },
    quiz: {
      endpoint: ENDPOINTS.generateQuiz,
      body: {
        course_id: courseId,
        topic,
        quantity: 10,
        difficulty: "medium",
      },
    },
    slides: {
      endpoint: ENDPOINTS.generateSlides,
      body: { course_id: courseId, topic, num_slides: 8 },
    },
    mindmap: {
      endpoint: ENDPOINTS.generateMindmap,
      body: { course_id: courseId, max_depth: 3 },
    },
    custom: {
      endpoint: ENDPOINTS.customPrompt,
      body: { course_id: courseId, prompt: topic },
    },
  };

  const { endpoint, body } = config[feature];
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return parseResponse<GenerateResponse>(response);
}
