# E2E Test + Label Filtering — Design Spec

**Date:** 2026-04-22
**Status:** Approved

## Overview

Two related pieces of work:

1. **`--label` flag** — a new CLI argument that restricts task pickup to issues carrying a specific GitHub label, enabling targeted runs (and isolated test runs).
2. **E2E test** — a deterministic end-to-end test that runs the real boiler-room pipeline against the real GitHub project, using a UUID-scoped label to avoid cross-run interference. Acts as living documentation of the system's expected behaviour and artefacts.

---

## Part 1: `--label` Feature

### CLI

```
boiler-room --agent claude --project <url> --label e2e-test-abc123
```

`--label` is optional. When omitted, behaviour is unchanged (all Todo tasks are picked up).

### Changes

**`main.py`**
- Add `--label` optional argument.
- Pass it to `GitHubClient(project_url, label=label)`.

**`github.py` — `_FETCH_ITEMS_QUERY`**

Add inside the `... on Issue` fragment:

```graphql
labels(first: 10) {
  nodes { name }
}
```

**`github.py` — `GitHubClient`**

- `__init__` gains `label: str | None = None`, stored as `self._label`.
- `fetch_first_todo_task()` — after checking `status == "Todo"`, additionally checks that the issue's labels contain `self._label` (if set). Issues not carrying the label are skipped silently.

### Unit tests (additions to `test_github.py`)

- `test_fetch_returns_labeled_task` — item has matching label → returned.
- `test_fetch_skips_unlabeled_task` — item lacks the label → `None` returned.

---

## Part 2: E2E Test

### Location

```
tests/e2e/__init__.py
tests/e2e/test_e2e.py
```

Marked `@pytest.mark.e2e`. Not included in default `pytest` runs. Registered in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["e2e: end-to-end tests against real GitHub (slow, requires gh auth)"]
```

### Run command

```bash
pytest -m e2e tests/e2e/test_e2e.py -v -s
```

### Test tasks

Two trivially simple GitHub issues created fresh per run:

| # | Title | Body |
|---|-------|------|
| 1 | `Create file hello.txt` | `Create a file named hello.txt in the repo root containing the text 'Hello World'` |
| 2 | `Create file goodbye.txt` | `Create a file named goodbye.txt in the repo root containing the text 'Goodbye World'` |

Both issues are labeled `e2e-test-<uuid4[:8]>` and added to the project board in `Todo` status.

### Fixture (`scope="module"`)

```
generate run_id = uuid4()[:8]
label = f"e2e-test-{run_id}"

client.ensure_label(label)

for each task_spec:
    issue_number = client.create_issue(title, body, label)
    item_id = client.add_to_project(issue_number)
    client.set_item_status_todo(item_id)

yield RunContext(label, items, client)

# teardown (always runs):
for each item:
    client.close_issue(issue_number)
    client.close_pr(pr_number)          # find by branch feature/<issue_number>
    client.delete_branch(branch)
    client.remove_from_project(item_id)
client.delete_label(label)
```

Teardown is registered before yield so it runs even if the test body raises.

### Test body assertions

1. Run CLI as subprocess:
   ```python
   result = subprocess.run(
       ["boiler-room", "--agent", "claude",
        "--project", PROJECT_URL,
        "--count", "2",
        "--label", label],
       timeout=600,
   )
   assert result.returncode == 0
   ```

2. For each issue — `output.json` structure:
   ```python
   output = AgentOutput(**json.load(open(f".agent-runs/{issue_number}/output.json")))
   assert output.success is True
   assert output.pr_title        # non-empty
   assert output.pr_description  # non-empty
   ```

3. For each issue — PR exists:
   ```python
   # gh pr list --head feature/<issue_number> --state open --json number
   assert len(prs) == 1
   ```

4. Project board status — both items in `Done`:
   ```python
   # re-fetch items via GraphQL, check status field == "Done"
   ```

### New `GitHubClient` methods

| Method | Implementation |
|--------|---------------|
| `create_issue(title, body, label) -> int` | `gh issue create`, returns issue number |
| `add_to_project(issue_number) -> str` | fetch issue node_id via REST, then `addProjectV2ItemByContentId` mutation; returns project item ID |
| `set_item_status_todo(item_id)` | calls existing `_update_status` with `todo_option_id` |
| `close_issue(issue_number)` | `gh issue close` |
| `close_pr(pr_number)` | `gh pr close` |
| `delete_branch(branch)` | `gh api -X DELETE repos/{repo}/git/refs/heads/{branch}` |
| `remove_from_project(item_id)` | `deleteProjectV2Item` GraphQL mutation |
| `delete_label(label)` | `gh label delete --yes` |
| `find_pr_for_branch(branch) -> int \| None` | `gh pr list --head {branch} --json number` |

### `add_to_project` detail

Two steps inside one method:
1. `gh api repos/{repo}/issues/{number} --jq .node_id` → `issue_node_id`
2. GraphQL mutation `addProjectV2ItemByContentId(input: { projectId, contentId: issue_node_id })` → returns `item.id`

### Flakiness posture

The tasks are intentionally trivial so the claude agent succeeds in effectively every run. The test is marked `e2e` and excluded from CI by default. Rerunning manually after a rare failure is acceptable — no in-test retry loop.

---

## Scope

Not in scope:
- Testing the `copilot` agent path.
- Org-owned project boards (user board only).
- Parallel e2e runs (UUID label isolates them, but sequential is assumed).
