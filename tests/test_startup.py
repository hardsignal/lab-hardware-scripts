"""Startup observes identified hardware; all transports here are injected mocks."""
from unittest.mock import Mock

from lab_power_control.connections import connected_session
from lab_power_control.errors import IdentityError, InstrumentError, SafetyError, ShutdownError
from tests import test_connections
from tests.support import OfflineTest


class StartupTests(OfflineTest):
    def open_session(self):
        profile = test_connections.ConnectionTests.profile(self)
        return connected_session(self.policy, self.log, profile, dry_run=False,
                                 usb_factory=Mock(return_value=self.rt),
                                 tcp_factory=Mock(return_value=self.st))

    def test_startup_order_and_already_on_untouched_at_exit(self):
        self.rt.state[':OUTP? CH2'] = 'ON'
        self.st.state[':SOUR:INP?'] = '1'
        with self.open_session() as session:
            self.assertEqual(session.startup_state['rigol']['state'],
                             {'CH1': 'OFF', 'CH2': 'ON', 'CH3': 'OFF'})
            self.assertEqual(session.startup_state['siglent']['state'], {'input': 'ON'})
            self.assertIn('startup_state', self.stream.getvalue())
        self.assertEqual(self.rt.commands,
                         ['*IDN?', ':OUTP? CH1', ':OUTP? CH2', ':OUTP? CH3'])
        self.assertEqual(self.st.commands, ['*IDN?', ':SOUR:INP?'])
        self.assertEqual(self.rt.state[':OUTP? CH2'], 'ON')
        self.assertEqual(self.st.state[':SOUR:INP?'], '1')
        self.assertTrue(self.rt.closed and self.st.closed)

    def test_mismatch_has_no_state_query_or_write(self):
        self.rt.identity = 'OTHER,DP832,serial,firmware'
        with self.assertRaises(IdentityError):
            with self.open_session():
                self.fail('unexpected successful startup')
        self.assertEqual(self.rt.commands, ['*IDN?'])
        self.assertEqual(self.st.commands, [])

    def test_second_identity_failure_does_not_turn_first_off(self):
        self.rt.state[':OUTP? CH1'] = 'ON'
        self.st.identity = 'OTHER,SDL1030X-E,serial,firmware'
        with self.assertRaises(IdentityError):
            with self.open_session():
                pass
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'ON')
        self.assertEqual(self.st.commands, ['*IDN?'])
        self.assertFalse(any('OFF' in command for command in self.rt.commands))

    def test_unknown_state_fails_without_assuming_off(self):
        self.rt.state[':OUTP? CH1'] = 'UNKNOWN'
        with self.assertRaises(InstrumentError):
            with self.open_session():
                pass
        self.assertEqual(self.rt.commands, ['*IDN?', ':OUTP? CH1'])

    def test_no_control_or_state_query_before_identity(self):
        operations = [lambda: self.r.configure(1, 3.3, .2),
                      lambda: self.s.configure_cc(.05), lambda: self.r.output_on(1),
                      self.s.input_on, lambda: self.r.output_off(1), self.s.input_off,
                      self.r.physical_state, self.s.physical_state]
        for operation in operations:
            with self.assertRaises(SafetyError):
                operation()
        self.assertEqual(self.rt.commands, [])
        self.assertEqual(self.st.commands, [])

    def test_all_off_only_positively_identified_instruments(self):
        self.r.identify()
        with self.assertRaises(ShutdownError) as caught:
            self.session.all_off()
        self.assertIn('not identified', str(caught.exception))
        self.assertEqual(self.st.commands, [])
        for channel in (1, 2, 3):
            self.assertIn(f':OUTP CH{channel},OFF', self.rt.commands)

    def test_observation_exception_does_not_alter_on_state(self):
        self.rt.state[':OUTP? CH1'] = 'ON'
        with self.assertRaisesRegex(RuntimeError, 'application'):
            with self.open_session():
                raise RuntimeError('application')
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'ON')

    def test_control_session_exit_shuts_down_identified_pair(self):
        with self.open_session() as session:
            session.rigol.configure(1, 3.3, .2)
        self.assertIn(':SOUR:INP OFF', self.st.commands)
        self.assertIn(':OUTP CH3,OFF', self.rt.commands)
