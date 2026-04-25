import re

from pydantic import BaseModel


class Task(BaseModel):
    id: str
    title: str
    description: str
    comments: list[str]
    issue_number: int | None = None
    issue_url: str | None = None
    is_draft: bool = False
    draft_issue_id: str | None = None

    @property
    def ref(self) -> str:
        if self.issue_number is not None:
            return str(self.issue_number)
        return f"draft-{_slugify(self.id)}"

    @property
    def branch_suffix(self) -> str:
        return self.ref

    @property
    def output_id(self) -> str:
        return self.ref


class AgentOutput(BaseModel):
    pr_title: str | None = None
    pr_description: str | None = None
    summary: str | None = None
    success: bool = False


class RunResult(BaseModel):
    task: Task
    exit_code: int
    output: AgentOutput | None = None
    branch: str
    output_dir: str


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"
