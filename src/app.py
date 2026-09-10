import os
from pathlib import Path

from backends import create_backend
from commands import CommandRouter
from completer import CommandCompleter
from helper import ClickerHelper
from hotkeys import HotkeyManager
from models import ClickerSettings, TaskState
from storage import JsonStorage
from targets import TargetRegistry
from task_manager import TaskManager
from utils import GREEN, RED, RESET, YELLOW, clear_terminal, safe_prompt, str_to_bool


class AfkClicker:
    def __init__(self, base_thread_num=5, click_mode=0, key=0, delay=0.25, safety=True,
                 storage=None, backend=None):
        legacy_dir = Path(__file__).parent / 'data'
        self.storage = storage or JsonStorage(legacy_dir=legacy_dir)
        self.defaults = self.storage.load_settings(
            ClickerSettings(click_mode, key, delay, safety)
        )
        self.backend = backend or create_backend()
        self.targets = TargetRegistry(self.storage, self.backend)
        self.tasks = TaskManager(self.backend, self.defaults, base_thread_num)
        self.debug_mode = False
        self.closed = False

        self.helper = ClickerHelper(
            prog='afkclicker',
            description='Interactive AFK clicker commands',
        )
        self.router = CommandRouter(self.helper)
        self._register_commands()
        self.completer = CommandCompleter(self.helper.completion_map)
        self.hotkeys = HotkeyManager(
            self.storage,
            self._handle_hotkey_action,
            self.backend.is_key_pressed,
        )

    def _register_commands(self):
        self.router.register(
            '!start', self._cmd_start,
            'Start a clicker task.',
            options=['-p', '-n'],
            usage='!start -p <pid> | !start -n <target>',
        )
        self.router.register(
            '!stop', self._cmd_stop,
            'Stop a task or all tasks.',
            options=['-p', '-n', 'all'],
            usage='!stop -p <pid> | !stop -n <target> | !stop all',
        )
        self.router.register(
            '!toggle', self._cmd_toggle,
            'Pause or resume a task.',
            options=['-p', '-n'],
            usage='!toggle -p <pid> | !toggle -n <target>',
        )
        self.router.register(
            '!set', self._cmd_set,
            'Change settings for a running task.',
            options=['-m', '-k', '-d', '-s', 'default'],
            usage='!set <pid|target> [-m mode] [-k key] [-d seconds] [-s true|false]',
        )
        self.router.register(
            '!status', self._cmd_status,
            'Show all active tasks.',
        )
        self.router.register(
            '!path', self._cmd_path,
            'Manage saved target paths.',
            subcommands={
                'save': ['-n', '-p'],
                'del': ['-n'],
                'def': ['mc'],
                'list': [],
            },
            usage='!path <save|del|list> ...',
        )
        self.router.register(
            '!hotkey', self._cmd_hotkey,
            'Manage global hotkeys.',
            subcommands={
                'list': [],
                'save': ['-n', '-a'],
                'mod': ['-a', 'rb'],
                'del': ['-n'],
            },
            usage='!hotkey <list|save|mod|del> ...',
        )
        self.router.register(
            '!debug', self._cmd_debug,
            'Enable, disable, or toggle debug output.',
            options=['true', 'false'],
            usage='!debug [true|false]',
        )
        self.router.register('!clear', lambda _: clear_terminal(), 'Clear the terminal.')
        self.router.register('!help', self._cmd_help, 'Show command help.', usage='!help [command]')
        self.router.register('!quit', lambda _: self.close(), 'Exit the clicker.')
        self.helper.commands['!help'].options = tuple(self.helper.commands)

    def _handle_hotkey_action(self, action):
        result = self.router.dispatch(action)
        if isinstance(result, str):
            print(result)

    @staticmethod
    def _parse_options(args):
        values = {}
        index = 0
        while index < len(args):
            option = args[index]
            if not option.startswith('-') or index + 1 >= len(args):
                raise ValueError(f'Missing value for option {option}')
            values[option] = args[index + 1]
            index += 2
        return values

    def _resolve_target(self, args):
        if not args:
            raise ValueError('Target is required: use -p <pid> or -n <name>')
        if args[0] == '-p':
            if len(args) < 2:
                raise ValueError('Missing PID after -p')
            return int(args[1]), None, 2
        if args[0] == '-n':
            if len(args) < 2:
                raise ValueError('Missing target name after -n')
            name = args[1]
            for task in self.tasks.status():
                if task.profile_name == name:
                    return task.pid, name, 2
            pids = self.targets.find_pids(name)
            if not pids:
                raise RuntimeError(f'No process found for target {name!r}')
            if len(pids) > 1:
                raise RuntimeError(f'Multiple processes found for target {name!r}: {pids}')
            return pids[0], name, 2
        if args[0].isdigit():
            return int(args[0]), None, 1
        name = args[0]
        for task in self.tasks.status():
            if task.profile_name == name:
                return task.pid, name, 1
        pids = self.targets.find_pids(name)
        if not pids:
            raise RuntimeError(f'No process found for target {name!r}')
        if len(pids) > 1:
            raise RuntimeError(f'Multiple processes found for target {name!r}: {pids}')
        return pids[0], name, 1

    def _cmd_start(self, args):
        pid, profile, _ = self._resolve_target(args)
        task = self.tasks.start(pid, profile_name=profile)
        print(f'{GREEN}[STARTED] PID {task.pid} ({self.backend.name}){RESET}')

    def _cmd_stop(self, args):
        if args == ['all']:
            self.tasks.stop_all()
            print(f'{GREEN}[STOPPED] all tasks{RESET}')
            return
        pid, _, _ = self._resolve_target(args)
        if not self.tasks.stop(pid):
            raise RuntimeError(f'Task {pid} did not stop within the timeout')
        print(f'{GREEN}[STOPPED] PID {pid}{RESET}')

    def _cmd_toggle(self, args):
        pid, profile, _ = self._resolve_target(args)
        task = self.tasks.toggle(pid, profile_name=profile)
        print(f'{GREEN}[{task.state.value.upper()}] PID {task.pid}{RESET}')

    def _cmd_set(self, args):
        pid, _, consumed = self._resolve_target(args)
        values = args[consumed:]
        task = self.tasks.tasks.get(pid)
        if task is None:
            raise RuntimeError(f'No active task for PID {pid}')
        if values == ['default']:
            task.settings = self.defaults.copy()
            return
        options = self._parse_options(values)
        updates = {}
        if '-m' in options:
            updates['click_mode'] = int(options['-m'])
        if '-k' in options:
            updates['key'] = options['-k']
        if '-d' in options:
            delay = float(options['-d'])
            if task.settings.safety and delay < self.defaults.delay:
                raise ValueError(f'Delay must be at least {self.defaults.delay} seconds')
            updates['delay'] = delay
        if '-s' in options:
            updates['safety'] = str_to_bool(options['-s'])
        self.tasks.update_settings(pid, **updates)
        print(f'{GREEN}[UPDATED] PID {pid}{RESET}')

    def _cmd_status(self, _):
        tasks = self.tasks.status()
        if not tasks:
            print('No active tasks.')
            return
        print('PROFILE\tPID\tSTATE\tDELAY\tMODE')
        for task in tasks:
            profile = task.profile_name or '-'
            print(f'{profile}\t{task.pid}\t{task.state.value}\t{task.settings.delay}\t{task.settings.click_mode}')

    def _cmd_path(self, args):
        if not args:
            raise ValueError('Use !path save, !path del, or !path list')
        action = args[0]
        if action == 'list':
            for name, path in self.targets.list().items():
                print(f'{name}: {path}')
            return
        if action == 'def':
            if len(args) < 2 or args[1] != 'mc':
                raise ValueError('Supported built-in target: mc')
            appdata = os.environ.get('APPDATA')
            if not appdata:
                raise RuntimeError('APPDATA is not available on this operating system')
            path = Path(appdata) / '.minecraft' / 'runtime' / 'java-runtime-gamma' / 'windows' / 'java-runtime-gamma' / 'bin' / 'javaw.exe'
            self.targets.save('mc', str(path), validate=False)
            print(f'{GREEN}[SAVED] mc -> {path}{RESET}')
            return
        options = self._parse_options(args[1:])
        name = options.get('-n')
        if not name:
            raise ValueError('Missing -n <name>')
        if action == 'save':
            raw_path = options.get('-p')
            if not raw_path:
                raise ValueError('Missing -p <path>')
            path = self.targets.save(name, raw_path)
            print(f'{GREEN}[SAVED] {name} -> {path}{RESET}')
        elif action == 'del':
            if self.targets.delete(name):
                print(f'{GREEN}[DELETED] {name}{RESET}')
        else:
            raise ValueError(f'Unknown path action: {action}')

    def _cmd_hotkey(self, args):
        if not args:
            raise ValueError('Use !hotkey list, save, mod, or del')
        action = args[0]
        if action == 'list':
            for name, data in self.hotkeys.bindings.items():
                print(f"{name}: {'+'.join(data['keys'])} -> {data['action']}")
            return
        if action == 'save':
            options = self._parse_options(args[1:])
            name = options.get('-n')
            command = options.get('-a')
            if not name or not command:
                raise ValueError('Use !hotkey save -n <name> -a <command>')
            keys = self.hotkeys.capture_binding(name, command)
            print(f"{GREEN}[SAVED] {'+'.join(sorted(keys))}{RESET}")
            return
        if action == 'mod':
            if len(args) < 2:
                raise ValueError('Missing hotkey name')
            name = args[1]
            options = args[2:]
            if options and options[0] == 'rb':
                command = self.hotkeys.bindings[name]['action']
                keys = self.hotkeys.capture_binding(name, command)
                print(f"{GREEN}[UPDATED] {'+'.join(sorted(keys))}{RESET}")
            else:
                values = self._parse_options(options)
                self.hotkeys.update_action(name, values['-a'])
            return
        if action == 'del':
            options = self._parse_options(args[1:])
            if self.hotkeys.delete_binding(options['-n']):
                print(f'{GREEN}[DELETED] {options["-n"]}{RESET}')
            return
        raise ValueError(f'Unknown hotkey action: {action}')

    def _cmd_debug(self, args):
        if args:
            self.debug_mode = str_to_bool(args[0])
        else:
            self.debug_mode = not self.debug_mode
        print(f'Debug: {self.debug_mode}')

    def _cmd_help(self, args):
        self.helper.print_help(args[0] if args else None)

    def run(self):
        self.hotkeys.start()
        try:
            while not self.tasks.global_stop.is_set():
                line = safe_prompt('>> ', completer=self.completer)
                result = self.router.dispatch(line)
                if isinstance(result, str):
                    print(result)
        except (EOFError, KeyboardInterrupt):
            print(f'{YELLOW}Stopping clicker...{RESET}')
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.hotkeys.stop()
        self.tasks.close()
