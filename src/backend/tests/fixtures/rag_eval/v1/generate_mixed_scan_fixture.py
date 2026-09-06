"""Build a deterministic two-page PDF with one native page and one image-only page."""

from __future__ import annotations

import hashlib

import fitz


NATIVE_TEXT = "The control sample is B-18 and must not be confused with B-17."
FAKE_OCR_TEXT = "The scanned label reads: Mau so B-17."


def build_fixture() -> bytes:
    document = fitz.open()
    native = document.new_page(width=360, height=240)
    native.insert_text((36, 72), NATIVE_TEXT, fontsize=12)

    scan = document.new_page(width=360, height=240)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="288" height="120">'
        '<rect width="288" height="120" fill="white"/>'
        '<text x="12" y="62" font-family="sans-serif" font-size="18">Mau so B-17</text>'
        "</svg>"
    ).encode("utf-8")
    image_doc = fitz.open("svg", svg)
    pixmap = image_doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    scan.insert_image(fitz.Rect(36, 54, 324, 174), stream=pixmap.tobytes("png"))
    image_doc.close()

    document.set_metadata(
        {
            "title": "Synthetic mixed native and image fixture",
            "author": "HackaGen",
            "creator": "HackaGen deterministic fixture v1",
            "producer": "HackaGen deterministic fixture v1",
            "creationDate": "D:20260905000000Z",
            "modDate": "D:20260905000000Z",
        }
    )
    payload = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    return payload


if __name__ == "__main__":
    payload = build_fixture()
    print(hashlib.sha256(payload).hexdigest())
