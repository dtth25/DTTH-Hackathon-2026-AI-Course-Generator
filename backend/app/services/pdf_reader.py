import io
from dataclasses import dataclass
from typing import List

import fitz  # PyMuPDF
from PIL import Image

from backend.app.config import Settings


@dataclass
class PageText:
    page_number: int
    text: str
    source_type: str  # TEXT_PDF or OCR_PDF


def _ocr_page(page: fitz.Page, settings: Settings) -> str:
    import pytesseract

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    pix = page.get_pixmap(dpi=220)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image, lang=settings.ocr_lang, config="--psm 3")


def extract_pages_from_pdf(file_bytes: bytes, settings: Settings) -> List[PageText]:
    """Extract page-by-page text and preserve exact page numbers for citations."""
    pages: List[PageText] = []

    try:
        document = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Không mở được PDF: {exc}") from exc

    try:
        for page_index in range(len(document)):
            page = document.load_page(page_index)
            page_number = page_index + 1
            text = (page.get_text("text") or "").strip()
            source_type = "TEXT_PDF"

            if not text and settings.enable_ocr:
                try:
                    text = (_ocr_page(page, settings) or "").strip()
                    source_type = "OCR_PDF"
                except Exception as exc:
                    text = ""
                    source_type = f"OCR_FAILED: {exc}"

            if text:
                pages.append(PageText(page_number=page_number, text=text, source_type=source_type))
    finally:
        document.close()

    return pages


def build_model_context(pages: List[PageText], max_chars: int) -> str:
    """Build context with page tags that the model must reuse in page_reference."""
    chunks: List[str] = []
    total = 0

    for page in pages:
        block = (
            "=== BẮT ĐẦU DỮ LIỆU TRUY XUẤT ===\n"
            f"[MÃ ĐỊNH DANH TRANG: {page.page_number}]\n"
            f"[NGUỒN: {page.source_type}]\n"
            f"NỘI DUNG:\n{page.text}\n"
            f"=== KẾT THÚC DỮ LIỆU TRANG {page.page_number} ===\n"
        )
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 500:
                chunks.append(block[:remaining])
            break
        chunks.append(block)
        total += len(block)

    return "\n".join(chunks).strip()
