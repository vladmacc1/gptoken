"""Installation-independent paths and per-user instance signalling."""

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time

APP_ID = "VLADMACC.CodexUsageWidget"
APP_NAME = "Codex Usage Widget"
VERSION = "5.1.1"
RESOURCE_DIR = Path(__file__).resolve().parent


def data_directory(override=None):
    if override:
        value = Path(override).expanduser()
        if not value.is_absolute():
            raise ValueError("--data-dir must be an absolute path")
        return value.resolve()
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / "AppData" / "Local") / "VLADMACC" / "CodexUsageWidget"


def command_line(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else Path(sys.executable)), str(RESOURCE_DIR / "codex_usage.pyw"), *args]


def instance_names(folder):
    suffix = hashlib.sha256(str(Path(folder).resolve()).casefold().encode("utf-8")).hexdigest()[:20]
    root = f"Local\\{APP_ID}.{suffix}"
    return {key: root + "." + key for key in ("widget", "watcher", "stop", "settings")}


class Signals:
    def __init__(self, folder, create=False):
        self.names = instance_names(folder)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.k.CreateMutexW.restype = wintypes.HANDLE
        self.k.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self.k.OpenMutexW.restype = wintypes.HANDLE
        self.k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.k.CreateEventW.restype = wintypes.HANDLE
        self.k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self.k.OpenEventW.restype = wintypes.HANDLE
        self.k.SetEvent.argtypes = [wintypes.HANDLE]
        self.k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handles = {}
        if create:
            for key in ("stop", "settings"):
                handle = self.k.CreateEventW(None, False, False, self.names[key])
                if not handle:
                    raise OSError(ctypes.get_last_error(), "Could not create application event")
                self.handles[key] = handle

    def acquire(self, key):
        ctypes.set_last_error(0)
        handle = self.k.CreateMutexW(None, False, self.names[key])
        existed = ctypes.get_last_error() == 183
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create application mutex")
        self.handles[key] = handle
        return not existed

    def running(self, key):
        handle = self.k.OpenMutexW(0x100000, False, self.names[key])
        if handle:
            self.k.CloseHandle(handle)
        return bool(handle)

    def send(self, key):
        handle = self.k.OpenEventW(0x0002, False, self.names[key])
        if not handle:
            return False
        try:
            return bool(self.k.SetEvent(handle))
        finally:
            self.k.CloseHandle(handle)

    def received(self, key):
        handle = self.handles.get(key)
        return bool(handle and self.k.WaitForSingleObject(handle, 0) == 0)

    def close(self):
        for handle in self.handles.values():
            self.k.CloseHandle(handle)
        self.handles.clear()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def request_shutdown(folder, timeout=10):
    signals = Signals(folder)
    deadline = time.monotonic() + timeout
    # Repeat the auto-reset signal until both independent consumers have exited.
    while signals.running("widget") or signals.running("watcher"):
        signals.send("stop")
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
    return True
