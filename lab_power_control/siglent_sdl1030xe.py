"""Static CC electronic load, never a primary target protection device."""
from .instrument import Instrument, guarded
from .errors import InstrumentError, SafetyError
from .safety import number


class SiglentSDL1030XE(Instrument):
    kind = 'siglent'
    state_queries = {'input': ':SOUR:INP?'}

    def local_off(self):
        if not self.verified:
            return [(self.kind, 'not identified; OFF not attempted')]
        self.ready = None
        return self._off_action('input OFF', lambda: self._emergency_off(
            ':SOUR:INP OFF', ':SOUR:INP?'))

    def _check_mode(self):
        if self._query(':SOUR:FUNC?') not in ('CURR', 'CURRENT'):
            raise SafetyError('static CC mode not confirmed')
        for command in (':SOUR:SHOR?', ':SOUR:EXT:INPUT?'):
            if self._query(command) not in ('0', 'OFF'):
                raise SafetyError('short/external input control must be OFF')

    @guarded
    def configure_cc(self, current):
        self.ready = None
        self.require_identity()
        self.policy.load(current)
        self._emergency_off(':SOUR:INP OFF', ':SOUR:INP?')
        self._write(':SOUR:SHOR OFF')
        self._write(':SOUR:EXT:INPUT OFF')
        self._write(':SOUR:FUNC CURR')
        self._write(f':SOUR:CURR {current:.9f}')
        self._check_mode()
        actual = self._number(':SOUR:CURR?')
        self.policy.load(actual)
        if abs(actual - current) > 1e-8:
            raise SafetyError('current readback mismatch')
        self.ready = actual
        return actual

    @guarded
    def input_on(self):
        self.require_identity()
        if self.ready is None:
            raise SafetyError('verified CC configuration required')
        self._check_mode()
        current = self._number(':SOUR:CURR?')
        self.policy.load(current)
        if current != self.ready:
            raise SafetyError('configuration changed')
        measurements = self.measure()
        number(measurements['voltage'], 0, self.policy.voltage_max)
        number(measurements['voltage'] * current, 0, self.policy.power_max)
        self._write(':SOUR:INP ON')
        if self._query(':SOUR:INP?') not in ('1', 'ON'):
            raise SafetyError('input ON not confirmed')

    @guarded
    def input_off(self):
        self.ready = None
        self._emergency_off(':SOUR:INP OFF', ':SOUR:INP?')

    @guarded
    def measure(self):
        self.require_identity()
        return {name: self._number(f':MEAS:{command}?') for name, command in
                [('voltage', 'VOLT'), ('current', 'CURR'), ('power', 'POW')]}

    @guarded
    def status(self):
        """Read static-mode configuration and measurements without selecting a mode."""
        self.require_identity()
        state = self.physical_state()
        mode = self._query(':SOUR:FUNC?')
        modes = {'CURR': 'CC', 'CURRENT': 'CC', 'VOLT': 'CV', 'VOLTAGE': 'CV',
                 'POW': 'CP', 'POWER': 'CP', 'RES': 'CR', 'RESISTANCE': 'CR', 'LED': 'LED'}
        if mode not in modes:
            raise InstrumentError(f'unknown static mode: {mode!r}')
        current_key = ('cc_current_setpoint' if modes[mode] == 'CC'
                       else 'stored_cc_current_setpoint')
        return {'input': state['input'], 'static_mode': modes[mode],
                current_key: self._number(':SOUR:CURR?'),
                'measured': self.measure()}
