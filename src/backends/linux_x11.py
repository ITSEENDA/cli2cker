import os

from .base import InputBackend, WindowRef


class LinuxX11Backend(InputBackend):
    name = 'linux-x11'

    def __init__(self):
        try:
            from Xlib import X, XK, display
            from Xlib.ext import xtest
        except ImportError as exc:
            raise RuntimeError(
                'Linux X11 backend requires python-xlib.'
            ) from exc

        self.X = X
        self.XK = XK
        self.display = display.Display()
        self.xtest = xtest

    def _atom(self, name):
        return self.display.intern_atom(name)

    def _client_windows(self):
        root = self.display.screen().root
        prop = root.get_full_property(
            self._atom('_NET_CLIENT_LIST'),
            self.X.AnyPropertyType,
        )
        if not prop:
            return []
        return [self.display.create_resource_object('window', wid) for wid in prop.value]

    def find_windows_by_pid(self, pid: int) -> list[WindowRef]:
        result = []
        pid_atom = self._atom('_NET_WM_PID')
        for window in self._client_windows():
            prop = window.get_full_property(pid_atom, self.X.AnyPropertyType)
            if prop and int(prop.value[0]) == pid:
                result.append(WindowRef(window.id, pid))
        return result

    def find_pids_by_executable(self, executable_path: str) -> list[int]:
        expected = os.path.realpath(os.path.abspath(executable_path))
        pids = []
        for window in self._client_windows():
            prop = window.get_full_property(self._atom('_NET_WM_PID'), self.X.AnyPropertyType)
            if not prop:
                continue
            pid = int(prop.value[0])
            try:
                actual = os.path.realpath(f'/proc/{pid}/exe')
            except OSError:
                continue
            if actual == expected and pid not in pids:
                pids.append(pid)
        return pids

    def click(self, window: WindowRef, mode: int, x: int = 300, y: int = 300):
        del window, x, y
        buttons = {
            1: (1,),
            2: (3,),
            3: (1, 3),
            4: (3, 1),
        }.get(mode, ())
        for button in buttons:
            self.xtest.fake_input(self.display, self.X.ButtonPress, button)
            self.xtest.fake_input(self.display, self.X.ButtonRelease, button)
        self.display.sync()

    def press_key(self, window: WindowRef, key: int | str):
        del window
        if isinstance(key, int):
            keycode = key
        else:
            keycode = self.display.keysym_to_keycode(self.XK.string_to_keysym(key))
        if not keycode:
            raise ValueError(f'Unknown X11 key: {key!r}')
        self.xtest.fake_input(self.display, self.X.KeyPress, keycode)
        self.xtest.fake_input(self.display, self.X.KeyRelease, keycode)
        self.display.sync()
