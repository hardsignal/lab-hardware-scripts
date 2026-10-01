"""One shared exception hierarchy for all package layers."""


class InstrumentError(RuntimeError):
    pass


class SafetyError(InstrumentError, ValueError):
    pass


class IdentityError(SafetyError):
    pass


class TransportError(InstrumentError):
    pass


class TransportTimeout(TransportError):
    pass


class ShutdownError(InstrumentError):
    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__(f'Shutdown failures: {self.failures!r}')


def note_failure(primary, label, action):
    """Run secondary reporting/cleanup without replacing the primary failure."""
    try:
        return action()
    except BaseException as secondary:
        primary.add_note(f'{label}: {secondary!r}')
        return None
