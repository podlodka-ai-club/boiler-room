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


from boiler_room.agents.copilot import CopilotAdapter


def test_copilot_adapter_command_starts_with_gh():
    adapter = CopilotAdapter()
    cmd = adapter.build_command("do the task", OUTPUT_PATH)
    assert cmd[0] == "copilot"


def test_copilot_adapter_command_includes_prompt():
    adapter = CopilotAdapter()
    cmd = adapter.build_command("do the task", OUTPUT_PATH)
    assert "do the task" in cmd
    assert "--allow-all-tools" in cmd


def test_copilot_adapter_build_prompt_delegates_to_base():
    adapter = CopilotAdapter()
    prompt = adapter.build_prompt(TASK, OUTPUT_PATH)
    assert "Add login endpoint" in prompt
    assert OUTPUT_PATH in prompt
