"""Mock CRM API service for agent evaluation (FastAPI on port 9110).

This service is designed for error-recovery testing: the task YAML sets
ERROR_RATE=0.5 so roughly half of tool calls will fail with 429/500.
The agent must retry to complete the data export.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock CRM API")

from mock_services._base import add_error_injection, load_fixtures

add_error_injection(app)

FIXTURES_PATH = Path(os.environ.get("CRM_FIXTURES", "/dev/null"))
