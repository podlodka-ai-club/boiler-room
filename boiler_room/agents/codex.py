from boiler_room.agents.base import AgentAdapter


class CodexAdapter(AgentAdapter):
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        return ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", prompt]
