"""Provider-neutral, safe error contracts for public API responses.

Internal provider codes and diagnostics remain useful in persistence and logs.  They
must be translated before crossing an HTTP response boundary.
"""

from typing import Optional


PROVIDER_CODE_MAP = {
    "OPENROUTER_KEY_INVALID": "AI_CONFIGURATION_ERROR",
    "OPENROUTER_ACCESS_DENIED": "AI_ACCESS_DENIED",
    "OPENROUTER_KEY_LIMIT_EXCEEDED": "AI_QUOTA_EXHAUSTED",
    "OPENROUTER_CREDITS_EXHAUSTED": "AI_QUOTA_EXHAUSTED",
    "OPENROUTER_RATE_LIMITED": "AI_RATE_LIMITED",
    "OPENROUTER_UNAVAILABLE": "AI_UNAVAILABLE",
    "OPENROUTER_TIMEOUT": "AI_TIMEOUT",
    "OPENROUTER_REQUEST_FAILED": "AI_REQUEST_FAILED",
}

PUBLIC_MESSAGES = {
    "AI_CONFIGURATION_ERROR": "Dịch vụ AI chưa được cấu hình hợp lệ. Vui lòng liên hệ quản trị viên.",
    "AI_ACCESS_DENIED": "Dịch vụ AI không có quyền thực hiện yêu cầu này.",
    "AI_QUOTA_EXHAUSTED": "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
    "AI_RATE_LIMITED": "Dịch vụ AI đang bận. Tác vụ có thể thử lại sau.",
    "AI_UNAVAILABLE": "Dịch vụ AI tạm thời không khả dụng.",
    "AI_TIMEOUT": "Kết nối dịch vụ AI quá thời gian chờ.",
    "AI_REQUEST_FAILED": "Không thể hoàn thành yêu cầu AI. Vui lòng thử lại.",
    "DOCUMENT_TEXT_EXTRACTION_FAILED": "Không thể đọc văn bản trong tệp.",
    "DOCUMENT_SCHEDULING_FAILED": "Không thể bắt đầu xử lý tài liệu. Vui lòng thử lại.",
    "DOCUMENT_PROCESSING_FAILED": "Xử lý tài liệu thất bại.",
    "DOCUMENT_PROCESSING_PERSISTENCE_FAILED": "Không thể lưu kết quả xử lý tài liệu. Vui lòng thử lại.",
    "DOCUMENT_PROCESSING_CANCELLED": "Tài liệu đã bị hủy trước khi xử lý hoàn tất.",
    "INLINE_PROCESSING_INTERRUPTED": "Tác vụ xử lý trước đó bị gián đoạn. Vui lòng thử lại.",
    "ARTIFACT_SOURCE_UNAVAILABLE": "Không tìm thấy nội dung tài liệu đã lập chỉ mục để tạo học liệu.",
    "BOOK_GENERATION_FAILED": "Không thể tạo sách ôn tập. Vui lòng thử lại.",
    "SLIDE_GENERATION_FAILED": "Không thể tạo bài trình chiếu. Vui lòng thử lại.",
    "QUIZ_GENERATION_FAILED": "Không thể tạo bài trắc nghiệm. Vui lòng thử lại.",
    "VIDEO_GENERATION_FAILED": "Không thể tạo video. Vui lòng thử lại.",
}


def public_error_code(error_code: Optional[str], default: str) -> str:
    """Translate an internal code to a closed provider-neutral public code."""
    if not error_code:
        return default
    translated = PROVIDER_CODE_MAP.get(error_code, error_code)
    return translated if translated in PUBLIC_MESSAGES else default


def public_error(error_code: Optional[str], default_code: str) -> tuple[str, str]:
    code = public_error_code(error_code, default_code)
    return code, PUBLIC_MESSAGES[code]
