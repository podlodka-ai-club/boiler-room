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
