import os

from prompt_toolkit import prompt
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

try:
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError
except ImportError:
    class NoConsoleScreenBufferError(Exception):
        pass


RED = '\033[31m'
YELLOW = '\033[33m'
GREEN = '\033[32m'
RESET = '\033[0m'


def safe_prompt(prompt_text, completer=None):
    try:
        return prompt(
            prompt_text,
            completer=completer,
            auto_suggest=AutoSuggestFromHistory(),
        ).strip()
    except NoConsoleScreenBufferError:
        return input(prompt_text).strip()


def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


def str_to_bool(value):
    normalized = str(value).strip().lower()
    if normalized not in {'true', 'false'}:
        raise ValueError(f'Expected true or false, got {value!r}')
    return normalized == 'true'
