from lab_power_control import SafetyError, InstrumentError
from tests.support import OfflineTest


class RigolTests(OfflineTest):
    def test_initial_off_no_io(self):
        self.assertEqual(self.rt.commands, [])
        self.assertTrue(all(self.rt.state[f':OUTP? CH{ch}'] == 'OFF'
                            for ch in (1, 2, 3)))
        self.assertFalse(self.r.verified)

    def test_configure_format_and_readback(self):
        self.r.identify()
        self.assertEqual(self.r.configure(1, 3.3, .2), (3.3, .2))
        self.assertIn(':INST:NSEL 1', self.rt.commands)
        self.assertIn(':SOUR1:VOLT 3.300000000', self.rt.commands)
        self.assertIn(':SOUR1:CURR 0.200000000', self.rt.commands)
        self.assertFalse(any(',ON' in cmd for cmd in self.rt.commands))
        self.assertEqual(self.r.measure(1), {'voltage': 0, 'current': 0})

    def test_enable_interlocks_and_explicit_enable(self):
        with self.assertRaises(SafetyError):
            self.r.output_on(1)
        self.r.identify()
        with self.assertRaises(SafetyError):
            self.r.output_on(1)
        self.r.configure(1, 3.3, .2)
        self.r.output_on(1)
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'ON')
        self.r.output_off(1)
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'OFF')

    def test_identity_exact_and_revoked(self):
        for identity in ('RIGOL TECHNOLOGIES,DP832A,x,1',
                         'Other,DP832,x,1', 'RIGOL TECHNOLOGIES,DP832'):
            self.rt.identity = identity
            with self.assertRaises(SafetyError):
                self.r.identify()
            self.assertFalse(self.r.verified)

    def test_changed_readback_blocks_enable_and_shuts_both_off(self):
        self.s.identify()
        self.r.identify()
        self.r.configure(1, 3.3, .2)
        self.rt.state[':SOUR1:VOLT?'] = '3.4'
        with self.assertRaises(SafetyError):
            self.r.output_on(1)
        self.assertNotIn(':OUTP CH1,ON', self.rt.commands)
        self.assertIn(':SOUR:INP OFF', self.st.commands)

    def test_invalid_response(self):
        self.r.identify()
        for value in ('nan', 'inf', '-1', 'garbage'):
            self.rt.state[':MEAS:VOLT? CH1'] = value
            with self.assertRaises(InstrumentError):
                self.r.measure(1)

    def test_setpoint_mismatch(self):
        self.r.identify()
        query = self.rt.query
        self.rt.query = lambda cmd: '3.2' if cmd == ':SOUR1:VOLT?' else query(
            cmd)
        with self.assertRaises(SafetyError):
            self.r.configure(1, 3.3, .2)
        self.assertIsNone(self.r.ready)

    def test_individual_setters_leave_off(self):
        self.r.identify()
        self.r.configure(1, 3, .1)
        self.r.set_voltage(1, 3.3)
        self.r.set_current_limit(1, .2)
        self.assertEqual(self.r.configured(1), (3.3, .2))
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'OFF')

    def test_failure_during_active_operation_shuts_pair_off(self):
        self.s.identify()
        from lab_power_control.io_transport import TransportTimeout
        self.r.identify()
        self.r.configure(1, 3.3, .2)
        self.r.output_on(1)
        query = self.rt.query

        def fail_measure(command):
            if command.startswith(':MEAS:'):
                raise TransportTimeout('mock timeout')
            return query(command)

        self.rt.query = fail_measure
        with self.assertRaises(TransportTimeout):
            self.r.measure(1)
        self.assertEqual(self.rt.state[':OUTP? CH1'], 'OFF')
        self.assertIn(':SOUR:INP OFF', self.st.commands)
