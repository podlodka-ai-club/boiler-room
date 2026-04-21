import pytest
from unittest.mock import patch
from boiler_room.main import build_adapter, main
from boiler_room.agents.claude import ClaudeAdapter
from boiler_room.agents.copilot import CopilotAdapter


def test_build_adapter_claude():
    assert isinstance(build_adapter("claude"), ClaudeAdapter)


def test_build_adapter_copilot():
    assert isinstance(build_adapter("copilot"), CopilotAdapter)


def test_build_adapter_unknown_exits():
    with pytest.raises(SystemExit):
        build_adapter("unknown")


@patch("boiler_room.main.run_one_task")
@patch("boiler_room.main.GitHubClient")
def test_main_prints_welcome_message(mock_client_cls, mock_run, capsys):
    mock_run.return_value = False  # queue empty immediately
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
    ]):
        main()
    out = capsys.readouterr().out
    assert "Welcome to boiler-room" in out


@patch("boiler_room.main.run_one_task")
@patch("boiler_room.main.GitHubClient")
def test_main_loops_until_queue_empty(mock_client_cls, mock_run):
    mock_run.side_effect = [True, True, False]  # 2 tasks then empty
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
    ]):
        main()
    assert mock_run.call_count == 3


@patch("boiler_room.main.run_one_task")
@patch("boiler_room.main.GitHubClient")
def test_main_stops_after_count(mock_client_cls, mock_run):
    mock_run.return_value = True  # always finds a task
    with patch("sys.argv", [
        "boiler-room",
        "--agent", "claude",
        "--project", "https://github.com/users/x/projects/1",
        "--count", "2",
    ]):
        main()
    assert mock_run.call_count == 2
