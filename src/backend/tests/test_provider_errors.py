from app.services.provider_errors import (
    ProviderErrorCode,
    classify_openrouter_error,
)


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def test_key_limit_403_is_manual_retry_only():
    failure = classify_openrouter_error(
        FakeStatusError(403, "Key limit exceeded (total limit)")
    )
    assert failure.code == ProviderErrorCode.KEY_LIMIT_EXCEEDED
    assert failure.can_retry is True
    assert failure.automatic_retry is False
    assert failure.recommended_action == "restore_provider_quota"
    assert "Key limit" not in failure.user_message


def test_rate_limit_429_is_automatic_retry():
    failure = classify_openrouter_error(FakeStatusError(429, "rate limited"))
    assert failure.code == ProviderErrorCode.RATE_LIMITED
    assert failure.automatic_retry is True


def test_invalid_key_and_payment_are_not_automatically_retried():
    invalid = classify_openrouter_error(FakeStatusError(401, "invalid api key"))
    payment = classify_openrouter_error(FakeStatusError(402, "payment required"))
    assert invalid.code == ProviderErrorCode.KEY_INVALID
    assert payment.code == ProviderErrorCode.CREDITS_EXHAUSTED
    assert invalid.automatic_retry is False
    assert payment.automatic_retry is False
