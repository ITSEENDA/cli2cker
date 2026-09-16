import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from app import AfkClicker
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
        completer = CommandCompleter({'!profile': {'create': ['-n', '-p']}})
        completions = [
            item.text
            for item in completer.get_completions(Document('!profile'), None)
        ]
        self.assertEqual(completions, ['create'])
        completions = [
            item.text
            for item in completer.get_completions(Document('!profile c'), None)
        ]
        self.assertEqual(completions, ['create'])
        completions = [
            item.text
            for item in completer.get_completions(Document('!profile create '), None)
        ]
        self.assertEqual(completions, ['-n', '-p'])

    def test_shell_context_resolves_relative_profile_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shell_dir = root / 'games'
            shell_dir.mkdir()
            executable = shell_dir / 'game.exe'
            executable.write_text('', encoding='utf-8')
            app = AfkClicker(
                storage=JsonStorage(root / 'data'),
                backend=FakeBackend(),
            )
            try:
                original_cwd = Path.cwd()
                app.working_dir = root
                app.router.dispatch('!cd games')
                self.assertEqual(Path.cwd(), original_cwd)
                app.router.dispatch('!profile create game --path game.exe')
                self.assertEqual(app.targets.show('game'), str(executable.resolve()))
                output = StringIO()
                with redirect_stdout(output):
                    app.router.dispatch('!pwd')
                    app.router.dispatch('!ls')
                self.assertIn(str(shell_dir.resolve()), output.getvalue())
                self.assertIn('game.exe', output.getvalue())
            finally:
                app.close()

    def test_task_commands_are_grouped_with_legacy_alias_support(self):
        app = AfkClicker(storage=JsonStorage(Path(tempfile.mkdtemp()) / 'data'), backend=FakeBackend())
        try:
            self.assertIn('!task', app.router.handlers)
            self.assertNotIn('!set', app.router.handlers)
            self.assertNotIn('!status', app.router.handlers)
            self.assertEqual(app.router.dispatch('!set 123 -d 1'), 'Command error: No active task for PID 123')
        finally:
            app.close()

    def test_task_config_accepts_readable_parameter_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'game.exe'
            executable.write_text('', encoding='utf-8')
            app = AfkClicker(
                storage=JsonStorage(root / 'data'),
                backend=FakeBackend(),
            )
            try:
                app.working_dir = root
                app.router.dispatch('!profile create game --path game.exe')
                app.router.dispatch('!task start game')
                app.router.dispatch(
                    '!task config game --mode right-left --delay 0.5 '
                    '--key space --safety strict'
                )
                task = app.tasks.status()[0]
                self.assertEqual(task.settings.click_mode, 4)
                self.assertEqual(task.settings.delay, 0.5)
                self.assertEqual(task.settings.key, 'space')
                self.assertTrue(task.settings.safety)
            finally:
                app.close()

    def test_help_includes_subcommand_and_parameter_descriptions(self):
        app = AfkClicker(
            storage=JsonStorage(Path(tempfile.mkdtemp()) / 'data'),
            backend=FakeBackend(),
        )
        try:
            task_help = app.helper.format_help('!task')
            config_help = app.helper.format_help('!task config')
            self.assertIn('Start a task for a profile or PID.', task_help)
            self.assertIn('--mode - off, left, right, left-right, or right-left.', config_help)
            self.assertIn('(example: right-left)', config_help)
            self.assertIn('--safety - strict or off.', config_help)
        finally:
            app.close()

    def test_completer_suggests_option_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'game.exe'
            executable.write_text('', encoding='utf-8')
            app = AfkClicker(
                storage=JsonStorage(root / 'data'),
                backend=FakeBackend(),
            )
            try:
                app.working_dir = root
                app.router.dispatch('!profile create mc --path game.exe')
                profile_values = [
                    item.text
                    for item in app.completer.get_completions(
                        Document('!task start --profile '), None
                    )
                ]
                mode_values = [
                    item.text
                    for item in app.completer.get_completions(
                        Document('!task config mc --mode r'), None
                    )
                ]
                self.assertIn('mc', profile_values)
                self.assertEqual(mode_values, ['right', 'right-left'])
            finally:
                app.close()

    def test_hotkey_edit_updates_action_and_keys_without_capture(self):
        app = AfkClicker(
            storage=JsonStorage(Path(tempfile.mkdtemp()) / 'data'),
            backend=FakeBackend(),
        )
        try:
            app.router.dispatch(
                '!hotkey create toggle-mc --keys alt+` '
                '--action "!task toggle mc"'
            )
            names = [
                item.text
                for item in app.completer.get_completions(
                    Document('!hotkey edit '), None
                )
            ]
            self.assertIn('toggle-mc', names)
            app.router.dispatch('!hotkey edit toggle-mc --action noop')
            app.router.dispatch('!hotkey edit toggle-mc --keys shift+tab')
            binding = app.hotkeys.bindings['toggle-mc']
            self.assertEqual(binding['action'], 'noop')
            self.assertEqual(binding['keys'], ['shift', 'tab'])
        finally:
            app.close()

    def test_path_completion_uses_shell_working_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            games = root / 'Games'
            games.mkdir()
            (games / 'game.exe').write_text('', encoding='utf-8')
            app = AfkClicker(
                storage=JsonStorage(root / 'data'),
                backend=FakeBackend(),
            )
            try:
                app.working_dir = root
                cd_values = [
                    item.text
                    for item in app.completer.get_completions(
                        Document('!cd G'), None
                    )
                ]
                nested_values = [
                    item.text
                    for item in app.completer.get_completions(
                        Document('!profile create game --path Games\\'), None
                    )
                ]
                self.assertIn('Games\\', cd_values)
                self.assertIn('Games\\game.exe', nested_values)
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()
