from prompt_toolkit.completion import Completer, Completion


class CommandCompleter(Completer):
    """Complete command names, subcommands, and option names."""

    def __init__(self, commands=None):
        self.commands = commands or {}

    def update_commands(self, commands):
        self.commands = commands or {}

    def update_candidates(self, command, candidates):
        spec = self.commands.get(command)
        if isinstance(spec, list):
            self.commands[command] = list(dict.fromkeys([*spec, *candidates]))

    def update_subcommand_candidates(self, command, subcommand, candidates):
        spec = self.commands.get(command)
        if isinstance(spec, dict) and subcommand in spec:
            spec[subcommand] = list(dict.fromkeys([*spec[subcommand], *candidates]))

    @staticmethod
    def _completion(text, candidate):
        if candidate.startswith(text):
            return Completion(candidate, start_position=-len(text))
        return None

    def _yield_candidates(self, candidates, prefix, typed):
        for candidate in candidates or ():
            if not candidate or candidate in typed or candidate == prefix:
                continue
            completion = self._completion(prefix, candidate)
            if completion is not None:
                yield completion

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        tokens = text.split()
        trailing_space = text.endswith((' ', '\t'))

        if not tokens:
            yield from self._yield_candidates(self.commands.keys(), '', set())
            return

        command = tokens[0]
        if command not in self.commands:
            prefix = '' if trailing_space else command
            yield from self._yield_candidates(self.commands.keys(), prefix, set())
            return

        spec = self.commands[command]
        if isinstance(spec, dict):
            if len(tokens) < 2 or (len(tokens) == 2 and not trailing_space):
                prefix = '' if trailing_space else tokens[1]
                yield from self._yield_candidates(spec.keys(), prefix, set())
                return

            subcommand = tokens[1]
            if subcommand not in spec:
                prefix = '' if trailing_space else tokens[-1]
                yield from self._yield_candidates(spec.keys(), prefix, set())
                return

            candidates = spec[subcommand]
            option_tokens = tokens[2:]
        else:
            candidates = spec
            option_tokens = tokens[1:]

        prefix = '' if trailing_space else (option_tokens[-1] if option_tokens else '')
        typed = set(option_tokens[:-1] if option_tokens and not trailing_space else option_tokens)
        yield from self._yield_candidates(candidates, prefix, typed)
