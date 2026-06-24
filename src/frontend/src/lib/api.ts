/**
 * API client for the four public outputs: Book, Slide, Quiz, and Vid.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const ENDPOINTS = {
  upload: `${API_BASE_URL}/api/upload`,
  getCoursesAll: `${API_BASE_URL}/api/courses/all`,
  courseStatus: (courseId: string) =>
    `${API_BASE_URL}/api/course/${courseId}/status`,
  generateBook: `${API_BASE_URL}/api/generate-book`,
  generateSlide: `${API_BASE_URL}/api/generate-slide`,
  generateQuiz: `${API_BASE_URL}/api/generate-quiz`,
  generateVid: `${API_BASE_URL}/api/generate-vid`,
  getBook: (courseId: string) => `${API_BASE_URL}/api/course/${courseId}/book`,
  getBookPdf: (courseId: string) =>
    `${API_BASE_URL}/api/course/${courseId}/book.pdf`,
  getVidFile: (courseId: string) =>
    `${API_BASE_URL}/api/course/${courseId}/vid/file`,
} as const;

export type GenerateFeature = "book" | "slide" | "quiz" | "vid";

export interface UploadResponse {
  course_id: string;
  filename: string;
  status: string;
  message: string;
}

export interface CourseStatusResponse {
  course_id: string;
  status: "pending" | "processing" | "ready" | "failed" | "unknown";
  error?: string;
}

export interface CourseListItem {
  course_id: string;
  status: string;
  created_at?: string | number;
  error?: string;
}

export interface CourseListResponse {
  courses: CourseListItem[];
  total: number;
}

export interface BookLesson {
  title: string;
  duration?: string;
  objectives?: string[];
  lecture?: string;
  key_points?: string[];
  activity?: string;
  assessment?: string[];
}

export interface BookChapter {
  title: string;
  description?: string;
  lessons: BookLesson[];
}

export interface BookOutput {
  title: string;
  description?: string;
  estimated_duration?: string;
  chapters: BookChapter[];
}

export interface SlideItem {
  title: string;
  content: string;
  layout_hint?: string;
  image_suggestion?: string;
}

export interface QuizQuestion {
  question: string;
  options: string[];
  correct: number;
  explanation: string;
  difficulty?: string;
}

export interface VidScene {
  title: string;
  visual_text: string;
  voiceover: string;
}

export interface VidOutput {
  filename: string;
  url: string;
  duration_minutes: number;
  estimated_duration_seconds?: number;
  voiceover_status?: string;
  scenes: VidScene[];
}

export interface GenerateResponse {
  course_id: string;
  book?: BookOutput;
  pdf_url?: string;
  topic?: string;
  total_slides?: number;
  slides?: SlideItem[];
  difficulty?: string;
  total_questions?: number;
  questions?: QuizQuestion[];
  vid?: VidOutput;
}

export interface QuizResponse extends GenerateResponse {
  topic: string;
  difficulty: string;
  questions: QuizQuestion[];
  total_questions: number;
}

export interface CourseResponse {
  course_id: string;
  book: BookOutput;
  pdf_url?: string | null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      payload?.detail ??
      payload?.message ??
      payload?.error ??
      `Request failed: ${response.statusText}`;
    throw new Error(message);
  }

  return payload as T;
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(ENDPOINTS.upload, {
    method: "POST",
    body: formData,
  });

  return parseResponse<UploadResponse>(response);
}

export async function getCourseStatus(
  courseId: string
): Promise<CourseStatusResponse> {
  const response = await fetch(ENDPOINTS.courseStatus(courseId), {
    cache: "no-store",
  });

  return parseResponse<CourseStatusResponse>(response);
}

export async function getCoursesAll(): Promise<CourseListResponse> {
  const response = await fetch(ENDPOINTS.getCoursesAll, {
    cache: "no-store",
  });

  return parseResponse<CourseListResponse>(response);
}

export async function getBook(courseId: string): Promise<CourseResponse> {
  const response = await fetch(ENDPOINTS.getBook(courseId), {
    cache: "no-store",
  });

  return parseResponse<CourseResponse>(response);
}

export const getCourse = getBook;

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

  return parseResponse<QuizResponse>(response);
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
    book: {
      endpoint: ENDPOINTS.generateBook,
      body: {
        course_id: courseId,
        user_prompt: prompt,
        target_audience: "sinh viên",
      },
    },
    slide: {
      endpoint: ENDPOINTS.generateSlide,
      body: { course_id: courseId, topic, num_slides: 8 },
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
    vid: {
      endpoint: ENDPOINTS.generateVid,
      body: { course_id: courseId, topic, duration_minutes: 3 },
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
