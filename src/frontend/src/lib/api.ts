/**
 * API configuration and endpoints for backend communication.
 * Backend runs on port 8000 by default.
 */

export const API_BASE_URL = "http://localhost:8000";

export const ENDPOINTS = {
  upload: `${API_BASE_URL}/api/upload`,
  generateCourse: `${API_BASE_URL}/api/generate-course`,
  generateSummary: `${API_BASE_URL}/api/generate-summary`,
  generateFlashcards: `${API_BASE_URL}/api/generate-flashcards`,
  generateQuiz: `${API_BASE_URL}/api/generate-quiz`,
  generateSlides: `${API_BASE_URL}/api/generate-slides`,
  generateMindmap: `${API_BASE_URL}/api/generate-mindmap`,
  customPrompt: `${API_BASE_URL}/api/custom-prompt`,
} as const;

export type Endpoint = keyof typeof ENDPOINTS;

/**
 * Upload files to backend.
 */
export async function uploadFiles(files: File[]): Promise<{ message: string }> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  const response = await fetch(ENDPOINTS.upload, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.message || `Lỗi tải lên: ${response.statusText}`);
  }

  return response.json();
}