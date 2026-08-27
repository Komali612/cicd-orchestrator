"""FROZEN — proves the frame is wired before you write a line of logic."""
from agent.agent import build_agent


def test_builds():
    assert build_agent() is not None
