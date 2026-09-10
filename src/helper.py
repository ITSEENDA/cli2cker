from dataclasses import dataclass, field
import sys


@dataclass
class CommandSpec:
    name: str
    description: str = ''
    usage: str = ''
    options: tuple[str, ...] = ()
    subcommands: dict[str, tuple[str, ...]] = field(default_factory=dict)


class ClickerHelper:
    """Store command metadata and render the interactive CLI help."""

    def __init__(self, prog='afk-clicker', description='AFK clicker command help'):
        self.prog = prog
        self.description = description
        self.commands = {}
        self.arguments = []

    @staticmethod
    def _command_name(name):
        return name if name.startswith('!') else f'!{name}'

    @classmethod
    def command_name(cls, name):
        return cls._command_name(name)

    @staticmethod
    def _as_options(options):
        return tuple(str(option) for option in (options or ()) if option)

    def add_command(self, name, description='', options=None, subcommands=None, usage=''):
        name = self._command_name(name)
        normalized_subcommands = {}
        for subcommand, sub_options in (subcommands or {}).items():
            normalized_subcommands[str(subcommand)] = self._as_options(sub_options)

        self.commands[name] = CommandSpec(
            name=name,
            description=description,
            usage=usage,
            options=self._as_options(options),
            subcommands=normalized_subcommands,
        )
        return self.commands[name]

    def add_option(self, option, definition, valid_param=None):
        """Backward-compatible alias for registering a command."""
        return self.add_command(option, definition, options=valid_param)

    def add_argument(self, argument, definition, type=str, help='', default=None):
        self.arguments.append({
            'name': argument,
            'definition': definition,
            'type': type,
            'help': help,
            'default': default,
        })

    @property
    def completion_map(self):
        """Return the compact schema consumed by CommandCompleter."""
        result = {}
        for name, spec in self.commands.items():
            if spec.subcommands:
                result[name] = {
                    subcommand: list(options)
                    for subcommand, options in spec.subcommands.items()
                }
            else:
                result[name] = list(spec.options)
        return result

    def _format_usage(self, spec):
        if spec.usage:
            return spec.usage
        if spec.subcommands:
            return f"{spec.name} <subcommand>"
        if spec.options:
            return f"{spec.name} [options]"
        return spec.name

    def format_help(self, command=None):
        command = command.strip().split()[0] if command and command.strip() else None
        if command:
            command = self._command_name(command)
            spec = self.commands.get(command)
            if spec is None:
                return f"Unknown command: {command}"

            lines = [f"{spec.name} - {spec.description}", f"Usage: {self._format_usage(spec)}"]
            if spec.options:
                lines.append('Options: ' + ', '.join(spec.options))
            if spec.subcommands:
                lines.append('Subcommands:')
                for subcommand, options in spec.subcommands.items():
                    suffix = f" [{', '.join(options)}]" if options else ''
                    lines.append(f"  {subcommand}{suffix}")
            return '\n'.join(lines)

        lines = [self.description, '', 'Commands:']
        rows = [
            (self._format_usage(spec), spec.description)
            for spec in self.commands.values()
        ]
        width = max((len(usage) for usage, _ in rows), default=0)
        for usage, description in rows:
            lines.append(f"  {usage.ljust(width)}  {description}".rstrip())

        if self.arguments:
            lines.extend(['', 'Arguments:'])
            for argument in self.arguments:
                lines.append(f"  {argument['name']}: {argument['definition']}")
        return '\n'.join(lines)

    def print_help(self, command=None, file=None):
        print(self.format_help(command), file=file or sys.stdout)

    def print_helper(self, file=None):
        """Backward-compatible alias for print_help."""
        self.print_help(file=file)
