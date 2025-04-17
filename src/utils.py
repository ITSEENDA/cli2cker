from prompt_toolkit import prompt
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.output.win32 import NoConsoleScreenBufferError
from pynput.keyboard import KeyCode, Key

RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def get_key(key):
    return int(hex(ord(key)), 16) if key != 0 else key


def normalize_key(key):
    if isinstance(key, KeyCode):
        if key.char:
            ch = key.char
            if ord(ch) < 32:
                decoded = chr(ord(ch) + 96)
                return decoded.lower()
            return ch.lower()
    elif isinstance(key, Key):
        # Normalize modifier keys
        if key in [Key.ctrl, Key.ctrl_l, Key.ctrl_r]:
            return 'ctrl'
        if key in [Key.shift, Key.shift_l, Key.shift_r]:
            return 'shift'
        if key in [Key.alt, Key.alt_l, Key.alt_r]:
            return 'alt'
        return str(key).replace('Key.', '')
    return None


def is_key(key):
    return isinstance(key, Key)

def safe_prompt(prompt_text, completer=None):
    try:
        return prompt(
            prompt_text,
            completer=completer,
            auto_suggest=AutoSuggestFromHistory()
        )
    except NoConsoleScreenBufferError:
        # print("[!] No advanced console found. Falling back to basic input.")
        return input(prompt_text)