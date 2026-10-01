from lab_power_control import SafetyError
from tests.support import OfflineTest


class SiglentTests(OfflineTest):
    def test_default_no_io(self):
        self.assertEqual(self.st.commands, [])
        self.assertEqual(self.st.state[':SOUR:INP?'], '0')

    def test_configure_format(self):
        self.s.identify()
        self.assertEqual(self.s.configure_cc(.05), .05)
        for command in (':SOUR:INP OFF', ':SOUR:SHOR OFF',
                        ':SOUR:EXT:INPUT OFF', ':SOUR:FUNC CURR',
                        ':SOUR:CURR 0.050000000'):
            self.assertIn(command, self.st.commands)
        self.assertNotIn(':SOUR:INP ON', self.st.commands)
        self.assertEqual(self.s.measure(), {
                         'voltage': 0, 'current': 0, 'power': 0})

    def test_enable_interlocks(self):
        with self.assertRaises(SafetyError):
            self.s.input_on()
        self.s.identify()
        with self.assertRaises(SafetyError):
            self.s.input_on()
        self.s.configure_cc(.05)
        self.s.input_on()
        self.assertEqual(self.st.state[':SOUR:INP?'], '1')
        self.s.input_off()
        self.assertEqual(self.st.state[':SOUR:INP?'], '0')

    def test_unknown_identity(self):
        self.st.identity = 'Siglent Technologies,SDL1030X,x,1'
        with self.assertRaises(SafetyError):
            self.s.identify()

    def test_unsafe_mode_or_voltage_blocks_enable(self):
        for key, value in ((':SOUR:FUNC?', 'VOLT'), (':SOUR:SHOR?', '1'),
                           (':SOUR:EXT:INPUT?', '1'), (':MEAS:VOLT?', '4')):
            self.s.identify()
            self.s.configure_cc(.05)
            self.st.state[key] = value
            with self.assertRaises(SafetyError):
                self.s.input_on()
            self.st.state.pop(':MEAS:VOLT?', None)
        self.assertNotIn(':SOUR:INP ON', self.st.commands)
