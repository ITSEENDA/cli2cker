import os
from pathlib import Path


class TargetRegistry:
    """Persist executable aliases and resolve them to runtime PIDs."""

    def __init__(self, storage, backend):
        self.storage = storage
        self.backend = backend

    def list(self):
        return self.storage.load_paths()

    def save(self, name, raw_path, base_dir=None, validate=True):
        path = Path(os.path.expandvars(os.path.expanduser(raw_path)))
        if not path.is_absolute():
            path = Path(base_dir or Path.cwd()) / path
        path = path.resolve()
        if validate and not path.is_file():
            raise FileNotFoundError(f'Target executable does not exist: {path}')
        paths = self.storage.load_paths()
        paths[name] = str(path)
        self.storage.save_paths(paths)
        return path

    def delete(self, name):
        paths = self.storage.load_paths()
        if name not in paths:
            return False
        del paths[name]
        self.storage.save_paths(paths)
        return True

    def resolve(self, name):
        paths = self.storage.load_paths()
        if name not in paths:
            raise KeyError(f'No saved target named {name!r}')
        return Path(paths[name])

    def find_pids(self, name):
        return self.backend.find_pids_by_executable(str(self.resolve(name)))
