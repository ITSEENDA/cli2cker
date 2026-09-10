import os

from prompt_toolkit import prompt
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory

try:
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError
except ImportError:
    class NoConsoleScreenBufferError(Exception):
        pass


RED = '\033[31m'
YELLOW = '\033[33m'
GREEN = '\033[32m'
RESET = '\033[0m'


def safe_prompt(prompt_text, completer=None, session=None):
    try:
        if session is not None:
            return session.prompt(prompt_text).strip()
        return prompt(
            prompt_text,
            completer=completer,
            auto_suggest=AutoSuggestFromHistory(),
        ).strip()
    except NoConsoleScreenBufferError:
        return input(prompt_text).strip()


def create_prompt_session(history_path, completer=None):
    from prompt_toolkit import PromptSession

    try:
        return PromptSession(
            history=FileHistory(str(history_path)),
            completer=completer,
            auto_suggest=AutoSuggestFromHistory(),
        )
    except NoConsoleScreenBufferError:
        return None


def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


def str_to_bool(value):
    normalized = str(value).strip().lower()
    if normalized not in {'true', 'false'}:
        raise ValueError(f'Expected true or false, got {value!r}')
    return normalized == 'true'
