from boiler_room.agents.base import AgentAdapter


class CopilotAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        # gh copilot is primarily designed for shell command suggestions.
        # Verify the exact sub-command against your installed gh copilot version
        # if the agent does not behave as expected.
        return ["gh", "copilot", "suggest", "-t", "shell", prompt]
