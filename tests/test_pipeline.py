import threading
from unittest.mock import MagicMock, patch

import pytest

from boiler_room.git import GitError
from boiler_room.models import AgentOutput, RunResult, Task
from boiler_room.pipeline import PreparedTask, run_one_task, run_tasks

TASK = Task(
    id="PVTI_abc",
    title="Add login",
    description="Create POST /login",
    comments=[],
    issue_number=42,
    issue_url="https://github.com/owner/repo/issues/42",
)

DRAFT_TASK = Task(
    id="PVTI_draft1",
    title="Draft login",
    description="Prototype auth",
    comments=[],
    is_draft=True,
    draft_issue_id="DI_draft1",
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
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=0,
        output=None,
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.cleanup_worktree"):
        result = run_one_task(client, make_adapter(), "/repo")
    assert result is True
    mock_push.assert_called_once_with("/repo/.worktrees/42", "feature/42")
    client.create_pr.assert_called_once()
    client.move_to_done.assert_called_once_with(TASK.id)


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_agent_failure_resets_to_todo_and_labels_failed(mock_prepare, mock_run_agent):
    client = make_client()
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=1,
        output=None,
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.push_branch"), patch("boiler_room.pipeline.cleanup_worktree"):
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
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=0,
        output=AgentOutput(success=True),
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.cleanup_worktree"):
        run_one_task(client, make_adapter(), "/repo")
    title_used = client.create_pr.call_args.args[1]
    assert title_used == f"feat: {TASK.title}"


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_uses_agent_output_when_present(mock_prepare, mock_run_agent, mock_push):
    client = make_client()
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
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
    with patch("boiler_room.pipeline.cleanup_worktree"):
        run_one_task(client, make_adapter(), "/repo")
    client.create_pr.assert_called_once_with("feature/42", "feat: custom title", "## Custom body")


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_finalize_failure_pushes_branch_and_labels_failed(mock_prepare, mock_run_agent):
    client = make_client()
    client.create_pr.side_effect = Exception("network error")
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=0,
        output=None,
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.push_branch") as mock_push, patch(
        "boiler_room.pipeline.cleanup_worktree"
    ):
        run_one_task(client, make_adapter(), "/repo")
    mock_push.assert_any_call("/repo/.worktrees/42", "feature/42")
    mock_push.assert_any_call("/repo/.worktrees/42", "feature/42", force=True)
    client.add_label.assert_any_call(TASK.issue_number, "failed")
    client.move_to_todo.assert_not_called()
    client.move_to_done.assert_not_called()


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_already_exists_marks_done(mock_prepare, mock_run_agent, mock_push):
    client = make_client()
    client.create_pr.side_effect = Exception("a pull request already exists for branch")
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=0,
        output=None,
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.cleanup_worktree"):
        run_one_task(client, make_adapter(), "/repo")
    client.move_to_done.assert_called_once_with(TASK.id)
    client.add_label.assert_not_called()


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_move_to_todo_called_even_if_label_fails(mock_prepare, mock_run_agent):
    client = make_client()
    client.add_label.side_effect = Exception("label error")
    mock_prepare.return_value = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    mock_run_agent.return_value = RunResult(
        task=TASK,
        exit_code=1,
        output=None,
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    with patch("boiler_room.pipeline.push_branch"), patch("boiler_room.pipeline.cleanup_worktree"):
        run_one_task(client, make_adapter(), "/repo")
    client.move_to_todo.assert_called_once_with(TASK.id)


@patch(
    "boiler_room.pipeline.prepare_worktree",
    return_value=("feature/draft-pvti-draft1", "/repo/.worktrees/draft"),
)
def test_prepare_env_skips_issue_labeling_for_drafts(mock_prepare_worktree):
    client = MagicMock()
    from boiler_room.pipeline import prepare_env

    prepared = prepare_env(client, DRAFT_TASK, "/repo")

    assert prepared.branch == "feature/draft-pvti-draft1"
    assert prepared.worktree_path == "/repo/.worktrees/draft"
    client.move_to_in_progress.assert_called_once_with(DRAFT_TASK.id)
    client.ensure_label.assert_not_called()
    client.add_label.assert_not_called()
    client.remove_draft_tag.assert_called_once_with(DRAFT_TASK, "failed")
    client.add_draft_tag.assert_called_once_with(DRAFT_TASK, "agent-run")
    mock_prepare_worktree.assert_called_once_with("/repo", DRAFT_TASK.branch_suffix)


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_draft_task_uses_draft_pr_body(mock_prepare, mock_run_agent, mock_push):
    client = make_client(task=DRAFT_TASK)
    mock_prepare.return_value = PreparedTask(
        DRAFT_TASK, "feature/draft-pvti-draft1", "/repo/.worktrees/draft"
    )
    mock_run_agent.return_value = RunResult(
        task=DRAFT_TASK,
        exit_code=0,
        output=AgentOutput(success=True),
        branch="feature/draft-pvti-draft1",
        output_dir=".agent-runs/draft-pvti-draft1",
    )

    with patch("boiler_room.pipeline.cleanup_worktree"):
        run_one_task(client, make_adapter(), "/repo")

    client.create_pr.assert_called_once_with(
        "feature/draft-pvti-draft1",
        "feat: Draft login",
        "Implements project draft: Draft login\n\nAutomated by boiler-room.",
    )


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_draft_failure_does_not_try_to_label_issue(mock_prepare, mock_run_agent):
    client = make_client(task=DRAFT_TASK)
    mock_prepare.return_value = PreparedTask(
        DRAFT_TASK, "feature/draft-pvti-draft1", "/repo/.worktrees/draft"
    )
    mock_run_agent.return_value = RunResult(
        task=DRAFT_TASK,
        exit_code=1,
        output=None,
        branch="feature/draft-pvti-draft1",
        output_dir=".agent-runs/draft-pvti-draft1",
    )

    with patch("boiler_room.pipeline.push_branch"), patch("boiler_room.pipeline.cleanup_worktree"):
        result = run_one_task(client, make_adapter(), "/repo")

    assert result is True
    client.ensure_label.assert_not_called()
    client.add_label.assert_not_called()
    client.remove_draft_tag.assert_called_once_with(DRAFT_TASK, "agent-run")
    client.add_draft_tag.assert_called_once_with(DRAFT_TASK, "failed")
    client.move_to_todo.assert_called_once_with(DRAFT_TASK.id)


@patch("boiler_room.pipeline.push_branch")
@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_draft_success_clears_draft_tags(mock_prepare, mock_run_agent, mock_push):
    client = make_client(task=DRAFT_TASK)
    mock_prepare.return_value = PreparedTask(
        DRAFT_TASK, "feature/draft-pvti-draft1", "/repo/.worktrees/draft"
    )
    mock_run_agent.return_value = RunResult(
        task=DRAFT_TASK,
        exit_code=0,
        output=AgentOutput(success=True),
        branch="feature/draft-pvti-draft1",
        output_dir=".agent-runs/draft-pvti-draft1",
    )

    with patch("boiler_room.pipeline.cleanup_worktree"):
        run_one_task(client, make_adapter(), "/repo")

    client.remove_draft_tag.assert_any_call(DRAFT_TASK, "agent-run")
    client.remove_draft_tag.assert_any_call(DRAFT_TASK, "failed")


def test_run_tasks_respects_count_limit():
    task2 = TASK.model_copy(
        update={
            "id": "PVTI_two",
            "issue_number": 43,
            "issue_url": "https://github.com/owner/repo/issues/43",
        }
    )
    client = MagicMock()
    client.fetch_first_todo_task.side_effect = [TASK, task2]

    prepared1 = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    prepared2 = PreparedTask(task2, "feature/43", "/repo/.worktrees/43")

    with (
        patch("boiler_room.pipeline.prepare_env", side_effect=[prepared1, prepared2]) as mock_prepare,
        patch("boiler_room.pipeline._run_prepared_task") as mock_worker,
    ):
        launched = run_tasks(client, make_adapter(), "/repo", count=2, parallelism=2)

    assert launched == 2
    assert client.fetch_first_todo_task.call_count == 2
    assert mock_prepare.call_count == 2
    assert mock_worker.call_count == 2


def test_run_tasks_runs_two_tasks_before_starting_third():
    task2 = TASK.model_copy(
        update={
            "id": "PVTI_two",
            "issue_number": 43,
            "issue_url": "https://github.com/owner/repo/issues/43",
        }
    )
    task3 = TASK.model_copy(
        update={
            "id": "PVTI_three",
            "issue_number": 44,
            "issue_url": "https://github.com/owner/repo/issues/44",
        }
    )
    client = MagicMock()
    client.fetch_first_todo_task.side_effect = [TASK, task2, task3, None]

    prepared1 = PreparedTask(TASK, "feature/42", "/repo/.worktrees/42")
    prepared2 = PreparedTask(task2, "feature/43", "/repo/.worktrees/43")
    prepared3 = PreparedTask(task3, "feature/44", "/repo/.worktrees/44")

    release = threading.Event()
    both_started = threading.Event()
    third_started = threading.Event()
    started: list[str] = []
    started_lock = threading.Lock()

    def fake_worker(_client, _adapter, prepared, _repo_path):
        with started_lock:
            started.append(prepared.task.id)
            if len(started) >= 2:
                both_started.set()
        if prepared.task.id == task3.id:
            third_started.set()
            return
        release.wait(timeout=1)

    with (
        patch("boiler_room.pipeline.prepare_env", side_effect=[prepared1, prepared2, prepared3]),
        patch("boiler_room.pipeline._run_prepared_task", side_effect=fake_worker),
    ):
        runner = threading.Thread(
            target=run_tasks,
            args=(client, make_adapter(), "/repo"),
            kwargs={"parallelism": 2},
        )
        runner.start()
        assert both_started.wait(timeout=1)
        assert not third_started.is_set()
        release.set()
        runner.join(timeout=2)

    assert third_started.is_set()
