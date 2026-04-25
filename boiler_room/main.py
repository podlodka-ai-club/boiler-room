import argparse
import logging
import os
import sys

from boiler_room.agents.base import AgentAdapter
from boiler_room.agents.claude import ClaudeAdapter
from boiler_room.agents.copilot import CopilotAdapter
from boiler_room.github import GitHubClient
from boiler_room.pipeline import run_one_task

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def build_adapter(agent: str) -> AgentAdapter:
    if agent == "claude":
        return ClaudeAdapter()
    if agent == "copilot":
        return CopilotAdapter()
    print(f"Unknown agent: {agent!r}. Choose 'claude' or 'copilot'.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pick tasks from a GitHub Project and delegate them to a local AI coding agent."
    )
    parser.add_argument(
        "--version", action="version", version="boiler-room 0.1.0",
    )
    parser.add_argument(
        "--agent", required=True, choices=["claude", "copilot"],
        help="Which AI agent to use",
    )
    parser.add_argument(
        "--project", required=True,
        help="GitHub Project URL, e.g. https://github.com/users/dznavak/projects/2",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="Maximum number of tasks to process (default: unlimited)",
    )
    parser.add_argument(
        "--label", default=None,
        help="Only process issues carrying this GitHub label",
    )
    args = parser.parse_args()

    print("Welcome to boiler-room — your AI-powered task runner!")

    adapter = build_adapter(args.agent)
    client = GitHubClient(args.project, label=args.label)
    repo_path = os.getcwd()

    processed = 0
    while args.count is None or processed < args.count:
        found = run_one_task(client, adapter, repo_path)
        if not found:
            logging.info("Queue empty. Done.")
            break
        processed += 1
