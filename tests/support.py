import io
import unittest
from unittest.mock import patch

from lab_power_control import RigolDP832, SiglentSDL1030XE, SafetyPolicy, Experiment
from lab_power_control.io_transport import MockTransport
from lab_power_control.logger import JsonlLogger


class OfflineTest(unittest.TestCase):
    def setUp(self):
        # Fail closed if any tested code attempts real network/USB access.
        for target in ('socket.create_connection', 'socket.socket',
                       'lab_power_control.io_transport.USBVisaTransport.__init__'):
            patcher = patch(
                target, side_effect=AssertionError('hardware forbidden'))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.stream = io.StringIO()
        self.log = JsonlLogger(self.stream)
        self.policy = SafetyPolicy()
        self.rt = MockTransport('rigol')
        self.st = MockTransport('siglent')
        self.r = RigolDP832(self.rt, self.policy, self.log)
        self.s = SiglentSDL1030XE(self.st, self.policy, self.log)
        self.session = Experiment(self.r, self.s)
