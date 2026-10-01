"""Explicit, injected transports; importing this module never opens hardware."""
import math
import re
import socket
import time

from typing import Protocol

from .errors import TransportError, TransportTimeout, note_failure


class Transport(Protocol):
    def write(self, command: str) -> None:
        ...

    def query(self, command: str) -> str:
        ...

    def close(self) -> None:
        ...


def timeout_value(timeout):
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    return timeout


class EthernetTransport:
    """Newline-framed raw SCPI; port must be supplied, never discovered."""

    def __init__(self, host, port, timeout=3.0, connector=None):
        timeout_value(timeout)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('invalid port')
        self.timeout = timeout
        self.buffer = b''
        self.broken = False
        try:
            self.socket = (connector or socket.create_connection)(
                (host, port), timeout=timeout)
            self.socket.settimeout(timeout)
        except TimeoutError as exc:
            raise TransportTimeout(str(exc)) from exc
        except OSError as exc:
            raise TransportError(str(exc)) from exc

    def _send(self, command):
        if self.broken:
            raise TransportError(
                'connection unusable; explicit reconnect required')
        try:
            self.socket.settimeout(self.timeout)
            self.socket.sendall((command + '\n').encode('ascii'))
        except (OSError, UnicodeError) as exc:
            self.broken = True
            error = TransportTimeout if isinstance(
                exc, TimeoutError) else TransportError
            raise error(str(exc)) from exc

    def write(self, command):
        self._send(command)

    def query(self, command):
        self._send(command)
        deadline = time.monotonic() + self.timeout
        try:
            while b'\n' not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('response deadline exceeded')
                self.socket.settimeout(remaining)
                data = self.socket.recv(4096)
                if not data:
                    raise OSError('connection closed before response')
                self.buffer += data
                if len(self.buffer) > 65536:
                    raise OSError('oversized response')
            line, self.buffer = self.buffer.split(b'\n', 1)
            return line.decode('ascii').strip()
        except (OSError, UnicodeError) as exc:
            self.broken = True
            error = TransportTimeout if isinstance(
                exc, TimeoutError) else TransportError
            raise error(str(exc)) from exc

    def close(self):
        self.socket.close()


class USBVisaTransport:
    def __init__(self, resource, timeout=3.0, manager_factory=None):
        timeout_value(timeout)
        if not re.fullmatch(r'USB\d*::[^\r\n]+::INSTR', resource):
            raise ValueError('explicit USB VISA INSTR resource required')
        self.manager = self.instrument = None
        try:
            if manager_factory is None:
                import pyvisa

                def manager_factory():
                    return pyvisa.ResourceManager('@py')
            self.manager = manager_factory()
            self.instrument = self.manager.open_resource(
                resource, open_timeout=int(timeout * 1000))
            self.instrument.timeout = max(1, int(timeout * 1000))
            self.instrument.read_termination = '\n'
            self.instrument.write_termination = '\n'
        except Exception as exc:
            note_failure(exc, 'USB cleanup failure', self.close)
            error = TransportError(str(exc))
            for note in getattr(exc, '__notes__', ()):
                error.add_note(note)
            raise error from exc

    def _call(self, method, *args):
        try:
            return getattr(self.instrument, method)(*args)
        except Exception as exc:
            timed_out = isinstance(exc, TimeoutError)
            visa_timeout = getattr(exc, 'error_code', None) == -1073807339
            error = TransportTimeout if timed_out or visa_timeout else TransportError
            raise error(str(exc)) from exc

    def write(self, command):
        self._call('write', command)

    def query(self, command):
        return self._call('query', command).strip()

    def close(self):
        primary = None
        for handle in (self.instrument, self.manager):
            if handle is not None:
                try:
                    handle.close()
                except BaseException as exc:
                    if primary is None:
                        primary = exc
                    else:
                        primary.add_note(f'Additional USB close failure: {exc!r}')
        if primary is not None:
            raise primary


class MockTransport:
    """Zero measurements: no circuit, source/load coupling, or physical simulation."""

    def __init__(self, kind, identity=None):
        self.kind = kind
        self.identity = identity or {
            "rigol": "RIGOL TECHNOLOGIES,DP832,MOCK-RIGOL,0.1",
            "siglent": "Siglent Technologies,SDL1030X-E,MOCK-SIGLENT,0.1",
        }[kind]
        self.commands = []
        self.state = {}
        self.closed = False
        if kind == 'rigol':
            for channel in (1, 2, 3):
                self.state[f':OUTP? CH{channel}'] = 'OFF'
                for parameter in ('VOLT', 'CURR'):
                    self.state[f':SOUR{channel}:{parameter}?'] = '0'
        else:
            self.state.update({':SOUR:INP?': '0', ':SOUR:SHOR?': '0',
                               ':SOUR:EXT:INPUT?': '0', ':SOUR:FUNC?': 'CURR',
                               ':SOUR:CURR?': '0'})

    def _record(self, command):
        if self.closed:
            raise RuntimeError("transport closed")
        self.commands.append(command)

    def write(self, command):
        self._record(command)
        if self.kind == 'rigol' and re.fullmatch(r':INST:NSEL [123]', command):
            return
        if self.kind == "rigol":
            match = re.fullmatch(r":OUTP CH([123]),(ON|OFF)", command)
            if match:
                self.state[f":OUTP? CH{match[1]}"] = match[2]
                return
            match = re.fullmatch(r"(:SOUR[123]:(?:VOLT|CURR)) ([0-9.eE+-]+)", command)
        else:
            match = re.fullmatch(
                r"(:SOUR:(?:INP|SHOR|EXT:INPUT)) (ON|OFF)", command)
            if match:
                self.state[match[1] + "?"] = "1" if match[2] == "ON" else "0"
                return
            match = re.fullmatch(r"(:SOUR:(?:FUNC|CURR)) (CURR|[0-9.eE+-]+)", command)
        if match:
            self.state[match[1] + "?"] = match[2]
            return
        raise ValueError(f"unsupported mock command: {command}")

    def query(self, command):
        self._record(command)
        if command == "*IDN?":
            return self.identity
        if command in self.state:
            return self.state[command]
        if self.kind == "rigol" and re.fullmatch(r":MEAS:(VOLT|CURR|POWE)\? CH[123]", command):
            return "0.0"
        if self.kind == "siglent" and command in (
            ":MEAS:VOLT?", ":MEAS:CURR?", ":MEAS:POW?"
        ):
            return "0.0"
        raise ValueError(f"unsupported mock query: {command}")

    def close(self):
        self.closed = True
