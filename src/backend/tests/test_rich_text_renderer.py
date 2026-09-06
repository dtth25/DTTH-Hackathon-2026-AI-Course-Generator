"""Offline contract tests for the private Markdown/KaTeX Chromium renderer."""

import json
from pathlib import Path

import pytest

from app.services.rich_text_renderer import RichTextRenderError, RichTextRenderer


_CORPUS = Path(__file__).parent / "fixtures" / "math" / "canonical_display.json"


@pytest.fixture
def renderer(tmp_path):
    instance = RichTextRenderer(output_root=tmp_path / "blocks", timeout_seconds=20)
    try:
        yield instance
    finally:
        instance.close()


def test_corpus_math_renders_with_real_local_katex_and_chromium(renderer):
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    blocks = [renderer.render(item["text"], 480, 18, "light") for item in corpus if item["id"] not in {"glyphs", "literal-question"}]

    assert all(block.math_count == 1 for block in blocks)
    assert all(block.png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for block in blocks)
    assert all(block.height_px > 0 and block.width_px == 480 for block in blocks)


def test_fraction_is_katex_rendered_and_cache_is_content_addressed(renderer):
    first = renderer.render(r"$\frac{a+b}{c+d}$", 480, 18, "light")
    second = renderer.render(r"$\frac{a+b}{c+d}$", 480, 18, "light")

    assert first.png_path == second.png_path
    assert first.math_count == 1
    assert first.renderer_revision == "rich-text-v1-katex-0.16.47"


@pytest.mark.parametrize(
    ("markdown", "code"),
    [
        ("<img src=x onerror=alert(1)>", "raw_html"),
        ("![remote](https://example.test/a.png)", "image_not_supported"),
        (r"$\def\bad{1}\bad$", "unsupported_math"),
        ("x" * 100_001, "input_limit"),
    ],
    ids=["raw-html", "remote-image", "macro", "input-limit"],
)
def test_unsafe_or_unbounded_content_is_controlled(renderer, markdown, code):
    with pytest.raises(RichTextRenderError) as error:
        renderer.render(markdown, 480, 18, "light")
    assert error.value.code == code


def test_dimension_timeout_and_missing_font_are_controlled(tmp_path):
    renderer = RichTextRenderer(output_root=tmp_path / "blocks", timeout_seconds=0.0001)
    try:
        with pytest.raises(RichTextRenderError) as error:
            renderer.render("plain", 480, 18, "light")
        assert error.value.code == "render_timeout"
    finally:
        renderer.close()

    missing_font = RichTextRenderer(output_root=tmp_path / "missing", font_dir=tmp_path / "no-fonts")
    with pytest.raises(RichTextRenderError) as error:
        missing_font.render("plain", 480, 18, "light")
    assert error.value.code == "renderer_unavailable"

    valid = RichTextRenderer(output_root=tmp_path / "valid")
    try:
        with pytest.raises(RichTextRenderError) as error:
            valid.render("plain", 4097, 18, "light")
        assert error.value.code == "dimension_limit"
    finally:
        valid.close()


def test_existing_corpus_unicode_is_identified_instead_of_replaced(renderer):
    glyph_text = next(item["text"] for item in json.loads(_CORPUS.read_text(encoding="utf-8")) if item["id"] == "glyphs")
    with pytest.raises(RichTextRenderError) as error:
        renderer.render(glyph_text, 480, 18, "light")
    assert error.value.code == "unsupported_codepoints"
    assert "U+4E2D" in error.value.unsupported_codepoints
