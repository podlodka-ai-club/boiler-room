# Boiler Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that picks tasks from a GitHub Project board, delegates them to a local AI coding agent, and opens PRs with the results.

**Architecture:** Four-stage pipeline (fetch → prepare_env → run_agent → finalize) in `pipeline.py`; GitHub interactions via `GitHubClient` using the `gh` CLI; agent adapters implement a common ABC; Pydantic v2 models for typed data exchange throughout.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, pytest-mock, `gh` CLI, `git` CLI, `claude` CLI or `copilot` CLI

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, deps, `boiler-room` entry point |
| `boiler_room/models.py` | Pydantic models: `Task`, `AgentOutput`, `RunResult` |
| `boiler_room/git.py` | Git subprocess wrappers: checkout, clean, pull, branch, push |
| `boiler_room/github.py` | `GitHubClient`: fetch tasks, update statuses, labels, PRs via `gh` |
| `boiler_room/agents/base.py` | `AgentAdapter` ABC + shared `build_prompt` function |
| `boiler_room/agents/claude.py` | Claude Code CLI adapter |
| `boiler_room/agents/copilot.py` | GitHub Copilot CLI adapter |
| `boiler_room/pipeline.py` | Orchestrates 4 stages; all failure/success branching logic |
| `boiler_room/main.py` | Argument parsing, adapter selection, main loop |

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `boiler_room/__init__.py` (empty)
- Create: `boiler_room/agents/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/agents/__init__.py` (empty)

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "boiler-room"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
]

[project.scripts]
boiler-room = "boiler_room.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["boiler_room*"]
```

- [ ] **Step 2: Create .gitignore**

```
.agent-runs/
__pycache__/
*.pyc
*.egg-info/
dist/
.venv/
```

- [ ] **Step 3: Create empty package init files**

Create these four empty files:
- `boiler_room/__init__.py`
- `boiler_room/agents/__init__.py`
- `tests/__init__.py`
- `tests/agents/__init__.py`

- [ ] **Step 4: Install package in dev mode**

```bash
pip install -e . && pip install pytest pytest-mock
```

Expected: no errors, `boiler-room` command available.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore boiler_room/ tests/
git commit -m "chore: initial project scaffold"
```

---

## Task 2: Data Models

**Files:**
- Create: `boiler_room/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py
from boiler_room.models import Task, AgentOutput, RunResult


def test_task_fields():
    task = Task(
        id="PVTI_abc123",
        title="Add login",
        description="As a user I want to log in",
        comments=["Please use JWT", "See issue #10"],
        issue_number=42,
        issue_url="https://github.com/owner/repo/issues/42",
    )
    assert task.id == "PVTI_abc123"
    assert task.issue_number == 42
    assert len(task.comments) == 2


def test_agent_output_defaults():
    output = AgentOutput(success=True)
    assert output.pr_title is None
    assert output.pr_description is None
    assert output.summary is None
    assert output.success is True


def test_agent_output_from_dict():
    output = AgentOutput(
        pr_title="feat: add login",
        pr_description="## What\nAdded login",
        summary="Implemented JWT auth",
        success=True,
    )
    assert output.pr_title == "feat: add login"


def test_run_result():
    task = Task(
        id="PVTI_abc123",
        title="Add login",
        description="",
        comments=[],
        issue_number=42,
        issue_url="https://github.com/owner/repo/issues/42",
    )
    result = RunResult(
        task=task,
        exit_code=0,
        output=None,
        branch="feature/42",
        output_dir=".agent-runs/42",
    )
    assert result.exit_code == 0
    assert result.branch == "feature/42"
    assert result.output is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: `ImportError` — `boiler_room.models` does not exist yet.

- [ ] **Step 3: Write models.py**

```python
# boiler_room/models.py
from pydantic import BaseModel


class Task(BaseModel):
    id: str
    title: str
    description: str
    comments: list[str]
    issue_number: int
    issue_url: str


class AgentOutput(BaseModel):
    pr_title: str | None = None
    pr_description: str | None = None
    summary: str | None = None
    success: bool = False


class RunResult(BaseModel):
    task: Task
    exit_code: int
    output: AgentOutput | None = None
    branch: str
    output_dir: str
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add boiler_room/models.py tests/test_models.py
git commit -m "feat: add Pydantic data models"
```

---

## Task 3: git.py

**Files:**
- Create: `boiler_room/git.py`
- Create: `tests/test_git.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_git.py
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
    assert ["git", "checkout", "-b", "feature/42"] in issued


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
def test_push_branch_raises_on_error(mock_run):
    mock_run.return_value = _mock_proc(returncode=1, stderr="remote rejected")
    with pytest.raises(GitError, match="remote rejected"):
        push_branch("/repo", "feature/42")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_git.py -v
```

Expected: `ImportError` — `boiler_room.git` does not exist yet.

- [ ] **Step 3: Write git.py**

```python
# boiler_room/git.py
import subprocess


class GitError(Exception):
    pass


def _run(*args: str, cwd: str) -> str:
    result = subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise GitError(result.stderr.strip())
    return result.stdout.strip()


def prepare_branch(repo_path: str, issue_number: int) -> str:
    branch = f"feature/{issue_number}"
    _run("git", "checkout", "main", cwd=repo_path)
    _run("git", "reset", "--hard", "HEAD", cwd=repo_path)
    _run("git", "clean", "-fd", cwd=repo_path)
    _run("git", "pull", cwd=repo_path)
    _run("git", "checkout", "-b", branch, cwd=repo_path)
    return branch


def push_branch(repo_path: str, branch: str) -> None:
    _run("git", "push", "origin", branch, cwd=repo_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_git.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add boiler_room/git.py tests/test_git.py
git commit -m "feat: add git subprocess wrappers"
```

---

## Task 4: github.py

**Files:**
- Create: `boiler_room/github.py`
- Create: `tests/test_github.py`

All subprocess calls are isolated in module-level `_gh_json()` and `_gh_run()` helpers. Tests mock those helpers — no real `gh` calls made during tests.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_github.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_github.py -v
```

Expected: `ImportError` — `boiler_room.github` does not exist yet.

- [ ] **Step 3: Write github.py**

```python
# boiler_room/github.py
import json
import subprocess
from dataclasses import dataclass

from boiler_room.models import Task


class GitHubError(Exception):
    pass


@dataclass
class _ProjectMeta:
    project_id: str
    status_field_id: str
    todo_option_id: str
    in_progress_option_id: str


def _gh_json(args: list[str]) -> dict:
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitHubError(result.stderr.strip())
    return json.loads(result.stdout)


def _gh_run(args: list[str]) -> None:
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitHubError(result.stderr.strip())


_FETCH_META_QUERY = """
query($login: String!, $number: Int!) {
  user(login: $login) {
    projectV2(number: $number) {
      id
      fields(first: 20) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name }
          }
        }
      }
    }
  }
}
"""

_FETCH_ITEMS_QUERY = """
query($projectId: ID!) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 50, orderBy: {field: POSITION, direction: ASC}) {
        nodes {
          id
          fieldValues(first: 10) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
            }
          }
          content {
            ... on Issue {
              number
              title
              body
              url
              comments(first: 20) { nodes { body } }
            }
          }
        }
      }
    }
  }
}
"""

_UPDATE_STATUS_MUTATION = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId
    itemId: $itemId
    fieldId: $fieldId
    value: { singleSelectOptionId: $optionId }
  }) {
    projectV2Item { id }
  }
}
"""


class GitHubClient:
    def __init__(self, project_url: str):
        self._login, self._project_number = _parse_project_url(project_url)
        self._repo = self._detect_repo()
        self._meta: _ProjectMeta | None = None

    @staticmethod
    def _detect_repo() -> str:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise GitHubError(
                "Could not detect repo. Run from inside a git repo with gh configured."
            )
        return result.stdout.strip()

    def _get_meta(self) -> _ProjectMeta:
        if self._meta is None:
            self._meta = self._fetch_meta()
        return self._meta

    def _fetch_meta(self) -> _ProjectMeta:
        data = _gh_json([
            "api", "graphql",
            "-f", f"query={_FETCH_META_QUERY}",
            "-F", f"login={self._login}",
            "-F", f"number={self._project_number}",
        ])
        project = data["data"]["user"]["projectV2"]
        project_id = project["id"]
        status_field = next(
            (n for n in project["fields"]["nodes"] if n.get("name") == "Status"),
            None,
        )
        if status_field is None:
            raise GitHubError("Project has no 'Status' field")
        options = {o["name"]: o["id"] for o in status_field["options"]}
        if "Todo" not in options:
            raise GitHubError("Status field has no 'Todo' option")
        if "In Progress" not in options:
            raise GitHubError("Status field has no 'In Progress' option")
        return _ProjectMeta(
            project_id=project_id,
            status_field_id=status_field["id"],
            todo_option_id=options["Todo"],
            in_progress_option_id=options["In Progress"],
        )

    def fetch_first_todo_task(self) -> Task | None:
        meta = self._get_meta()
        data = _gh_json([
            "api", "graphql",
            "-f", f"query={_FETCH_ITEMS_QUERY}",
            "-F", f"projectId={meta.project_id}",
        ])
        items = data["data"]["node"]["items"]["nodes"]
        for item in items:
            if _get_item_status(item) == "Todo" and item.get("content"):
                content = item["content"]
                return Task(
                    id=item["id"],
                    title=content["title"],
                    description=content.get("body") or "",
                    comments=[c["body"] for c in content["comments"]["nodes"]],
                    issue_number=content["number"],
                    issue_url=content["url"],
                )
        return None

    def move_to_in_progress(self, item_id: str) -> None:
        self._update_status(item_id, self._get_meta().in_progress_option_id)

    def move_to_todo(self, item_id: str) -> None:
        self._update_status(item_id, self._get_meta().todo_option_id)

    def _update_status(self, item_id: str, option_id: str) -> None:
        meta = self._get_meta()
        _gh_run([
            "api", "graphql",
            "-f", f"query={_UPDATE_STATUS_MUTATION}",
            "-F", f"projectId={meta.project_id}",
            "-F", f"itemId={item_id}",
            "-F", f"fieldId={meta.status_field_id}",
            "-F", f"optionId={option_id}",
        ])

    def ensure_label(self, label: str) -> None:
        _gh_run(["label", "create", label, "--repo", self._repo, "--force"])

    def add_label(self, issue_number: int, label: str) -> None:
        _gh_run([
            "issue", "edit", str(issue_number),
            "--repo", self._repo,
            "--add-label", label,
        ])

    def create_pr(self, branch: str, title: str, body: str) -> str:
        data = _gh_json([
            "pr", "create",
            "--repo", self._repo,
            "--head", branch,
            "--base", "main",
            "--title", title,
            "--body", body,
            "--json", "url",
        ])
        return data["url"]


def _parse_project_url(url: str) -> tuple[str, int]:
    # "https://github.com/users/dznavak/projects/2" -> ("dznavak", 2)
    parts = url.rstrip("/").split("/")
    return parts[-3], int(parts[-1])


def _get_item_status(item: dict) -> str | None:
    for node in item.get("fieldValues", {}).get("nodes", []):
        if node.get("field", {}).get("name") == "Status":
            return node.get("name")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_github.py -v
```

Expected: 6 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add boiler_room/github.py tests/test_github.py
git commit -m "feat: add GitHubClient with gh CLI wrappers"
```

---

## Task 5: Agent Adapters — Base and Claude

**Files:**
- Create: `boiler_room/agents/base.py`
- Create: `boiler_room/agents/claude.py`
- Create: `tests/agents/test_agents.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_agents.py
import pytest
from boiler_room.models import Task
from boiler_room.agents.base import AgentAdapter, build_prompt
from boiler_room.agents.claude import ClaudeAdapter

TASK = Task(
    id="PVTI_abc",
    title="Add login endpoint",
    description="Create POST /login that returns a JWT",
    comments=["Use bcrypt for passwords", "Return 401 on bad creds"],
    issue_number=42,
    issue_url="https://github.com/owner/repo/issues/42",
)
OUTPUT_PATH = ".agent-runs/42/output.json"


def test_build_prompt_contains_title():
    assert "Add login endpoint" in build_prompt(TASK, OUTPUT_PATH)


def test_build_prompt_contains_description():
    assert "Create POST /login" in build_prompt(TASK, OUTPUT_PATH)


def test_build_prompt_contains_comments():
    prompt = build_prompt(TASK, OUTPUT_PATH)
    assert "Use bcrypt for passwords" in prompt
    assert "Return 401 on bad creds" in prompt


def test_build_prompt_contains_output_path():
    assert OUTPUT_PATH in build_prompt(TASK, OUTPUT_PATH)


def test_agent_adapter_is_abstract():
    with pytest.raises(TypeError):
        AgentAdapter()


def test_claude_adapter_command_starts_with_claude():
    adapter = ClaudeAdapter()
    cmd = adapter.build_command("do the task", OUTPUT_PATH)
    assert cmd[0] == "claude"


def test_claude_adapter_command_includes_prompt():
    adapter = ClaudeAdapter()
    cmd = adapter.build_command("do the task", OUTPUT_PATH)
    assert "do the task" in cmd


def test_claude_adapter_build_prompt_delegates_to_base():
    adapter = ClaudeAdapter()
    prompt = adapter.build_prompt(TASK, OUTPUT_PATH)
    assert "Add login endpoint" in prompt
    assert OUTPUT_PATH in prompt
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/agents/test_agents.py -v
```

Expected: `ImportError` — `boiler_room.agents.base` does not exist yet.

- [ ] **Step 3: Write agents/base.py**

```python
# boiler_room/agents/base.py
from abc import ABC, abstractmethod

from boiler_room.models import Task

_PROMPT_TEMPLATE = """\
Task: {title}

{description}

---
Comments:
{comments}

---
When you have completed the task, write a JSON file to {output_path} with these fields:
  pr_title (str): title for the pull request
  pr_description (str): markdown body for the pull request
  summary (str): brief human-readable summary of what was done
  success (bool): true if the task was completed successfully

Do not exit until the JSON file has been written to {output_path}.
"""


def build_prompt(task: Task, output_path: str) -> str:
    comments = "\n".join(f"- {c}" for c in task.comments) if task.comments else "(none)"
    return _PROMPT_TEMPLATE.format(
        title=task.title,
        description=task.description,
        comments=comments,
        output_path=output_path,
    )


class AgentAdapter(ABC):
    def build_prompt(self, task: Task, output_path: str) -> str:
        return build_prompt(task, output_path)

    @abstractmethod
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        """Return subprocess argv to invoke the agent with this prompt."""
```

- [ ] **Step 4: Write agents/claude.py**

```python
# boiler_room/agents/claude.py
from boiler_room.agents.base import AgentAdapter


class ClaudeAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        return ["claude", "-p", prompt]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/agents/test_agents.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add boiler_room/agents/base.py boiler_room/agents/claude.py tests/agents/test_agents.py
git commit -m "feat: add agent adapter interface and Claude adapter"
```

---

## Task 6: Copilot Adapter

**Files:**
- Create: `boiler_room/agents/copilot.py`
- Modify: `tests/agents/test_agents.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/agents/test_agents.py`:

```python
from boiler_room.agents.copilot import CopilotAdapter


def test_copilot_adapter_command_starts_with_gh():
    adapter = CopilotAdapter()
    cmd = adapter.build_command("do the task", OUTPUT_PATH)
    assert cmd[0] == "gh"
    assert "copilot" in cmd


def test_copilot_adapter_command_includes_prompt():
    adapter = CopilotAdapter()
    cmd = adapter.build_command("do the task", OUTPUT_PATH)
    assert "do the task" in cmd


def test_copilot_adapter_build_prompt_delegates_to_base():
    adapter = CopilotAdapter()
    prompt = adapter.build_prompt(TASK, OUTPUT_PATH)
    assert "Add login endpoint" in prompt
    assert OUTPUT_PATH in prompt
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest tests/agents/test_agents.py::test_copilot_adapter_command_starts_with_gh -v
```

Expected: `ImportError` — `boiler_room.agents.copilot` does not exist yet.

- [ ] **Step 3: Write agents/copilot.py**

```python
# boiler_room/agents/copilot.py
from boiler_room.agents.base import AgentAdapter


class CopilotAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        # copilot is primarily designed for shell command suggestions.
        # Verify the exact sub-command against your installed copilot version
        # if the agent does not behave as expected.
        return ["copilot", "--prompt", prompt, "--allow-all-tools"]
```

- [ ] **Step 4: Run all agent tests**

```bash
pytest tests/agents/test_agents.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add boiler_room/agents/copilot.py tests/agents/test_agents.py
git commit -m "feat: add GitHub Copilot CLI adapter"
```

---

## Task 7: Pipeline

**Files:**
- Create: `boiler_room/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline.py
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


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_success_creates_pr(mock_prepare, mock_run_agent):
    client = make_client()
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=0, output=None,
        branch="feature/42", output_dir=".agent-runs/42",
    )
    result = run_one_task(client, make_adapter(), "/repo")
    assert result is True
    client.create_pr.assert_called_once()


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


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_title_falls_back_to_task_title(mock_prepare, mock_run_agent):
    client = make_client()
    mock_prepare.return_value = "feature/42"
    mock_run_agent.return_value = RunResult(
        task=TASK, exit_code=0, output=AgentOutput(success=True),
        branch="feature/42", output_dir=".agent-runs/42",
    )
    run_one_task(client, make_adapter(), "/repo")
    title_used = client.create_pr.call_args.args[1]
    assert title_used == f"feat: {TASK.title}"


@patch("boiler_room.pipeline.run_agent")
@patch("boiler_room.pipeline.prepare_env")
def test_pr_uses_agent_output_when_present(mock_prepare, mock_run_agent):
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
    mock_push.assert_called_once_with("/repo", "feature/42")
    client.add_label.assert_any_call(TASK.issue_number, "failed")
    client.move_to_todo.assert_not_called()  # task left In Progress — code is done
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pipeline.py -v
```

Expected: `ImportError` — `boiler_room.pipeline` does not exist yet.

- [ ] **Step 3: Write pipeline.py**

```python
# boiler_room/pipeline.py
import json
import logging
import os
import subprocess

from boiler_room.agents.base import AgentAdapter
from boiler_room.git import push_branch
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
        logger.error("prepare_env failed for task %s: %s", task.issue_number, e)
        client.move_to_todo(task.id)
        return True

    result = run_agent(adapter, task, branch, repo_path)
    _finalize(client, result, repo_path)
    return True


def prepare_env(client: GitHubClient, task: Task, repo_path: str) -> str:
    from boiler_room.git import prepare_branch
    branch = prepare_branch(repo_path, task.issue_number)
    client.move_to_in_progress(task.id)
    client.ensure_label("agent-run")
    client.add_label(task.issue_number, "agent-run")
    return branch


def run_agent(adapter: AgentAdapter, task: Task, branch: str, repo_path: str) -> RunResult:
    output_dir = os.path.join(repo_path, ".agent-runs", str(task.issue_number))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "output.json")

    prompt = adapter.build_prompt(task, output_path)
    command = adapter.build_command(prompt, output_path)

    proc = subprocess.run(command, cwd=repo_path)

    return RunResult(
        task=task,
        exit_code=proc.returncode,
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
        else f"Implements #{result.task.issue_number}\n\nAutomated by boiler-room."
    )

    try:
        url = client.create_pr(result.branch, pr_title, pr_body)
        logger.info("PR created: %s", url)
    except Exception as e:
        logger.error("create_pr failed: %s — pushing branch, leaving task In Progress", e)
        _handle_failure(client, result, repo_path, reset_to_todo=False)


def _handle_failure(
    client: GitHubClient, result: RunResult, repo_path: str, *, reset_to_todo: bool
) -> None:
    try:
        push_branch(repo_path, result.branch)
    except Exception as e:
        logger.warning("Could not push failure branch %s: %s", result.branch, e)
    client.ensure_label("failed")
    client.add_label(result.task.issue_number, "failed")
    if reset_to_todo:
        client.move_to_todo(result.task.id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipeline.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 5: Run full suite to confirm nothing broken**

```bash
pytest -v
```

Expected: all 25+ tests PASSED across all modules.

- [ ] **Step 6: Commit**

```bash
git add boiler_room/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestration with failure handling"
```

---

## Task 8: CLI Entry Point

**Files:**
- Create: `boiler_room/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_main.py -v
```

Expected: `ImportError` — `boiler_room.main` does not exist yet.

- [ ] **Step 3: Write main.py**

```python
# boiler_room/main.py
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
    args = parser.parse_args()

    adapter = build_adapter(args.agent)
    client = GitHubClient(args.project)
    repo_path = os.getcwd()

    processed = 0
    while args.count is None or processed < args.count:
        found = run_one_task(client, adapter, repo_path)
        if not found:
            logging.info("Queue empty. Done.")
            break
        processed += 1
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASSED (29+ tests across all modules).

- [ ] **Step 6: Verify the CLI entry point works**

```bash
pip install -e . && boiler-room --help
```

Expected output includes:
```
usage: boiler-room [-h] --agent {claude,copilot} --project PROJECT [--count COUNT]

Pick tasks from a GitHub Project and delegate them to a local AI coding agent.
```

- [ ] **Step 7: Commit**

```bash
git add boiler_room/main.py tests/test_main.py
git commit -m "feat: add CLI entry point with loop and --count support"
```
