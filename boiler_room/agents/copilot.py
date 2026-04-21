from boiler_room.agents.base import AgentAdapter


class CopilotAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        return ["copilot", "--prompt", prompt, "--allow-all-tools"]
