import subprocess
from pathlib import Path

import pytest



class Repo:
    """A throwaway git repository with a `main` branch."""

    def __init__(self, path: Path):
        self.path = path
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.path), *args], check=True,
                              capture_output=True, text=True).stdout

    def write(self, files: dict[str, str | None]) -> None:
        for name, content in files.items():
            target = self.path / name
            if content is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)

    def commit(self, files: dict[str, str | None], message: str = "change",
               author: str | None = None) -> None:
        self.write(files)
        self.git("add", "-A")
        extra = ["--author", author] if author else []
        self.git("commit", "-q", "--allow-empty", "-m", message, *extra)

    def tag(self, name: str) -> None:
        self.git("tag", name)

    def branch(self, name: str) -> None:
        self.git("checkout", "-q", "-b", name)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)
