import json
from dataclasses import replace

from lab_power_control import SafetyError, SafetyPolicy, ShutdownError
from tests.support import OfflineTest


class SafetyTests(OfflineTest):
    def test_boundaries(self):
        for v in (0, 3.3):
            for i in (0, .2):
                self.policy.source(1, v, i)
        for i in (0, .1):
            self.policy.load(i)
        p = replace(self.policy, voltage_min=1)
        p.source(1, 1, .1)
        with self.assertRaises(SafetyError):
            p.source(1, .999, .1)

    def test_invalid_numbers(self):
        for value in (-1, float('nan'), float('inf'), -float('inf'), True, '1'):
            for action in (lambda: self.policy.source(1, value, .1),
                           lambda: self.policy.source(1, 3, value),
                           lambda: self.policy.load(value)):
                with self.subTest(value=value), self.assertRaises(SafetyError):
                    action()

    def test_outside_limits(self):
        for args in ((1, 3.301, .1), (1, 3, .201), (2, 3, .1),
                     (0, 3, .1), (True, 3, .1), (1.0, 3, .1)):
            with self.assertRaises(SafetyError):
                self.policy.source(*args)
        with self.assertRaises(SafetyError):
            self.policy.load(.101)
        p = replace(self.policy, power_max=.1)
        with self.assertRaises(SafetyError):
            p.source(1, 3, .1)
        with self.assertRaises(SafetyError):
            p.load(.1)

    def test_invalid_policy(self):
        for kwargs in ({'channels': []}, {'channels': [1, 1]}, {'channels': [4]},
                       {'voltage_max': float('nan')}, {'power_max': -1},
                       {'voltage_min': 4}, {'rigol_model': 'DP832A'},
                       {'channels': [3], 'voltage_max': 6}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SafetyError):
                SafetyPolicy(**kwargs)

    def test_shutdown_order_and_partial_failure(self):
        self.session.startup()
        order = []
        rw, sw = self.rt.write, self.st.write

        def fail_load(command):
            order.append(command)
            raise OSError('load offline')

        def fail_channel(command):
            order.append(command)
            if 'CH1' in command:
                raise OSError('channel failure')
            rw(command)

        self.st.write, self.rt.write = fail_load, fail_channel
        with self.assertRaises(ShutdownError) as caught:
            self.session.all_off()
        self.assertEqual(len(caught.exception.failures), 2)
        self.assertEqual(order, [':SOUR:INP OFF', ':OUTP CH1,OFF',
                                 ':OUTP CH2,OFF', ':OUTP CH3,OFF'])
        self.st.write = sw

    def test_shutdown_despite_broken_logger(self):
        self.session.startup()

        def fail(*args, **kwargs):
            raise OSError('disk full')
        self.log.record = fail
        with self.assertRaises(ShutdownError):
            self.session.all_off()
        self.assertIn(':SOUR:INP OFF', self.st.commands)
        for channel in (1, 2, 3):
            self.assertIn(f':OUTP CH{channel},OFF', self.rt.commands)

    def test_context_exception_preserved(self):
        with self.assertRaisesRegex(RuntimeError, 'original'):
            with self.session:
                self.r.configure(1, 3.3, .2)
                raise RuntimeError('original')
        self.assertIn(':OUTP CH3,OFF', self.rt.commands)

    def test_jsonl(self):
        self.session.startup()
        self.r.identify()
        self.r.measure(1)
        self.session.all_off()
        rows = [json.loads(line)
                for line in self.stream.getvalue().splitlines()]
        self.assertTrue(all('timestamp' in row for row in rows))
        self.assertIn('verified_measurement', [row['event'] for row in rows])
        self.assertIn('shutdown_attempt', [row['event'] for row in rows])

    def test_shutdown_failure_audited(self):
        self.session.startup()
        self.st.write = lambda command: (_ for _ in ()).throw(OSError('offline'))
        with self.assertRaises(ShutdownError):
            self.session.all_off()
        self.assertIn('shutdown_failure', self.stream.getvalue())

    def test_sample_config(self):
        p = SafetyPolicy.load_file('lab_power_control/config/stm32_safe.json')
        self.assertEqual(p, self.policy)
