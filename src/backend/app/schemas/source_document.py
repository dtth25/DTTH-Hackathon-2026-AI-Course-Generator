"""Canonical, server-side representation of uploaded source content."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SourceBlock(BaseModel):
    kind: Literal["paragraph", "table", "math"]
    text: Optional[str] = None
    math_latex: Optional[str] = None
    source_file: str
    page: Optional[int] = None
    location: str


class ExtractionReport(BaseModel):
    total_pages: Optional[int] = None
    extracted_pages: list[int] = Field(default_factory=list)
    ocr_pages: list[int] = Field(default_factory=list)
    skipped_pages: list[int] = Field(default_factory=list)
    damaged_pages: list[int] = Field(default_factory=list)
    blank_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ocr_details: list[dict] = Field(default_factory=list, exclude=True)
    complete: bool = True

    def normalize(self) -> "ExtractionReport":
        for name in ("extracted_pages", "ocr_pages", "skipped_pages", "damaged_pages", "blank_pages"):
            setattr(self, name, sorted(set(getattr(self, name))))
        self.complete = self.complete and not self.skipped_pages and not self.damaged_pages
        return self
