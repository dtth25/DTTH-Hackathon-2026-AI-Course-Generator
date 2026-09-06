"""Canonical extraction and per-page PDF coverage assessment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Optional

import fitz

from app.schemas.source_document import ExtractionReport, SourceBlock
from app.services.docx_extract import extract_docx


@dataclass(frozen=True, eq=False)
class OCRResult:
    text: str
    complete: bool
    finish_reason: Optional[str] = None
    latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    def __bool__(self):
        return bool(self.text)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.text == other
        if isinstance(other, OCRResult):
            return self.__dict__ == other.__dict__
        return NotImplemented


OCRCallable = Callable[[bytes, int], OCRResult]


@dataclass(frozen=True)
class PDFPageAssessment:
    needs_ocr: bool
    damaged: bool
    empty_span_ratio: float
    image_only: bool
    suspicious_reading_order: bool
    suspicious_math: bool
    confirmed_blank: bool


def _clean_filename(path: Path) -> str:
    parts = path.name.split("_", 1)
    return parts[1] if len(parts) == 2 and parts[0].isdigit() else path.name


def _damaged_glyph_count(text: str) -> int:
    return text.count("\ufffd") + sum(0xE000 <= ord(char) <= 0xF8FF for char in text)


def assess_pdf_page(
    *,
    text: str,
    spans: list[dict],
    image_count: int,
    min_chars: int,
    drawing_count: int = 0,
    displayed_image_count: int = 0,
) -> PDFPageAssessment:
    empty_ratio = sum(not (span.get("text") or "").strip() for span in spans) / max(1, len(spans))
    damaged = _damaged_glyph_count(text) >= 4
    image_only = (image_count > 0 or displayed_image_count > 0) and not text.strip()
    suspicious_order = len(spans) > 4 and any(spans[i].get("bbox", (0, 0, 0, 0))[1] > spans[i + 1].get("bbox", (0, 0, 0, 0))[1] + 20 for i in range(len(spans) - 1))
    suspicious_math = any("�" in (span.get("text") or "") for span in spans)
    confirmed_blank = (
        not text.strip()
        and not spans
        and image_count == 0
        and displayed_image_count == 0
        and drawing_count == 0
    )
    return PDFPageAssessment(
        needs_ocr=not confirmed_blank and (image_only or len(text.strip()) < min_chars or damaged or empty_ratio > 0.5 or suspicious_order or suspicious_math),
        damaged=damaged,
        empty_span_ratio=empty_ratio,
        image_only=image_only,
        suspicious_reading_order=suspicious_order,
        suspicious_math=suspicious_math,
        confirmed_blank=confirmed_blank,
    )


def _assess_page(page, text: str, min_chars: int) -> PDFPageAssessment:
    raw = page.get_text("dict")
    spans = [span for block in raw.get("blocks", []) for line in block.get("lines", []) for span in line.get("spans", [])]
    displayed_image_count = sum(block.get("type") == 1 for block in raw.get("blocks", []))
    return assess_pdf_page(
        text=text,
        spans=spans,
        image_count=len(page.get_images(full=True)),
        drawing_count=len(page.get_drawings()),
        displayed_image_count=displayed_image_count,
        min_chars=min_chars,
    )


def _extract_pdf(path: Path, ocr_page: Optional[OCRCallable], ocr_max_pages: int, ocr_dpi: int, min_chars: int, page_analysis_inputs=None):
    blocks: list[SourceBlock] = []
    report = ExtractionReport(total_pages=0)
    source_file = _clean_filename(path)
    with fitz.open(path) as document:
        report.total_pages = document.page_count
        candidates = []
        native = {}
        damaged_native = set()
        assessments = {}
        for index, page in enumerate(document):
            page_number = index + 1
            text = (page.get_text() or "").strip()
            native[page_number] = text
            injected_inputs = (page_analysis_inputs or {}).get(page_number)
            assessment = (
                assess_pdf_page(min_chars=min_chars, **injected_inputs)
                if injected_inputs is not None
                else _assess_page(page, text, min_chars)
            )
            assessments[page_number] = assessment
            if assessment.confirmed_blank:
                report.blank_pages.append(page_number)
            if assessment.needs_ocr:
                candidates.append(page_number)
            if assessment.damaged:
                damaged_native.add(page_number)
        selected = candidates[:ocr_max_pages] if ocr_page else []
        report.skipped_pages.extend(candidates[len(selected):])
        if report.skipped_pages:
            report.warnings.append(f"OCR page cap omitted {len(report.skipped_pages)} page(s)")
        for page_number in range(1, document.page_count + 1):
            text = native[page_number]
            if assessments[page_number].confirmed_blank:
                continue
            used_ocr = page_number in selected
            if used_ocr:
                page = document[page_number - 1]
                pix = page.get_pixmap(matrix=fitz.Matrix(ocr_dpi / 72.0, ocr_dpi / 72.0))
                started = perf_counter()
                result = ocr_page(pix.tobytes("png"), page_number)
                _ = result.latency_ms if result.latency_ms is not None else int((perf_counter() - started) * 1000)
                report.ocr_pages.append(page_number)
                report.ocr_details.append({
                    "page": page_number,
                    "latency_ms": result.latency_ms if result.latency_ms is not None else int((perf_counter() - started) * 1000),
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "finish_reason": result.finish_reason,
                    "complete": result.complete,
                })
                if result.text.strip():
                    text = result.text.strip()
                else:
                    report.damaged_pages.append(page_number)
                    report.warnings.append(f"OCR returned no usable text on page {page_number}")
                if not result.complete:
                    report.damaged_pages.append(page_number)
                    reason = "truncated" if result.finish_reason == "length" else "incomplete"
                    report.warnings.append(f"OCR {reason} on page {page_number}")
            if page_number in damaged_native and (not used_ocr or not result.text.strip()):
                report.damaged_pages.append(page_number)
                report.warnings.append(f"Damaged symbols on page {page_number}")
            if text:
                report.extracted_pages.append(page_number)
                rect = document[page_number - 1].rect
                location = f"page[{page_number}]/bbox[{rect.x0:.1f},{rect.y0:.1f},{rect.x1:.1f},{rect.y1:.1f}]"
                blocks.append(SourceBlock(kind="paragraph", text=text, source_file=source_file, page=page_number, location=location))
    return blocks, report.normalize()


def extract_source(path: Path, *, ocr_page: Optional[OCRCallable] = None, ocr_max_pages: int = 12, ocr_dpi: int = 120, min_chars: int = 50, page_analysis_inputs=None):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        blocks, report = extract_docx(path)
        for block in blocks:
            block.source_file = _clean_filename(path)
        return blocks, report
    if suffix == ".pdf":
        return _extract_pdf(path, ocr_page, ocr_max_pages, ocr_dpi, min_chars, page_analysis_inputs)
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8-sig", errors="strict").strip()
        blocks = [SourceBlock(kind="paragraph", text=text, source_file=_clean_filename(path), page=1, location="page[1]")] if text else []
        return blocks, ExtractionReport(total_pages=1, extracted_pages=[1] if text else [], damaged_pages=[] if text else [1], complete=bool(text)).normalize()
    raise ValueError(f"Unsupported file extension: {suffix}")
