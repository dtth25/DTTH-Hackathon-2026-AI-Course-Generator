import { getAuthHeaders, removeToken, getToken } from "@/lib/auth";
import type {
  AuthResponse,
  LoginRequest,
  RegisterRequest,
  RegisterResponse,
  VerifyEmailRequest,
  MessageResponse,
  CoursesResponse,
  CourseStatusResponse,
  UploadResponse,
  StudyPackResponse,
  User,
  GenerateResponse,
  BookArtifactStatus,
  SlideArtifactStatus,
  QuizArtifactStatus,
  VidArtifactStatus,
  DocumentRetryResponse,
  JobResponse,
} from "@/lib/types";

/** Thrown by apiFetch on any non-2xx response. Carries the raw `detail` payload
 * (string or structured object, e.g. `{code, message}`) so callers can branch on
 * it instead of parsing `.message` back out. */
export type ApiErrorCode =
  | "UNKNOWN_ERROR"
  | "FORBIDDEN"
  | "SOURCE_FILE_MISSING"
  | "DOCUMENT_RETRY_NOT_ALLOWED"
  | "DOCUMENT_RETRY_UNAVAILABLE"
  | "DOCUMENT_SCHEDULING_FAILED"
  | "email_not_verified"
  | "version_cap_reached";

const SAFE_HTTP_ERROR_MESSAGES: Partial<Record<ApiErrorCode, string>> = {
  FORBIDDEN: "Bạn không có quyền truy cập tài nguyên này.",
  SOURCE_FILE_MISSING: "Không tìm thấy tệp nguồn đã tải lên.",
  DOCUMENT_RETRY_NOT_ALLOWED: "Tài liệu chưa ở trạng thái có thể thử lại.",
  DOCUMENT_RETRY_UNAVAILABLE: "Không thể bắt đầu thử lại tài liệu.",
  DOCUMENT_SCHEDULING_FAILED: "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại.",
  email_not_verified: "Email chưa được xác thực. Vui lòng xác thực ngay.",
};

const SAFE_HTTP_ERROR_CODES = new Set<ApiErrorCode>([
  "SOURCE_FILE_MISSING",
  "DOCUMENT_RETRY_NOT_ALLOWED",
  "DOCUMENT_RETRY_UNAVAILABLE",
  "DOCUMENT_SCHEDULING_FAILED",
  "email_not_verified",
  "version_cap_reached",
]);

/** A typed HTTP failure. `detail` is retained only for programmatic branching;
 * `.message` is always an allowlisted public message or a stable fallback. */
export class ApiRequestError extends Error {
  status: number;
  detail: unknown;
  code: ApiErrorCode;

  constructor(message: string, status: number, detail?: unknown, code: ApiErrorCode = "UNKNOWN_ERROR") {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

export const NETWORK_UNAVAILABLE_MESSAGE =
  "Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.";

/** A stable, public error for browser/proxy/CORS failures before an HTTP response exists. */
export class ApiNetworkError extends Error {
  readonly code = "NETWORK_UNAVAILABLE" as const;

  constructor() {
    super(NETWORK_UNAVAILABLE_MESSAGE);
    this.name = "ApiNetworkError";
  }
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

function safeHttpErrorCode(detail: unknown, status: number): ApiErrorCode {
  if (detail && typeof detail === "object" && "code" in detail) {
    const code = (detail as { code?: unknown }).code;
    if (typeof code === "string" && SAFE_HTTP_ERROR_CODES.has(code as ApiErrorCode)) {
      return code as ApiErrorCode;
    }
  }
  return status === 403 ? "FORBIDDEN" : "UNKNOWN_ERROR";
}

function safeHttpErrorMessage(code: ApiErrorCode): string {
  return SAFE_HTTP_ERROR_MESSAGES[code] ?? "Đã xảy ra lỗi. Vui lòng thử lại.";
}

// Base URL for the FastAPI backend. Prefer the documented public env vars;
// fall back to same-origin in production builds, or the conventional local
// backend port in dev. `??` (not `||`) so an explicitly blank
// NEXT_PUBLIC_API_BASE_URL still means same-origin. The NODE_ENV-based final
// fallback matters because a production build that never had NEXT_PUBLIC_*
// injected (e.g. `npm run build` run directly, outside `docker compose
// build`'s build-arg pipeline) must NOT silently default to
// "http://localhost:8000" — that resolves to each visitor's own machine, not
// the server, and breaks every request with "Failed to fetch".
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

// ============================================================
// Core Fetch Wrapper
// ============================================================

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const headers: Record<string, string> = {
    ...getAuthHeaders(),
    ...((init?.headers as Record<string, string>) || {}),
  };

  if (!(init?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    if (error instanceof TypeError) throw new ApiNetworkError();
    throw error;
  }

  const isAuthEndpoint =
    path === "/api/auth/login" || path === "/api/auth/register";

  if (response.status === 401 && !isAuthEndpoint) {
    removeToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail;
    } catch {
      // The stable fallback deliberately avoids rendering arbitrary HTTP payloads.
    }
    const code = safeHttpErrorCode(detail, response.status);
    throw new ApiRequestError(safeHttpErrorMessage(code), response.status, detail, code);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ============================================================
// Auth API
// ============================================================

export async function apiLogin(data: LoginRequest): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function apiRegister(
  data: RegisterRequest
): Promise<RegisterResponse> {
  return apiFetch<RegisterResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function apiVerifyEmail(
  data: VerifyEmailRequest
): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/api/auth/verify-email", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function apiResendVerification(
  email: string
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function apiForgotPassword(
  email: string
): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function apiResetPassword(data: {
  email: string;
  code: string;
  new_password: string;
}): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function apiLogout(): Promise<void> {
  try {
    await apiFetch<{ detail: string }>("/api/auth/logout", {
      method: "POST",
    });
  } catch {
    // Ignore network errors on logout
  }
}

export async function apiDeleteAccount(password: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/auth/me", {
    method: "DELETE",
    body: JSON.stringify({ password }),
  });
}

export async function apiGetCurrentUser(): Promise<User> {
  return apiFetch<User>("/api/auth/me");
}

// ============================================================
// Course API
// ============================================================

export async function apiGetCourses(): Promise<CoursesResponse> {
  return apiFetch<CoursesResponse>("/api/courses/all");
}

export async function apiGetCourseStatus(
  courseId: string,
  init?: RequestInit
): Promise<CourseStatusResponse> {
  return apiFetch<CourseStatusResponse>(`/api/course/${encodeURIComponent(courseId)}/status`, init);
}

export function apiRetryDocument(courseId: string, init?: RequestInit): Promise<DocumentRetryResponse> {
  return apiFetch<DocumentRetryResponse>(
    `/api/documents/${encodeURIComponent(courseId)}/retry`,
    { ...init, method: "POST" }
  );
}

export function apiGetJob(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function apiDeleteCourse(courseId: string): Promise<void> {
  await apiFetch<{ status: string }>(`/api/courses/${courseId}`, {
    method: "DELETE",
  });
}

export async function apiRenameCourse(
  courseId: string,
  name: string
): Promise<void> {
  await apiFetch<{ id: string }>(`/api/courses/${courseId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

// ============================================================
// Upload API
// ============================================================

export async function apiUploadFiles(
  files: File[],
  onProgress?: (percent: number) => void
): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  if (onProgress) {
    return new Promise<UploadResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/upload`);

      const headers = getAuthHeaders();
      Object.entries(headers).forEach(([key, value]) => {
        xhr.setRequestHeader(key, value);
      });
      xhr.withCredentials = true;

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
        } else if (xhr.status === 401) {
          removeToken();
          window.location.href = "/login";
          reject(new Error("Phiên đăng nhập đã hết hạn."));
        } else {
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(err.detail || "Upload thất bại."));
          } catch {
            reject(new Error("Upload thất bại. Vui lòng thử lại."));
          }
        }
      });

      xhr.addEventListener("error", () => {
        reject(new Error("Lỗi kết nối. Vui lòng kiểm tra backend."));
      });

      xhr.send(formData);
    });
  }

  return apiFetch<UploadResponse>("/api/upload", {
    method: "POST",
    body: formData,
  });
}

// ============================================================
// Study Pack API (for future use)
// ============================================================

export async function apiGetStudyPack(
  courseId: string,
  init?: RequestInit
): Promise<StudyPackResponse> {
  return apiFetch<StudyPackResponse>(`/api/course/${encodeURIComponent(courseId)}/study-pack`, init);
}

// ============================================================
// Generation & Artifact API
// ============================================================

export async function apiGenerateBook(
  courseId: string,
  params?: Record<string, unknown>
): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>("/api/generate-book", {
    method: "POST",
    body: JSON.stringify({ course_id: courseId, ...(params || {}) }),
  });
}

export async function apiGenerateSlide(
  courseId: string,
  params?: Record<string, unknown>
): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>("/api/generate-slide", {
    method: "POST",
    body: JSON.stringify({ course_id: courseId, ...(params || {}) }),
  });
}

export async function apiGenerateQuiz(
  courseId: string,
  params?: Record<string, unknown>
): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>("/api/generate-quiz", {
    method: "POST",
    body: JSON.stringify({ course_id: courseId, ...(params || {}) }),
  });
}

export async function apiGenerateVid(
  courseId: string,
  params?: Record<string, unknown>
): Promise<GenerateResponse> {
  return apiFetch<GenerateResponse>("/api/generate-vid", {
    method: "POST",
    body: JSON.stringify({ course_id: courseId, ...(params || {}) }),
  });
}

function versionQuery(version?: string | null): string {
  return version ? `?version=${encodeURIComponent(version)}` : "";
}

export async function apiRenameArtifactVersion(courseId: string, artifact: string, versionId: string, label: string): Promise<void> {
  await apiFetch(`/api/course/${courseId}/artifacts/${artifact}/versions/${versionId}`, {
    method: "PATCH",
    body: JSON.stringify({ label }),
  });
}

export async function apiDeleteArtifactVersion(courseId: string, artifact: string, versionId: string): Promise<void> {
  await apiFetch(`/api/course/${courseId}/artifacts/${artifact}/versions/${versionId}`, { method: "DELETE" });
}

export async function apiGetBook(courseId: string, version?: string | null): Promise<BookArtifactStatus> {
  return apiFetch<BookArtifactStatus>(`/api/course/${courseId}/book${versionQuery(version)}`);
}

export async function apiGetSlide(courseId: string, version?: string | null): Promise<SlideArtifactStatus> {
  return apiFetch<SlideArtifactStatus>(`/api/course/${courseId}/slide${versionQuery(version)}`);
}

export async function apiGetQuiz(courseId: string, version?: string | null): Promise<QuizArtifactStatus> {
  return apiFetch<QuizArtifactStatus>(`/api/course/${courseId}/quiz${versionQuery(version)}`);
}

export async function apiGetVid(courseId: string, version?: string | null): Promise<VidArtifactStatus> {
  return apiFetch<VidArtifactStatus>(`/api/course/${courseId}/vid${versionQuery(version)}`);
}

// ============================================================
// Download Helpers
// ============================================================

function downloadSuffix(version?: string | null): string {
  const token = getToken();
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  if (version) params.set("version", version);
  return params.size ? `?${params.toString()}` : "";
}

export function getDownloadBookUrl(courseId: string, version?: string | null): string {
  const suffix = downloadSuffix(version);
  return `${API_BASE}/api/course/${courseId}/book.pdf${suffix}`;
}

export function getDownloadSlideUrl(courseId: string, version?: string | null): string {
  const suffix = downloadSuffix(version);
  return `${API_BASE}/api/course/${courseId}/slide.pptx${suffix}`;
}

export function getDownloadSlidePdfUrl(courseId: string, version?: string | null): string {
  const suffix = downloadSuffix(version);
  return `${API_BASE}/api/course/${courseId}/slide.pdf${suffix}`;
}

export function getDownloadQuizKeyUrl(courseId: string, version?: string | null): string {
  const suffix = downloadSuffix(version);
  return `${API_BASE}/api/course/${courseId}/quiz-key.pdf${suffix}`;
}

export function getDownloadVidMp4Url(courseId: string, version?: string | null): string {
  const suffix = downloadSuffix(version);
  return `${API_BASE}/api/course/${courseId}/vid.mp4${suffix}`;
}

export const getBookPdfUrl = getDownloadBookUrl;
export const getSlidePptxUrl = getDownloadSlideUrl;
export const getQuizKeyPdfUrl = getDownloadQuizKeyUrl;
export const getVidFileUrl = getDownloadVidMp4Url;

export function getSlideImageUrl(courseId: string, slideNum: number, version?: string | null): string {
  const suffix = downloadSuffix(version);
  return `${API_BASE}/api/course/${courseId}/slide-images/${slideNum}${suffix}`;
}
