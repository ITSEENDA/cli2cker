import tempfile
import time
import unittest
from pathlib import Path

from backends.base import InputBackend, WindowRef
from completer import CommandCompleter
from models import ClickerSettings, TaskState
from storage import JsonStorage
from targets import TargetRegistry
from task_manager import TaskManager
from prompt_toolkit.document import Document


class FakeBackend(InputBackend):
    name = 'fake'

    def __init__(self):
        self.click_count = 0
        self.key_count = 0

    def find_windows_by_pid(self, pid):
        return [WindowRef(pid, pid)]

    def find_pids_by_executable(self, executable_path):
        return [123]

    def click(self, window, mode, x=300, y=300):
        self.click_count += 1

    def press_key(self, window, key):
        self.key_count += 1


class CoreTests(unittest.TestCase):
    def test_relative_target_path_is_saved_as_absolute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'game.exe'
            executable.write_text('', encoding='utf-8')
            storage = JsonStorage(root / 'data')
            registry = TargetRegistry(storage, FakeBackend())

            saved = registry.save('game', 'game.exe', base_dir=root)

            self.assertEqual(saved, executable.resolve())
            self.assertEqual(storage.load_paths()['game'], str(executable.resolve()))

    def test_task_stops_without_waiting_for_delay(self):
        backend = FakeBackend()
        manager = TaskManager(
            backend,
            ClickerSettings(click_mode=1, delay=10),
            worker_count=1,
        )
        try:
            task = manager.start(123)
            deadline = time.monotonic() + 1
            while backend.click_count == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            started = time.monotonic()
            self.assertTrue(manager.stop(123, timeout=1))
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(task.state, TaskState.STOPPED)
        finally:
            manager.close()

    def test_completer_handles_subcommands_and_trailing_space(self):
        completer = CommandCompleter({'!path': {'save': ['-n', '-p']}})
        completions = [
            item.text
            for item in completer.get_completions(Document('!path s'), None)
        ]
        self.assertEqual(completions, ['save'])
        completions = [
            item.text
            for item in completer.get_completions(Document('!path save '), None)
        ]
        self.assertEqual(completions, ['-n', '-p'])


if __name__ == '__main__':
    unittest.main()
