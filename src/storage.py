import json
import os
import sys
from pathlib import Path

from models import ClickerSettings


class JsonStorage:
    def __init__(self, data_dir=None, legacy_dir=None):
        self.data_dir = Path(data_dir or self.default_data_dir())
        self.legacy_dir = Path(legacy_dir) if legacy_dir else None
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.defaults_path = self.data_dir / 'defaults.json'
        self.paths_path = self.data_dir / 'paths.json'
        self.hotkeys_path = self.data_dir / 'hotkeys.json'

    @staticmethod
    def default_data_dir():
        if sys.platform == 'win32':
            root = os.environ.get('APPDATA')
            if root:
                return Path(root) / 'AfkClicker'
        else:
            root = os.environ.get('XDG_CONFIG_HOME')
            if root:
                return Path(root) / 'afkclicker'
            return Path.home() / '.config' / 'afkclicker'
        return Path.home() / 'AfkClicker'

    def _load(self, path, default):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError):
            if self.legacy_dir:
                legacy_path = self.legacy_dir / path.name
                try:
                    return json.loads(legacy_path.read_text(encoding='utf-8'))
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
            return default

    @staticmethod
    def _save(path, data):
        temp_path = path.with_suffix(path.suffix + '.tmp')
        temp_path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False),
            encoding='utf-8',
        )
        temp_path.replace(path)

    def load_settings(self, fallback=None):
        fallback = fallback or ClickerSettings()
        data = self._load(self.defaults_path, fallback.to_mapping())
        settings = ClickerSettings.from_mapping(data)
        if not self.defaults_path.exists():
            self.save_settings(settings)
        return settings

    def save_settings(self, settings):
        self._save(self.defaults_path, settings.to_mapping())

    def load_paths(self):
        data = self._load(self.paths_path, {})
        return data if isinstance(data, dict) else {}

    def save_paths(self, paths):
        self._save(self.paths_path, paths)

    def load_hotkeys(self):
        data = self._load(self.hotkeys_path, {})
        return data if isinstance(data, dict) else {}

    def save_hotkeys(self, hotkeys):
        self._save(self.hotkeys_path, hotkeys)
