from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowRef:
    native_id: int
    pid: int


class InputBackend(ABC):
    name = 'unknown'

    @abstractmethod
    def find_windows_by_pid(self, pid: int) -> list[WindowRef]:
        raise NotImplementedError

    @abstractmethod
    def find_pids_by_executable(self, executable_path: str) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def click(self, window: WindowRef, mode: int, x: int = 300, y: int = 300):
        raise NotImplementedError

    @abstractmethod
    def press_key(self, window: WindowRef, key: int | str):
        raise NotImplementedError

    def is_key_pressed(self, key: str):
        return None
