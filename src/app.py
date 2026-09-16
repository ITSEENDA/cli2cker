import os
from pathlib import Path

from backends import create_backend
from commands import CommandRouter
from completer import CommandCompleter
from helper import ClickerHelper
from hotkeys import HotkeyManager
from models import ClickerSettings, click_mode_name
from storage import JsonStorage
from targets import TargetRegistry
from task_manager import TaskManager
from utils import (
    GREEN,
    RED,
    RESET,
    YELLOW,
    clear_terminal,
    create_prompt_session,
    safe_prompt,
    str_to_bool,
)


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
        self.working_dir = Path.cwd()
        self.debug_mode = False
        self.closed = False

        self.helper = ClickerHelper(
            prog='afkclicker',
            description='Interactive AFK clicker commands',
        )
        self.router = CommandRouter(self.helper)
        self._register_commands()
        self.completer = CommandCompleter(
            self.helper.completion_map,
            path_provider=self._complete_paths,
        )
        self._refresh_profile_completions()
        self.prompt_session = create_prompt_session(
            self.storage.history_path,
            completer=self.completer,
        )
        self.hotkeys = HotkeyManager(
            self.storage,
            self._handle_hotkey_action,
            self.backend.is_key_pressed,
        )
        self._refresh_hotkey_completions()

    def _register_commands(self):
        self.router.register(
            '!task', self._cmd_task,
            'Manage running clicker tasks.',
            subcommands={
                'start': ['--pid', '--profile'],
                'pause': ['--pid', '--profile'],
                'resume': ['--pid', '--profile'],
                'toggle': ['--pid', '--profile'],
                'config': ['--mode', '--delay', '--key', '--safety'],
                'reset': [],
                'stop': ['--pid', '--profile', 'all'],
                'status': [],
                'list': [],
            },
            subcommand_arguments={
                'start': ['<target>'],
                'pause': ['<target>'],
                'resume': ['<target>'],
                'toggle': ['<target>'],
                'config': ['<target>'],
                'reset': ['<target>'],
                'stop': ['<target>'],
            },
            subcommand_argument_descriptions={
                'start': {'<target>': 'Profile name, or a numeric PID.'},
                'pause': {'<target>': 'Profile name, or a numeric PID.'},
                'resume': {'<target>': 'Profile name, or a numeric PID.'},
                'toggle': {'<target>': 'Profile name, or a numeric PID.'},
                'config': {'<target>': 'Running task profile name, or PID.'},
                'reset': {'<target>': 'Running task profile name, or PID.'},
                'stop': {'<target>': 'Profile name, or a numeric PID.'},
            },
            usage='!task <start|pause|resume|toggle|config|reset|stop|status> ...',
            subcommand_descriptions={
                'start': 'Start a task for a profile or PID.',
                'pause': 'Pause a running task without removing it.',
                'resume': 'Resume a paused task.',
                'toggle': 'Toggle between running and paused.',
                'config': 'Change runtime parameters of a task.',
                'reset': 'Restore the task default parameters.',
                'stop': 'Stop and remove a task.',
                'status': 'Show all active tasks.',
                'list': 'Alias for status.',
            },
            subcommand_option_descriptions={
                'start': {
                    '--pid': 'Use a process ID instead of a profile.',
                    '--profile': 'Use a saved profile name.',
                },
                'pause': {
                    '--pid': 'Process ID of the task.',
                    '--profile': 'Profile name of the task.',
                },
                'resume': {
                    '--pid': 'Process ID of the task.',
                    '--profile': 'Profile name of the task.',
                },
                'toggle': {
                    '--pid': 'Process ID of the task.',
                    '--profile': 'Profile name of the task.',
                },
                'config': {
                    '--mode': 'off, left, right, left-right, or right-left.',
                    '--delay': 'Seconds between triggers.',
                    '--key': 'Key sent to the target, or none.',
                    '--safety': 'strict or off.',
                },
                'stop': {
                    '--pid': 'Process ID of the task.',
                    '--profile': 'Profile name of the task.',
                    'all': 'Stop every active task.',
                },
            },
            subcommand_option_examples={
                'start': {'--pid': '36140', '--profile': 'mc'},
                'pause': {'--pid': '36140', '--profile': 'mc'},
                'resume': {'--pid': '36140', '--profile': 'mc'},
                'toggle': {'--pid': '36140', '--profile': 'mc'},
                'config': {
                    '--mode': 'right-left',
                    '--delay': '0.5',
                    '--key': 'space',
                    '--safety': 'strict',
                },
                'stop': {'--pid': '36140', '--profile': 'mc'},
            },
        )
        self.router.register(
            '!profile', self._cmd_profile,
            'Create and manage target profiles.',
            subcommands={
                'create': ['--path'],
                'list': [],
                'show': [],
                'edit': ['--path'],
                'delete': [],
            },
            subcommand_arguments={
                'create': ['<name>'],
                'show': ['<name>'],
                'edit': ['<name>'],
                'delete': ['<name>'],
            },
            subcommand_argument_descriptions={
                'create': {'<name>': 'Unique profile alias.'},
                'show': {'<name>': 'Profile alias to inspect.'},
                'edit': {'<name>': 'Profile alias to update.'},
                'delete': {'<name>': 'Profile alias to delete.'},
            },
            usage='!profile <create|list|show|edit|delete> ...',
            subcommand_descriptions={
                'create': 'Create a saved executable profile.',
                'list': 'List saved profiles.',
                'show': 'Show one profile.',
                'edit': 'Change a profile executable path.',
                'delete': 'Delete a profile.',
            },
            subcommand_option_descriptions={
                'create': {'--path': 'Executable path; relative paths use !cd context.'},
                'edit': {'--path': 'New executable path.'},
            },
            subcommand_option_examples={
                'create': {'--path': '.\\Minecraft\\javaw.exe'},
                'edit': {'--path': '.\\Minecraft\\javaw-new.exe'},
            },
        )
        self.router.register(
            '!cd', self._cmd_cd,
            'Change the shell working directory.',
            usage='!cd [path]',
        )
        self.router.register('!pwd', self._cmd_pwd, 'Show the shell working directory.')
        self.router.register(
            '!ls', self._cmd_ls,
            'List files in the shell working directory.',
            options=['-a'],
            usage='!ls [-a] [path]',
            option_descriptions={'-a': 'Include hidden entries.'},
            option_examples={'-a': '!ls -a'},
        )
        self.router.register(
            '!hotkey', self._cmd_hotkey,
            'Manage global hotkeys.',
            subcommands={
                'list': [],
                'create': ['--keys', '--action'],
                'edit': ['--keys', '--action', 'rb'],
                'delete': [],
            },
            subcommand_arguments={
                'create': ['<name>'],
                'edit': ['<name>'],
                'delete': ['<name>'],
            },
            subcommand_argument_descriptions={
                'create': {'<name>': 'Unique hotkey alias.'},
                'edit': {'<name>': 'Hotkey alias to update.'},
                'delete': {'<name>': 'Hotkey alias to delete.'},
            },
            usage='!hotkey <list|create|edit|delete> ...',
            subcommand_descriptions={
                'list': 'List saved hotkeys.',
                'create': 'Create a hotkey binding.',
                'edit': 'Change a hotkey binding.',
                'delete': 'Delete a hotkey binding.',
            },
            subcommand_option_descriptions={
                'create': {
                    '--keys': 'Key combination such as alt+`.',
                    '--action': 'Command to dispatch when triggered.',
                },
                'edit': {
                    '--keys': 'New key combination.',
                    '--action': 'New command action.',
                    'rb': 'Capture a new combination interactively.',
                },
            },
            subcommand_option_examples={
                'create': {
                    '--keys': 'alt+`',
                    '--action': '"!task toggle mc"',
                },
                'edit': {
                    '--keys': 'shift+tab',
                    '--action': '"!task pause mc"',
                },
            },
        )
        self.router.register(
            '!debug', self._cmd_debug,
            'Enable, disable, or toggle debug output.',
            options=['true', 'false'],
            usage='!debug [true|false]',
            option_descriptions={
                'true': 'Enable debug output.',
                'false': 'Disable debug output.',
            },
            option_examples={'true': '!debug true', 'false': '!debug false'},
        )
        self.router.register('!clear', lambda _: clear_terminal(), 'Clear the terminal.')
        self.router.register('!help', self._cmd_help, 'Show command help.', usage='!help [command]')
        self.router.register('!quit', lambda _: self.close(), 'Exit the clicker.')
        self.helper.commands['!help'].options = tuple(self.helper.commands)

    def _refresh_profile_completions(self):
        profiles = list(self.targets.list())
        task_subcommands = ('start', 'pause', 'resume', 'toggle', 'config', 'reset', 'stop')
        for subcommand in task_subcommands:
            self.completer.update_argument_candidates('!task', subcommand, profiles)
            self.completer.update_value_candidates('!task', subcommand, '--profile', profiles)
        for subcommand in ('show', 'edit', 'delete'):
            self.completer.update_argument_candidates('!profile', subcommand, profiles)
        self.completer.update_value_candidates(
            '!task', 'config', '--mode',
            ['off', 'left', 'right', 'left-right', 'right-left'],
        )
        self.completer.update_value_candidates(
            '!task', 'config', '--safety', ['strict', 'off']
        )
        self.completer.update_value_candidates(
            '!task', 'config', '--key', ['none', 'space', 'enter', 'tab']
        )

    def _refresh_hotkey_completions(self):
        names = list(self.hotkeys.bindings)
        for subcommand in ('edit', 'delete'):
            self.completer.update_argument_candidates('!hotkey', subcommand, names)
        self.completer.update_value_candidates(
            '!hotkey', 'create', '--keys', ['alt+`', 'shift+tab']
        )
        self.completer.update_value_candidates(
            '!hotkey', 'edit', '--keys', ['alt+`', 'shift+tab']
        )
        self.completer.update_value_candidates(
            '!hotkey', 'create', '--action', ['"!task toggle mc"', '"!task pause mc"']
        )
        self.completer.update_value_candidates(
            '!hotkey', 'edit', '--action', ['"!task toggle mc"', '"!task pause mc"']
        )

    def _handle_hotkey_action(self, action):
        result = self.router.dispatch(action)
        if isinstance(result, str):
            print(result)

    @staticmethod
    def _parse_options(args):
        aliases = {
            '-p': '--pid',
            '-n': '--profile',
            '--name': '--profile',
            '--path': '--path',
            '-m': '--mode',
            '-k': '--key',
            '-d': '--delay',
            '-s': '--safety',
            '-a': '--action',
            '--mouse': '--mode',
            '--keyboard': '--key',
        }
        values = {}
        index = 0
        while index < len(args):
            option = args[index]
            if not option.startswith('-'):
                raise ValueError(f'Missing value for option {option}')
            if '=' in option:
                option, value = option.split('=', 1)
            else:
                if index + 1 >= len(args):
                    raise ValueError(f'Missing value for option {option}')
                value = args[index + 1]
            values[aliases.get(option, option)] = value
            index += 1 if '=' in option else 2
        return values

    def _resolve_target(self, args):
        if not args:
            raise ValueError('Target is required: use -p <pid> or -n <name>')
        if args[0] in {'-p', '--pid'}:
            if len(args) < 2:
                raise ValueError('Missing PID after -p')
            return int(args[1]), None, 2
        if args[0] in {'-n', '--profile', '--name'}:
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
        target = profile or f'PID {task.pid}'
        print(f'{GREEN}[STARTED] {target} ({self.backend.name}){RESET}')

    def _cmd_pause(self, args):
        pid, profile, _ = self._resolve_target(args)
        task = self.tasks.pause(pid)
        target = profile or f'PID {task.pid}'
        print(f'{YELLOW}[PAUSED] {target} (PID {task.pid}){RESET}')

    def _cmd_resume(self, args):
        pid, profile, _ = self._resolve_target(args)
        task = self.tasks.resume(pid)
        target = profile or f'PID {task.pid}'
        print(f'{GREEN}[RESUMED] {target} (PID {task.pid}){RESET}')

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
        target = profile or f'PID {task.pid}'
        print(f'{GREEN}[{task.state.value.upper()}] {target} (PID {task.pid}){RESET}')

    def _cmd_task(self, args):
        if not args:
            self.helper.print_help('!task')
            return
        handlers = {
            'start': self._cmd_start,
            'pause': self._cmd_pause,
            'resume': self._cmd_resume,
            'toggle': self._cmd_toggle,
            'config': self._cmd_config,
            'reset': self._cmd_reset,
            'stop': self._cmd_stop,
            'status': self._cmd_status,
            'list': self._cmd_status,
        }
        action = args[0]
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f'Unknown task action: {action}')
        return handler(args[1:])

    def _cmd_reset(self, args):
        pid, _, _ = self._resolve_target(args)
        task = self.tasks.reset_settings(pid, self.defaults)
        print(f'{GREEN}[RESET] PID {task.pid}{RESET}')

    @staticmethod
    def _parse_mode(value):
        modes = {
            'off': 0,
            'none': 0,
            'left': 1,
            'right': 2,
            'left-right': 3,
            'right-left': 4,
        }
        normalized = str(value).lower()
        if normalized in modes:
            return modes[normalized]
        mode = int(value)
        if mode not in range(5):
            raise ValueError('Mode must be off, left, right, left-right, or right-left')
        return mode

    @staticmethod
    def _parse_safety(value):
        normalized = str(value).lower()
        if normalized in {'strict', 'on', 'true'}:
            return True
        if normalized in {'off', 'none', 'false'}:
            return False
        raise ValueError('Safety must be strict or off')

    def _cmd_config(self, args):
        pid, _, consumed = self._resolve_target(args)
        values = args[consumed:]
        task = self.tasks.tasks.get(pid)
        if task is None:
            raise RuntimeError(f'No active task for PID {pid}')
        if values == ['default']:
            self.tasks.reset_settings(pid, self.defaults)
            print(f'{GREEN}[RESET] PID {pid}{RESET}')
            return
        options = self._parse_options(values)
        updates = {}
        effective_safety = task.settings.safety
        if '--safety' in options:
            effective_safety = self._parse_safety(options['--safety'])
            updates['safety'] = effective_safety
        if '--mode' in options:
            updates['click_mode'] = self._parse_mode(options['--mode'])
        if '--key' in options:
            key = options['--key']
            updates['key'] = 0 if key.lower() in {'none', 'off'} else key
        if '--delay' in options:
            delay = float(options['--delay'])
            if effective_safety and delay < self.defaults.delay:
                raise ValueError(f'Delay must be at least {self.defaults.delay} seconds')
            updates['delay'] = delay
        self.tasks.update_settings(pid, **updates)
        print(f'{GREEN}[UPDATED] PID {pid}{RESET}')

    def _cmd_status(self, _):
        tasks = self.tasks.status()
        if not tasks:
            print('No active tasks.')
            return
        rows = [
            [
                task.profile_name or '-',
                task.pid,
                task.state.value,
                task.settings.delay,
                click_mode_name(task.settings.click_mode),
            ]
            for task in tasks
        ]
        print(self.helper.format_table(['PROFILE', 'PID', 'STATE', 'DELAY', 'MODE'], rows))

    def _resolve_shell_path(self, raw_path):
        path = Path(os.path.expandvars(os.path.expanduser(raw_path)))
        if not path.is_absolute():
            path = self.working_dir / path
        return path.resolve()

    def _complete_paths(self, prefix, directories_only=False):
        separator_index = max(prefix.rfind('/'), prefix.rfind('\\'))
        has_separator = separator_index >= 0
        ends_with_separator = prefix.endswith(('/', '\\'))
        raw_directory = prefix if ends_with_separator else (
            prefix[:separator_index + 1] if has_separator else '.'
        )
        partial = '' if ends_with_separator else (
            prefix[separator_index + 1:] if has_separator else prefix
        )
        try:
            directory = self._resolve_shell_path(raw_directory)
            entries = directory.iterdir()
        except (FileNotFoundError, NotADirectoryError, OSError):
            return []

        display_separator = '\\' if '\\' in prefix else os.sep
        show_hidden = partial.startswith('.')
        candidates = []
        for entry in sorted(entries, key=lambda item: (not item.is_dir(), item.name.lower())):
            if not show_hidden and entry.name.startswith('.'):
                continue
            if directories_only and not entry.is_dir():
                continue
            if partial and not entry.name.lower().startswith(partial.lower()):
                continue
            suffix = display_separator if entry.is_dir() else ''
            if has_separator:
                candidates.append(f'{prefix[:separator_index + 1]}{entry.name}{suffix}')
            else:
                candidates.append(f'{entry.name}{suffix}')
        return candidates

    def _cmd_cd(self, args):
        if len(args) > 1:
            raise ValueError('Usage: !cd [path]')
        target = self._resolve_shell_path(args[0] if args else str(Path.home()))
        if not target.is_dir():
            raise FileNotFoundError(f'Not a directory: {target}')
        self.working_dir = target
        print(f'{GREEN}{self.working_dir}{RESET}')

    def _cmd_pwd(self, _):
        print(self.working_dir)

    def _cmd_ls(self, args):
        show_hidden = False
        path_args = []
        for arg in args:
            if arg == '-a':
                show_hidden = True
            else:
                path_args.append(arg)
        if len(path_args) > 1:
            raise ValueError('Usage: !ls [-a] [path]')

        target = self._resolve_shell_path(path_args[0] if path_args else '.')
        if not target.exists():
            raise FileNotFoundError(f'Path does not exist: {target}')
        if target.is_file():
            print(target.name)
            return

        rows = []
        for item in sorted(target.iterdir(), key=lambda entry: (entry.is_file(), entry.name.lower())):
            if not show_hidden and item.name.startswith('.'):
                continue
            kind = 'DIR' if item.is_dir() else 'FILE'
            rows.append([kind, item.name])
        if rows:
            print(self.helper.format_table(['TYPE', 'NAME'], rows))

    def _cmd_profile(self, args):
        if not args:
            raise ValueError('Use !profile create, list, show, edit, or delete')
        action = args[0]
        if action == 'list':
            rows = [[name, path] for name, path in self.targets.list().items()]
            if rows:
                print(self.helper.format_table(['NAME', 'EXECUTABLE'], rows))
            else:
                print('No profiles saved.')
            return

        if action in {'create', 'edit'}:
            profile_args = list(args[1:])
            name = profile_args.pop(0) if profile_args and not profile_args[0].startswith('-') else None
            options = self._parse_options(profile_args)
            name = name or options.get('--profile')
            path = options.get('--path')
            if not name or not path:
                raise ValueError(f'Use !profile {action} <name> --path <path>')
            resolved = self.targets.save(name, path, base_dir=self.working_dir)
            self._refresh_profile_completions()
            label = 'CREATED' if action == 'create' else 'UPDATED'
            print(f'{GREEN}[PROFILE {label}] {name} -> {resolved}{RESET}')
            return

        profile_args = list(args[1:])
        name = profile_args.pop(0) if profile_args and not profile_args[0].startswith('-') else None
        options = self._parse_options(profile_args)
        name = name or options.get('--profile')
        if not name:
            raise ValueError('Missing profile name')
        if action == 'show':
            print(f'{name}: {self.targets.show(name)}')
        elif action == 'delete':
            if self.targets.delete(name):
                self._refresh_profile_completions()
                print(f'{GREEN}[PROFILE DELETED] {name}{RESET}')
        else:
            raise ValueError(f'Unknown profile action: {action}')

    def _cmd_hotkey(self, args):
        if not args:
            raise ValueError('Use !hotkey list, create, edit, or delete')
        action = args[0]
        if action == 'list':
            rows = [
                [name, '+'.join(data['keys']), data['action']]
                for name, data in self.hotkeys.bindings.items()
            ]
            if rows:
                print(self.helper.format_table(['NAME', 'KEYS', 'ACTION'], rows))
            return
        if action in {'save', 'create'}:
            hotkey_args = list(args[1:])
            name = hotkey_args.pop(0) if hotkey_args and not hotkey_args[0].startswith('-') else None
            options = self._parse_options(hotkey_args)
            name = name or options.get('--profile') or options.get('--name')
            command = options.get('--action')
            if not name or not command:
                raise ValueError('Use !hotkey create <name> --action "<command>"')
            keys = self._parse_hotkey_keys(options['--keys']) if '--keys' in options else None
            if keys:
                self.hotkeys.save_binding(name, keys, command)
            else:
                keys = self.hotkeys.capture_binding(name, command)
            self._refresh_hotkey_completions()
            print(f"{GREEN}[SAVED] {'+'.join(sorted(keys))}{RESET}")
            return
        if action in {'mod', 'edit'}:
            hotkey_args = list(args[1:])
            name = hotkey_args.pop(0) if hotkey_args and not hotkey_args[0].startswith('-') else None
            options = self._parse_options(hotkey_args) if hotkey_args and hotkey_args[0] != 'rb' else {}
            name = name or options.get('--profile') or options.get('--name')
            if not name or name not in self.hotkeys.bindings:
                raise ValueError('Missing hotkey name')
            if 'rb' in hotkey_args:
                command = self.hotkeys.bindings[name]['action']
                keys = self.hotkeys.capture_binding(name, command)
                print(f"{GREEN}[UPDATED] {'+'.join(sorted(keys))}{RESET}")
            else:
                command = options.get('--action', self.hotkeys.bindings[name]['action'])
                keys = self._parse_hotkey_keys(options['--keys']) if '--keys' in options else self.hotkeys.bindings[name]['keys']
                self.hotkeys.save_binding(name, keys, command)
                print(f'{GREEN}[UPDATED] {name}{RESET}')
            return
        if action in {'del', 'delete'}:
            hotkey_args = list(args[1:])
            name = hotkey_args.pop(0) if hotkey_args and not hotkey_args[0].startswith('-') else None
            options = self._parse_options(hotkey_args)
            name = name or options.get('--profile') or options.get('--name')
            if not name:
                raise ValueError('Missing hotkey name')
            if self.hotkeys.delete_binding(name):
                self._refresh_hotkey_completions()
                print(f'{GREEN}[DELETED] {name}{RESET}')
            return
        raise ValueError(f'Unknown hotkey action: {action}')

    @staticmethod
    def _parse_hotkey_keys(raw_keys):
        aliases = {'control': 'ctrl', 'option': 'alt'}
        keys = [part.strip().lower() for part in raw_keys.split('+') if part.strip()]
        return [aliases.get(key, key) for key in keys]

    def _cmd_debug(self, args):
        if args:
            self.debug_mode = str_to_bool(args[0])
        else:
            self.debug_mode = not self.debug_mode
        print(f'Debug: {self.debug_mode}')

    def _cmd_help(self, args):
        self.helper.print_help(' '.join(args) if args else None)

    def run(self):
        self.hotkeys.start()
        try:
            while not self.tasks.global_stop.is_set():
                line = safe_prompt('>> ', session=self.prompt_session)
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
