"""
End-to-end test for the boiler-room pipeline.

Creates real GitHub issues on a real project board, runs the CLI, and asserts
that the full pipeline produced the expected artefacts. Acts as living
documentation of what the system guarantees on every successful run.

Run with:
    pytest -m e2e tests/e2e/test_e2e.py -v -s

Requirements:
    - `gh` CLI authenticated with write access to the repo
    - `boiler-room` installed in the current Python environment (`pip install -e .`)
    - The GitHub project at PROJECT_URL must have Todo / In Progress / Done columns
"""

import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field

import pytest

from boiler_room.github import GitHubClient
from boiler_room.models import AgentOutput

PROJECT_URL = "https://github.com/users/dznavak/projects/2"

_TASK_SPECS = [
    {
        "title": "Create file hello.txt",
        "body": (
            "Create a file named hello.txt in the repo root "
            "containing the text 'Hello World'"
        ),
    },
    {
        "title": "Create file goodbye.txt",
        "body": (
            "Create a file named goodbye.txt in the repo root "
            "containing the text 'Goodbye World'"
        ),
    },
]


@dataclass
class _E2EItem:
    issue_number: int
    item_id: str
    branch: str


@dataclass
class _E2EContext:
    label: str
    items: list[_E2EItem] = field(default_factory=list)
    client: GitHubClient = None


@pytest.fixture(scope="module")
def e2e_context():
    run_id = str(uuid.uuid4())[:8]
    label = f"e2e-test-{run_id}"
    client = GitHubClient(PROJECT_URL, label=label)

    ctx = _E2EContext(label=label, client=client)

    client.ensure_label(label)

    try:
        for spec in _TASK_SPECS:
            issue_number = client.create_issue(spec["title"], spec["body"], label)
            item_id = client.add_to_project(issue_number)
            client.move_to_todo(item_id)
            ctx.items.append(_E2EItem(
                issue_number=issue_number,
                item_id=item_id,
                branch=f"feature/{issue_number}",
            ))

        yield ctx

    finally:
        for item in ctx.items:
            pr_number = client.find_pr_for_branch(item.branch)
            if pr_number is not None:
                try:
                    client.close_pr(pr_number)
                except Exception:
                    pass
            try:
                client.delete_branch(item.branch)
            except Exception:
                pass
            try:
                client.close_issue(item.issue_number)
            except Exception:
                pass
            try:
                client.remove_from_project(item.item_id)
            except Exception:
                pass
        try:
            client.delete_label(label)
        except Exception:
            pass


@pytest.mark.e2e
def test_pipeline_processes_labeled_tasks(e2e_context):
    """
    Full pipeline run: boiler-room picks up the two e2e-labeled tasks,
    delegates them to claude, commits code, opens PRs, and marks both Done.
    """
    ctx = e2e_context

    # --- Run the CLI ---
    result = subprocess.run(
        [
            "boiler-room",
            "--agent", "claude",
            "--project", PROJECT_URL,
            "--count", "2",
            "--label", ctx.label,
        ],
        timeout=600,
    )
    assert result.returncode == 0, (
        f"boiler-room exited with code {result.returncode}"
    )

    # --- Assert output artefacts ---
    for item in ctx.items:
        output_path = os.path.join(
            ".agent-runs", str(item.issue_number), "output.json"
        )
        assert os.path.exists(output_path), (
            f"output.json missing for issue #{item.issue_number} at {output_path}"
        )
        with open(output_path) as f:
            raw = json.load(f)
        output = AgentOutput(**raw)

        assert output.success is True, (
            f"Agent reported success=False for issue #{item.issue_number}. "
            f"summary: {output.summary!r}"
        )
        assert output.pr_title, (
            f"pr_title is empty for issue #{item.issue_number}"
        )
        assert output.pr_description, (
            f"pr_description is empty for issue #{item.issue_number}"
        )

    # --- Assert PRs were created ---
    for item in ctx.items:
        pr_number = ctx.client.find_pr_for_branch(item.branch)
        assert pr_number is not None, (
            f"No open PR found for branch {item.branch!r} (issue #{item.issue_number})"
        )

    # --- Assert project board items are Done ---
    for item in ctx.items:
        status = ctx.client.get_item_status(item.item_id)
        assert status == "Done", (
            f"Project item {item.item_id} (issue #{item.issue_number}) "
            f"expected status 'Done', got {status!r}"
        )
