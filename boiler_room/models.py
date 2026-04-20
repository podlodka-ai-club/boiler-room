from pydantic import BaseModel


class Task(BaseModel):
    id: str
    title: str
    description: str
    comments: list[str]
    issue_number: int
    issue_url: str


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
