/**
 * File validation utilities for document ingestion.
 * Ensures only valid PDF, DOCX, TXT files are accepted.
 */

export const ALLOWED_EXTENSIONS = ["pdf", "docx", "txt"] as const;
export type AllowedExtension = (typeof ALLOWED_EXTENSIONS)[number];

export const ALLOWED_MIME_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
] as const;

export const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Validates a single file against all ingestion rules.
 * Order of checks: empty file → MIME type → extension → file size.
 */
export function validateFile(file: File): ValidationResult {
  // 1. Check for empty file (0 bytes)
  if (file.size === 0) {
    return {
      valid: false,
      error: `"${file.name}" là file rỗng. Vui lòng chọn file có nội dung.`,
    };
  }

  // 2. Check MIME type (prevents renamed .exe → .pdf attacks)
  const isMimeValid = (ALLOWED_MIME_TYPES as readonly string[]).includes(file.type);
  if (!isMimeValid) {
    return {
      valid: false,
      error: `"${file.name}" có định dạng không hợp lệ. Chỉ chấp nhận file PDF, DOCX, TXT.`,
    };
  }

  // 3. Check file extension (double-check against MIME)
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const isExtValid = (ALLOWED_EXTENSIONS as readonly string[]).includes(extension);
  if (!isExtValid) {
    return {
      valid: false,
      error: `"${file.name}" có phần mở rộng ".${extension}" không được hỗ trợ. Chỉ chấp nhận .pdf, .docx, .txt.`,
    };
  }

  // 4. Check file size
  if (file.size > MAX_FILE_SIZE) {
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    return {
      valid: false,
      error: `"${file.name}" (${sizeMB} MB) vượt quá giới hạn 50MB.`,
    };
  }

  return { valid: true };
}

/**
 * Validates an array of files and returns separate valid/invalid lists.
 */
export function validateFiles(
  files: File[]
): { validFiles: File[]; errors: string[] } {
  const validFiles: File[] = [];
  const errors: string[] = [];

  for (const file of files) {
    const result = validateFile(file);
    if (result.valid) {
      validFiles.push(file);
    } else if (result.error) {
      errors.push(result.error);
    }
  }

  return { validFiles, errors };
}