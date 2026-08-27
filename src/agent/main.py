"""FROZEN — identical in every agent repo. Do not edit."""
from agent_core import runtime

from .agent import build_agent


def main() -> None:
    runtime.run(build_agent())


if __name__ == "__main__":
    main()
