from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from lab_power_control.__main__ import main
from lab_power_control.connections import Connections, Endpoint, connected_session
from lab_power_control.io_transport import MockTransport
from tests.support import OfflineTest


class ConnectionTests(OfflineTest):
    def profile(self, backend='usb'):
        rigol = (Endpoint('usb', .4, resource='USB0::MOCK::INSTR') if backend == 'usb'
                 else Endpoint('tcp', .4, host='source.invalid', port=12345))
        return Connections(rigol, Endpoint('tcp', .7, host='load.invalid', port=23456))

    def exercise(self, profile):
        rigol, siglent = MockTransport('rigol'), MockTransport('siglent')
        usb = Mock(return_value=rigol)
        tcp = Mock(side_effect=[siglent] if profile.rigol.backend == 'usb'
                   else [rigol, siglent])
        with connected_session(self.policy, self.log, profile, dry_run=False,
                               usb_factory=usb, tcp_factory=tcp) as session:
            session.rigol.identify()
            session.rigol.configure(1, 3.3, .2)
        self.assertTrue(rigol.closed and siglent.closed)
        return rigol.commands, usb, tcp

    def test_usb_commissioning_and_tcp_migration_same_driver_commands(self):
        usb_commands, usb, tcp = self.exercise(self.profile())
        usb.assert_called_once_with('USB0::MOCK::INSTR', timeout=.4)
        tcp.assert_called_once_with('load.invalid', 23456, timeout=.7)
        tcp_commands, usb, tcp = self.exercise(self.profile('tcp'))
        usb.assert_not_called()
        self.assertEqual(tcp.call_args_list[0].args, ('source.invalid', 12345))
        self.assertEqual(tcp.call_args_list[0].kwargs, {'timeout': .4})
        self.assertEqual(usb_commands, tcp_commands)

    def test_dry_run_never_opens_configured_endpoints(self):
        forbidden = Mock(side_effect=AssertionError('hardware forbidden'))
        for profile in (None, self.profile(), self.profile('tcp')):
            with connected_session(self.policy, self.log, profile,
                                   usb_factory=forbidden, tcp_factory=forbidden) as session:
                session.rigol.identify()
        forbidden.assert_not_called()

    def test_hardware_requires_profile(self):
        with self.assertRaises(ValueError):
            with connected_session(self.policy, self.log, dry_run=False):
                self.fail('must reject before opening')

    def test_invalid_endpoints(self):
        for args in ({'backend': 'tcp', 'timeout': 1},
                     {'backend': 'tcp', 'timeout': 1, 'host': 'x', 'port': 0},
                     {'backend': 'tcp', 'timeout': 1, 'host': 'x', 'port': True},
                     {'backend': 'tcp', 'timeout': 1, 'host': 'x\ny', 'port': 12345},
                     {'backend': 'usb', 'timeout': 1},
                     {'backend': 'serial', 'timeout': 1},
                     {'backend': 'usb', 'timeout': 0, 'resource': 'USB0::MOCK::INSTR'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Endpoint(**args)
        with self.assertRaises(ValueError):
            Connections(self.profile().rigol, self.profile().rigol)

    def test_open_failure_cleans_first_transport_without_fallback(self):
        rigol = MockTransport('rigol')
        usb = Mock(return_value=rigol)
        tcp = Mock(side_effect=OSError('cannot connect'))
        with self.assertRaisesRegex(OSError, 'cannot connect'):
            with connected_session(self.policy, self.log, self.profile(), dry_run=False,
                                   usb_factory=usb, tcp_factory=tcp):
                self.fail('must not enter')
        self.assertTrue(rigol.closed)
        self.assertEqual(rigol.commands, [])
        self.assertEqual(usb.call_count, 1)
        self.assertEqual(tcp.call_count, 1)

    def test_close_failure_does_not_skip_other_close(self):
        rigol, siglent = MockTransport('rigol'), MockTransport('siglent')
        siglent.close = Mock(side_effect=OSError('close failed'))
        from lab_power_control import ShutdownError
        with self.assertRaises(ShutdownError):
            with connected_session(self.policy, self.log, self.profile(), dry_run=False,
                                   usb_factory=Mock(return_value=rigol),
                                   tcp_factory=Mock(return_value=siglent)):
                pass
        self.assertTrue(rigol.closed)

    def test_cli_config_only_migration_with_injected_hardware(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'connections.json'
            for backend in ('usb', 'tcp'):
                profile = self.profile(backend)
                path.write_text(json.dumps({'rigol': vars(profile.rigol),
                                            'siglent': vars(profile.siglent)}))
                rigol, siglent = MockTransport('rigol'), MockTransport('siglent')
                with patch('lab_power_control.connections.USBVisaTransport',
                           return_value=rigol), patch(
                               'lab_power_control.connections.EthernetTransport',
                               side_effect=[siglent] if backend == 'usb' else [rigol, siglent]):
                    output = io.StringIO()
                    with redirect_stdout(output), redirect_stderr(io.StringIO()):
                        self.assertEqual(main(['idn', '--hardware', '--connections', str(path)]), 0)
                    self.assertFalse(json.loads(output.getvalue())['dry_run'])

    def test_templates_fail_closed_until_filled(self):
        for name in ('usb', 'tcp'):
            with self.assertRaises(ValueError):
                Connections.load_file(f'lab_power_control/config/connections_{name}.template.json')
