"""One entry point for repository checks, with src importable on any checkout."""

from pathlib import Path
import os
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUTF8="1")
for source in (ROOT / "src").glob("*.pyw"):
    py_compile.compile(str(source), doraise=True)
for command in (
    ["-m", "compileall", "-q", "src", "tests", "scripts"],
    ["-m", "ruff", "check", "src", "tests", "scripts"],
    ["-m", "ruff", "format", "--check", "src", "tests", "scripts"],
    ["-m", "unittest", "discover", "-s", "tests", "-q"],
):
    subprocess.run([sys.executable, *command], cwd=ROOT, env=env, check=True)
