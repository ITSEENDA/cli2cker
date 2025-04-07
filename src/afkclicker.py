import os
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

from utils import RED, RESET, get_key, GREEN


class AfkClicker:

    def __init__(self, mouse_btn=0, keyboard_key=0x0, delay=1, pid=-1, safety=True):
        self.stop_event = None
        self.process_thread_stop_event = None
        self.input_thread = None
        self.process_thread = None

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
        lParam = y << 15 | x
        try:
            match self.click_mode:
                case 0:
                    return
                case 1:
                    pycwnd.SendMessage(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                    pycwnd.SendMessage(win32con.WM_LBUTTONUP, 0, lParam)
                    pycwnd.UpdateWindow()
                case 2:
                    pycwnd.SendMessage(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
                    pycwnd.SendMessage(win32con.WM_RBUTTONUP, 0, lParam)
                    pycwnd.UpdateWindow()
                case 3:
                    pycwnd.SendMessage(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                    pycwnd.SendMessage(win32con.WM_LBUTTONUP, 0, lParam)
                    pycwnd.SendMessage(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
                    pycwnd.SendMessage(win32con.WM_RBUTTONUP, 0, lParam)
                    pycwnd.UpdateWindow()
                case 4:
                    pycwnd.SendMessage(win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
                    pycwnd.SendMessage(win32con.WM_RBUTTONUP, 0, lParam)
                    pycwnd.SendMessage(win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                    pycwnd.SendMessage(win32con.WM_LBUTTONUP, 0, lParam)
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
        PyCWnd = win32ui.CreateWindowFromHandle(hwnd)
        return PyCWnd

    def run(self):
        self.input_thread = threading.Thread(target=self.input_listener, daemon=True)
        self.stop_event = threading.Event()

        self.input_thread.start()
        self.input_thread.join()

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
            print('listening')
            try:
                msg = input().strip()
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
            '!start': lambda _: self.start(),
            '!stop': lambda _: self.stop(),
            '!help': lambda _: self.parser.print_help(),
            '!quit': lambda _: self.close_clicker(),
        }
        if commands.get(cmd) is not None:
            return commands.get(cmd)(args)

    def start(self):
        try:
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
        if self.process_thread_stop_event is not None:
            print(f'{GREEN}Stopping the process...{RESET}')
            self.process_thread_stop_event.set()

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
        self.stop_event.set()
