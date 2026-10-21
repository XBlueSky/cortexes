"""Agent-facing failure contract for the cortex-vec CLI.

Callers are mostly agents, which choose their next step from the exit code:

  0  success, including an empty result
  1  unexpected failure (an uncaught traceback exits 1 too)
  2  caller error: fix the command and retry (argparse and raw-page errors
     already use 2)
  3  environment not set up: stop and tell the user, or run the named setup

`cli.main` catches CliError and prints it as one stderr line that names the
fix. The raw-map / raw-span family keeps its own JSON-on-stdout envelope.
"""

EXIT_CALLER = 2
EXIT_SETUP = 3


class CliError(Exception):
    """A failure the caller can act on; `hint` says how."""

    def __init__(self, message, hint="", code=EXIT_CALLER):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code

    def render(self):
        line = f"cortex-vec: error: {self.message}"
        return f"{line} ({self.hint})" if self.hint else line
