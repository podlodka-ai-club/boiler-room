from boiler_room.agents.base import AgentAdapter


class CopilotAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        return ["gh", "copilot", "suggest", "-t", "shell", prompt]
