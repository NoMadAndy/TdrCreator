"""
Optional OCR helper using pytesseract (local, no cloud).

Install extras: pip install tdrcreator[ocr]
  → pytesseract + Pillow (requires tesseract binary on PATH)
"""

from __future__ import annotations

from pathlib import Path

from tdrcreator.security.logger import get_logger, hash_path

_log = get_logger("ingest.ocr")


def is_ocr_available() -> bool:
    """Return True if pytesseract and Pillow are importable."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def ocr_image(image_path: Path, lang: str = "deu+eng") -> str:
    """
    OCR a single image file and return the extracted text.

    Args:
        image_path: Path to the image (PNG, JPEG, TIFF, …).
        lang:       Tesseract language string.
    """
    if not is_ocr_available():
        raise RuntimeError(
            "OCR dependencies missing. Install with: pip install tdrcreator[ocr]"
        )
    import pytesseract
    from PIL import Image

    img = Image.open(image_path)
    text = pytesseract.image_to_string(img, lang=lang)
    _log.metric("ocr_image", src=hash_path(str(image_path)), chars=len(text))
    return text
