import shlex


class CommandRouter:
    LEGACY_ALIASES = {
        '!start': ('!task', 'start'),
        '!pause': ('!task', 'pause'),
        '!resume': ('!task', 'resume'),
        '!toggle': ('!task', 'toggle'),
        '!set': ('!task', 'config'),
        '!stop': ('!task', 'stop'),
        '!status': ('!task', 'status'),
    }

    def __init__(self, helper):
        self.helper = helper
        self.handlers = {}

    def register(
            self,
            name,
            handler,
            description='',
            options=None,
            subcommands=None,
            usage='',
            option_descriptions=None,
            subcommand_descriptions=None,
            subcommand_option_descriptions=None,
            option_examples=None,
            subcommand_option_examples=None):
        spec = self.helper.add_command(
            name,
            description=description,
            options=options,
            subcommands=subcommands,
            usage=usage,
            option_descriptions=option_descriptions,
            option_examples=option_examples,
            subcommand_descriptions=subcommand_descriptions,
            subcommand_option_descriptions=subcommand_option_descriptions,
            subcommand_option_examples=subcommand_option_examples,
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
        if command in self.LEGACY_ALIASES:
            command, subcommand = self.LEGACY_ALIASES[command]
            tokens.insert(0, subcommand)
        handler = self.handlers.get(command)
        if handler is None:
            return f'Unknown command: {command}'
        try:
            return handler(tokens)
        except Exception as exc:
            return f'Command error: {exc}'
