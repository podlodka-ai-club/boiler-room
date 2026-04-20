from abc import ABC, abstractmethod

from boiler_room.models import Task

_PROMPT_TEMPLATE = """\
Task: {title}

{description}

---
Comments:
{comments}

---
When you have completed the task, write a JSON file to {output_path} with these fields:
  pr_title (str): title for the pull request
  pr_description (str): markdown body for the pull request
  summary (str): brief human-readable summary of what was done
  success (bool): true if the task was completed successfully

Do not exit until the JSON file has been written to {output_path}.
"""


def build_prompt(task: Task, output_path: str) -> str:
    comments = "\n".join(f"- {c}" for c in task.comments) if task.comments else "(none)"
    return _PROMPT_TEMPLATE.format(
        title=task.title,
        description=task.description,
        comments=comments,
        output_path=output_path,
    )


class AgentAdapter(ABC):
    def build_prompt(self, task: Task, output_path: str) -> str:
        return build_prompt(task, output_path)

    @abstractmethod
    def build_command(self, prompt: str, output_path: str) -> list[str]:
        """Return subprocess argv to invoke the agent with this prompt."""
