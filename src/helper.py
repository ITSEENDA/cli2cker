from dataclasses import dataclass, field
import sys


@dataclass
class CommandSpec:
    name: str
    description: str = ''
    usage: str = ''
    options: tuple[str, ...] = ()
    subcommands: dict[str, tuple[str, ...]] = field(default_factory=dict)
    option_descriptions: dict[str, str] = field(default_factory=dict)
    option_examples: dict[str, str] = field(default_factory=dict)
    subcommand_descriptions: dict[str, str] = field(default_factory=dict)
    subcommand_option_descriptions: dict[str, dict[str, str]] = field(default_factory=dict)
    subcommand_option_examples: dict[str, dict[str, str]] = field(default_factory=dict)


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

    def add_command(
            self,
            name,
            description='',
            options=None,
            subcommands=None,
            usage='',
            option_descriptions=None,
            option_examples=None,
            subcommand_descriptions=None,
            subcommand_option_descriptions=None,
            subcommand_option_examples=None):
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
            option_descriptions=option_descriptions or {},
            option_examples=option_examples or {},
            subcommand_descriptions=subcommand_descriptions or {},
            subcommand_option_descriptions=subcommand_option_descriptions or {},
            subcommand_option_examples=subcommand_option_examples or {},
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
        command_tokens = command.strip().split() if command and command.strip() else []
        command_name = self._command_name(command_tokens[0]) if command_tokens else None
        if command_name:
            spec = self.commands.get(command_name)
            if spec is None:
                return f"Unknown command: {command_name}"

            subcommand = command_tokens[1] if len(command_tokens) > 1 else None
            lines = [f"{spec.name} - {spec.description}", f"Usage: {self._format_usage(spec)}"]
            if spec.options:
                lines.append('Options:')
                for option in spec.options:
                    description = spec.option_descriptions.get(option, '')
                    example = spec.option_examples.get(option)
                    suffix = f' - {description}' if description else ''
                    if example:
                        suffix += f' (example: {example})'
                    lines.append(f'  {option}{suffix}')
            if spec.subcommands:
                if subcommand and subcommand in spec.subcommands:
                    options = spec.subcommands[subcommand]
                    description = spec.subcommand_descriptions.get(subcommand, '')
                    if description:
                        lines.append(f'Subcommand: {subcommand} - {description}')
                    if options:
                        lines.append('Parameters:')
                        descriptions = spec.subcommand_option_descriptions.get(subcommand, {})
                        examples = spec.subcommand_option_examples.get(subcommand, {})
                        for option in options:
                            option_description = descriptions.get(option, '')
                            example = examples.get(option)
                            suffix = f' - {option_description}' if option_description else ''
                            if example:
                                suffix += f' (example: {example})'
                            lines.append(f'  {option}{suffix}')
                    return '\n'.join(lines)

                lines.append('Subcommands:')
                for subcommand_name, options in spec.subcommands.items():
                    suffix = f" [{', '.join(options)}]" if options else ''
                    description = spec.subcommand_descriptions.get(subcommand_name, '')
                    if description:
                        suffix += f' - {description}'
                    lines.append(f"  {subcommand_name}{suffix}")
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

    @staticmethod
    def format_table(headers, rows):
        headers = [str(header) for header in headers]
        rows = [[str(value) for value in row] for row in rows]
        widths = [len(header) for header in headers]
        for row in rows:
            widths = [
                max(width, len(value))
                for width, value in zip(widths, row)
            ]

        def format_row(row):
            return '  '.join(value.ljust(width) for value, width in zip(row, widths)).rstrip()

        lines = [format_row(headers)]
        lines.append('  '.join('-' * width for width in widths).rstrip())
        lines.extend(format_row(row) for row in rows)
        return '\n'.join(lines)
