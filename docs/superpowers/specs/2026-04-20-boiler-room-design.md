# Boiler Room — Design Spec

**Date:** 2026-04-20
**Status:** Approved

## Overview

A Python CLI app that autonomously picks tasks from a GitHub Project board, prepares a clean local git environment, delegates each task to a local AI coding agent, and opens a PR with the results. Supports Claude Code CLI and GitHub Copilot CLI via a pluggable adapter interface.

---

## Project Structure

```
boiler-room/
├── boiler_room/
│   ├── __init__.py
│   ├── main.py          # CLI entry point (argparse), loop control
│   ├── pipeline.py      # Orchestrates 4 stages for one task
│   ├── github.py        # All gh CLI interactions (fetch tasks, labels, PR, board moves)
│   ├── git.py           # git operations (checkout, clean, pull, branch, push)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py      # AgentAdapter ABC
│   │   ├── claude.py    # Claude Code CLI adapter
│   │   └── copilot.py   # GitHub Copilot CLI adapter
│   └── models.py        # Pydantic models: Task, AgentOutput, RunResult
├── .agent-runs/         # Per-task output dirs (gitignored)
├── tests/
├── pyproject.toml
└── README.md
```

---

## CLI Interface

```
boiler-room --agent claude             # run until queue empty
boiler-room --agent copilot --count 3  # process at most 3 tasks then stop
```

**Arguments:**
- `--agent` (required): `claude` or `copilot`
- `--count N` (optional): stop after N tasks (default: unlimited)

Authentication: uses existing `gh` CLI session. No token management.

---

## Data Models

```python
class Task:
    id: str                  # GitHub project item ID
    title: str
    description: str         # issue body
    comments: list[str]      # linked issue comments
    issue_number: int
    issue_url: str

class AgentOutput:
    pr_title: str | None          # fallback: "feat: <task title>"
    pr_description: str | None    # fallback: default template
    summary: str | None
    success: bool                 # agent self-reports success

class RunResult:
    task: Task
    exit_code: int
    output: AgentOutput | None    # None if file missing or unparseable
    branch: str
    output_dir: str               # .agent-runs/<issueNumber>/
```

**Agent handoff file:** `.agent-runs/<issueNumber>/output.json`
```json
{
  "pr_title": "feat: implement user login",
  "pr_description": "## What\n...\n## How\n...",
  "summary": "Added JWT auth to /login endpoint",
  "success": true
}
```

If the file is absent or malformed after agent exit, the CLI falls back to defaults. Exit code determines success/failure — `AgentOutput.success` is informational only.

---

## Pipeline

Four sequential stages in `pipeline.py`. Any unrecoverable stage error triggers the failure path.

```
fetch_task()     → Task | None   (None = queue empty, exits loop)
     ↓
prepare_env()    → branch name   (git clean + pull + create branch, THEN move task to In Progress + add agent-run label)
     ↓
run_agent()      → RunResult     (subprocess, wait for exit, read output.json)
     ↓
finalize()       → success: create PR
                 → failure: push branch, add "failed" label, reset task to Todo
```

### Failure handling per stage

| Stage | Failure action |
|-------|---------------|
| `fetch_task` | Log error, stop loop |
| `prepare_env` | Reset task to Todo, no branch pushed, log error, continue loop |
| `run_agent` | Push branch, add `failed` label, reset task to Todo, continue loop |
| `finalize` | Push branch, add `failed` label, leave task In Progress (code is done — human intervenes) |

---

## Labels

| Label | Applied when |
|-------|-------------|
| `agent-run` | Task is picked up (In Progress) |
| `failed` | Failure path triggered |

Both labels are created automatically on first use if they don't exist in the repo.

---

## Agent Adapter Interface

```python
# agents/base.py

class AgentAdapter(ABC):
    @abstractmethod
    def build_prompt(self, task: Task) -> str:
        """Construct the prompt string from task fields."""

    @abstractmethod
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        """Return the subprocess argv to invoke the agent."""
```

### Prompt template (shared base)

```
Task: {title}

{description}

---
Comments:
{comments}

---
When you have completed the task, write a JSON file to {output_path} with fields:
  pr_title (str), pr_description (str), summary (str), success (bool).
```

The `output_path` is embedded in the prompt — the agent is instructed to write the handoff file as the final step. Adapters can override `build_prompt` to customize framing.

### Claude Code adapter

```python
["claude", "--print", "--system", SYSTEM_PROMPT, prompt]
```

### Copilot adapter

```python
["gh", "copilot", "suggest", "-t", "shell", prompt]
```

---

## Git Workflow

For each task:
1. `git checkout main`
2. `git reset --hard HEAD && git clean -fd`
3. `git pull`
4. `git checkout -b feature/<issueNumber>`

On success: PR is created (branch pushed by `gh pr create`).
On failure: `git push origin feature/<issueNumber>` for inspection, no PR.

---

## GitHub Project Integration

- Project board: `https://github.com/users/dznavak/projects/2`
- Uses GitHub GraphQL API via `gh api graphql` to read/update project items
- **Task selection:** "First task" = top-most item in the `Todo` column by board position
- Task statuses: `Todo` → `In Progress` → (handled via PR merge or manual)
- Failed tasks: reset to `Todo`, labelled `failed`

---

## Error Handling Philosophy

- Stage failures are logged and the loop continues where possible
- The system is designed to be re-runnable: a failed task lands back in `Todo` ready for retry
- No silent failures — every failure writes a log entry and updates the task/label state

---

## Testing Strategy

- Each module (`github.py`, `git.py`, `pipeline.py`, adapters) is independently unit-testable
- `github.py` and `git.py` wrap subprocess calls — tests mock at the subprocess boundary
- `pipeline.py` tests use fake `Task` objects and mock stage functions
- Adapter tests verify prompt construction and command building without running real agents
