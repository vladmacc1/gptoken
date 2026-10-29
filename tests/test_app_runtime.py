from pathlib import Path
import os
import unittest
from unittest.mock import patch

from app_runtime import command_line, data_directory, instance_names, Signals
from usage_discovery import find_codex


class RuntimeTests(unittest.TestCase):
    def test_relative_data_override_is_rejected(self):
        with self.assertRaises(ValueError):
            data_directory("relative-data")

    def test_default_is_in_user_data(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:\\ExampleUserData"}):
            self.assertEqual(data_directory(), Path("C:/ExampleUserData/VLADMACC/CodexUsageWidget"))

    def test_packaged_command_does_not_need_python(self):
        with patch("sys.frozen", True, create=True), patch("sys.executable", "C:/App/CodexUsageWidget.exe"):
            self.assertEqual(command_line("--watch"), ["C:/App/CodexUsageWidget.exe", "--watch"])

    def test_instances_are_isolated_by_data_directory(self):
        self.assertNotEqual(instance_names("C:/qa/one"), instance_names("C:/qa/two"))
        self.assertEqual(instance_names("C:/qa/one"), instance_names("c:/QA/ONE"))

    def test_settings_signal_and_duplicate_instance(self):
        folder = Path(__file__).resolve().parent / "artifacts" / f"signals-{os.getpid()}"
        first, second = Signals(folder, create=True), Signals(folder, create=True)
        try:
            self.assertTrue(first.acquire("widget"))
            self.assertFalse(second.acquire("widget"))
            self.assertTrue(second.send("settings"))
            self.assertTrue(first.received("settings"))
            self.assertFalse(first.received("settings"))
        finally:
            second.close()
            first.close()

    def test_codex_override_rejects_commands_relative_paths_and_other_executables(self):
        for value in ("codex.exe", "cmd.exe /c codex", "C:/Windows/System32/cmd.exe", "C:/missing/codex.exe"):
            with self.subTest(value=value), patch.dict(os.environ, {"VLADMACC_CODEX_PATH": value}):
                with self.assertRaises(FileNotFoundError):
                    find_codex()
