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
    """Parse a GitHub user project URL.

    Expected format: https://github.com/users/<login>/projects/<number>
    """
    parts = url.rstrip("/").split("/")
    # Expected: ['https:', '', 'github.com', 'users', '<login>', 'projects', '<n>']
    if len(parts) < 7 or parts[-2] != "projects" or parts[-4] != "users":
        raise GitHubError(
            f"Unsupported project URL: {url!r}. "
            "Expected format: https://github.com/users/<login>/projects/<number>"
        )
    try:
        return parts[-3], int(parts[-1])
    except (ValueError, IndexError):
        raise GitHubError(f"Could not parse project number from URL: {url!r}")


def _get_item_status(item: dict) -> str | None:
    for node in item.get("fieldValues", {}).get("nodes", []):
        if node.get("field", {}).get("name") == "Status":
            return node.get("name")
    return None
