import os

import win32api
import win32con
import win32gui
import win32process
import win32ui
from prompt_toolkit import prompt
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.output.win32 import NoConsoleScreenBufferError
from pynput.keyboard import KeyCode, Key

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def get_key(key):
    return int(hex(ord(key)), 16) if key != 0 else key


def normalize_key(key):
    if isinstance(key, KeyCode):
        if key.char:
            ch = key.char
            if ord(ch) < 32:
                decoded = chr(ord(ch) + 96)
                return decoded.lower()
            return ch.lower()
    elif isinstance(key, Key):
        # Normalize modifier keys
        if key in [Key.ctrl, Key.ctrl_l, Key.ctrl_r]:
            return 'ctrl'
        if key in [Key.shift, Key.shift_l, Key.shift_r]:
            return 'shift'
        if key in [Key.alt, Key.alt_l, Key.alt_r]:
            return 'alt'
        return str(key).replace('Key.', '')
    return None


def is_key(key):
    return isinstance(key, Key)


def safe_prompt(prompt_text, completer=None):
    try:
        return prompt(
            prompt_text,
            completer=completer,
            auto_suggest=AutoSuggestFromHistory()
        ).replace(prompt_text, '').strip()
    except NoConsoleScreenBufferError:
        return input(prompt_text).replace(prompt_text, '').strip()


def get_hwnds_by_name(name):
    hwnd = win32gui.FindWindow(None, name)
    if hwnd is None or hwnd == 0:
        hwnd = win32gui.FindWindow(name, None)

    return hwnd


def get_process_path(pid):
    try:
        h_process = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
        return win32process.GetModuleFileNameEx(h_process, 0)
    except Exception:
        return None


def get_hwnds_by_pid(pid):
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid:
                hwnds.append(hwnd)
        return True

    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds


def get_child_hwnd(hwnd):
    return win32gui.GetWindow(hwnd, win32con.GW_CHILD)


def make_pycwnd(hwnd):
    py_c_wnd = win32ui.CreateWindowFromHandle(hwnd)
    return py_c_wnd


def get_pid_from_exe_path(exe_path):
    exe_path = os.path.normcase(os.path.normpath(exe_path))

    def callback(hwnd, hwnds):
        try:
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            process_path = get_process_path(pid)
            if process_path and os.path.normcase(os.path.normpath(process_path)) == exe_path:
                hwnds.append(pid)
        except Exception:
            pass
        return True

    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds[0] if hwnds else -1


def press_key(hwnd, key):
    win32api.PostMessage(get_child_hwnd(hwnd), win32con.WM_CHAR, key, 0)


def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


def str_to_bool(value):
    return False if value.lower() == 'false' else True
