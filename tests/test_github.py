import pytest
from unittest.mock import patch, MagicMock
from boiler_room.github import GitHubClient, GitHubError, _ProjectMeta

PROJECT_URL = "https://github.com/users/dznavak/projects/2"
REPO = "dznavak/my-repo"

META_RESPONSE = {
    "data": {
        "user": {
            "projectV2": {
                "id": "PVT_proj1",
                "fields": {
                    "nodes": [
                        {
                            "id": "FIELD_status",
                            "name": "Status",
                            "options": [
                                {"id": "OPT_todo", "name": "Todo"},
                                {"id": "OPT_inprogress", "name": "In Progress"},
                            ],
                        }
                    ]
                },
            }
        }
    }
}

ITEMS_RESPONSE = {
    "data": {
        "node": {
            "items": {
                "nodes": [
                    {
                        "id": "PVTI_item1",
                        "fieldValues": {
                            "nodes": [
                                {"name": "Todo", "field": {"name": "Status"}}
                            ]
                        },
                        "content": {
                            "number": 42,
                            "title": "Add login",
                            "body": "As a user...",
                            "url": "https://github.com/dznavak/my-repo/issues/42",
                            "comments": {"nodes": [{"body": "Use JWT"}]},
                        },
                    }
                ]
            }
        }
    }
}


def _prebuild_meta():
    return _ProjectMeta(
        project_id="PVT_proj1",
        status_field_id="FIELD_status",
        todo_option_id="OPT_todo",
        in_progress_option_id="OPT_inprogress",
    )


def make_client():
    with patch("boiler_room.github.GitHubClient._detect_repo", return_value=REPO):
        client = GitHubClient(PROJECT_URL)
    return client


@patch("boiler_room.github._gh_json")
def test_fetch_first_todo_task(mock_gh):
    mock_gh.side_effect = [META_RESPONSE, ITEMS_RESPONSE]
    client = make_client()
    task = client.fetch_first_todo_task()
    assert task is not None
    assert task.issue_number == 42
    assert task.title == "Add login"
    assert task.comments == ["Use JWT"]
    assert task.id == "PVTI_item1"


@patch("boiler_room.github._gh_json")
def test_fetch_returns_none_when_queue_empty(mock_gh):
    empty = {"data": {"node": {"items": {"nodes": []}}}}
    mock_gh.side_effect = [META_RESPONSE, empty]
    client = make_client()
    assert client.fetch_first_todo_task() is None


@patch("boiler_room.github._gh_json")
def test_fetch_skips_non_todo_items(mock_gh):
    in_progress_items = {
        "data": {
            "node": {
                "items": {
                    "nodes": [
                        {
                            "id": "PVTI_item1",
                            "fieldValues": {
                                "nodes": [
                                    {"name": "In Progress", "field": {"name": "Status"}}
                                ]
                            },
                            "content": {
                                "number": 5,
                                "title": "Other",
                                "body": "",
                                "url": "https://github.com/dznavak/repo/issues/5",
                                "comments": {"nodes": []},
                            },
                        }
                    ]
                }
            }
        }
    }
    mock_gh.side_effect = [META_RESPONSE, in_progress_items]
    client = make_client()
    assert client.fetch_first_todo_task() is None


@patch("boiler_room.github._gh_run")
def test_move_to_in_progress_calls_mutation(mock_gh_run):
    client = make_client()
    client._meta = _prebuild_meta()
    client.move_to_in_progress("PVTI_item1")
    mock_gh_run.assert_called_once()
    assert "updateProjectV2ItemFieldValue" in " ".join(mock_gh_run.call_args.args[0])


@patch("boiler_room.github._gh_run")
def test_ensure_label_calls_gh_label_create(mock_gh_run):
    client = make_client()
    client.ensure_label("agent-run")
    mock_gh_run.assert_called_once()
    args = mock_gh_run.call_args.args[0]
    assert "label" in args
    assert "agent-run" in args


@patch("boiler_room.github._gh_json")
def test_create_pr_returns_url(mock_gh_json):
    mock_gh_json.return_value = {"url": "https://github.com/dznavak/repo/pull/10"}
    client = make_client()
    url = client.create_pr("feature/42", "feat: add login", "## What\nAdded login")
    assert url == "https://github.com/dznavak/repo/pull/10"
