from concurrent.futures import ThreadPoolExecutor, TimeoutError
from time import monotonic
import threading

from models import ClickerSettings, ClickerTask, TaskState


class TaskManager:
    def __init__(self, backend, defaults=None, worker_count=5):
        self.backend = backend
        self.defaults = defaults or ClickerSettings()
        self.global_stop = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=worker_count)
        self.tasks = {}
        self.lock = threading.RLock()

    def _wait(self, task, timeout):
        deadline = monotonic() + max(timeout, 0)
        while not task.stop_event.is_set() and not self.global_stop.is_set():
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            task.stop_event.wait(min(0.05, remaining))
        return True

    def _worker(self, task):
        try:
            task.state = TaskState.RUNNING
            while not task.stop_event.is_set() and not self.global_stop.is_set():
                if task.state == TaskState.PAUSED:
                    if self._wait(task, 0.1):
                        break
                    continue
                self.backend.click(task.window, task.settings.click_mode)
                if task.settings.key not in (None, 0, ''):
                    self.backend.press_key(task.window, task.settings.key)
                if self._wait(task, task.settings.delay):
                    break
        except Exception as exc:
            task.error = str(exc)
            task.state = TaskState.FAILED
            raise
        finally:
            if task.state != TaskState.FAILED:
                task.state = TaskState.STOPPED

    def start(self, pid, profile_name=None, settings=None):
        with self.lock:
            if pid in self.tasks:
                raise RuntimeError(f'Task for PID {pid} is already running')
            windows = self.backend.find_windows_by_pid(pid)
            if not windows:
                raise RuntimeError(f'No usable window found for PID {pid}')
            task = ClickerTask(
                pid=pid,
                settings=(settings or self.defaults).copy(),
                window=windows[0],
                profile_name=profile_name,
                stop_event=threading.Event(),
            )
            self.tasks[pid] = task
            task.future = self.executor.submit(self._worker, task)
            return task

    def stop(self, pid, timeout=1):
        with self.lock:
            task = self.tasks.get(pid)
            if task is None:
                return False
            task.state = TaskState.STOPPING
            task.stop_event.set()
            future = task.future
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            return False
        except Exception:
            pass
        with self.lock:
            self.tasks.pop(pid, None)
        return True

    def stop_all(self):
        for pid in list(self.tasks):
            self.stop(pid)

    def toggle(self, pid, profile_name=None, settings=None):
        with self.lock:
            task = self.tasks.get(pid)
            if task is None:
                return self.start(pid, profile_name, settings)
            if task.state == TaskState.PAUSED:
                task.state = TaskState.RUNNING
            elif task.state == TaskState.RUNNING:
                task.state = TaskState.PAUSED
            return task

    def pause(self, pid):
        with self.lock:
            task = self.tasks[pid]
            if task.state == TaskState.RUNNING:
                task.state = TaskState.PAUSED
            return task

    def resume(self, pid):
        with self.lock:
            task = self.tasks[pid]
            if task.state == TaskState.PAUSED:
                task.state = TaskState.RUNNING
            return task

    def update_settings(self, pid, **values):
        with self.lock:
            task = self.tasks[pid]
            for key, value in values.items():
                if hasattr(task.settings, key):
                    setattr(task.settings, key, value)
            return task

    def reset_settings(self, pid, defaults):
        with self.lock:
            task = self.tasks[pid]
            task.settings = defaults.copy()
            return task

    def status(self):
        with self.lock:
            return list(self.tasks.values())

    def close(self):
        self.global_stop.set()
        for task in self.tasks.values():
            task.stop_event.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
