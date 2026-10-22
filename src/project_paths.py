"""Resolve project assets independently of the working directory."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_SPECS = ROOT / "config" / "tool_list.json"
