import os

import win32api
import win32con
import win32gui
import win32process

from .base import InputBackend, WindowRef


class WindowsBackend(InputBackend):
    name = 'windows'

    def find_windows_by_pid(self, pid: int) -> list[WindowRef]:
        windows = []

        def callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    result.append(WindowRef(hwnd, pid))
            return True

        win32gui.EnumWindows(callback, windows)
        return windows

    def find_pids_by_executable(self, executable_path: str) -> list[int]:
        expected = os.path.normcase(os.path.normpath(executable_path))
        pids = []

        def callback(hwnd, result):
            try:
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                process_path = self._get_process_path(pid)
                if process_path:
                    actual = os.path.normcase(os.path.normpath(process_path))
                    if actual == expected and pid not in result:
                        result.append(pid)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(callback, pids)
        return pids

    @staticmethod
    def _get_process_path(pid: int):
        process_handle = None
        try:
            process_handle = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
            return win32process.GetModuleFileNameEx(process_handle, 0)
        except Exception:
            return None
        finally:
            if process_handle:
                win32api.CloseHandle(process_handle)

    def click(self, window: WindowRef, mode: int, x: int = 300, y: int = 300):
        l_param = y << 15 | x
        messages = {
            1: (
                (win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON),
                (win32con.WM_LBUTTONUP, 0),
            ),
            2: (
                (win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON),
                (win32con.WM_RBUTTONUP, 0),
            ),
            3: (
                (win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON),
                (win32con.WM_LBUTTONUP, 0),
                (win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON),
                (win32con.WM_RBUTTONUP, 0),
            ),
            4: (
                (win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON),
                (win32con.WM_RBUTTONUP, 0),
                (win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON),
                (win32con.WM_LBUTTONUP, 0),
            ),
        }
        for message, w_param in messages.get(mode, ()):
            win32gui.PostMessage(window.native_id, message, w_param, l_param)

    def press_key(self, window: WindowRef, key: int | str):
        child_hwnd = win32gui.GetWindow(window.native_id, win32con.GW_CHILD)
        if isinstance(key, str):
            key = {
                'space': ' ',
                'enter': '\r',
                'tab': '\t',
                'backspace': '\b',
            }.get(key.lower(), key)
            if len(key) != 1:
                raise ValueError(f'Windows backend expects one character, got {key!r}')
            key = ord(key)
        win32gui.PostMessage(child_hwnd or window.native_id, win32con.WM_CHAR, key, 0)

    def is_key_pressed(self, key: str):
        virtual_keys = {
            'ctrl': 0x11,
            'shift': 0x10,
            'alt': 0x12,
            'tab': 0x09,
            'space': 0x20,
            'enter': 0x0D,
            'esc': 0x1B,
            'backspace': 0x08,
            'left': 0x25,
            'up': 0x26,
            'right': 0x27,
            'down': 0x28,
        }
        virtual_key = virtual_keys.get(key)
        if virtual_key is None and len(key) == 1:
            scan_code = win32api.VkKeyScan(key)
            if scan_code != -1:
                virtual_key = scan_code & 0xFF
        if virtual_key is None:
            return None
        return bool(win32api.GetAsyncKeyState(virtual_key) & 0x8000)
