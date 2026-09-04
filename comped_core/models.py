from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class UsageRecord:
    harness: str
    session_id: str
    record_id: str
    timestamp: str
    model: str
    input_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    output_tokens: int
    reasoning_tokens: int
    project: str
    is_subagent: bool
    turn_id: str


@dataclass(frozen=True)
class HumanMessage:
    harness: str
    session_id: str
    message_id: str
    timestamp: str
    text: str
    text_sha256: str
    project: str
    origin: str  # "human" | "unknown" | "automated"


@dataclass(frozen=True)
class ToolEvent:
    harness: str
    session_id: str
    event_id: str
    timestamp: str
    tool_name: str
    input_summary: str
    is_error: bool
    error_text: str
    turn_id: str


@dataclass
class Source:
    harness: str
    root: str
    found: bool = False
    files: int = 0
    lines: int = 0
    parsed: int = 0
    duplicates: int = 0
    unparsed: int = 0
    note: str = ""


@dataclass
class Ledger:
    records: List[UsageRecord]
    humans: List[HumanMessage]
    tools: List[ToolEvent]
    sources: List[Source]
    generated_at: str
