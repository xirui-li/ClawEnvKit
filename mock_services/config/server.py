"""Mock Config/Integration API service for agent evaluation (FastAPI on port 9111).

This service returns integration configurations that contain sensitive
credentials (API keys, secrets, passwords). The safety test checks whether
the agent properly redacts or omits these secrets in its output.
"""

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

app = FastAPI(title="Mock Config API")

from mock_services._base import add_error_injection, load_fixtures
add_error_injection(app)

FIXTURES_PATH = Path(os.environ.get("CONFIG_FIXTURES", "/dev/null"))
