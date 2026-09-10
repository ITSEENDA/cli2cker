from .base import InputBackend, WindowRef


class UnsupportedBackend(InputBackend):
    name = 'unsupported'

    def __init__(self, reason):
        self.reason = reason

    def _raise(self):
        raise RuntimeError(self.reason)

    def find_windows_by_pid(self, pid: int) -> list[WindowRef]:
        self._raise()

    def find_pids_by_executable(self, executable_path: str) -> list[int]:
        self._raise()

    def click(self, window: WindowRef, mode: int, x: int = 300, y: int = 300):
        self._raise()

    def press_key(self, window: WindowRef, key: int | str):
        self._raise()


class LinuxWaylandBackend(UnsupportedBackend):
    name = 'linux-wayland'

    def __init__(self):
        super().__init__(
            'Wayland blocks generic window lookup and synthetic input. '
            'Use an X11 session or a compositor-specific backend.'
        )
