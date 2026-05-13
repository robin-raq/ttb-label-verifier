"""Append-only JSON-lines audit writer — FR-013, §2.1.

Each call to `write_audit_record` appends one JSON object (followed by newline)
to the file at AUDIT_LOG_PATH. The file is created with mode 0o600 on first
write, and the parent directory is created if it does not exist.

Image bytes are NEVER written here — only the SHA-256 digest.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Default path; tests override this module-level var to redirect to tmp_path.
AUDIT_LOG_PATH: str = os.environ.get("AUDIT_LOG_PATH", "./data/audit.jsonl")


def write_audit_record(record: dict[str, Any]) -> None:
    """Append one audit record to the JSONL file.

    Thread-safety: writes are atomic at the OS level for small records because
    we open the file, write one line, and close it immediately. For high
    concurrency, a dedicated writer process or async queue would be preferable
    — deferred to v2 per ROADMAP.
    """
    path = Path(AUDIT_LOG_PATH)
    _ensure_parent(path)

    line = json.dumps(record, default=str) + "\n"

    # Open with append mode; create with 0o600 if new.
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(str(path), flags, mode=0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def _ensure_parent(path: Path) -> None:
    """Create parent directories if they do not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
