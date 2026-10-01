"""Shared identity, auditing, and failure handling."""
from functools import wraps
import math

from .errors import IdentityError, InstrumentError, SafetyError, TransportError, note_failure


def guarded(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            self.log.record('operation', instrument=self.kind,
                            operation=method.__name__, arguments=repr((args, kwargs)))
            return method(self, *args, **kwargs)
        except BaseException as exc:
            self.ready = None
            note_failure(exc, 'Failure logging failed', lambda primary=exc: self.log.record(
                'failure', instrument=self.kind, error=repr(primary)))
            if self.activity_check():
                failures = note_failure(exc, 'Shutdown raised', self.shutdown)
                if failures:
                    exc.add_note('Shutdown failures: ' + repr(failures))
            raise
    return call


class Instrument:
    def __init__(self, transport, policy, logger):
        self.transport, self.policy, self.log = transport, policy, logger
        self.verified = False
        self.ready = None
        self.active = False
        self.activity_check = lambda: self.active
        self.shutdown = self.local_off

    def _write(self, command):
        self.require_identity()
        self.active = True
        self.log.record('requested_command',
                        instrument=self.kind, command=command)
        try:
            self.transport.write(command)
        except Exception as exc:
            if isinstance(exc, TransportError):
                raise
            raise TransportError(str(exc)) from exc

    def _query(self, command):
        self.log.record('requested_query',
                        instrument=self.kind, command=command)
        try:
            value = self.transport.query(command).strip()
        except Exception as exc:
            if isinstance(exc, TransportError):
                raise
            raise TransportError(str(exc)) from exc
        self.log.record('response', instrument=self.kind,
                        command=command, value=value)
        return value

    def _number(self, command):
        try:
            value = float(self._query(command))
        except ValueError as exc:
            raise InstrumentError('invalid numeric response') from exc
        if not math.isfinite(value) or value < 0:
            raise InstrumentError('nonfinite or negative response')
        self.log.record('verified_measurement', instrument=self.kind,
                        command=command, value=value, simulated=getattr(
                            self.transport, 'kind', None) is not None)
        return value

    @guarded
    def identify(self):
        self.verified = False
        self.ready = None
        identity = self._query('*IDN?')
        fields = [field.strip() for field in identity.split(',')]
        expected = [getattr(self.policy, self.kind + '_vendor'),
                    getattr(self.policy, self.kind + '_model')]
        if len(fields) != 4 or fields[:2] != expected or not all(fields):
            raise IdentityError(f'unexpected {self.kind} identity: {identity!r}')
        self.verified = True
        return identity

    @guarded
    def physical_state(self):
        self.require_identity()
        states = {}
        for name, command in self.state_queries.items():
            response = self._query(command)
            if response not in ('ON', 'OFF', '1', '0'):
                raise InstrumentError(f'unknown physical state: {response!r}')
            states[name] = 'ON' if response in ('ON', '1') else 'OFF'
        self.log.record('physical_state', instrument=self.kind, states=states)
        return states

    def require_identity(self):
        if not self.verified:
            raise SafetyError('identity has not been verified')

    def _off_action(self, name, action):
        failures = []
        try:
            self.log.record('shutdown_attempt',
                            instrument=self.kind, action=name)
        except BaseException as exc:
            failures.append((name + ':log', repr(exc)))
        try:
            action()
        except BaseException as exc:
            failures.append((name, repr(exc)))
            try:
                self.log.record('shutdown_failure', instrument=self.kind,
                                action=name, error=repr(exc))
            except BaseException as log_exc:
                failures.append((name + ':failure_log', repr(log_exc)))
        return failures

    def _emergency_off(self, command, query):
        self.require_identity()
        self.active = True
        # Logging failure must never suppress the physical OFF write.
        self.transport.write(command)
        response = self.transport.query(query).strip()
        if response not in ('OFF', '0'):
            raise InstrumentError(f'OFF not confirmed: {response!r}')
        self.log.record('shutdown_confirmed',
                        instrument=self.kind, command=command)
