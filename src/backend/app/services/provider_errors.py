from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class ProviderErrorCode(StrEnum):
    KEY_INVALID = "OPENROUTER_KEY_INVALID"
    KEY_LIMIT_EXCEEDED = "OPENROUTER_KEY_LIMIT_EXCEEDED"
    CREDITS_EXHAUSTED = "OPENROUTER_CREDITS_EXHAUSTED"
    ACCESS_DENIED = "OPENROUTER_ACCESS_DENIED"
    RATE_LIMITED = "OPENROUTER_RATE_LIMITED"
    UNAVAILABLE = "OPENROUTER_UNAVAILABLE"
    TIMEOUT = "OPENROUTER_TIMEOUT"
    REQUEST_FAILED = "OPENROUTER_REQUEST_FAILED"


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    code: ProviderErrorCode
    user_message: str
    can_retry: bool
    automatic_retry: bool
    recommended_action: str
    http_status: Optional[int]
    technical_message: str


class ProviderRequestError(RuntimeError):
    def __init__(self, failure: ProviderFailure):
        super().__init__(failure.user_message)
        self.failure = failure


def _status_code(exc: Exception) -> Optional[int]:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def classify_openrouter_error(exc: Exception) -> ProviderFailure:
    status = _status_code(exc)
    technical = str(exc)[:1000]
    folded = technical.casefold()
    if status == 401:
        return ProviderFailure(
            ProviderErrorCode.KEY_INVALID,
            "Dịch vụ AI chưa được cấu hình hợp lệ.",
            True,
            False,
            "contact_admin",
            status,
            technical,
        )
    if status == 402 or "insufficient credit" in folded or "payment required" in folded:
        return ProviderFailure(
            ProviderErrorCode.CREDITS_EXHAUSTED,
            "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
            True,
            False,
            "restore_provider_quota",
            status,
            technical,
        )
    if status == 403 and "key limit exceeded" in folded:
        return ProviderFailure(
            ProviderErrorCode.KEY_LIMIT_EXCEEDED,
            "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
            True,
            False,
            "restore_provider_quota",
            status,
            technical,
        )
    if status == 403:
        return ProviderFailure(
            ProviderErrorCode.ACCESS_DENIED,
            "Dịch vụ AI không có quyền thực hiện yêu cầu này.",
            True,
            False,
            "contact_admin",
            status,
            technical,
        )
    if status == 429:
        return ProviderFailure(
            ProviderErrorCode.RATE_LIMITED,
            "Dịch vụ AI đang bận. Tác vụ có thể thử lại sau.",
            True,
            True,
            "retry_later",
            status,
            technical,
        )
    if status is not None and status >= 500:
        return ProviderFailure(
            ProviderErrorCode.UNAVAILABLE,
            "Dịch vụ AI tạm thời không khả dụng.",
            True,
            True,
            "retry_later",
            status,
            technical,
        )
    if "timeout" in folded or "timed out" in folded:
        return ProviderFailure(
            ProviderErrorCode.TIMEOUT,
            "Kết nối dịch vụ AI quá thời gian chờ.",
            True,
            True,
            "retry_later",
            status,
            technical,
        )
    return ProviderFailure(
        ProviderErrorCode.REQUEST_FAILED,
        "Không thể hoàn tất yêu cầu AI.",
        True,
        False,
        "retry_later",
        status,
        technical,
    )
