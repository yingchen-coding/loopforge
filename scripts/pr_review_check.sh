#!/usr/bin/env bash
set -euo pipefail

python -m ruff check .
python -m mypy loopforge
python -m compileall -q loopforge tests
python -m pytest -q
python -m pip install -e '.[dev]'
mkdir -p /tmp/loopforge-review
loopforge init ci-green --dest /tmp/loopforge-review --force >/tmp/loopforge-review-init.txt
loopforge lint /tmp/loopforge-review/ci-green --score >/tmp/loopforge-review-lint.txt
agentguard --publish-check --score --no-color .

python - <<'PY'
from pathlib import Path

blocked = [
    "/" + "Users" + "/",
    "ghp" + "_",
    "BEGIN " + "RSA" + " KEY",
    "BEGIN " + "OPENSSH" + " KEY",
    "BEGIN " + "PRIVATE" + " KEY",
    "private-user" + "-images",
    "Temporary" + "Items",
]
skip_dirs = {".git", ".pytest_cache", ".ruff_cache", ".mypy_cache", "__pycache__", "build", "dist"}
findings: list[str] = []

for path in Path(".").rglob("*"):
    if not path.is_file():
        continue
    if any(part in skip_dirs or part.endswith(".egg-info") for part in path.parts):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for needle in blocked:
        if needle in text:
            findings.append(f"{path}: contains blocked public-surface marker")
            break

if findings:
    print("\n".join(findings))
    raise SystemExit("public-surface scan failed")
PY
