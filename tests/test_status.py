"""Read-only commissioning; all hardware boundaries are mocked or forbidden."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import tempfile
from unittest.mock import Mock, patch

from lab_power_control.__main__ import main
from lab_power_control.connections import connected_session
from lab_power_control.errors import IdentityError, InstrumentError, SafetyError, TransportError
from lab_power_control.io_transport import EthernetTransport
from tests.support import OfflineTest
from tests import test_connections


class StatusTests(OfflineTest):
    def open_session(self):
        return connected_session(
            self.policy, self.log, test_connections.ConnectionTests.profile(self), dry_run=False,
            usb_factory=Mock(return_value=self.rt), tcp_factory=Mock(return_value=self.st))

    def forbid_writes(self):
        self.rt.write = Mock(side_effect=AssertionError('write forbidden'))
        self.st.write = Mock(side_effect=AssertionError('write forbidden'))

    def assert_queries_only(self):
        self.rt.write.assert_not_called()
        self.st.write.assert_not_called()
        self.assertTrue(all('?' in cmd and ';' not in cmd
                            for cmd in self.rt.commands + self.st.commands))

    def test_exact_queries_parse_all_channels_and_preserve_state(self):
        self.forbid_writes()
        for ch in (1, 2, 3):
            self.rt.state.update({f':OUTP? CH{ch}': 'ON' if ch == 2 else 'OFF',
                                  f':SOUR{ch}:VOLT?': str(ch + 10),
                                  f':SOUR{ch}:CURR?': '2.5e-1',
                                  f':MEAS:VOLT? CH{ch}': str(ch),
                                  f':MEAS:CURR? CH{ch}': '.125',
                                  f':MEAS:POWE? CH{ch}': str(ch * .125)})
        self.st.state.update({':SOUR:INP?': '1', ':SOUR:FUNC?': 'VOLTAGE',
                              ':SOUR:CURR?': '.05', ':MEAS:VOLT?': '3.25e0',
                              ':MEAS:CURR?': '0.04', ':MEAS:POW?': '.13'})
        before = (dict(self.rt.state), dict(self.st.state))
        with self.open_session() as session:
            result = session.status()
            self.assertFalse(session.has_activity())
        for ch in (1, 2, 3):
            self.assertEqual(result['rigol'][f'CH{ch}'], {
                'output': 'ON' if ch == 2 else 'OFF', 'voltage_setpoint': ch + 10,
                'current_limit': .25,
                'measured': {'voltage': ch, 'current': .125, 'power': ch * .125}})
        self.assertEqual(result['siglent'], {
            'identity': self.st.identity, 'input': 'ON', 'static_mode': 'CV',
            'stored_cc_current_setpoint': .05,
            'measured': {'voltage': 3.25, 'current': .04, 'power': .13}})
        states = [f':OUTP? CH{ch}' for ch in (1, 2, 3)]
        expected = ['*IDN?'] + states + states
        for ch in (1, 2, 3):
            expected += [f':SOUR{ch}:VOLT?', f':SOUR{ch}:CURR?',
                         f':MEAS:VOLT? CH{ch}', f':MEAS:CURR? CH{ch}', f':MEAS:POWE? CH{ch}']
        self.assertEqual(self.rt.commands, expected)
        self.assertEqual(self.st.commands, ['*IDN?', ':SOUR:INP?', ':SOUR:INP?',
                                            ':SOUR:FUNC?', ':SOUR:CURR?',
                                            ':MEAS:VOLT?', ':MEAS:CURR?', ':MEAS:POW?'])
        self.assertEqual((self.rt.state, self.st.state), before)
        self.assertTrue(self.rt.closed and self.st.closed)
        self.assert_queries_only()

    def test_malformed_numeric_responses_leave_on_state_untouched(self):
        self.forbid_writes()
        self.rt.state[':OUTP? CH1'] = 'ON'
        self.st.state[':SOUR:INP?'] = '1'
        with self.open_session() as session:
            queries = [(self.rt, f':{prefix}{ch}{suffix}')
                       for ch in (1, 2, 3)
                       for prefix, suffix in [('SOUR', ':VOLT?'), ('SOUR', ':CURR?')]]
            queries += [(self.rt, f':MEAS:{key}? CH{ch}') for ch in (1, 2, 3)
                        for key in ('VOLT', 'CURR', 'POWE')]
            queries += [(self.st, cmd) for cmd in
                        (':SOUR:CURR?', ':MEAS:VOLT?', ':MEAS:CURR?', ':MEAS:POW?')]
            for transport, command in queries:
                for response in ('', 'garbage', '1,2', 'nan', 'inf', '-inf', '1e999', '-1'):
                    with self.subTest(command=command, response=response):
                        with patch.dict(transport.state, {command: response}):
                            with self.assertRaises(InstrumentError):
                                session.status()
            self.assertFalse(session.has_activity())
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'ON')
        self.assertEqual(self.st.state[':SOUR:INP?'], '1')
        self.assert_queries_only()

    def test_invalid_mode_and_state_fail_without_writes(self):
        self.forbid_writes()
        with self.open_session() as session:
            for transport, command in ((self.rt, ':OUTP? CH3'),
                                       (self.st, ':SOUR:INP?'), (self.st, ':SOUR:FUNC?')):
                with patch.dict(transport.state, {command: 'UNKNOWN'}):
                    with self.assertRaises(InstrumentError):
                        session.status()
        self.assert_queries_only()

    def test_static_modes_label_cc_preset_without_changing_state(self):
        self.forbid_writes()
        self.st.state[':SOUR:CURR?'] = '.075'
        with self.open_session() as session:
            for mode, expected in [('CURR', 'CC'), ('CURRENT', 'CC'),
                                   ('VOLT', 'CV'), ('VOLTAGE', 'CV'),
                                   ('POW', 'CP'), ('POWER', 'CP'),
                                   ('RES', 'CR'), ('RESISTANCE', 'CR'), ('LED', 'LED')]:
                for input_state in ('0', '1'):
                    with self.subTest(mode=mode, input_state=input_state):
                        self.st.state.update({':SOUR:FUNC?': mode, ':SOUR:INP?': input_state})
                        before = dict(self.st.state)
                        result = session.status()['siglent']
                        self.assertEqual(result['static_mode'], expected)
                        key = ('cc_current_setpoint' if expected == 'CC'
                               else 'stored_cc_current_setpoint')
                        other = ('stored_cc_current_setpoint' if expected == 'CC'
                                 else 'cc_current_setpoint')
                        self.assertEqual(result[key], .075)
                        self.assertNotIn(other, result)
                        self.assertEqual(self.st.state, before)
        self.assert_queries_only()

    def test_either_identity_mismatch_blocks_status_queries(self):
        self.forbid_writes()
        for transport in (self.rt, self.st):
            self.rt.closed = self.st.closed = False
            self.rt.commands.clear()
            self.st.commands.clear()
            with patch.object(transport, 'identity', 'OTHER,WRONG,serial,firmware'):
                with self.assertRaises(IdentityError):
                    with self.open_session() as session:
                        session.status()
            self.assertFalse(any(cmd.startswith((':MEAS', ':SOUR1', ':SOUR2', ':SOUR3'))
                                 for cmd in self.rt.commands + self.st.commands))
            self.assertEqual(transport.commands, ['*IDN?'])
        self.assert_queries_only()

    def test_logger_failure_preserves_instrument_error(self):
        self.forbid_writes()
        with self.assertRaisesRegex(TransportError, 'primary') as caught:
            with self.open_session() as session:
                original = self.log.record

                def record(event, **fields):
                    if event == 'failure':
                        raise RuntimeError('logger broken')
                    original(event, **fields)

                self.log.record = record
                self.st.query = Mock(side_effect=TransportError('primary'))
                session.status()
        self.assertIn('logger broken', str(caught.exception.__notes__))
        self.assert_queries_only()

    def test_status_requires_both_identities_before_readbacks(self):
        self.forbid_writes()
        with self.assertRaises(SafetyError):
            self.session.status()
        self.r.identify()
        self.rt.commands.clear()
        with self.assertRaises(SafetyError):
            self.session.status()
        self.assertEqual(self.rt.commands + self.st.commands, [])
        self.assert_queries_only()

    def test_cli_parse_failure_has_no_partial_result_or_shutdown(self):
        self.forbid_writes()
        self.rt.state[':OUTP? CH1'] = 'ON'
        self.st.state.update({':SOUR:INP?': '1', ':MEAS:POW?': 'nan'})
        out, err = io.StringIO(), io.StringIO()
        with patch('lab_power_control.connections.MockTransport',
                   side_effect=[self.rt, self.st]), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(['status', '--dry-run']), 1)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('nonfinite', err.getvalue())
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'ON')
        self.assertEqual(self.st.state[':SOUR:INP?'], '1')
        self.assertNotIn('shutdown_attempt', err.getvalue())
        self.assert_queries_only()

    def test_cli_dry_run_zero_hardware_io(self):
        out, err = io.StringIO(), io.StringIO()
        with patch('lab_power_control.connections.USBVisaTransport') as usb, \
                patch('lab_power_control.connections.EthernetTransport') as tcp, \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(['status', '--dry-run']), 0)
        usb.assert_not_called()
        tcp.assert_not_called()
        result = json.loads(out.getvalue())
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['status']['rigol']['CH3']['measured']['power'], 0)
        self.assertNotIn('requested_command', err.getvalue())
        self.assertNotIn('shutdown_attempt', err.getvalue())

    def test_cli_hardware_profile_with_injected_factories_only(self):
        self.forbid_writes()
        from dataclasses import asdict
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json') as profile:
            json.dump(asdict(test_connections.ConnectionTests.profile(self)), profile)
            profile.flush()
            for flag in ('--hardware', '--dry-run'):
                out = io.StringIO()
                with patch('lab_power_control.connections.USBVisaTransport',
                           return_value=self.rt) as usb, \
                        patch('lab_power_control.connections.EthernetTransport',
                              return_value=self.st) as tcp, \
                        redirect_stdout(out), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(['status', flag, '--connections', profile.name]), 0)
                self.assertEqual(json.loads(out.getvalue())['dry_run'], flag == '--dry-run')
                if flag == '--dry-run':
                    usb.assert_not_called()
                    tcp.assert_not_called()
                else:
                    usb.assert_called_once()
                    tcp.assert_called_once()
        self.assert_queries_only()

    def test_tcp_query_does_not_call_transport_write(self):
        sock = Mock()
        sock.recv.return_value = b'1.25\n'
        transport = EthernetTransport('mock.invalid', 1234, connector=Mock(return_value=sock))
        with patch.object(transport, 'write', side_effect=AssertionError('write forbidden')):
            self.assertEqual(transport.query(':MEAS:VOLT?'), '1.25')
        sock.sendall.assert_called_once_with(b':MEAS:VOLT?\n')
