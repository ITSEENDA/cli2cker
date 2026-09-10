from dataclasses import dataclass, field
from enum import Enum


@dataclass
class ClickerSettings:
    click_mode: int = 0
    key: int | str = 0
    delay: float = 0.25
    safety: bool = True

    def copy(self):
        return ClickerSettings(
            click_mode=self.click_mode,
            key=self.key,
            delay=self.delay,
            safety=self.safety,
        )

    @classmethod
    def from_mapping(cls, data):
        safety = data.get('safety', True)
        if isinstance(safety, str):
            safety = safety.strip().lower() == 'true'
        return cls(
            click_mode=int(data.get('click_mode', 0)),
            key=data.get('key', 0),
            delay=float(data.get('delay', 0.25)),
            safety=safety,
        )

    def to_mapping(self):
        return {
            'click_mode': self.click_mode,
            'key': self.key,
            'delay': self.delay,
            'safety': self.safety,
        }


@dataclass(frozen=True)
class TargetProfile:
    name: str
    executable_path: str


class TaskState(str, Enum):
    STARTING = 'starting'
    RUNNING = 'running'
    PAUSED = 'paused'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    FAILED = 'failed'


def click_mode_name(mode):
    return {
        0: 'off',
        1: 'left',
        2: 'right',
        3: 'left-right',
        4: 'right-left',
    }.get(mode, str(mode))


@dataclass
class ClickerTask:
    pid: int
    settings: ClickerSettings
    window: object
    profile_name: str | None = None
    state: TaskState = TaskState.STARTING
    stop_event: object = field(default=None, repr=False)
    future: object = field(default=None, repr=False)
    error: str | None = None
