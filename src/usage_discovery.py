"""Locate an existing Codex executable without executing shell shims or cwd files."""

import os
from pathlib import Path


def find_codex():
    explicit = os.environ.get("VLADMACC_CODEX_PATH")
    if explicit:
        path = Path(explicit)
        if path.is_absolute() and path.is_file() and path.name.casefold() == "codex.exe":
            return str(path.resolve())
        raise FileNotFoundError("CODEX_NOT_FOUND")
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates = list((local / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"))
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    npm = roaming / "npm" / "node_modules" / "@openai"
    for pattern in (
        "codex/vendor/*/codex/codex.exe",
        "codex/node_modules/@openai/codex-win32-x64/vendor/*/codex/codex.exe",
        "codex-win32-x64/vendor/*/codex/codex.exe",
    ):
        candidates.extend(npm.glob(pattern))
    real = [p for p in candidates if p.is_file()]
    if real:
        return str(max(real, key=lambda p: p.stat().st_mtime).resolve())
    # Python's Windows which() can search cwd; explicitly reject this implicit location.
    for directory in os.get_exec_path():
        if not directory or Path(directory).resolve() == Path.cwd().resolve():
            continue
        parent = Path(directory)
        if not parent.is_absolute():
            continue
        path = (parent / "codex.exe").resolve()
        if path.parent != Path.cwd().resolve() and path.is_file():
            return str(path)
    raise FileNotFoundError("CODEX_NOT_FOUND")
