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
  error_code?: DocumentFailureCode | "NETWORK_UNAVAILABLE" | string;
  can_retry?: boolean;
  recommended_action?: "restore_provider_quota" | "retry_later" | string;
  job_id?: string;
}

export type DocumentFailureCode =
  | "OPENROUTER_KEY_INVALID"
  | "OPENROUTER_KEY_LIMIT_EXCEEDED"
  | "OPENROUTER_CREDITS_EXHAUSTED"
  | "OPENROUTER_ACCESS_DENIED"
  | "OPENROUTER_RATE_LIMITED"
  | "OPENROUTER_UNAVAILABLE"
  | "OPENROUTER_TIMEOUT"
  | "DOCUMENT_TEXT_EXTRACTION_FAILED"
  | "OPENROUTER_REQUEST_FAILED";

export interface DocumentRetryResponse {
  document_id: string;
  status: "processing";
  stage: "extracting";
  progress: number;
  message: string;
  job_id: string;
}

export interface JobResponse {
  id: string;
  document_id: string;
  user_id?: string | null;
  job_type: string;
  status: string;
  progress: number;
  message: string;
  error?: string | null;
  error_code?: DocumentFailureCode | string | null;
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
