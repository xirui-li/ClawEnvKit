"""Mock Caption service — returns pre-loaded image captions keyed by image path.

Port: 9118
Endpoints:
  POST /caption/describe   — return caption for the given image
  GET  /caption/health     — health check
  POST /caption/reset      — reset state
  GET  /caption/audit      — return call log

Fixtures (CAPTION_FIXTURES env var) should be a JSON file:
  [
    {"image_path": "photo.jpg", "caption": "A sunset over the ocean", "confidence": 0.95},
    {"image_path": "chart.png", "caption": "Bar chart showing Q1-Q4 revenue", "confidence": 0.88}
  ]
"""

from __future__ import annotations

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

app = FastAPI(title="Mock Caption API")
add_error_injection(app)

# ── State ────────────────────────────────────────────────────────────

_caption_items: list[dict[str, Any]] = []
_call_log: list[dict] = []


def _load_fixtures():
    global _caption_items
    fixtures_path = os.environ.get("CAPTION_FIXTURES", "")
    if not fixtures_path or not Path(fixtures_path).exists():
        _caption_items = []
        return
    _caption_items = load_fixtures(fixtures_path)


_load_fixtures()


def _find_caption(image_path: str) -> dict[str, Any]:
    """Find caption matching the given image path."""
    if not image_path:
        return _caption_items[0] if _caption_items else {}

    image_name = Path(image_path).name
    image_stem = Path(image_path).stem

    for item in _caption_items:
        item_path = item.get("image_path", "")
        if item_path == image_path:
            return item
        if Path(item_path).name == image_name:
            return item
        if Path(item_path).stem == image_stem:
            return item

    return _caption_items[0] if _caption_items else {}


# ── Request / Response models ────────────────────────────────────────

class CaptionRequest(BaseModel):
    image_path: str = Field("", description="Path to the image file to describe")


class CaptionResponse(BaseModel):
    caption: str
    confidence: float = 0.92
    image_path: str = ""


# ── Endpoints ────────────────────────────────────────────────────────

@app.post("/caption/describe", response_model=CaptionResponse)
async def caption_describe(req: CaptionRequest):
    result = _find_caption(req.image_path)

    response = CaptionResponse(
        caption=result.get("caption", ""),
        confidence=result.get("confidence", 0.92),
        image_path=req.image_path,
    )

    _call_log.append({
        "endpoint": "/caption/describe",
        "action": "describe_image",
        "request_body": req.model_dump(),
        "response_body": response.model_dump(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return response


@app.get("/caption/health")
async def health():
    return {"status": "ok", "service": "caption", "fixtures_loaded": len(_caption_items)}


@app.post("/caption/reset")
async def reset():
    global _call_log
    _call_log = []
    _load_fixtures()
    return {"status": "reset"}


@app.get("/caption/audit")
async def audit():
    return {"calls": _call_log}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9118"))
    uvicorn.run(app, host="0.0.0.0", port=port)
