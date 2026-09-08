import json
import shlex
import traceback
from pathlib import Path
from builtins import staticmethod

from time import sleep
import threading
from concurrent.futures import ThreadPoolExecutor
import queue

from pynput import keyboard

from completer import CommandCompleter
from helper import ClickerHelper
from utils import *

saved_paths_path = Path(__file__).parent / 'data' / 'paths.json'
saved_hotkeys_path = Path(__file__).parent / 'data' / 'hotkeys.json'
default_clicker_settings = Path(__file__).parent / 'data' / 'defaults.json'


class AfkClicker(object):

    def __init__(self, base_thread_num=5,
                 click_mode=0,
                 key=0x0,
                 delay=0.25,
                 safety=True):

        (Path(__file__).parent / 'data').mkdir(parents=True, exist_ok=True)

        try:
            with open(default_clicker_settings, 'r') as f:
                self.defaults = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            try:
                defaults = {
                    'click_mode': click_mode,
                    'key': key,
                    'delay': delay,
                    'safety': safety,
                }
                with open(default_clicker_settings, 'w') as f:
                    json.dump(defaults, f, indent=4)
                self.defaults = defaults
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"{RED}An error occurred: {e}{RESET}")

        self.stop_event = None
        self.input_thread = None
        self.process_thread = None
        self.hotkey_thread = None
        self.hotkey_watchdog_thread = None

        self.execute_pool = ThreadPoolExecutor(base_thread_num)
        self.tasks = {}
        self.running_tasks = {}
        self.tasks_data = {}

        self._configure_commands()
        self.input_queue = queue.Queue()
        self.debug_mode = False

        try:
            with open(saved_hotkeys_path, 'r') as f:
                self.current_hotkeys = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.current_hotkeys = {}

        self.hotkey_lookup = {}
        for hotkey_name, data in self.current_hotkeys.items():
            key_set = frozenset(data['keys'])
            self.hotkey_lookup[key_set] = data['action']
        self.pressed_keys = set()
        self.hotkey_toggle = False
        self.key_triggered = False
        self.hotkey_state_lock = threading.RLock()

    def _configure_commands(self):
        self.helper = ClickerHelper(
            prog='afk-clicker',
            description='Interactive AFK clicker commands',
        )
        self.helper.add_command(
            '!start',
            'Start a clicker task for a process.',
            options=['-p', '-n'],
            usage='!start -p <pid> | !start -n <saved-path>',
        )
        self.helper.add_command(
            '!stop',
            'Stop a task, or stop all tasks.',
            options=['-p', '-n', 'all'],
            usage='!stop -p <pid> | !stop -n <saved-path> | !stop all',
        )
        self.helper.add_command(
            '!toggle',
            'Pause or resume a task.',
            options=['-p', '-n'],
            usage='!toggle -p <pid> | !toggle -n <saved-path>',
        )
        self.helper.add_command(
            '!set',
            'Change one or more settings for a running task.',
            options=['-m', '-k', '-d', '-s', 'default'],
            usage='!set <pid> [-m mode] [-k key] [-d seconds] [-s true|false]',
        )
        self.helper.add_command(
            '!path',
            'Save, delete, or create a built-in process path.',
            subcommands={
                'save': ['-n', '-p'],
                'del': ['-n'],
                'def': ['mc'],
            },
            usage='!path <save|del|def> ...',
        )
        self.helper.add_command(
            '!hotkey',
            'Create, modify, or delete a saved hotkey.',
            subcommands={
                'save': ['-n', '-a'],
                'mod': ['-a', 'rb'],
                'del': ['-n'],
            },
            usage='!hotkey <save|mod|del> ...',
        )
        self.helper.add_command(
            '!debug',
            'Toggle debug output.',
            options=['true', 'false'],
            usage='!debug [true|false]',
        )
        self.helper.add_command('!clear', 'Clear the terminal.')
        self.helper.add_command('!help', 'Show command help.', usage='!help [command]')
        self.helper.add_command('!quit', 'Exit the clicker.')
        self.helper.commands['!help'].options = tuple(self.helper.commands)

        self.command_handlers = {
            '!set': self.handle_set_cmd,
            '!path': self.handle_save_process_path,
            '!hotkey': self.handle_set_hotkey,
            '!start': self.start,
            '!stop': self.stop,
            '!toggle': self.toggle,
            '!debug': self.toggle_debug,
            '!clear': lambda _: clear_terminal(),
            '!help': lambda args: self.helper.print_help(args),
            '!quit': lambda _: self.close_clicker(),
        }
        self.completer = CommandCompleter(self.helper.completion_map)

    def _create_hotkey_listener(self):
        return keyboard.Listener(
            on_press=self.on_hotkey_press,
            on_release=self.on_hotkey_release,
        )

    def _restart_hotkey_listener(self):
        with self.hotkey_state_lock:
            if self.stop_event is None or self.stop_event.is_set():
                return
            self.pressed_keys.clear()
            self.key_triggered = False
            listener = self._create_hotkey_listener()
            self.hotkey_thread = listener
        listener.start()

    def _watch_hotkey_listener(self):
        while self.stop_event is not None and not self.stop_event.wait(1):
            listener = self.hotkey_thread
            if listener is None or listener.is_alive():
                continue
            try:
                self._restart_hotkey_listener()
            except Exception as e:
                print(f"{RED}Hotkey listener restart failed: {e}{RESET}")

    def mouse_click(self, pycwnd, pid):
        if pid not in self.tasks_data:
            return
        click_mode = self.tasks_data[pid]['click_mode']
        if not click_mode:
            return
        x = 300
        y = 300
        l_param = y << 15 | x
        try:
            match click_mode:
                case 0:
                    return
                case 1:
                    pycwnd.SendMessage(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, l_param)
                    pycwnd.SendMessage(win32con.WM_LBUTTONUP, 0, l_param)
                    pycwnd.UpdateWindow()
                case 2:
                    pycwnd.SendMessage(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, l_param)
                    pycwnd.SendMessage(win32con.WM_RBUTTONUP, 0, l_param)
                    pycwnd.UpdateWindow()
                case 3:
                    pycwnd.SendMessage(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, l_param)
                    pycwnd.SendMessage(win32con.WM_LBUTTONUP, 0, l_param)
                    pycwnd.SendMessage(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, l_param)
                    pycwnd.SendMessage(win32con.WM_RBUTTONUP, 0, l_param)
                    pycwnd.UpdateWindow()
                case 4:
                    pycwnd.SendMessage(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, l_param)
                    pycwnd.SendMessage(win32con.WM_RBUTTONUP, 0, l_param)
                    pycwnd.SendMessage(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, l_param)
                    pycwnd.SendMessage(win32con.WM_LBUTTONUP, 0, l_param)
                    pycwnd.UpdateWindow()
                case _:
                    raise ValueError("An error occurred: Invalid click mode")
        except Exception as e:
            print(f"{RED}An error occurred: {e}. (If the process is still running try Enter){RESET}")

    def keystroke(self, hwnd, pid):
        if pid not in self.tasks_data:
            return
        keyboard_key = self.tasks_data[pid]['key']
        if not keyboard_key or keyboard_key == 0:
            return
        press_key(hwnd, keyboard_key)

    def run(self):
        self.input_thread = threading.Thread(target=self.input_listener, daemon=True)
        self.stop_event = threading.Event()
        self.hotkey_thread = self._create_hotkey_listener()
        self.hotkey_watchdog_thread = threading.Thread(
            target=self._watch_hotkey_listener,
            daemon=True,
        )

        self.hotkey_thread.start()
        self.hotkey_watchdog_thread.start()
        self.input_thread.start()
        try:
            self.input_thread.join()
        except KeyboardInterrupt:
            print(f"{YELLOW}Stopping clicker...{RESET}")
            self.close_clicker()

    def process_input(self):
        try:
            if not self.input_queue.empty():
                msg = self.input_queue.get_nowait()
                tokens = str(msg).split()
                if len(tokens) >= 1:
                    cmd = tokens.pop(0)
                    args = ' '.join(tokens)
                    self.check_cmd(cmd, args)
                    return
        except queue.Empty:
            pass

    def input_listener(self):
        while not self.stop_event.is_set():
            try:
                msg = safe_prompt('>> ', completer=self.completer)
                self.input_queue.put(msg)
                self.process_input()
            except EOFError:
                self.close_clicker()
                break
            except KeyboardInterrupt | queue.Empty | ValueError as e:
                print(f"{RED}An error occurred: {e}{RESET}")
                self.close_clicker()
                break

    def check_cmd(self, cmd: str, args: str):
        handler = self.command_handlers.get(cmd)
        if handler is not None:
            return handler(args)

    def start(self, args):
        try:
            pid = self.get_pid_key_from_args(args)
            if pid in self.tasks:
                print(f"Task with pid '{pid}' is already running.")
                return

            if pid not in self.tasks_data:
                self.tasks_data[pid] = self.defaults
            self.running_tasks[pid] = False
            stop_event = threading.Event()

            def handle_auto():
                hwnds = get_hwnds_by_pid(pid)
                if not hwnds:
                    raise Exception(f"No window handle found for PID {pid}")
                hwndMain = hwnds[0]
                if hwndMain == 0 or hwndMain is None:
                    raise Exception("Invalid handler, please check PID or process name")
                pycwnd = make_pycwnd(hwndMain)
                while not stop_event.is_set() and not self.stop_event.is_set():
                    if not self.running_tasks[pid]:
                        sleep(0.1)
                        continue
                    delay = float(self.tasks_data[pid]['delay'])
                    self.mouse_click(pycwnd, pid)
                    self.keystroke(hwndMain, pid)
                    sleep(delay)

            print(f'{GREEN}Running auto clicker on process with pid {pid}{RESET}')
            process_thread = self.execute_pool.submit(handle_auto)
            self.tasks[pid] = (process_thread, stop_event)
            self.running_tasks[pid] = True
            if self.debug_mode:
                print(self.tasks)
                print(self.running_tasks)
                print(self.tasks_data)
        except Exception as e:
            traceback.print_exc()
            print(f"{RED}An error occurred: {e}{RESET}")

    def stop(self, args):
        try:
            if args.strip() == 'all':
                for pid in list(self.tasks):
                    self.stop(f'-p {pid}')
                return
            pid = self.get_pid_key_from_args(args)
            if pid not in self.tasks:
                return
            task, stop_event = self.tasks[pid]
            stop_event.set()
            task.cancel()
            print("Task keys:", self.tasks.keys())
            print("Trying to stop:", pid)
            del self.tasks[pid]
            del self.tasks_data[pid]
            del self.running_tasks[pid]
            print(f'\n{GREEN}Stopping the process...{RESET}')
            if self.debug_mode:
                print(self.tasks)
                print(self.running_tasks)
                print(self.tasks_data)
        except Exception as e:
            print(f"{RED}An error occurred: {e}{RESET}")

    def toggle(self, args):
        try:
            pid = self.get_pid_key_from_args(args)
            if pid not in self.tasks:
                self.start(args)
            else:
                self.running_tasks[pid] = not self.running_tasks[pid]
            if self.debug_mode:
                print(self.running_tasks)
        except Exception as e:
            print(f"{RED}An error occurred: {e}{RESET}")

    def toggle_debug(self, args=''):
        value = args.strip().lower()
        if value in {'true', 'false'}:
            self.debug_mode = value == 'true'
        else:
            self.debug_mode = not self.debug_mode

    @staticmethod
    def get_pid_key_from_args(args):
        tokens = args.split()
        arg = tokens.pop(0)
        if arg == '-n':
            path_name = tokens.pop(0)
            if not os.path.exists(saved_paths_path):
                raise IOError(f"{RED}\"Saved paths\" file has not been initialized{RESET}")
            with open(saved_paths_path, 'r') as f:
                paths = json.load(f)
                if path_name not in paths:
                    raise IOError(f"{RED}No path found with path key {path_name}{RESET}")
                path = paths[path_name]
                pid = get_pid_from_exe_path(path)
            if pid == -1:
                raise IOError(f"{RED}No process found with path {path}{RESET}")
        elif arg == '-p':
            try:
                pid = int(tokens.pop(0))
            except Exception as e:
                raise ValueError(e)
        return pid

    @staticmethod
    def handle_save_process_path(args: str):
        tokens = args.split()
        if len(tokens) > 1:
            sub_cmd = tokens.pop(0)
            match sub_cmd:
                case 'save':
                    key = tokens.pop(0)
                    with open(saved_paths_path, 'w') as f:
                        pass
                    pass
                case 'del':
                    pass
                case 'def':
                    sub_args = tokens.pop(0)
                    match sub_args:
                        case 'mc':
                            path_data = {}
                            if os.path.exists(saved_paths_path):
                                with open(saved_paths_path, 'r') as f:
                                    path_data = json.load(f)
                            appdata_path = os.environ.get('APPDATA')
                            minecraft_path = '.minecraft\\runtime\\java-runtime-gamma\\windows\\java-runtime-gamma' \
                                             '\\bin\\javaw.exe'
                            key = 'mc'
                            path_data[key] = os.path.join(appdata_path, minecraft_path)
                            with open(saved_paths_path, 'w') as f:
                                json.dump(path_data, f, indent=4)
                        case _:
                            pass

    def handle_set_hotkey(self, args):
        tokens = shlex.split(args)
        option = tokens.pop(0)

        match option:
            case 'save':
                hotkey_name = ''
                hotkey_action = ''

                while len(tokens) > 0:
                    key = tokens.pop(0)
                    if key == '-n' and not hotkey_name:
                        hotkey_name = tokens.pop(0)
                    elif key == '-a' and not hotkey_action:
                        hotkey_action = tokens.pop(0)
                    if hotkey_name and hotkey_action:
                        break

                print(f"{YELLOW}Reassign your hotkey. Press a key or a combo...{RESET}")
                temp_keys = set()
                assigned = [False]

                def on_press(key):
                    norm_key = normalize_key(key)
                    if norm_key:
                        temp_keys.add(norm_key)

                def on_release(key):
                    if not assigned[0] and len(temp_keys) > 0:
                        assigned[0] = True
                        if hotkey_name in self.current_hotkeys:
                            data = self.current_hotkeys[hotkey_name]
                            lookup_key = frozenset(data['keys'])
                            if lookup_key in self.hotkey_lookup:
                                del self.hotkey_lookup[lookup_key]
                            del self.current_hotkeys[hotkey_name]
                        data = {
                            'keys': sorted(temp_keys),
                            'action': hotkey_action,
                        }
                        self.current_hotkeys[hotkey_name] = data
                        lookup_key = frozenset(data['keys'])
                        self.hotkey_lookup[lookup_key] = data['action']

                        print(f"{GREEN}New hotkey set: {'+'.join(sorted(temp_keys))}{RESET}")
                        with open(saved_hotkeys_path, 'w') as f:
                            json.dump(self.current_hotkeys, f, indent=4)
                        return False

                with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                    listener.join()
            case 'mod':
                hotkey_name = tokens.pop(0)
                if not hotkey_name or hotkey_name not in self.current_hotkeys:
                    return
                while len(tokens) > 0:
                    arg = tokens.pop(0)
                    match arg:
                        case '-a':
                            if len(tokens) > 0:
                                new_action = tokens.pop(0)
                                self.current_hotkeys[hotkey_name]['action'] = new_action
                                with open(saved_hotkeys_path, 'w') as f:
                                    json.dump(self.current_hotkeys, f, indent=4)
                                return
                        case 'rb':
                            print(f"{YELLOW}Reassign your hotkey. Press a key or a combo...{RESET}")
                            temp_keys = set()
                            assigned = [False]

                            def on_press(key):
                                norm_key = normalize_key(key)
                                if norm_key:
                                    temp_keys.add(norm_key)

                            def on_release(key):
                                if not assigned[0] and len(temp_keys) > 0:
                                    assigned[0] = True
                                    if hotkey_name in self.current_hotkeys:
                                        data = self.current_hotkeys[hotkey_name]
                                        lookup_key = frozenset(data['keys'])
                                        if lookup_key in self.hotkey_lookup:
                                            del self.hotkey_lookup[lookup_key]
                                    self.current_hotkeys[hotkey_name]['keys'] = sorted(temp_keys)
                                    lookup_key = frozenset(self.current_hotkeys[hotkey_name]['keys'])
                                    self.hotkey_lookup[lookup_key] = self.current_hotkeys[hotkey_name]['action']

                                    print(f"{GREEN}New hotkey set: {'+'.join(sorted(temp_keys))}{RESET}")
                                    with open(saved_hotkeys_path, 'w') as f:
                                        json.dump(self.current_hotkeys, f, indent=4)
                                    return False

                            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                                listener.join()
                        case _:
                            pass
            case 'del':
                key = tokens.pop(0)
                if key == '-n':
                    hotkey_name = tokens.pop(0)
                    if hotkey_name in self.current_hotkeys:
                        data = self.current_hotkeys[hotkey_name]
                        lookup_key = frozenset(data['keys'])
                        if lookup_key in self.hotkey_lookup:
                            del self.hotkey_lookup[lookup_key]
                        del self.current_hotkeys[hotkey_name]
                    with open(saved_hotkeys_path, 'w') as f:
                        json.dump(self.current_hotkeys, f, indent=4)
            case _:
                pass

    def on_hotkey_press(self, key):
        try:
            normalized_key = normalize_key(key)
            if not normalized_key:
                return

            action = None
            with self.hotkey_state_lock:
                self.pressed_keys.add(normalized_key)
                lookup_key = frozenset(self.pressed_keys)
                if lookup_key in self.hotkey_lookup and not self.key_triggered:
                    self.key_triggered = True
                    action = self.hotkey_lookup[lookup_key]

            if action is not None:
                print(f"{GREEN}Triggered action: {action}{RESET}")
                tokens = str(action).split()
                if tokens:
                    cmd = tokens.pop(0)
                    args = ' '.join(tokens)
                    self.check_cmd(cmd, args)
        except Exception as e:
            # Exceptions in pynput callbacks stop the listener thread.
            print(f"{RED}Hotkey callback failed: {e}{RESET}")
            traceback.print_exc()

    def on_hotkey_release(self, key):
        try:
            normalized_key = normalize_key(key)
            if not normalized_key:
                return
            with self.hotkey_state_lock:
                self.pressed_keys.discard(normalized_key)
                if not self.pressed_keys:
                    self.key_triggered = False
        except Exception as e:
            print(f"{RED}Hotkey release callback failed: {e}{RESET}")
            traceback.print_exc()

    def handle_set_cmd(self, args):
        try:
            args = args.split()
            if len(args) == 0:
                return
            pid = int(args.pop(0))
            if not pid or pid not in self.tasks or pid not in self.running_tasks or pid not in self.tasks_data:
                return
            if self.debug_mode:
                print(self.tasks)
                print(self.running_tasks)
                print(self.tasks_data)
            while len(args) > 0:
                key = args.pop(0)
                value = args.pop(0)

                if key == 'default':
                    self.tasks_data[pid] = self.defaults
                else:
                    match key:
                        case '-m':
                            self.tasks_data[pid]['click_mode'] = int(value)
                        case '-d':
                            try:
                                delay = float(value)
                                safety = self.tasks_data[pid]['safety']
                                if safety and float(self.tasks_data[pid]['delay']) >= self.defaults['delay']:
                                    self.tasks_data[pid]['delay'] = delay
                                else:
                                    raise ValueError(
                                        "Delay per triggers should be greater or equals to 0.5 for safety")
                            except Exception as e:
                                print(f"{RED}{e}{RESET}")

                        case '-k':
                            self.tasks_data[pid]['key'] = value
                        case '-s':
                            safety = str_to_bool(value)
                            self.tasks_data[pid]['safety'] = safety
                            if safety and float(self.tasks_data[pid]['delay']) < self.defaults['delay']:
                                self.tasks_data[pid]['delay'] = self.defaults['delay']
                        case _:
                            pass
            if self.debug_mode:
                print(self.tasks_data[pid])
        except Exception as e:
            traceback.print_exc()
            print(f"{RED}An error occurred: {e}{RESET}")
        sleep(1)

    def close_clicker(self):
        if self.stop_event:
            self.stop_event.set()
        if self.hotkey_thread:
            self.hotkey_thread.stop()
        self.execute_pool.shutdown()
        os._exit(0)
