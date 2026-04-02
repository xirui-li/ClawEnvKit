"""Mock Scheduler API service for agent evaluation (FastAPI on port 9112).

Manages cron/scheduled jobs with execution history tracking.
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

app = FastAPI(title="Mock Scheduler API")

from mock_services._base import add_error_injection, load_fixtures

add_error_injection(app)

FIXTURES_PATH = Path(os.environ.get("SCHEDULER_FIXTURES", "/dev/null"))
