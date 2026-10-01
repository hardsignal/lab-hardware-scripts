from unittest.mock import Mock, patch
from contextlib import redirect_stderr
import io

from lab_power_control import errors
from lab_power_control import InstrumentError, ShutdownError, SafetyError
from lab_power_control.__main__ import main
from tests.support import OfflineTest


class ErrorTests(OfflineTest):
    def test_shared_hierarchy(self):
        self.assertIs(InstrumentError, errors.InstrumentError)
        self.assertIs(ShutdownError, errors.ShutdownError)
        self.assertIs(SafetyError, errors.SafetyError)
        self.assertTrue(issubclass(errors.TransportTimeout, InstrumentError))
        self.assertTrue(issubclass(errors.IdentityError, SafetyError))

    def test_primary_transport_error_survives_failure_logging(self):
        self.session.startup()
        self.r.configure(1, 3.3, .2)
        primary = errors.TransportTimeout('primary measurement failure')
        query, record = self.rt.query, self.log.record

        def fail_query(command):
            if command.startswith(':MEAS:'):
                raise primary
            return query(command)

        def fail_log(event, **fields):
            if event == 'failure':
                raise OSError('failure log unavailable')
            return record(event, **fields)

        self.rt.query, self.log.record = fail_query, fail_log
        with self.assertRaises(errors.TransportTimeout) as caught:
            self.r.measure(1)
        self.assertIs(caught.exception, primary)
        self.assertIn('failure log unavailable', ' '.join(primary.__notes__))
        self.assertIn(':OUTP CH3,OFF', self.rt.commands)
        self.assertIn(':SOUR:INP OFF', self.st.commands)

    def test_primary_survives_logging_and_shutdown_failures(self):
        self.session.startup()
        self.r.configure(1, 3.3, .2)
        primary = errors.TransportError('primary')
        query = self.rt.query

        def fail_query(command):
            if command.startswith(':MEAS:'):
                raise primary
            return query(command)

        record = self.log.record

        def fail_log(event, **fields):
            if event in ('failure', 'shutdown_attempt', 'shutdown_failure'):
                raise OSError('log failed')
            record(event, **fields)

        self.rt.query = fail_query
        self.log.record = fail_log
        self.st.write = Mock(side_effect=OSError('SDL disconnected'))
        with self.assertRaises(errors.TransportError) as caught:
            self.r.measure(1)
        self.assertIs(caught.exception, primary)
        self.assertIn('SDL disconnected', ' '.join(primary.__notes__))
        self.assertIn(':OUTP CH3,OFF', self.rt.commands)

    def test_cli_reports_primary_when_error_logging_fails(self):
        primary = errors.TransportError('primary CLI failure')
        with patch('lab_power_control.__main__.connected_session', side_effect=primary), patch(
                'lab_power_control.__main__.JsonlLogger') as logger:
            logger.return_value.record.side_effect = OSError('CLI logger failed')
            output = io.StringIO()
            with redirect_stderr(output):
                self.assertEqual(main(['idn', '--dry-run']), 1)
        self.assertIn('primary CLI failure', output.getvalue())
        self.assertIn('CLI logger failed', output.getvalue())
