RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RESET = "\033[0m"


def get_key(key):
    return int(hex(ord(key)), 16) if key != 0 else key