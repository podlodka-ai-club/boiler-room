from boiler_room.agents.base import AgentAdapter


class ClaudeAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        return ["claude", "-p", prompt, "--dangerously-skip-permissions"]
