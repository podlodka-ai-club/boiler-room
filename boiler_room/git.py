import subprocess


class GitError(Exception):
    pass


def _run(*args: str, cwd: str) -> str:
    result = subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise GitError(result.stderr.strip())
    return result.stdout.strip()


def prepare_branch(repo_path: str, branch_suffix: str) -> str:
    branch = f"feature/{branch_suffix}"
    _run("git", "checkout", "main", cwd=repo_path)
    _run("git", "reset", "--hard", "HEAD", cwd=repo_path)
    _run("git", "clean", "-fd", cwd=repo_path)
    _run("git", "pull", cwd=repo_path)
    _run("git", "checkout", "-B", branch, cwd=repo_path)
    return branch


def push_branch(repo_path: str, branch: str, *, force: bool = False) -> None:
    args = ["git", "push", "origin", branch]
    if force:
        args.append("--force-with-lease")
    _run(*args, cwd=repo_path)
