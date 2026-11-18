"""扫描工作区候选文件或 Git 暂存文件，发现敏感内容和本地制品。"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SENSITIVE = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"), "GitHub token"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "AWS access key"),
    (re.compile(
        r"(?i)(?:private[_-]?key|signing[_-]?key|wallet[_-]?key|secret[_-]?key)"
        r"[\"']?\s*[:=]\s*[\"']?(?:0x)?[0-9a-f]{64}\b"
    ), "hex signing key"),
)
LOCAL_DIRS = {".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "node_modules"}
LOCAL_FILE = re.compile(r"\.(?:sqlite\d*|db)(?:-(?:wal|shm|journal))?$", re.IGNORECASE)


def git(*args: str) -> bytes:
    result = subprocess.run(["git", *args], capture_output=True, check=True)
    return result.stdout


def forbidden_path(name: str) -> bool:
    path = PurePosixPath(name.lower())
    return (
        bool(set(path.parts) & LOCAL_DIRS)
        or path.suffix in {".pyc", ".pyo", ".whl", ".pem", ".key", ".p12", ".pfx"}
        or bool(LOCAL_FILE.search(path.name))
        or (path.name.startswith(".env.") or path.name == ".env") and path.name != ".env.example"
    )


def findings(name: str, content: bytes) -> list[str]:
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeError:
        return [f"{name}: file needs manual review because it is not UTF-8 text"]
    return [
        f"{name}:{number}: {description}"
        for number, line in enumerate(lines, 1)
        for pattern, description in SENSITIVE
        if pattern.search(line)
    ]


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--staged", action="store_true", help="scan blobs staged for commit")
    cli.add_argument("--tracked", action="store_true", help="scan only tracked files in the checkout")
    args = cli.parse_args()
    if args.staged and args.tracked:
        cli.error("choose only one file selection option")
    try:
        os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel").rstrip(b"\r\n")))
        if args.staged:
            listing = git("diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z")
        elif args.tracked:
            listing = git("ls-files", "--cached", "-z")
        else:
            listing = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
        problems = []
        files = sorted(set(os.fsdecode(name) for name in listing.split(b"\0") if name))
        for name in files:
            path = Path(name)
            if forbidden_path(name):
                problems.append(f"{name}: local artifact or secret-bearing file")
            elif args.staged and git("ls-files", "--format=%(objectmode)", "--", name).strip() not in {
                b"100644", b"100755",
            }:
                problems.append(f"{name}: staged entry needs manual review because it is not a regular file")
            elif not args.staged and path.is_symlink():
                problems.append(f"{name}: symbolic link needs manual review")
            elif args.staged or path.is_file():
                blob = git("show", f":{name}") if args.staged else path.read_bytes()
                problems.extend(findings(name, blob))
    except (OSError, subprocess.CalledProcessError):
        print("Contribution scan could not read the Git checkout or index.", file=sys.stderr)
        return 2

    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Contribution scan passed ({len(files)} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
