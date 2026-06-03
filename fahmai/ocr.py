# -*- coding: utf-8 -*-
"""OCR over images and PDFs via the typhoon-ocr-preview vLLM model.

run_ocr(data_b64) -> {"result": "<text>", "pages": N, "total_output_token": N}

- Images (PNG/JPEG/etc.) are sent directly to the model as a data: URL.
- PDFs are rasterized page-by-page with PyMuPDF, each page OCR'd, results concatenated.
"""
from __future__ import annotations

import base64
import os

import httpx

from fahmai.agents.config import OCR_API_KEY_ENV, OCR_BASE_URL, OCR_MODEL

_PROMPT = (
    "Extract ALL text visible in this image exactly as it appears, preserving reading order, "
    "line breaks, numbers, and Thai/English characters. Return only the extracted text."
)
_TIMEOUT = 360
# The vision encoder rejects very large images (HTTP 500). Cap the longest side; statement
# pages downscaled to <=2000px OCR cleanly. Override with FAHMAI_OCR_MAX_SIDE.
_MAX_SIDE = int(os.getenv("FAHMAI_OCR_MAX_SIDE", "2000"))


def _image_to_capped_png_b64(raw: bytes) -> tuple[str, str]:
    """Decode an image, downscale so its longest side <= _MAX_SIDE, return (b64_png, mime).

    If the image is already within bounds it is returned unchanged (re-encoded as PNG by fitz
    only when downscaling is needed)."""
    import fitz  # lazy

    doc = fitz.open(stream=raw, filetype=None)  # fitz sniffs the image type
    try:
        page = doc[0]
        w, h = page.rect.width, page.rect.height
        longest = max(w, h)
        if longest <= _MAX_SIDE:
            return base64.b64encode(raw).decode(), _detect(raw)[0]
        scale = _MAX_SIDE / longest
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        return base64.b64encode(pix.tobytes("png")).decode(), "image/png"
    finally:
        doc.close()


def _detect(raw: bytes) -> tuple[str, bool]:
    """Return (mime, is_pdf). Sniffs magic bytes."""
    if raw[:5] == b"%PDF-":
        return "application/pdf", True
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", False
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg", False
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp", False
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", False
    return "image/png", False  # default; let the model try


def _ocr_image_b64(client: httpx.Client, img_b64: str, mime: str) -> tuple[str, int]:
    """OCR one base64 image; returns (text, total_tokens)."""
    key = os.environ.get(OCR_API_KEY_ENV, "EMPTY")
    r = client.post(
        OCR_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": OCR_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    {"type": "text", "text": _PROMPT},
                ],
            }],
            "max_tokens": 4096,
            "temperature": 0.0,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    j = r.json()
    text = j["choices"][0]["message"]["content"]
    total = (j.get("usage") or {}).get("total_tokens", 0)
    return text, total


def _pdf_pages_to_png(raw: bytes, dpi: int = 200) -> list[bytes]:
    """Rasterize each PDF page to PNG bytes (PyMuPDF), capping the longest side at _MAX_SIDE."""
    import fitz  # lazy import — only needed for PDFs

    pages: list[bytes] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        zoom = dpi / 72.0
        for page in doc:
            w, h = page.rect.width * zoom, page.rect.height * zoom
            longest = max(w, h)
            z = zoom * (_MAX_SIDE / longest) if longest > _MAX_SIDE else zoom
            pix = page.get_pixmap(matrix=fitz.Matrix(z, z))
            pages.append(pix.tobytes("png"))
    finally:
        doc.close()
    return pages


def run_ocr(data_b64: str) -> dict:
    """OCR an image or PDF given as a base64 string. Returns {result, pages, total_output_token}."""
    try:
        raw = base64.b64decode(data_b64, validate=False)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"invalid base64 input: {e}") from e
    if not raw:
        raise ValueError("empty input")

    mime, is_pdf = _detect(raw)
    total_tokens = 0

    with httpx.Client(timeout=_TIMEOUT) as client:
        if is_pdf:
            page_pngs = _pdf_pages_to_png(raw)
            texts = []
            for i, png in enumerate(page_pngs, 1):
                b64 = base64.b64encode(png).decode()
                txt, tok = _ocr_image_b64(client, b64, "image/png")
                total_tokens += tok
                texts.append(f"--- page {i} ---\n{txt}")
            return {"result": "\n\n".join(texts), "pages": len(page_pngs),
                    "total_output_token": total_tokens}
        else:
            img_b64, img_mime = _image_to_capped_png_b64(raw)
            txt, tok = _ocr_image_b64(client, img_b64, img_mime)
            return {"result": txt, "pages": 1, "total_output_token": tok}
