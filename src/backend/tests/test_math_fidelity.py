"""Canonical display text must survive generation cleanup and JSON persistence."""

import json
from pathlib import Path

from app.schemas.generator_output import SlideItem, SlidesOutput, VidOutput, VidScene
from app.services.generator import _clean_slides_output, _clean_vid_output
from app.services.text_format import normalize_display_text, normalize_narration


_CORPUS_PATH = Path(__file__).parent / "fixtures" / "math" / "canonical_display.json"


def _corpus() -> list[dict[str, str]]:
    return json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))


def test_slide_display_math_and_unicode_round_trip_without_loss():
    corpus = _corpus()
    deck = SlidesOutput(
        title=corpus[0]["text"],
        slides=[
            SlideItem(slide_number=1, title=corpus[1]["text"], bullet_points=[item["text"] for item in corpus])
        ],
    )

    cleaned = _clean_slides_output(deck)

    assert cleaned.title == corpus[0]["text"]
    assert cleaned.slides[0].title == corpus[1]["text"]
    assert cleaned.slides[0].bullet_points == [item["text"] for item in corpus]
    assert SlidesOutput.model_validate_json(cleaned.model_dump_json()) == cleaned


def test_video_screen_text_stays_canonical_while_narration_is_speech_only():
    formula = r"$\frac{a+b}{c+d}$"
    vid = VidOutput(
        title=formula,
        total_duration_seconds=1,
        scenes=[
            VidScene(
                scene_number=1,
                title=formula,
                on_screen_text=r"$\sqrt{x+1}$",
                key_points=[r"$x^{a+b}$", "Tiếng Việt: đạo hàm. 𝛼 ∑ ℝ ∇ ∀ ₁ ᵢ 中文"],
                narration=formula,
            )
        ],
    )

    cleaned = _clean_vid_output(vid)

    assert cleaned.title == formula
    assert cleaned.scenes[0].title == formula
    assert cleaned.scenes[0].on_screen_text == r"$\sqrt{x+1}$"
    assert cleaned.scenes[0].key_points[0] == r"$x^{a+b}$"
    assert cleaned.scenes[0].key_points[1].endswith("中文")
    assert cleaned.scenes[0].narration == "a+b/c+d"
    assert VidOutput.model_validate_json(cleaned.model_dump_json()) == cleaned


def test_display_normalization_preserves_delimiters_code_currency_and_question_marks():
    text = r"Use `$x^2$`, pay $5, then \(x+1\) and \[x^2\]?" + "\x00"

    assert normalize_display_text(text) == r"Use `$x^2$`, pay $5, then \(x+1\) and \[x^2\]?"
    assert normalize_narration(r"$\frac{a+b}{c+d}$") == "a+b/c+d"
