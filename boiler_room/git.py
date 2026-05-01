import os
import subprocess
import tempfile


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


def prepare_worktree(repo_path: str, branch_suffix: str) -> tuple[str, str]:
    branch = f"feature/{branch_suffix}"
    worktrees_root = os.path.join(repo_path, ".worktrees")
    os.makedirs(worktrees_root, exist_ok=True)

    worktree_path = tempfile.mkdtemp(prefix=f"{branch_suffix}-", dir=worktrees_root)
    os.rmdir(worktree_path)

    _run("git", "fetch", "origin", "main", cwd=repo_path)
    _run("git", "worktree", "add", "-B", branch, worktree_path, "origin/main", cwd=repo_path)
    return branch, worktree_path


def cleanup_worktree(repo_path: str, worktree_path: str) -> None:
    if not os.path.exists(worktree_path):
        return
    _run("git", "worktree", "remove", "--force", worktree_path, cwd=repo_path)
