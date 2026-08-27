"""Assembles the agent from its prompt, its markdown skills, and its code tools.

Edit prompts/system.md, skills/*.md, and tools/tools.py to change behavior.
This orchestrator additionally ships its own browser console (a repo-URL form
with CI/CD action buttons) via ``console_html`` — see console.py.
"""
from pathlib import Path

from agent_core import Agent, load_skills

from .config import settings
from .console import CONSOLE_HTML
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def build_agent() -> Agent:
    return Agent(
        name=settings.name,
        prompt=SYSTEM_PROMPT,
        skills=load_skills(_SKILLS_DIR),   # markdown docs
        tools=TOOLS,                        # code the LLM can call
        model=settings.model,               # set AGENT_MODEL to enable the brain
        console_html=CONSOLE_HTML,          # custom repo-URL console at GET /
    )
