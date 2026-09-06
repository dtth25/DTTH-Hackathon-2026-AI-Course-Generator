from decimal import Decimal as D

from app.services.provider_usage import can_reserve, estimate_call_usd, normalize_usage


def test_book_price_envelope():
    assert estimate_call_usd(40_000, 18_000, D("0.30"), D("2.50")) == D("0.057")


def test_budget_includes_all_live_calls():
    assert not can_reserve(D("0.06"), D("0.02"), D("0.016"), D("0.095"))
    assert can_reserve(D("0.06"), D("0.02"), D("0.015"), D("0.095"))


def test_missing_usage_is_unknown():
    assert normalize_usage(None) == {"cost_usd": None, "input_tokens": None, "output_tokens": None}
