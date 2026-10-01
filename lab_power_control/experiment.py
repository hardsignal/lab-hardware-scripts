"""Sequential safety coordination only; no automatic experiment sequences."""
from .errors import SafetyError, ShutdownError


class Experiment:
    def __init__(self, rigol, siglent):
        self.rigol, self.siglent = rigol, siglent
        rigol.shutdown = siglent.shutdown = self._shutdown
        rigol.activity_check = siglent.activity_check = self.has_activity

    def has_activity(self):
        return self.rigol.active or self.siglent.active

    def startup(self):
        """Observe and report; never alter the physical state on session entry."""
        if self.has_activity():
            raise SafetyError('cannot restart startup after control activity')
        for instrument in (self.rigol, self.siglent):
            instrument.verified = False
            instrument.ready = None
        self.startup_state = {}
        for instrument in (self.rigol, self.siglent):
            identity = instrument.identify()
            state = instrument.physical_state()
            report = {'identity': identity, 'state': state}
            self.startup_state[instrument.kind] = report
            instrument.log.record('startup_state', instrument=instrument.kind, **report)
        return self.startup_state

    def status(self):
        """Observe an identity-verified session before any control activity."""
        if self.has_activity():
            raise SafetyError('status requires an observation-only session')
        for instrument in (self.rigol, self.siglent):
            instrument.require_identity()
        return {instrument.kind: {
            'identity': self.startup_state[instrument.kind]['identity'],
            **instrument.status(),
        } for instrument in (self.rigol, self.siglent)}

    def _shutdown(self):
        failures = []
        for instrument in (self.siglent, self.rigol):
            try:
                failures.extend(instrument.local_off())
            except BaseException as exc:
                failures.append((instrument.kind, repr(exc)))
        return failures

    def all_off(self):
        failures = self._shutdown()
        if failures:
            raise ShutdownError(failures)

    def __enter__(self):
        self.startup()
        return self

    def __exit__(self, kind, value, traceback):
        active = self.rigol.active or self.siglent.active
        failures = self._shutdown() if active else []
        if failures:
            if value is not None:
                value.add_note('Shutdown failures: ' + repr(failures))
            else:
                raise ShutdownError(failures)
        return False
