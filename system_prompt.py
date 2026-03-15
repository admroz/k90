"""Wczytuje system prompt — najpierw z DATA_DIR/system_prompt.md (override), potem z katalogu repo."""

import os
from pathlib import Path

_repo_default = Path(__file__).parent / "system_prompt.md"
_data_override = Path(os.getenv("DATA_DIR", "data")) / "system_prompt.md"

if _data_override.exists():
    SYSTEM_PROMPT = _data_override.read_text(encoding="utf-8")
else:
    SYSTEM_PROMPT = _repo_default.read_text(encoding="utf-8")
