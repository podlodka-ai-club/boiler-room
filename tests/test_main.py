import pytest
from unittest.mock import patch
from boiler_room.main import build_adapter, main
from boiler_room.agents.claude import ClaudeAdapter
from boiler_room.agents.copilot import CopilotAdapter


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


def test_build_adapter_unknown_exits():
    with pytest.raises(SystemExit):
        build_adapter("unknown")


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
    mock_client_cls.assert_called_once_with(
        "https://github.com/users/x/projects/1", label=None
    )


@patch("boiler_room.main.run_one_task")
@patch("boiler_room.main.GitHubClient")
def test_main_passes_label_to_client(mock_client_cls, mock_run):
    mock_run.return_value = False
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
