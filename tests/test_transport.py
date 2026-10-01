import unittest
from unittest.mock import Mock, patch

from lab_power_control.io_transport import (
    EthernetTransport, USBVisaTransport, TransportError, TransportTimeout)


class TransportTests(unittest.TestCase):
    def ethernet(self, responses):
        sock = Mock()
        sock.recv.side_effect = responses
        connector = Mock(return_value=sock)
        transport = EthernetTransport(
            'mock.invalid', 5025, .1, connector=connector)
        connector.assert_called_once_with(('mock.invalid', 5025), timeout=.1)
        return transport, sock

    def test_framing(self):
        transport, sock = self.ethernet([b'1.2', b'3\r\n'])
        self.assertEqual(transport.query('*IDN?'), '1.23')
        sock.sendall.assert_called_once_with(b'*IDN?\n')

    def test_timeout_and_no_stale_retry(self):
        transport, sock = self.ethernet([TimeoutError('timeout')])
        with self.assertRaises(TransportTimeout):
            transport.query('*IDN?')
        with self.assertRaises(TransportError):
            transport.query('*IDN?')
        self.assertEqual(sock.sendall.call_count, 1)

    def test_failures(self):
        for result in (b'', OSError('offline'), b'\xff\n', b'x' * 65537):
            transport, _ = self.ethernet([result])
            with self.assertRaises(TransportError):
                transport.query('*IDN?')

    def test_connect_failure(self):
        for error, expected in ((TimeoutError(), TransportTimeout),
                                (OSError(), TransportError)):
            with self.assertRaises(expected):
                EthernetTransport('mock.invalid', 5025,
                                  connector=Mock(side_effect=error))

    def test_invalid_timeout(self):
        for timeout in (0, -1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                EthernetTransport('mock.invalid', 5025,
                                  timeout, connector=Mock())

    def test_usb_injected(self):
        manager = Mock()
        instrument = manager.open_resource.return_value
        transport = USBVisaTransport('USB0::MOCK::INSTR', .2,
                                     manager_factory=lambda: manager)
        self.assertEqual(instrument.timeout, 200)
        instrument.query.side_effect = TimeoutError('timeout')
        with self.assertRaises(TransportTimeout):
            transport.query('*IDN?')
        transport.close()
        instrument.close.assert_called_once()
        manager.close.assert_called_once()

    def test_usb_query_does_not_call_transport_write(self):
        manager = Mock()
        manager.open_resource.return_value.query.return_value = '1.25\n'
        transport = USBVisaTransport('USB0::MOCK::INSTR', manager_factory=lambda: manager)
        with patch.object(transport, 'write', side_effect=AssertionError('write forbidden')):
            self.assertEqual(transport.query(':MEAS:VOLT?'), '1.25')
        manager.open_resource.return_value.write.assert_not_called()
