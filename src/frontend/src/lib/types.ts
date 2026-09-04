// ============================================================
// Auth Types
// ============================================================

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: "user" | "admin";
  is_active: boolean;
  is_verified: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
}

export interface RegisterResponse {
  email: string;
  message: string;
}

export interface VerifyEmailRequest {
  email: string;
  code: string;
}

export interface MessageResponse {
  message: string;
}

// ============================================================
// Course Types
// ============================================================

export interface CourseListItem {
  course_id: string;
  name?: string;
  status: string;
  created_at?: string;
  filenames?: string[];
  file_count?: number;
  error?: string;
  error_code?: CourseErrorCode | null;
}

export interface CoursesResponse {
  courses: CourseListItem[];
  total: number;
}

export interface CourseStatusResponse {
  course_id: string;
  name?: string;
  status: string;
  progress?: number;
  filename?: string;
  filenames?: string[];
  file_count?: number;
  created_at?: string;
  quality_score?: number;
  has_book?: boolean;
  has_slide?: boolean;
  has_quiz?: boolean;
  has_vid?: boolean;
  error?: string;
  failure_stage?: string;
  error_code?: CourseErrorCode | null;
  can_retry?: boolean;
  recommended_action?: DocumentRecommendedAction | null;
  job_id?: string;
}

export type DocumentFailureCode =
  | "AI_CONFIGURATION_ERROR"
  | "AI_ACCESS_DENIED"
  | "AI_QUOTA_EXHAUSTED"
  | "AI_RATE_LIMITED"
  | "AI_UNAVAILABLE"
  | "AI_TIMEOUT"
  | "AI_REQUEST_FAILED"
  | "DOCUMENT_TEXT_EXTRACTION_FAILED"
  | "DOCUMENT_SCHEDULING_FAILED"
  | "DOCUMENT_PROCESSING_FAILED"
  | "DOCUMENT_PROCESSING_PERSISTENCE_FAILED"
  | "DOCUMENT_PROCESSING_CANCELLED"
  | "INLINE_PROCESSING_INTERRUPTED"
  | "ARTIFACT_SOURCE_UNAVAILABLE"
  | "BOOK_GENERATION_FAILED"
  | "SLIDE_GENERATION_FAILED"
  | "QUIZ_GENERATION_FAILED"
  | "VIDEO_GENERATION_FAILED";

export type CourseErrorCode = DocumentFailureCode | "NETWORK_UNAVAILABLE";

const COURSE_ERROR_CODES: readonly CourseErrorCode[] = [
  "AI_CONFIGURATION_ERROR",
  "AI_ACCESS_DENIED",
  "AI_QUOTA_EXHAUSTED",
  "AI_RATE_LIMITED",
  "AI_UNAVAILABLE",
  "AI_TIMEOUT",
  "AI_REQUEST_FAILED",
  "DOCUMENT_TEXT_EXTRACTION_FAILED",
  "DOCUMENT_SCHEDULING_FAILED",
  "DOCUMENT_PROCESSING_FAILED",
  "DOCUMENT_PROCESSING_PERSISTENCE_FAILED",
  "DOCUMENT_PROCESSING_CANCELLED",
  "INLINE_PROCESSING_INTERRUPTED",
  "ARTIFACT_SOURCE_UNAVAILABLE",
  "BOOK_GENERATION_FAILED",
  "SLIDE_GENERATION_FAILED",
  "QUIZ_GENERATION_FAILED",
  "VIDEO_GENERATION_FAILED",
  "NETWORK_UNAVAILABLE",
];

export function normalizeCourseErrorCode(value: unknown): CourseErrorCode | null {
  return typeof value === "string" && (COURSE_ERROR_CODES as readonly string[]).includes(value)
    ? (value as CourseErrorCode)
    : null;
}

export const PUBLIC_ERROR_FALLBACK = "Xử lý tài liệu thất bại.";

const PUBLIC_ERROR_MESSAGES: Readonly<Record<CourseErrorCode, string>> = {
  AI_CONFIGURATION_ERROR: "Dịch vụ AI chưa được cấu hình hợp lệ. Vui lòng liên hệ quản trị viên.",
  AI_ACCESS_DENIED: "Dịch vụ AI không có quyền thực hiện yêu cầu này.",
  AI_QUOTA_EXHAUSTED: "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
  AI_RATE_LIMITED: "Dịch vụ AI đang bận. Tác vụ có thể thử lại sau.",
  AI_UNAVAILABLE: "Dịch vụ AI tạm thời không khả dụng.",
  AI_TIMEOUT: "Kết nối dịch vụ AI quá thời gian chờ.",
  AI_REQUEST_FAILED: "Không thể hoàn thành yêu cầu AI. Vui lòng thử lại.",
  DOCUMENT_TEXT_EXTRACTION_FAILED: "Không thể đọc văn bản trong tệp.",
  DOCUMENT_SCHEDULING_FAILED: "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại.",
  DOCUMENT_PROCESSING_FAILED: "Xử lý tài liệu thất bại.",
  DOCUMENT_PROCESSING_PERSISTENCE_FAILED: "Không thể lưu kết quả xử lý tài liệu. Vui lòng thử lại.",
  DOCUMENT_PROCESSING_CANCELLED: "Tài liệu đã bị hủy trước khi xử lý hoàn tất.",
  INLINE_PROCESSING_INTERRUPTED: "Tác vụ xử lý trước đó bị gián đoạn. Vui lòng thử lại.",
  ARTIFACT_SOURCE_UNAVAILABLE: "Không tìm thấy nội dung tài liệu đã lập chỉ mục để tạo học liệu.",
  BOOK_GENERATION_FAILED: "Không thể tạo sách ôn tập. Vui lòng thử lại.",
  SLIDE_GENERATION_FAILED: "Không thể tạo bài trình chiếu. Vui lòng thử lại.",
  QUIZ_GENERATION_FAILED: "Không thể tạo bài trắc nghiệm. Vui lòng thử lại.",
  VIDEO_GENERATION_FAILED: "Không thể tạo video. Vui lòng thử lại.",
  NETWORK_UNAVAILABLE: "Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.",
};

/** Convert an untrusted successful API status envelope into fixed product copy. */
export function normalizePublicError(
  value: unknown,
  fallback: string = PUBLIC_ERROR_FALLBACK
): string {
  return normalizeCourseErrorCode(value)
    ? PUBLIC_ERROR_MESSAGES[value as CourseErrorCode]
    : fallback;
}

export const DOCUMENT_RECOMMENDED_ACTIONS = [
  "restore_provider_quota",
  "retry_later",
  "upload_clearer_pdf",
  "contact_admin",
] as const;

export type DocumentRecommendedAction =
  (typeof DOCUMENT_RECOMMENDED_ACTIONS)[number];

export function normalizeDocumentRecommendedAction(
  value: unknown
): DocumentRecommendedAction | null {
  return typeof value === "string" &&
    (DOCUMENT_RECOMMENDED_ACTIONS as readonly string[]).includes(value)
    ? (value as DocumentRecommendedAction)
    : null;
}

export interface DocumentRetryResponse {
  document_id: string;
  status: "processing";
  stage: "extracting";
  progress: number;
  message: string;
  job_id: string;
}

export type JobType = "preprocess" | "book" | "slides" | "quiz" | "video";

export type JobStatus =
  | "queued"
  | "running"
  | "retry_scheduled"
  | "succeeded"
  | "failed"
  | "cancelled";

/** Owner-safe job envelope returned by the existing backend jobs endpoint.
 * `document_id` is the established backend name for the course/document id.
 * Internal queue, worker, payload, and provider fields are intentionally absent. */
export interface JobStatusResponse {
  id: string;
  document_id: string;
  job_type: JobType;
  status: JobStatus;
  queue_position?: number | null;
  progress: number;
  message: string;
  error?: string | null;
  error_code?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

// ============================================================
// Upload Types
// ============================================================

export interface UploadResponse {
  course_id: string;
  document_id: string;
  filename: string;
  filenames: string[];
  file_count: number;
  status: string;
  message: string;
}

// ============================================================
// Generation & Artifact Types
// ============================================================

export interface GenerateRequest {
  course_id?: string;
  [key: string]: unknown;
}

export interface GenerateResponse {
  course_id: string;
  job_id?: string | null;
  status?: string;
  message?: string;
  estimated_time?: string;
  version_id?: string | null;
}

export interface ArtifactVersion {
  version_id: string;
  label: string;
  options: Record<string, unknown>;
  status: "empty" | "processing" | "ready" | "error";
  error?: string | null;
  error_code?: CourseErrorCode | null;
  progress?: number | null;
  created_at?: string | null;
}

interface VersionedArtifactStatus {
  version_id?: string | null;
  active_version?: string | null;
  versions?: ArtifactVersion[];
}

export interface BookSection {
  title: string;
  content: string;
}

export interface BookChapter {
  chapter_title: string;
  introduction?: string;
  objectives?: string[];
  sections: BookSection[];
  key_points?: string[];
  review_questions?: string[];
  source_chunk_ids?: string[];
}

export interface BookOutput {
  title: string;
  summary: string;
  preface?: string;
  chapters: BookChapter[];
  description?: string;
  estimated_duration?: string;
}

export interface BookArtifactStatus extends VersionedArtifactStatus {
  status: "empty" | "processing" | "ready" | "error";
  error?: string | null;
  error_code?: CourseErrorCode | null;
  progress?: number | null;
  data: BookOutput | null;
}

export interface SlideItem {
  slide_number?: number;
  title: string;
  key_idea?: string;
  content?: string | string[];
  bullet_points?: string[];
  example?: string;
  layout_hint?: string;
  layout_type?: string;
  source_chunk_ids?: string[];
}

export interface SlidesOutput {
  title: string;
  slides: SlideItem[];
  total_slides?: number;
}

export interface SlideArtifactStatus extends VersionedArtifactStatus {
  status: "empty" | "processing" | "ready" | "error";
  error?: string | null;
  error_code?: CourseErrorCode | null;
  progress?: number | null;
  data: SlidesOutput | null;
}

export interface QuizOption {
  key?: string;
  text?: string;
}

export interface QuizQuestion {
  question_number?: number;
  question_text?: string;
  question?: string;
  options: (string | QuizOption)[];
  correct_answer?: string;
  correct?: number | string;
  explanation?: string;
  difficulty?: string;
  question_type?: string;
  source_chunk_ids?: string[];
}

export interface QuizOutput {
  title: string;
  questions: QuizQuestion[];
  total_questions?: number;
}

export interface QuizArtifactStatus extends VersionedArtifactStatus {
  status: "empty" | "processing" | "ready" | "error";
  error?: string | null;
  error_code?: CourseErrorCode | null;
  progress?: number | null;
  data: QuizQuestion[] | null;
}

export interface VidScene {
  scene_number: number;
  title: string;
  on_screen_text?: string;
  narration: string;
  duration_seconds: number;
}

export interface VidOutput {
  title: string;
  total_duration_seconds?: number;
  scenes: VidScene[];
}

export interface VidArtifactStatus extends VersionedArtifactStatus {
  status: "empty" | "processing" | "ready" | "error";
  error?: string | null;
  error_code?: CourseErrorCode | null;
  progress?: number | null;
  data: VidOutput | null;
}

// ============================================================
// Study Pack Types (for future use)
// ============================================================

export interface StudyPackStats {
  course_id: string;
  status: string;
  has_book: boolean;
  has_book_pdf: boolean;
  has_slide: boolean;
  has_slide_pptx: boolean;
  has_quiz: boolean;
  has_quiz_answer_key: boolean;
  has_vid: boolean;
  quality_score?: number;
  num_chunks?: number;
}

export interface StudyPackResponse {
  course_id: string;
  stats: StudyPackStats;
  study_pack: {
    title: string;
    book?: BookOutput;
    quiz?: QuizQuestion[];
    readiness?: Record<string, boolean>;
    quality_scores?: Record<string, number>;
    grounding?: {
      num_chunks: number;
      quality_score: number;
      warnings: string[];
    };
  };
}

// ============================================================
// API Error Types
// ============================================================

export interface ApiError {
  detail: string;
}

// ============================================================
// Component Prop Types
// ============================================================

export type CourseStatus = "processing" | "ready" | "error";

export function normalizeCourseStatus(status: string): CourseStatus {
  const s = status.toLowerCase();
  if (s === "ready" || s === "completed") return "ready";
  if (s === "error" || s === "failed" || s === "paused_due_to_quota") return "error";
  return "processing";
}
