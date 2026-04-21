import pytest
from unittest.mock import patch, MagicMock, call
from boiler_room.git import GitError, prepare_branch, push_branch


def _mock_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


@patch("boiler_room.git.subprocess.run")
def test_prepare_branch_happy_path(mock_run):
    mock_run.return_value = _mock_proc(returncode=0)
    branch = prepare_branch("/repo", 42)
    assert branch == "feature/42"
    issued = [c.args[0] for c in mock_run.call_args_list]
    assert ["git", "checkout", "main"] in issued
    assert ["git", "reset", "--hard", "HEAD"] in issued
    assert ["git", "clean", "-fd"] in issued
    assert ["git", "pull"] in issued
    assert ["git", "checkout", "-B", "feature/42"] in issued


@patch("boiler_room.git.subprocess.run")
def test_prepare_branch_raises_on_git_error(mock_run):
    mock_run.return_value = _mock_proc(returncode=1, stderr="not a git repo")
    with pytest.raises(GitError, match="not a git repo"):
        prepare_branch("/repo", 42)


@patch("boiler_room.git.subprocess.run")
def test_push_branch_issues_correct_command(mock_run):
    mock_run.return_value = _mock_proc(returncode=0)
    push_branch("/repo", "feature/42")
    mock_run.assert_called_once_with(
        ["git", "push", "origin", "feature/42"],
        capture_output=True, text=True, cwd="/repo",
    )


@patch("boiler_room.git.subprocess.run")
def test_push_branch_force_adds_flag(mock_run):
    mock_run.return_value = _mock_proc(returncode=0)
    push_branch("/repo", "feature/42", force=True)
    mock_run.assert_called_once_with(
        ["git", "push", "origin", "feature/42", "--force-with-lease"],
        capture_output=True, text=True, cwd="/repo",
    )


@patch("boiler_room.git.subprocess.run")
def test_push_branch_raises_on_error(mock_run):
    mock_run.return_value = _mock_proc(returncode=1, stderr="remote rejected")
    with pytest.raises(GitError, match="remote rejected"):
        push_branch("/repo", "feature/42")
