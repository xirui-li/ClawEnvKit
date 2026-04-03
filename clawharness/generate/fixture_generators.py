"""Auto-generate fixture files for file-dependent tasks.

Each generator creates real files (SQLite DBs, CSVs, text, PDFs, images)
and returns a list of file mount specs for the task.yaml `files` field.

Usage:
    from clawharness.generate.fixture_generators import generate_fixtures

    files = generate_fixtures(
        category="terminal",
        topic="SQLite WAL recovery",
        output_dir=Path("dataset/terminal-001/fixtures"),
    )
    # Returns: [{"source": "fixtures/test.db", "target": "/workspace/test.db"}, ...]
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import textwrap
from pathlib import Path
from typing import Any

from clawharness.llm_client import call_llm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_fixtures(
    category: str,
    topic: str,
    output_dir: Path,
    **kwargs,
) -> list[dict[str, str]]:
    """Generate fixture files for a task category.

    Args:
        category: Task category (terminal, office_qa, ocr, etc.)
        topic: Description of what fixtures to create
        output_dir: Directory to write fixture files into

    Returns:
        List of {"source": relative_path, "target": container_path} dicts
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    generator = GENERATORS.get(category)
    if not generator:
        raise ValueError(f"No fixture generator for category '{category}'. Available: {list(GENERATORS.keys())}")

    return generator(topic=topic, output_dir=output_dir, **kwargs)


# ---------------------------------------------------------------------------
# Terminal: programmatic generation of .db, .sql, .py, .txt files
# ---------------------------------------------------------------------------

def _generate_terminal_fixtures(
    topic: str,
    output_dir: Path,
    **kwargs,
) -> list[dict[str, str]]:
    """Generate fixture files for terminal/shell tasks.

    Uses LLM to design the data, then Python to create actual files.
    """
    # Ask LLM what files to create
    plan_prompt = f"""You are generating test fixture files for a terminal/shell task.

Topic: {topic}

Output a JSON object describing the files to create. Each file has a type and content spec.
Supported types: "sqlite" (creates .db), "sql" (creates .sql text), "python" (creates .py),
"text" (creates .txt or .md), "binary" (creates small binary file).

For sqlite: provide "tables" with schema + sample rows.
For sql/python/text: provide "content" as the file text.
For binary: provide "hex" as hex-encoded bytes (keep small, <1KB).

Example:
{{
  "files": [
    {{
      "filename": "test.db",
      "type": "sqlite",
      "tables": {{
        "users": {{
          "columns": "id INTEGER PRIMARY KEY, name TEXT, email TEXT",
          "rows": [
            [1, "Alice", "alice@example.com"],
            [2, "Bob", "bob@example.com"]
          ]
        }}
      }}
    }},
    {{
      "filename": "schema.sql",
      "type": "sql",
      "content": "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
    }}
  ]
}}

Return ONLY the JSON. No markdown fences, no explanation."""

    response = call_llm(plan_prompt, max_tokens=2048)
    plan = _parse_json(response)
    if not plan or "files" not in plan:
        raise ValueError(f"LLM returned invalid fixture plan: {response[:200]}")

    files = []
    for spec in plan["files"]:
        filename = spec["filename"]
        ftype = spec["type"]
        filepath = output_dir / filename

        if ftype == "sqlite":
            _create_sqlite(filepath, spec.get("tables", {}))
        elif ftype in ("sql", "python", "text"):
            filepath.write_text(spec.get("content", ""))
        elif ftype == "binary":
            hex_data = spec.get("hex", "")
            filepath.write_bytes(bytes.fromhex(hex_data))
        else:
            filepath.write_text(spec.get("content", ""))

        files.append({
            "source": str(filepath.relative_to(output_dir.parent)),
            "target": f"/workspace/{filename}",
        })

    return files


def _create_sqlite(path: Path, tables: dict[str, Any]) -> None:
    """Create a SQLite database from a table spec."""
    conn = sqlite3.connect(str(path))
    for table_name, table_spec in tables.items():
        columns = table_spec.get("columns", "id INTEGER PRIMARY KEY")
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")

        rows = table_spec.get("rows", [])
        if rows:
            placeholders = ", ".join(["?"] * len(rows[0]))
            conn.executemany(
                f"INSERT INTO {table_name} VALUES ({placeholders})",
                rows,
            )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CSV / Excel: programmatic generation
# ---------------------------------------------------------------------------

def _generate_data_fixtures(
    topic: str,
    output_dir: Path,
    **kwargs,
) -> list[dict[str, str]]:
    """Generate CSV/data files for data analysis tasks."""
    plan_prompt = f"""Generate realistic business data for a data analysis task.

Topic: {topic}

Output a JSON object with files to create:
{{
  "files": [
    {{
      "filename": "quarterly_sales.csv",
      "headers": ["quarter", "region", "revenue", "expenses", "units_sold"],
      "rows": [
        ["Q1 2025", "North", 1250000, 890000, 4500],
        ...
      ]
    }}
  ]
}}

Include 15-30 rows of realistic data. Return ONLY JSON."""

    response = call_llm(plan_prompt, max_tokens=4096)
    plan = _parse_json(response)
    if not plan or "files" not in plan:
        raise ValueError(f"Invalid data fixture plan: {response[:200]}")

    files = []
    for spec in plan["files"]:
        filename = spec["filename"]
        filepath = output_dir / filename

        headers = spec.get("headers", [])
        rows = spec.get("rows", [])

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            if headers:
                writer.writerow(headers)
            writer.writerows(rows)

        files.append({
            "source": str(filepath.relative_to(output_dir.parent)),
            "target": f"/workspace/{filename}",
        })

    return files


# ---------------------------------------------------------------------------
# Text: LLM-generated .txt files
# ---------------------------------------------------------------------------

def _generate_text_fixtures(
    topic: str,
    output_dir: Path,
    **kwargs,
) -> list[dict[str, str]]:
    """Generate text files (blog posts, articles, reports) via LLM."""
    prompt = f"""Write a realistic document for the following purpose:

{topic}

The document should be 400-800 words, well-structured, and contain specific facts/numbers
that can be used for verification in a grading rubric.

Return ONLY the document text. No markdown fences."""

    content = call_llm(prompt, max_tokens=2048)
    filename = kwargs.get("filename", "document.txt")
    filepath = output_dir / filename
    filepath.write_text(content)

    return [{
        "source": str(filepath.relative_to(output_dir.parent)),
        "target": f"/workspace/{filename}",
    }]


# ---------------------------------------------------------------------------
# PDF: web download
# ---------------------------------------------------------------------------

def _retrieve_pdf_fixtures(
    topic: str,
    output_dir: Path,
    **kwargs,
) -> list[dict[str, str]]:
    """Download a public PDF from the web for document tasks."""
    import urllib.request

    # Ask LLM for a specific public PDF URL
    url_prompt = f"""I need a direct URL to a freely available, public-domain PDF document.

Topic: {topic}

Requirements:
- Must be a direct .pdf link (not a landing page)
- Must be publicly accessible without login
- Prefer government documents, arXiv papers, or open-access reports
- The document should contain specific facts/numbers suitable for Q&A

Return ONLY the URL, nothing else."""

    url = call_llm(url_prompt, max_tokens=256).strip()

    # Validate it looks like a URL
    if not url.startswith("http"):
        raise ValueError(f"LLM returned invalid URL: {url}")

    filename = kwargs.get("filename", "document.pdf")
    filepath = output_dir / filename

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ClawHarnessing/1.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        filepath.write_bytes(resp.read())
    except Exception as e:
        raise ValueError(f"Failed to download PDF from {url}: {e}")

    return [{
        "source": str(filepath.relative_to(output_dir.parent)),
        "target": f"/workspace/{filename}",
    }]


# ---------------------------------------------------------------------------
# Image: web download or Pillow generation
# ---------------------------------------------------------------------------

def _retrieve_image_fixtures(
    topic: str,
    output_dir: Path,
    **kwargs,
) -> list[dict[str, str]]:
    """Download or generate an image for OCR/vision tasks.

    First tries to generate a meaningful test image with Pillow.
    Falls back to web download if visual complexity is needed.
    """
    mode = kwargs.get("mode", "generate")  # "generate" or "download"
    filename = kwargs.get("filename", "image.jpg")
    filepath = output_dir / filename

    if mode == "generate":
        _generate_test_image(topic, filepath)
    else:
        _download_image(topic, filepath)

    return [{
        "source": str(filepath.relative_to(output_dir.parent)),
        "target": f"/workspace/{filename}",
    }]


def _generate_test_image(topic: str, filepath: Path) -> None:
    """Generate a test image with text/data using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("Pillow required for image generation: pip install Pillow")

    # Ask LLM what text/layout to put on the image
    layout_prompt = f"""Design text content for a test image.

Topic: {topic}

Output JSON with text blocks to render:
{{
  "width": 800,
  "height": 600,
  "background": "white",
  "blocks": [
    {{"x": 50, "y": 30, "text": "Restaurant Menu", "size": 28, "color": "black"}},
    {{"x": 50, "y": 80, "text": "Kung Pao Chicken - $15.99", "size": 18, "color": "black"}},
    ...
  ]
}}

Return ONLY JSON."""

    response = call_llm(layout_prompt, max_tokens=1024)
    layout = _parse_json(response)
    if not layout:
        raise ValueError(f"Invalid image layout: {response[:200]}")

    w = layout.get("width", 800)
    h = layout.get("height", 600)
    bg = layout.get("background", "white")
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    for block in layout.get("blocks", []):
        x = block.get("x", 0)
        y = block.get("y", 0)
        text = block.get("text", "")
        color = block.get("color", "black")
        # Use default font (no external font file needed)
        try:
            size = block.get("size", 16)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except (OSError, IOError):
            font = ImageFont.load_default()
        draw.text((x, y), text, fill=color, font=font)

    img.save(str(filepath))


def _download_image(topic: str, filepath: Path) -> None:
    """Download a public image from the web."""
    import urllib.request

    url_prompt = f"""I need a direct URL to a freely available image.

Topic: {topic}

Requirements:
- Must be a direct image link (.jpg, .jpeg, .png)
- Must be publicly accessible (Creative Commons, public domain, or Wikimedia)
- Should be relevant to the topic

Return ONLY the URL, nothing else."""

    url = call_llm(url_prompt, max_tokens=256).strip()
    if not url.startswith("http"):
        raise ValueError(f"Invalid image URL: {url}")

    req = urllib.request.Request(url, headers={"User-Agent": "ClawHarnessing/1.0"})
    resp = urllib.request.urlopen(req, timeout=30)
    filepath.write_bytes(resp.read())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict | None:
    """Parse JSON from LLM response, stripping markdown fences."""
    import re

    text = text.strip()
    # Strip markdown fences: ```json\n...\n```
    fence_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GENERATORS = {
    "terminal": _generate_terminal_fixtures,
    "data_analysis": _generate_data_fixtures,
    "rewriting": _generate_text_fixtures,
    "comprehension": _retrieve_pdf_fixtures,
    "office_qa": _retrieve_pdf_fixtures,
    "ocr": _retrieve_image_fixtures,
    "safety": _generate_text_fixtures,
}
