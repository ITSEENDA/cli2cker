import shlex


class CommandRouter:
    def __init__(self, helper):
        self.helper = helper
        self.handlers = {}

    def register(self, name, handler, description='', options=None, subcommands=None, usage=''):
        spec = self.helper.add_command(
            name,
            description=description,
            options=options,
            subcommands=subcommands,
            usage=usage,
        )
        self.handlers[spec.name] = handler

    def dispatch(self, line):
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            return f'Command error: {exc}'
        if not tokens:
            return None
        command = tokens.pop(0)
        handler = self.handlers.get(command)
        if handler is None:
            return f'Unknown command: {command}'
        try:
            return handler(tokens)
        except Exception as exc:
            return f'Command error: {exc}'
