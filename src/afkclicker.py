import json
import os
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter, Completion
from builtins import staticmethod

import win32gui
import win32con
import win32api
import win32process
import win32ui
from time import sleep
from argparse import ArgumentParser
import threading
import queue
from pynput import keyboard

from command_completer import CommandCompleter
from utils import *


class AfkClicker(object):

    def __init__(self,
                 mouse_btn=0,
                 keyboard_key=0x0,
                 delay=1,
                 pid=-1,
                 safety=True):
        self.stop_event = None
        self.running = False
        self.process_thread_stop_event = None
        self.input_thread = None
        self.process_thread = None
        self.hotkey_thread = None

        # self.helper = ClickerHelper()
        self.parser = ArgumentParser()
        self.parser.add_argument(
            "-m",
            "--mouse",
            type=int,
            help="0 or empty disable, 1 for left mouse click, 2 for right mouse click, 3 for both (with L first then "
                 "R), 4 for both (with R first then L)."
        )
        self.parser.add_argument("-k", "--key", help="Character value for keyboard input, 0 for disable.", default=0x0)
        self.parser.add_argument("-p", "--pid", type=int, help="Target program PID, must be an integer")
        self.parser.add_argument("-d", "--delay", type=float, help="Delay per triggers (in seconds)")
        self.parser.add_argument("-s", "--safety", type=bool, help="Ignore safety constraints or not", default=True)

        self.completer = CommandCompleter({
            '!start': [],
            '!stop': [],
            '!set': ['-p', '-m', '-k', '-d', '-s', 'default'],
            '!save': ['default tlauncher'],
            '!key': [],
            '!help': [],
            '!quit': []
        })

        self.keyboard_key = keyboard_key
        self.click_mode = mouse_btn
        self.input_queue = queue.Queue()
        self.safety = safety
        self.pid = pid

        if (self.safety and delay >= 0.5) or not self.safety:
            self.delay = delay
        else:
            raise ValueError(
                f"{RED}An error occurred: Delay per triggers should be greater or equals to 0.5 for safety{RESET}")

        filepath = 'hotkey.json'
        try:
            with open(filepath, 'r') as f:
                self.current_hotkey = set(json.load(f))
            # print(f"[LOADED] Hotkey loaded from {filepath}: {' + '.join(sorted(self.current_hotkey))}")
        except (FileNotFoundError, json.JSONDecodeError):
            self.current_hotkey = {keyboard.Key.ctrl_l, keyboard.Key.shift, keyboard.KeyCode(char='`')}

        self.pressed_keys = set()
        self.hotkey_toggle = False
        self.key_triggered = False

    def get_hwnds_by_pid(self):
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == self.pid:
                    hwnds.append(hwnd)
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        return hwnds

    # @staticmethod
    # def get_hwnds_by_name(name):
    #     hwnd = win32gui.FindWindow(None, name)
    #     if hwnd is None or hwnd == 0:
    #         hwnd = win32gui.FindWindow(name, None)
    #
    #     return hwnd

    @staticmethod
    def get_child_hwnd(hwnd):
        return win32gui.GetWindow(hwnd, win32con.GW_CHILD)

    def mouse_click(self, pycwnd):
        x = 300
        y = 300
        l_param = y << 15 | x
        try:
            match self.click_mode:
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
            self.close_clicker()

    def keystroke(self, hwnd):
        win32api.PostMessage(
            self.get_child_hwnd(hwnd), win32con.WM_CHAR, self.keyboard_key, 0)

    @staticmethod
    def make_pycwnd(hwnd):
        py_c_wnd = win32ui.CreateWindowFromHandle(hwnd)
        return py_c_wnd

    def run(self):
        self.input_thread = threading.Thread(target=self.input_listener, daemon=True)
        self.stop_event = threading.Event()
        self.hotkey_thread = keyboard.Listener(on_press=self.on_hotkey_press, on_release=self.on_hotkey_release)

        self.hotkey_thread.start()
        self.input_thread.start()
        self.input_thread.join()
        # self.hotkey_thread.join()

    def handle_auto(self, hwndMain):
        pycwnd = self.make_pycwnd(hwndMain)
        while not self.stop_event.is_set() and not self.process_thread_stop_event.is_set():
            if self.click_mode != 0:
                self.mouse_click(pycwnd)
            if self.keyboard_key != 0:
                self.keystroke(hwndMain)
            sleep(self.delay)

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
                msg = safe_prompt('>> ', completer=self.completer).replace('>> ', '').strip()
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
        commands = {
            '!set': self.handle_set_cmd,
            '!save': self.handle_save_process_path,
            '!key': self.handle_set_key,
            '!start': lambda _: self.start(),
            '!stop': lambda _: self.stop(),
            '!help': lambda _: self.parser.print_help(),
            '!quit': lambda _: self.close_clicker(),
        }
        if commands.get(cmd) is not None:
            return commands.get(cmd)(args)

    def start(self):
        try:
            if self.running:
                return
            self.running = True
            path = self.get_saved_process_path()
            self.get_pid_from_exe_path(path)
            if self.pid == -1:
                raise IOError(f"No process found with path {path}")
            hwndMain = self.get_hwnds_by_pid()[0]
            if hwndMain == 0 or hwndMain is None:
                raise Exception("Invalid handler, please check PID or process name")
            self.process_thread_stop_event = threading.Event()
            self.process_thread = threading.Thread(target=self.handle_auto, daemon=True, args=(hwndMain,))
            self.process_thread.start()
        except Exception as e:
            print(f"{RED}An error occurred: {e}{RESET}")

    def stop(self):
        if not self.running:
            return
        if self.process_thread_stop_event is not None:
            print(f'\n{GREEN}Stopping the process...{RESET}')
            self.process_thread_stop_event.set()
            self.running = False

    @staticmethod
    def handle_save_process_path(args: str):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = 'saved_path.txt'
        file_path = os.path.join(current_dir, filename)
        with open(file_path, 'w') as f:
            tokens = args.split()
            if len(tokens) > 1:
                sub_cmd = tokens.pop(0)
                sub_args = tokens.pop(0)
                if sub_cmd and sub_cmd.strip() == 'default':
                    appdata_path = os.environ.get('APPDATA')
                    match sub_args:
                        case 'tlauncher':
                            minecraft_path = '.minecraft\\runtime\\java-runtime-gamma\\windows\\java-runtime-gamma' \
                                             '\\bin\\javaw.exe'
                            f.write(os.path.join(appdata_path, minecraft_path))
                        case _:
                            return
                return
            f.write(args.replace('"', ''))
        print(f"Saved path to {filename}")

    @staticmethod
    def get_saved_process_path():
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = 'saved_path.txt'
        file_path = os.path.join(current_dir, filename)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return f.read().strip()
        return None

    def handle_set_key(self, args):
        self.reassign_hotkey()

    def on_hotkey_press(self, key):
        key = normalize_key(key)
        if not key:
            return
        self.pressed_keys.add(key)
        if self.current_hotkey.issubset(self.pressed_keys):
            if not self.key_triggered:
                self.key_triggered = True
                if self.running:
                    self.stop()
                else:
                    self.start()

    def on_hotkey_release(self, key):
        norm_key = normalize_key(key)
        if not norm_key:
            return
        self.pressed_keys.clear()
        if norm_key in self.current_hotkey:
            self.key_triggered = False

    def reassign_hotkey(self):
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
                self.current_hotkey.clear()
                self.current_hotkey.update(temp_keys)
                readable = []
                for k in self.current_hotkey:
                    if is_key(k):
                        readable.append(str(k).replace("Key.", "").lower())
                    else:
                        readable.append(str(k).lower())

                print(f"{GREEN}New hotkey set: {'+'.join(sorted(readable))}{RESET}")
                filepath = 'hotkey.json'
                with open(filepath, 'w') as f:
                    json.dump(sorted(self.current_hotkey), f)
                # print(f"[SAVED] Hotkey saved to {filepath}")
                return False

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    def handle_set_cmd(self, args):
        try:
            args = args.split()
            while len(args) > 0:
                key = args.pop(0)
                value = args.pop(0)

                if key == 'default':
                    self.get_pid_from_exe_path(self.get_saved_process_path())
                    self.click_mode = 1
                    self.keyboard_key = get_key(0)
                    self.delay = 0.5
                    self.safety = True
                else:
                    match key:
                        case '-p':
                            self.pid = int(value)
                        case '-m':
                            self.click_mode = int(value)
                        case '-d':
                            try:
                                delay = float(value)
                                if (self.safety and delay >= 0.5) or not self.safety:
                                    self.delay = delay
                                else:
                                    raise ValueError(
                                        "Delay per triggers should be greater or equals to 0.5 for safety")
                            except Exception as e:
                                print(f"{RED}{e}{RESET}")

                        case '-k':
                            self.keyboard_key = get_key(value)
                        case '-s':
                            self.safety = False if value.lower() == 'false' else True
                            if self.safety and self.delay < 0.5:
                                self.delay = 0.5
                        case _:
                            pass
        except Exception as e:
            print(f"{RED}An An error occurred: {e}{RESET}")
        sleep(1)

    @staticmethod
    def get_process_path(pid):
        try:
            h_process = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
            return win32process.GetModuleFileNameEx(h_process, 0)
        except Exception:
            return None

    def get_pid_from_exe_path(self, exe_path):
        exe_path = os.path.normcase(os.path.normpath(exe_path))

        def callback(hwnd, hwnds):
            try:
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                process_path = self.get_process_path(pid)
                if process_path and os.path.normcase(os.path.normpath(process_path)) == exe_path:
                    hwnds.append(pid)
            except Exception:
                pass
            return True

        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        self.pid = hwnds[0] if hwnds else -1

    def close_clicker(self):
        if self.stop_event:
            self.stop_event.set()
        if self.process_thread_stop_event:
            self.process_thread_stop_event.set()
        if self.hotkey_thread:
            self.hotkey_thread.stop()
        os._exit(0)
