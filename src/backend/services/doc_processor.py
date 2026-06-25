"""
Document processing service: Extract text from PDF/DOCX/TXT files.
Based on core_v2.py PDF extraction logic.
"""
import io
import logging
from typing import List

import fitz
import pytesseract
import docx
from PIL import Image
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def is_cover_page(text: str, page_num: int) -> bool:
    """Check if a page is likely a cover page based on keywords and length."""
    if page_num > 1:
        return False
    cover_keywords = ["NHÀ XUẤT BẢN", "BỘ GIÁO DỤC", "TỔNG CHỦ BIÊN", "BẢN IN THỬ"]
    text_upper = text.upper()
    has_keyword = any(kw in text_upper for kw in cover_keywords)
    is_short = len(text) < 200
    return has_keyword or is_short


def get_text_from_any_file(file_path: str) -> List[Document]:
    """
    Extract text from PDF (with OCR fallback), DOCX, or TXT.
    Returns list of Documents with page metadata.
    """
    documents = []
    ext = file_path.lower().split('.')[-1]
    try:
        if ext == 'pdf':
            doc = fitz.open(file_path)
            logger.info(f"[PDF] Processing {len(doc)} pages...")

            for page_num in range(len(doc)):
                page = doc[page_num]
                raw_text = page.get_text()
                text = str(raw_text).strip() if raw_text else ""
                p_display = page_num + 1

                if not text:
                    logger.info(f" -> Page {p_display}: No text found, running OCR...")
                    try:
                        pix = page.get_pixmap(dpi=300)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        text = pytesseract.image_to_string(
                            img, lang='vie+eng', config='--psm 3'
                        )
                        source_type = "IMAGE_PDF"
                    except Exception as e:
                        logger.warning(f" -> OCR failed on page {p_display}: {e}")
                        continue
                else:
                    source_type = "TEXT_PDF"

                content_with_tag = (
                    f"=== BẮT ĐẦU DỮ LIỆU TRUY XUẤT ===\n"
                    f"[MÃ ĐỊNH DANH TRANG: {p_display}]\n"
                    f"NỘI DUNG: {text}\n"
                    f"=== KẾT THÚC DỮ LIỆU TRANG {p_display} ==="
                )

                if text.strip():
                    documents.append(Document(
                        page_content=content_with_tag,
                        metadata={
                            "source": file_path,
                            "page": p_display,
                            "type": source_type
                        }
                    ))

            doc.close()
            logger.info(f"[PDF] Extracted {len(documents)} pages with content.")
        elif ext == 'docx':
            doc = docx.Document(file_path)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            text = "\n".join(full_text)
            if text.strip():
                documents.append(Document(
                    page_content=text,
                    metadata={"source": file_path, "type": "DOCX"}
                ))
        elif ext == 'txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            if text.strip():
                documents.append(Document(
                    page_content=text,
                    metadata={"source": file_path, "type": "TXT"}
                ))

    except Exception as e:
        logger.error(f"[DocProcessor] Failed to read {file_path}: {e}")
        raise

    return documents
