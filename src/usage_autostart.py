"""Launch the local usage widget when the installed ChatGPT desktop app starts."""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time

from app_runtime import data_directory, command_line, Signals

BASE = data_directory()
WIDGET_MUTEX = "Local\\CodexUsageWidget_20261004"
WATCHER_MUTEX = "Local\\CodexUsageGPTLauncher_20261006"


class LaunchState:
    def __init__(self):
        self.roots = set()
        self.pending = False
        self.retry_at = 0

    def step(self, roots, widget_running, now):
        roots = set(roots)
        if not roots:
            self.roots, self.pending, self.retry_at = set(), False, 0
            return False
        if roots - self.roots:
            self.pending, self.retry_at = True, 0
        self.roots = roots
        if widget_running:
            self.pending = False
        if self.pending and now >= self.retry_at:
            self.pending = False
            return True
        return False

    def launch_failed(self, now):
        self.pending, self.retry_at = True, now + 60


def windows_api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenMutexW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    return kernel


def gpt_roots(kernel):
    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Process enumeration unavailable")
    candidates = {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() == "chatgpt.exe":
                handle = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if handle:
                    try:
                        size = wintypes.DWORD(32768)
                        path = ctypes.create_unicode_buffer(size.value)
                        if (
                            kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
                            and "openai" in path.value.lower()
                        ):
                            candidates[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                    finally:
                        kernel.CloseHandle(handle)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    # Electron subprocess churn is not an application restart.
    return {pid for pid, parent in candidates.items() if parent not in candidates}


def widget_running(kernel):
    handle = kernel.OpenMutexW(0x100000, False, WIDGET_MUTEX)
    if handle:
        kernel.CloseHandle(handle)
        return True
    return False


def save_status(value):
    try:
        path = BASE / "gpt-autostart-status.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def main(folder=None):
    global BASE
    BASE = Path(folder) if folder else data_directory()
    BASE.mkdir(parents=True, exist_ok=True)
    kernel = windows_api()
    signals = Signals(BASE, create=True)
    if not signals.acquire("watcher"):
        signals.close()
        return 0
    state, last_report, last_launch = LaunchState(), 0, None
    try:
        while not signals.received("stop"):
            now = time.monotonic()
            try:
                roots = gpt_roots(kernel)
                running = signals.running("widget")
                if state.step(roots, running, now):
                    try:
                        child = subprocess.Popen(
                            command_line("--data-dir", str(BASE)),
                            cwd=str(BASE),
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        last_launch = {"pid": child.pid, "at": time.time()}
                    except OSError:
                        state.launch_failed(now)
                if now - last_report >= 10 or last_report == 0:
                    save_status(
                        {
                            "pid": os.getpid(),
                            "checkedAt": time.time(),
                            "ok": True,
                            "gptProcessIds": sorted(roots),
                            "widgetRunning": signals.running("widget"),
                            "lastLaunch": last_launch,
                        }
                    )
                    last_report = now
            except OSError:
                save_status({"pid": os.getpid(), "checkedAt": time.time(), "ok": False})
            time.sleep(1)
    finally:
        signals.close()
    return 0


if __name__ == "__main__":
    main()
