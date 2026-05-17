from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class ExtractionResult:
    page_texts: list[str]
    method: str


def extract_pdf_pages(path: Path) -> ExtractionResult:
    reader = PdfReader(path)
    extracted = [(page.extract_text() or "").strip() for page in reader.pages]
    if has_meaningful_text(extracted):
        return ExtractionResult(page_texts=extracted, method="text")

    ocr_result = try_ocr_pdf(path)
    if ocr_result and has_meaningful_text(ocr_result):
        return ExtractionResult(page_texts=ocr_result, method="ocr")

    return ExtractionResult(page_texts=extracted, method="text")


def try_ocr_pdf(path: Path) -> list[str] | None:
    try:
        import pymupdf
    except ModuleNotFoundError:
        return None

    language = os.getenv("OCR_LANGUAGES", "eng")
    try:
        document = pymupdf.open(path)
        return [
            page.get_text(textpage=page.get_textpage_ocr(language=language, full=True)).strip()
            for page in document
        ]
    except Exception:
        return None


def has_meaningful_text(page_texts: list[str]) -> bool:
    return any(len(text.strip()) >= 20 for text in page_texts)
