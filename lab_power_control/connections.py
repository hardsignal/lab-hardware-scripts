"""Connection policy and session ownership, independent of SCPI and safety policy."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .experiment import Experiment
from .errors import ShutdownError
from .io_transport import EthernetTransport, MockTransport, USBVisaTransport, timeout_value
from .rigol_dp832 import RigolDP832
from .siglent_sdl1030xe import SiglentSDL1030XE


@dataclass(frozen=True)
class Endpoint:
    backend: str
    timeout: float
    resource: str | None = None
    host: str | None = None
    port: int | None = None

    def __post_init__(self):
        timeout_value(self.timeout)
        if self.backend == 'usb':
            if not isinstance(self.resource, str) or not re.fullmatch(
                    r'USB\d*::[^\r\n]+::INSTR', self.resource):
                raise ValueError('USB requires an explicit VISA USB INSTR resource')
            if self.host is not None or self.port is not None:
                raise ValueError('USB endpoint cannot contain TCP fields')
        elif self.backend == 'tcp':
            if not isinstance(self.host, str) or not self.host or any(
                    c.isspace() or c in ';/' for c in self.host):
                raise ValueError('TCP requires an explicit host without whitespace')
            if type(self.port) is not int or not 1 <= self.port <= 65535:
                raise ValueError('TCP requires an explicit port in 1..65535')
            if self.resource is not None:
                raise ValueError('TCP endpoint cannot contain a USB resource')
        else:
            raise ValueError('backend must be usb or tcp')


@dataclass(frozen=True)
class Connections:
    rigol: Endpoint
    siglent: Endpoint

    def __post_init__(self):
        if not isinstance(self.rigol, Endpoint) or not isinstance(self.siglent, Endpoint):
            raise ValueError('both instrument endpoints are required')
        if self.siglent.backend != 'tcp':
            raise ValueError('SDL1030X-E requires Ethernet TCP')

    @classmethod
    def load_file(cls, path):
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict) or set(data) != {'rigol', 'siglent'}:
            raise ValueError('connections must contain exactly rigol and siglent')
        return cls(**{kind: Endpoint(**values) for kind, values in data.items()})


def open_transport(kind, endpoint, *, dry_run, usb_factory=None, tcp_factory=None):
    if dry_run:
        return MockTransport(kind)
    if endpoint is None:
        raise ValueError('hardware requires explicit connection configuration')
    if endpoint.backend == 'usb':
        return (usb_factory or USBVisaTransport)(endpoint.resource, timeout=endpoint.timeout)
    return (tcp_factory or EthernetTransport)(
        endpoint.host, endpoint.port, timeout=endpoint.timeout)


@contextmanager
def connected_session(policy, logger, connections=None, *, dry_run=True,
                      usb_factory=None, tcp_factory=None):
    """Identify and observe at startup; shut down after control activity, then close.

    No discovery, automatic fallback, or automatic enable. Factories allow offline
    verification of hardware selection without opening network or USB devices.
    """
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be a boolean')
    if not dry_run and not isinstance(connections, Connections):
        raise ValueError('hardware requires explicit connection configuration')
    transports = []
    drivers = []
    original = None
    try:
        for kind, driver in (('rigol', RigolDP832), ('siglent', SiglentSDL1030XE)):
            endpoint = getattr(connections, kind) if connections is not None else None
            transport = open_transport(kind, endpoint, dry_run=dry_run,
                                       usb_factory=usb_factory, tcp_factory=tcp_factory)
            transports.append(transport)
            drivers.append(driver(transport, policy, logger))
        session = Experiment(*drivers)
        session.startup()
        yield session
    except BaseException as exc:
        original = exc
        raise
    finally:
        failures = []
        # Observation-only sessions leave already-ON instruments untouched.
        if any(driver.active for driver in drivers):
            for driver in reversed(drivers):
                if driver.verified:
                    try:
                        failures.extend(driver.local_off())
                    except BaseException as exc:
                        failures.append((driver.kind, repr(exc)))
        for transport in reversed(transports):
            try:
                transport.close()
            except BaseException as exc:
                failures.append(('transport close', repr(exc)))
        if failures:
            if original is not None:
                original.add_note('Cleanup failures: ' + repr(failures))
            else:
                raise ShutdownError(failures)
