"""Mock Todo API service for agent evaluation (FastAPI on port 9102)."""

from __future__ import annotations

import json
import copy
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock Todo API")

from mock_services._base import add_error_injection, load_fixtures
add_error_injection(app)

FIXTURES_PATH = Path(os.environ.get("TODO_FIXTURES", "/dev/null"))
