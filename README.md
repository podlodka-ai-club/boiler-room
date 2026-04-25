# boiler-room

A CLI that picks tasks from a GitHub Project board and delegates them to a local AI coding agent. For each task it prepares a clean git branch, runs the agent, commits the result, and opens a pull request.

## Requirements

- Python 3.10+
- [`gh` CLI](https://cli.github.com/) authenticated with write access to your repo
- Claude Code CLI (`claude`) or GitHub Copilot CLI (`copilot`) installed and authenticated
- Run from inside a git repository

## Installation

```bash
pip install -e .
```

## Usage

```bash
boiler-room --agent <agent> --project <project-url> [options]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--agent` | yes | AI agent to use: `claude` or `copilot` |
| `--project` | yes | GitHub Project URL, e.g. `https://github.com/users/dznavak/projects/2` |
| `--count N` | no | Stop after processing N tasks (default: run until queue empty) |
| `--label LABEL` | no | Only process issues carrying this GitHub label |

### Examples

Process all Todo tasks using Claude:

```bash
boiler-room --agent claude --project https://github.com/users/dznavak/projects/2
```

Process at most 3 tasks:

```bash
boiler-room --agent claude --project https://github.com/users/dznavak/projects/2 --count 3
```

Process only tasks labeled `sprint-42`:

```bash
boiler-room --agent claude --project https://github.com/users/dznavak/projects/2 --label sprint-42
```

## How It Works

For each task in the `Todo` column of the project board (filtered by `--label` if provided):

1. Creates a branch `feature/<issue-number>` from `main`
2. Moves the task to `In Progress` and applies an `agent-run` label
3. Runs the agent with the task description as a prompt
4. If the agent succeeds: pushes the branch and opens a pull request, moves task to `Done`
5. If the agent fails: pushes the branch for inspection, applies a `failed` label, resets task to `Todo`

The agent writes its results to `.agent-runs/<issue-number>/output.json`:

```json
{
  "pr_title": "feat: implement user login",
  "pr_description": "## What\n...",
  "summary": "Added JWT auth to /login endpoint",
  "success": true
}
```

## Development

### Run unit tests

```bash
pytest
```

### Run the e2e test

The e2e test creates real GitHub issues, runs the full pipeline against the real project board, and verifies all artefacts. It requires `gh` auth and `boiler-room` installed.

```bash
pytest -m e2e tests/e2e/test_e2e.py -v -s
```

The test:
- Generates a UUID-scoped label (`e2e-test-<uuid8>`) to isolate the run
- Creates 2 trivial issues on the board with that label
- Runs `boiler-room --agent claude --count 2 --label <label>`
- Asserts PRs are created, `output.json` is correct, and board items are `Done`
- Cleans up all created issues, PRs, branches, and the label automatically

The e2e test is excluded from bare `pytest` runs. It takes up to 10 minutes.
