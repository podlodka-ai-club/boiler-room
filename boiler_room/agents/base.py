from abc import ABC, abstractmethod

from boiler_room.models import Task

_PROMPT_TEMPLATE = """\
Task: {title}

{description}

---
Comments:
{comments}

---
Instructions:
1. Implement the task in the current git branch.
2. Run the test suite to verify everything passes.
3. Stage and commit all changes: git add -A && git commit -m "<short description>"
4. Write a JSON file to {output_path} with these fields:
     pr_title (str): title for the pull request
     pr_description (str): markdown body for the pull request
     summary (str): brief human-readable summary of what was done
     success (bool): true if the task was completed successfully

Do not exit until the git commit and the JSON file at {output_path} are both done.
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
