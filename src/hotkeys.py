import threading
from time import monotonic
import traceback
from queue import Queue

from pynput import keyboard
from pynput.keyboard import Key, KeyCode


def normalize_key(key):
    if isinstance(key, KeyCode):
        if key.char:
            return key.char.lower()
    if isinstance(key, Key):
        modifiers = {
            Key.ctrl: 'ctrl',
            Key.ctrl_l: 'ctrl',
            Key.ctrl_r: 'ctrl',
            Key.shift: 'shift',
            Key.shift_l: 'shift',
            Key.shift_r: 'shift',
            Key.alt: 'alt',
            Key.alt_l: 'alt',
            Key.alt_r: 'alt',
        }
        return modifiers.get(key, str(key).replace('Key.', ''))
    return None


class HotkeyManager:
    def __init__(self, storage, action_callback, key_state_probe=None):
        self.storage = storage
        self.action_callback = action_callback
        self.key_state_probe = key_state_probe
        self.bindings = storage.load_hotkeys()
        self.lookup = self._build_lookup(self.bindings)
        self.pressed_keys = set()
        self.key_triggered = False
        self.state_lock = threading.RLock()
        self.stop_event = threading.Event()
        self.listener = None
        self.watchdog_thread = None
        self.action_thread = None
        self.action_queue = Queue()
        self.last_event_at = monotonic()
        self.capture_lock = threading.Lock()
        self.capture_active = threading.Event()

    @staticmethod
    def _build_lookup(bindings):
        return {
            frozenset(data.get('keys', ())): data.get('action', '')
            for data in bindings.values()
            if data.get('keys') and data.get('action')
        }

    def _create_listener(self):
        return keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release,
        )

    def _synchronize_pressed_keys(self):
        with self.state_lock:
            current = tuple(self.pressed_keys)
            last_event_at = self.last_event_at
        if self.key_state_probe is None:
            if current and monotonic() - last_event_at > 2:
                with self.state_lock:
                    self.pressed_keys.clear()
                    self.key_triggered = False
            return
        stale = {
            key for key in current
            if self.key_state_probe(key) is False
        }
        if not stale:
            return
        with self.state_lock:
            self.pressed_keys.difference_update(stale)
            if not self.pressed_keys:
                self.key_triggered = False

    def _watchdog_loop(self):
        while not self.stop_event.wait(0.1):
            try:
                self._synchronize_pressed_keys()
                if not self.capture_active.is_set() and self.listener is not None and not self.listener.is_alive():
                    self._restart_listener()
            except Exception as exc:
                print(f'[hotkey] recovery failed: {exc}')

    def _action_loop(self):
        while True:
            action = self.action_queue.get()
            try:
                if action is None:
                    return
                if not self.stop_event.is_set():
                    self.action_callback(action)
            except Exception:
                traceback.print_exc()
            finally:
                self.action_queue.task_done()

    def start(self):
        if not self.stop_event.is_set() and self.listener is not None:
            return
        self.stop_event.clear()
        self.action_queue = Queue()
        self.listener = self._create_listener()
        self.action_thread = threading.Thread(
            target=self._action_loop,
            name='hotkey-actions',
            daemon=True,
        )
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name='hotkey-watchdog',
            daemon=True,
        )
        self.action_thread.start()
        self.listener.start()
        self.watchdog_thread.start()

    def _restart_listener(self):
        if self.stop_event.is_set():
            return
        with self.state_lock:
            self.pressed_keys.clear()
            self.key_triggered = False
            self.listener = self._create_listener()
            listener = self.listener
        listener.start()

    def on_press(self, key):
        normalized = normalize_key(key)
        if not normalized:
            return
        with self.state_lock:
            self.last_event_at = monotonic()
            self.pressed_keys.add(normalized)
            lookup_key = frozenset(self.pressed_keys)
            if self.key_triggered or lookup_key not in self.lookup:
                return
            self.key_triggered = True
            action = self.lookup[lookup_key]
        print(f'[hotkey] Triggered action: {action}')
        self.action_queue.put(action)

    def on_release(self, key):
        normalized = normalize_key(key)
        if not normalized:
            return
        with self.state_lock:
            self.last_event_at = monotonic()
            self.pressed_keys.discard(normalized)
            if not self.pressed_keys:
                self.key_triggered = False

    def save_binding(self, name, keys, action):
        data = {'keys': sorted(set(keys)), 'action': action}
        old = self.bindings.get(name)
        if old:
            self.lookup.pop(frozenset(old.get('keys', ())), None)
        self.bindings[name] = data
        self.lookup[frozenset(data['keys'])] = action
        self.storage.save_hotkeys(self.bindings)

    def capture_binding(self, name, action):
        with self.capture_lock:
            print('Press the hotkey combination, then release it.')
            captured = set()
            assigned = threading.Event()
            self.capture_active.set()
            listener = self.listener
            if listener is not None:
                listener.stop()
                listener.join(timeout=1)

            def on_press(key):
                normalized = normalize_key(key)
                if normalized:
                    captured.add(normalized)

            def on_release(key):
                if captured:
                    assigned.set()
                    return False

            try:
                with keyboard.Listener(on_press=on_press, on_release=on_release) as capture_listener:
                    capture_listener.join()
            finally:
                self.capture_active.clear()
                with self.state_lock:
                    self.pressed_keys.clear()
                    self.key_triggered = False
                if not self.stop_event.is_set():
                    self._restart_listener()

            if not assigned.is_set() or not captured:
                raise RuntimeError('No hotkey was captured')
            self.save_binding(name, captured, action)
            return captured

    def update_action(self, name, action):
        if name not in self.bindings:
            raise KeyError(f'Unknown hotkey: {name}')
        self.bindings[name]['action'] = action
        keys = frozenset(self.bindings[name].get('keys', ()))
        self.lookup[keys] = action
        self.storage.save_hotkeys(self.bindings)

    def delete_binding(self, name):
        data = self.bindings.pop(name, None)
        if data:
            self.lookup.pop(frozenset(data.get('keys', ())), None)
            self.storage.save_hotkeys(self.bindings)
            return True
        return False

    def stop(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        with self.state_lock:
            self.pressed_keys.clear()
            self.key_triggered = False
        if self.listener is not None:
            self.listener.stop()
        self.action_queue.put(None)
