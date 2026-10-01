"""DP832 controlled source and authoritative target voltage/current limits."""
from .instrument import Instrument, guarded
from .errors import SafetyError


class RigolDP832(Instrument):
    kind = 'rigol'
    state_queries = {f'CH{ch}': f':OUTP? CH{ch}' for ch in (1, 2, 3)}

    def local_off(self):
        if not self.verified:
            return [(self.kind, 'not identified; OFF not attempted')]
        self.ready = None
        failures = []
        for channel in (1, 2, 3):
            failures.extend(self._off_action(
                f'CH{channel} OFF', lambda ch=channel: self._emergency_off(
                    f':OUTP CH{ch},OFF', f':OUTP? CH{ch}')))
        return failures

    @guarded
    def configured(self, channel):
        self.require_identity()
        self.policy.channel(channel)
        return (self._number(f':SOUR{channel}:VOLT?'),
                self._number(f':SOUR{channel}:CURR?'))

    @guarded
    def configure(self, channel, voltage, current_limit):
        self.ready = None
        self.require_identity()
        self.policy.source(channel, voltage, current_limit)
        self._write(f':OUTP CH{channel},OFF')
        if self._query(f':OUTP? CH{channel}') != 'OFF':
            raise SafetyError('output OFF not confirmed')
        self._write(f':INST:NSEL {channel}')
        self._write(f':SOUR{channel}:CURR {current_limit:.9f}')
        self._write(f':SOUR{channel}:VOLT {voltage:.9f}')
        actual = self.configured(channel)
        self.policy.source(channel, *actual)
        if any(abs(a - b) > 1e-8 for a, b in zip(actual, (voltage, current_limit))):
            raise SafetyError('setpoint readback mismatch')
        self.ready = (channel, *actual)
        return actual

    @guarded
    def set_voltage(self, channel, voltage):
        _, current = self.configured(channel)
        return self.configure(channel, voltage, current)

    @guarded
    def set_current_limit(self, channel, current_limit):
        voltage, _ = self.configured(channel)
        return self.configure(channel, voltage, current_limit)

    @guarded
    def output_on(self, channel):
        self.require_identity()
        self.policy.channel(channel)
        if self.ready is None or self.ready[0] != channel:
            raise SafetyError('verified configuration required')
        actual = self.configured(channel)
        self.policy.source(channel, *actual)
        if actual != self.ready[1:]:
            raise SafetyError('configuration changed')
        self._write(f':OUTP CH{channel},ON')
        if self._query(f':OUTP? CH{channel}') != 'ON':
            raise SafetyError('output ON not confirmed')

    @guarded
    def output_off(self, channel):
        if type(channel) is not int or channel not in (1, 2, 3):
            raise SafetyError('unknown channel')
        self.ready = None
        self._emergency_off(f':OUTP CH{channel},OFF', f':OUTP? CH{channel}')

    @guarded
    def measure(self, channel):
        self.require_identity()
        self.policy.channel(channel)
        return {name: self._number(f':MEAS:{command}? CH{channel}')
                for name, command in [('voltage', 'VOLT'), ('current', 'CURR')]}

    @guarded
    def status(self):
        """Observe all physical channels, independent of control-policy limits."""
        self.require_identity()
        states = self.physical_state()
        return {f'CH{ch}': {
            'output': states[f'CH{ch}'],
            'voltage_setpoint': self._number(f':SOUR{ch}:VOLT?'),
            'current_limit': self._number(f':SOUR{ch}:CURR?'),
            'measured': {name: self._number(f':MEAS:{command}? CH{ch}')
                         for name, command in [('voltage', 'VOLT'),
                                               ('current', 'CURR'), ('power', 'POWE')]},
        } for ch in (1, 2, 3)}
