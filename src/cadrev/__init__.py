"""cadrev: verifiable CAD reconstruction from papers."""


class Fault(Exception):
    """Why one entry of a project cannot be read or evaluated. Whatever reads the entry catches it
    and files it as a finding under `rule`, or under its own rule where the fault names none. One
    with no message repeats a finding already filed."""

    def __init__(self, message: str = "", rule: str | None = None):
        super().__init__(message)
        self.message, self.rule = message, rule
