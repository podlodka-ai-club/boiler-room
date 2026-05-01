import pytest
from unittest.mock import ANY, patch
from boiler_room.main import build_adapter, main
from boiler_room.agents.claude import ClaudeAdapter
from boiler_room.agents.copilot import CopilotAdapter
from boiler_room.agents.codex import CodexAdapter


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.argv", ["boiler-room", "--version"]):
            main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "boiler-room 0.1.0" in captured.out


def test_build_adapter_claude():
    assert isinstance(build_adapter("claude"), ClaudeAdapter)


def test_build_adapter_copilot():
    assert isinstance(build_adapter("copilot"), CopilotAdapter)


def test_build_adapter_codex():
    assert isinstance(build_adapter("codex"), CodexAdapter)


def test_build_adapter_unknown_exits():
    with pytest.raises(SystemExit):
        build_adapter("unknown")


@patch("boiler_room.main.run_tasks")
@patch("boiler_room.main.GitHubClient")
def test_main_prints_welcome_message(mock_client_cls, mock_run_tasks, capsys):
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
    ]):
        main()
    captured = capsys.readouterr()
    assert "Welcome to boiler-room" in captured.out


def test_help_does_not_print_welcome(capsys):
    with pytest.raises(SystemExit):
        with patch("sys.argv", ["boiler-room", "--help"]):
            main()
    captured = capsys.readouterr()
    assert "Welcome to boiler-room" not in captured.out


@patch("boiler_room.main.run_tasks")
@patch("boiler_room.main.GitHubClient")
def test_main_uses_parallel_runner(mock_client_cls, mock_run_tasks):
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
    ]):
        main()
    mock_run_tasks.assert_called_once_with(
        mock_client_cls.return_value,
        ANY,
        ANY,
        count=None,
        parallelism=2,
    )


@patch("boiler_room.main.run_tasks")
@patch("boiler_room.main.GitHubClient")
def test_main_passes_count_to_parallel_runner(mock_client_cls, mock_run_tasks):
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
        "--count", "2",
    ]):
        main()
    mock_run_tasks.assert_called_once_with(
        mock_client_cls.return_value,
        ANY,
        ANY,
        count=2,
        parallelism=2,
    )
    mock_client_cls.assert_called_once_with(
        "https://github.com/users/x/projects/1", label=None
    )


@patch("boiler_room.main.run_tasks")
@patch("boiler_room.main.GitHubClient")
def test_main_passes_label_to_client(mock_client_cls, mock_run_tasks):
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
        "--label", "e2e-test-abc",
    ]):
        main()
    mock_client_cls.assert_called_once_with(
        "https://github.com/users/x/projects/1", label="e2e-test-abc"
    )


@patch("boiler_room.main.run_tasks")
@patch("boiler_room.main.GitHubClient")
def test_main_passes_parallel_to_runner(mock_client_cls, mock_run_tasks):
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
        "--parallel", "1",
    ]):
        main()
    mock_run_tasks.assert_called_once_with(
        mock_client_cls.return_value,
        ANY,
        ANY,
        count=None,
        parallelism=1,
    )
