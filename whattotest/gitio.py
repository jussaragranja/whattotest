"""Thin wrapper around the git CLI."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          errors="replace")
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def resolve(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def previous_tag(repo: Path, ref: str) -> str | None:
    """The nearest tag before `ref` (if `ref` itself is tagged, the one before it)."""
    out = git(repo, "describe", "--tags", "--abbrev=0", f"{ref}^", check=False).strip()
    return out or None


def merge_base(repo: Path, a: str, b: str) -> str:
    out = git(repo, "merge-base", a, b, check=False).strip()
    return out or resolve(repo, a)


@dataclass
class FileChange:
    path: str
    old_path: str | None
    status: str          # A M D R
    added: int = 0
    removed: int = 0


def changes(repo: Path, base: str, head: str) -> list[FileChange]:
    out: dict[str, FileChange] = {}
    parts = git(repo, "diff", "--name-status", "-M", "-z", base, head).split("\0")
    i = 0
    while i < len(parts) and parts[i]:
        status = parts[i][0]
        if status in "RC":
            out[parts[i + 2]] = FileChange(parts[i + 2], parts[i + 1], "R")
            i += 3
        else:
            path = parts[i + 1]
            out[path] = FileChange(path, None if status == "A" else path, status)
            i += 2
    for line in git(repo, "diff", "--numstat", "-M", base, head).splitlines():
        added, removed, path = line.split("\t", 2)
        if " => " in path:
            path = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", path).split(" => ")[-1].replace("//", "/")
        if path in out:
            out[path].added = int(added) if added.isdigit() else 0
            out[path].removed = int(removed) if removed.isdigit() else 0
    return list(out.values())


def files_at(repo: Path, ref: str) -> list[str]:
    return [p for p in git(repo, "ls-tree", "-r", "--name-only", "-z", ref).split("\0") if p]


def read_at(repo: Path, ref: str, path: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                          capture_output=True, text=True, errors="replace")
    return proc.stdout if proc.returncode == 0 else None


def read_many(repo: Path, ref: str, paths: list[str]) -> dict[str, str]:
    """Read many files at a ref with one `git cat-file --batch` process."""
    if not paths:
        return {}
    request = "".join(f"{ref}:{p}\n" for p in paths).encode()
    proc = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], input=request,
                          capture_output=True)
    data, out, pos = proc.stdout, {}, 0
    for path in paths:
        nl = data.find(b"\n", pos)
        if nl == -1:
            break
        header = data[pos:nl].decode(errors="replace").split()
        pos = nl + 1
        if len(header) < 3 or header[1] == "missing":
            continue
        size = int(header[2])
        out[path] = data[pos:pos + size].decode(errors="replace")
        pos += size + 1
    return out


def commit_time(repo: Path, ref: str) -> int:
    return int(git(repo, "show", "-s", "--format=%ct", ref).strip())


@dataclass
class Commit:
    sha: str
    subject: str
    body: str
    author: str
    files: list[str] = field(default_factory=list)


def log(repo: Path, rev_range: str | list[str], since: str | None = None) -> list[Commit]:
    """Commits with the files they touched. rev_range: 'a..b' or a ref."""
    args = ["log", "--no-renames", "--format=%x1e%H%x1f%s%x1f%an%x1f%b%x1d", "--name-only"]
    if since:
        args.append(f"--since={since}")
    args += [rev_range] if isinstance(rev_range, str) else rev_range
    out = []
    for record in git(repo, *args).split("\x1e"):
        if not record.strip():
            continue
        meta, _, files = record.partition("\x1d")
        sha, subject, author, body = (meta.split("\x1f") + ["", "", "", ""])[:4]
        out.append(Commit(sha.strip(), subject.strip(), body.strip(), author.strip(),
                          [f for f in files.strip().splitlines() if f.strip()]))
    return out
