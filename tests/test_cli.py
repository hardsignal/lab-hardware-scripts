from contextlib import redirect_stdout, redirect_stderr
import io
import json

from lab_power_control.__main__ import main
from tests.support import OfflineTest


class CliTests(OfflineTest):
    def test_examples(self):
        cases = [(['idn'], 'rigol'),
                 (['rigol', '--channel', '1', '--voltage', '3.30',
                   '--current-limit', '0.20'], 'output'),
                 (['siglent', '--mode', 'cc', '--current', '.05'], 'input'),
                 (['all-off'], 'all_off')]
        for args, key in cases:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(args + ['--dry-run']), 0)
            result = json.loads(out.getvalue())
            self.assertTrue(result['dry_run'])
            self.assertIn(key, result)
            self.assertIn('startup_state', result)
            if args[0] == 'idn':
                self.assertNotIn('shutdown_attempt', err.getvalue())
            else:
                self.assertIn('shutdown_attempt', err.getvalue())

    def test_live_cli_rejected(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['idn'])

    def test_invalid_value(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(['rigol', '--channel', '1', '--voltage', 'nan',
                                   '--current-limit', '.1', '--dry-run']), 1)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('failure', err.getvalue())
        self.assertNotIn('shutdown_attempt', err.getvalue())
