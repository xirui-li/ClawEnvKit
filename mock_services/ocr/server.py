"""Mock OCR service — returns pre-loaded text keyed by image path.

Port: 9116
Endpoints:
  POST /ocr/extract   — return OCR text for the given image
  GET  /ocr/health    — health check
  POST /ocr/reset     — reset state
  GET  /ocr/audit     — return call log

Fixtures (OCR_FIXTURES env var) should be a JSON file:
  [
    {"image_path": "menu.jpeg", "text": "Kung Pao Chicken $15.99...", "language": "en", "confidence": 0.95},
    {"image_path": "receipt.png", "text": "Total: $42.50", "language": "en", "confidence": 0.90}
  ]

If image_path doesn't match any fixture, returns empty text.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from mock_services._base import add_error_injection, load_fixtures

app = FastAPI(title="Mock OCR API")
add_error_injection(app)

# ── State ────────────────────────────────────────────────────────────

_ocr_items: list[dict[str, Any]] = []  # [{image_path, text, language, confidence}, ...]
_call_log: list[dict] = []


def _load_fixtures():
    global _ocr_items
    fixtures_path = os.environ.get("OCR_FIXTURES", "")
    if not fixtures_path or not Path(fixtures_path).exists():
        _ocr_items = []
        return

    raw = load_fixtures(fixtures_path)
    if isinstance(raw, list):
        _ocr_items = raw
    else:
        _ocr_items = []


_load_fixtures()


def _find_ocr_result(image_path: str) -> dict[str, Any]:
    """Find OCR result matching the given image path.

    Matches by exact path, filename, or basename without extension.
    """
    if not image_path:
        # No specific image — return first item or empty
        return _ocr_items[0] if _ocr_items else {}

    image_name = Path(image_path).name
    image_stem = Path(image_path).stem

    for item in _ocr_items:
        item_path = item.get("image_path", "")
        # Exact match
        if item_path == image_path:
            return item
        # Filename match
        if Path(item_path).name == image_name:
            return item
        # Stem match (without extension)
        if Path(item_path).stem == image_stem:
            return item

    # No match — return first item as fallback (backward compat)
    return _ocr_items[0] if _ocr_items else {}


# ── Request / Response models ────────────────────────────────────────

class OCRExtractRequest(BaseModel):
    image_path: str = Field("", description="Path to the image file to extract text from")
    language: str = Field("auto", description="Expected language: auto, en, zh, mixed, etc.")


class OCRExtractResponse(BaseModel):
    text: str
    confidence: float = 0.95
    language: str = "auto"
    image_path: str = ""


# ── Endpoints ────────────────────────────────────────────────────────

@app.post("/ocr/extract", response_model=OCRExtractResponse)
async def ocr_extract(req: OCRExtractRequest):
    result = _find_ocr_result(req.image_path)

    response = OCRExtractResponse(
        text=result.get("text", ""),
        confidence=result.get("confidence", 0.95),
        language=result.get("language", req.language),
        image_path=req.image_path,
    )

    _call_log.append({
        "endpoint": "/ocr/extract",
        "action": "extract_text",
        "request_body": req.model_dump(),
        "response_body": response.model_dump(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return response


@app.get("/ocr/health")
async def health():
    return {"status": "ok", "service": "ocr", "fixtures_loaded": len(_ocr_items)}


@app.post("/ocr/reset")
async def reset():
    global _call_log
    _call_log = []
    _load_fixtures()
    return {"status": "reset"}


@app.get("/ocr/audit")
async def audit():
    return {"calls": _call_log}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9116"))
    uvicorn.run(app, host="0.0.0.0", port=port)
