from pathlib import Path
from datetime import datetime
from typing import List, Tuple

from ..models import UsageRecord, HumanMessage, ToolEvent, Source

HARNESS = "pi"


def parse(root: Path, since: datetime, include_subagents: bool, redact_on: bool) -> Tuple[List[UsageRecord], List[HumanMessage], List[ToolEvent], Source]:
    return [], [], [], Source(HARNESS, str(root), note="adapter pending")
