"""FROZEN — loads the prompt file into SYSTEM_PROMPT."""
from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).parent / "system.md").read_text(encoding="utf-8")
