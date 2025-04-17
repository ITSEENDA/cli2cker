from abc import ABC

from prompt_toolkit.completion import Completer, Completion


class CommandCompleter(Completer, ABC):
    def __init__(self, commands=None):
        if commands is None:
            commands = {}
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        tokens = text.split()

        if not tokens:
            for cmd in self.commands.keys():
                yield Completion(cmd, start_position=0)
            return
        if tokens[0] not in self.commands:
            for cmd in self.commands:
                if cmd.startswith(tokens[0]):
                    yield Completion(cmd, start_position=-len(tokens[0]))
            return

        current_arg = tokens[-1]
        options = self.commands[tokens[0]]
        for opt in options:
            if opt.startswith(current_arg):
                yield Completion(opt, start_position=-len(current_arg))
