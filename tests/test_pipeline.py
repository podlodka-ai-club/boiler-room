import pytest
from unittest.mock import MagicMock, patch
from boiler_room.models import Task, AgentOutput, RunResult
from boiler_room.pipeline import run_one_task
from boiler_room.git import GitError

TASK = Task(
    id="PVTI_abc",
    title="Add login",
    description="Create POST /login",
    comments=[],
    issue_number=42,
    issue_url="https://github.com/owner/repo/issues/42",
)


def make_client(task=TASK):
    client = MagicMock()
    client.fetch_first_todo_task.return_value = task
    return client


def make_adapter():
    adapter = MagicMock()
    adapter.build_prompt.return_value = "do the task"
    adapter.build_command.return_value = ["claude", "-p", "do the task"]
    return adapter


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_success_creates_pr(mock_prepare, mock_run_agent, mock_push):
    client = make_client()
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=0, output=None,
        branch="feature/42", output_dir=".agent-runs/42",
    )
    result = run_one_task(client, make_adapter(), "/repo")
    assert result is True
    mock_push.assert_called_once_with("/repo", "feature/42")
    client.create_pr.assert_called_once()
    client.move_to_done.assert_called_once_with(TASK.id)


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_agent_failure_resets_to_todo_and_labels_failed(mock_prepare, mock_run_agent):
    client = make_client()
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=1, output=None,
        branch="feature/42", output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.push_branch"):
        result = run_one_task(client, make_adapter(), "/repo")
    assert result is True
    client.move_to_todo.assert_called_once_with(TASK.id)
    client.add_label.assert_any_call(TASK.issue_number, "failed")
    client.create_pr.assert_not_called()


@patch("boiler_room.pipeline.prepare_env", side_effect=GitError("not a git repo"))
def test_prepare_failure_resets_to_todo_no_pr(mock_prepare):
    client = make_client()
    result = run_one_task(client, make_adapter(), "/repo")
    assert result is True
    client.move_to_todo.assert_called_once_with(TASK.id)
    client.create_pr.assert_not_called()


def test_empty_queue_returns_false():
    client = MagicMock()
    client.fetch_first_todo_task.return_value = None
    result = run_one_task(client, make_adapter(), "/repo")
    assert result is False


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_title_falls_back_to_task_title(mock_prepare, mock_run_agent, mock_push):
    client = make_client()
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=0, output=AgentOutput(success=True),
        branch="feature/42", output_dir=".agent-runs/42",
    )
    run_one_task(client, make_adapter(), "/repo")
    title_used = client.create_pr.call_args.args[1]
    assert title_used == f"feat: {TASK.title}"


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_uses_agent_output_when_present(mock_prepare, mock_run_agent, mock_push):
    client = make_client()
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=0,
        output=AgentOutput(
            pr_title="feat: custom title",
            pr_description="## Custom body",
            success=True,
        ),
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    run_one_task(client, make_adapter(), "/repo")
    client.create_pr.assert_called_once_with("feature/42", "feat: custom title", "## Custom body")


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_finalize_failure_pushes_branch_and_labels_failed(mock_prepare, mock_run_agent):
    client = make_client()
    client.create_pr.side_effect = Exception("network error")
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=0, output=None,
        branch="feature/42", output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.push_branch") as mock_push:
        run_one_task(client, make_adapter(), "/repo")
    # First call: normal push before create_pr; second: force-push from _handle_failure
    mock_push.assert_any_call("/repo", "feature/42")
    mock_push.assert_any_call("/repo", "feature/42", force=True)
    client.add_label.assert_any_call(TASK.issue_number, "failed")
    client.move_to_todo.assert_not_called()  # task left In Progress — code is done
    client.move_to_done.assert_not_called()


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_already_exists_marks_done(mock_prepare, mock_run_agent, mock_push):
    client = make_client()
    client.create_pr.side_effect = Exception("a pull request already exists for branch")
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=0, output=None,
        branch="feature/42", output_dir=".agent-runs/42",
    )
    run_one_task(client, make_adapter(), "/repo")
    client.move_to_done.assert_called_once_with(TASK.id)
    client.add_label.assert_not_called()


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_move_to_todo_called_even_if_label_fails(mock_prepare, mock_run_agent):
    client = make_client()
    client.add_label.side_effect = Exception("label error")
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=1, output=None,
        branch="feature/42", output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.push_branch"):
        run_one_task(client, make_adapter(), "/repo")
    client.move_to_todo.assert_called_once_with(TASK.id)
