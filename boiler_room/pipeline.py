import json
import logging
import os
import subprocess

from boiler_room.agents.base import AgentAdapter
from boiler_room.git import prepare_branch, push_branch
from boiler_room.github import GitHubClient
from boiler_room.models import AgentOutput, RunResult, Task

logger = logging.getLogger(__name__)


def run_one_task(client: GitHubClient, adapter: AgentAdapter, repo_path: str) -> bool:
    """Process one task. Returns True if a task was found, False if queue is empty."""
    task = client.fetch_first_todo_task()
    if task is None:
        return False

    try:
        branch = prepare_env(client, task, repo_path)
    except Exception as e:
        logger.error("prepare_env failed for task %s: %s", task.ref, e)
        client.move_to_todo(task.id)
        return True

    result = run_agent(adapter, task, branch, repo_path)
    _finalize(client, result, repo_path)
    return True


def prepare_env(client: GitHubClient, task: Task, repo_path: str) -> str:
    branch = prepare_branch(repo_path, task.branch_suffix)
    client.move_to_in_progress(task.id)
    if task.issue_number is not None:
        client.ensure_label("agent-run")
        client.add_label(task.issue_number, "agent-run")
    elif task.is_draft:
        client.remove_draft_tag(task, "failed")
        client.add_draft_tag(task, "agent-run")
    return branch


def run_agent(adapter: AgentAdapter, task: Task, branch: str, repo_path: str) -> RunResult:
    output_dir = os.path.join(repo_path, ".agent-runs", task.output_id)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "output.json")

    if os.path.exists(output_path):
        os.remove(output_path)

    prompt = adapter.build_prompt(task, output_path)
    command = adapter.build_command(prompt, output_path)

    try:
        proc = subprocess.run(command, cwd=repo_path, timeout=3600)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        logger.error("Agent timed out after 3600s for task %s", task.ref)
        exit_code = 1

    return RunResult(
        task=task,
        exit_code=exit_code,
        output=_read_output(output_path),
        branch=branch,
        output_dir=output_dir,
    )


def _read_output(output_path: str) -> AgentOutput | None:
    if not os.path.exists(output_path):
        return None
    try:
        with open(output_path) as f:
            return AgentOutput(**json.load(f))
    except Exception as e:
        logger.warning("Could not parse agent output at %s: %s", output_path, e)
        return None


def _finalize(client: GitHubClient, result: RunResult, repo_path: str) -> None:
    if result.exit_code != 0:
        _handle_failure(client, result, repo_path, reset_to_todo=True)
        return

    pr_title = (
        result.output.pr_title
        if result.output and result.output.pr_title
        else f"feat: {result.task.title}"
    )
    pr_body = (
        result.output.pr_description
        if result.output and result.output.pr_description
        else _default_pr_body(result.task)
    )

    try:
        push_branch(repo_path, result.branch)
        url = client.create_pr(result.branch, pr_title, pr_body)
        logger.info("PR created: %s", url)
        if result.task.is_draft:
            client.remove_draft_tag(result.task, "agent-run")
            client.remove_draft_tag(result.task, "failed")
        client.move_to_done(result.task.id)
    except Exception as e:
        err = str(e)
        if "already exists" in err:
            logger.info("PR already open for branch %s — marking Done", result.branch)
            client.move_to_done(result.task.id)
        else:
            logger.error("finalize failed: %s — leaving task In Progress", e)
            _handle_failure(client, result, repo_path, reset_to_todo=False)


def _handle_failure(
    client: GitHubClient, result: RunResult, repo_path: str, *, reset_to_todo: bool
) -> None:
    try:
        push_branch(repo_path, result.branch, force=True)
    except Exception as e:
        logger.warning("Could not push failure branch %s: %s", result.branch, e)
    if result.task.issue_number is not None:
        try:
            client.ensure_label("failed")
            client.add_label(result.task.issue_number, "failed")
        except Exception as e:
            logger.error("Could not apply 'failed' label on issue %s: %s", result.task.issue_number, e)
    elif result.task.is_draft:
        try:
            client.remove_draft_tag(result.task, "agent-run")
            client.add_draft_tag(result.task, "failed")
        except Exception as e:
            logger.error("Could not tag failed draft %s: %s", result.task.ref, e)
    if reset_to_todo:
        client.move_to_todo(result.task.id)


def _default_pr_body(task: Task) -> str:
    if task.issue_number is not None:
        return f"Implements #{task.issue_number}\n\nAutomated by boiler-room."
    return f"Implements project draft: {task.title}\n\nAutomated by boiler-room."
